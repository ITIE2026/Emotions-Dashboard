"""
InstagramScreen - Instagram Reels browser backed by Edge WebView2.

Uses pywebview (edgechromium backend) instead of QtWebEngine because
QtWebEngine on this machine lacks H.264 codec support, while Instagram
Reels require H.264 playback. The actual browser surface runs in the
separate _wv2_host.py process and is kept aligned with the Qt placeholder.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    BG_CARD,
    BG_INPUT,
    BG_PRIMARY,
    BORDER_SUBTLE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

log = logging.getLogger(__name__)

_IG_HOME = "https://www.instagram.com"
_IG_REELS = "https://www.instagram.com/reels/"

_FOCUS_SCROLL_THRESHOLD = 60
_SCROLL_COOLDOWN_SEC = 6.0

_ACCENT_PINK = "#E1306C"

_WV_STORAGE = os.path.join(
    os.path.expanduser("~"), ".bci_dashboard", "instagram_wv2"
)
os.makedirs(_WV_STORAGE, exist_ok=True)

_HOST_SCRIPT = os.path.join(os.path.dirname(__file__), "_wv2_host.py")


class _Wv2Process:
    """
    Wraps the _wv2_host.py child process.
    All pywebview calls are forwarded as JSON over stdin.
    """

    def __init__(self, initial_url: str) -> None:
        self._ready = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._current_url = initial_url
        self._start(initial_url)

    def _start(self, initial_url: str) -> None:
        def _run() -> None:
            try:
                self._proc = subprocess.Popen(
                    [sys.executable, _HOST_SCRIPT, _WV_STORAGE, initial_url],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                )
                for raw_line in self._proc.stdout:  # type: ignore[union-attr]
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        msg = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    event = msg.get("event")
                    if event == "ready":
                        log.info("Instagram Edge WebView2 host ready")
                        self._ready.set()
                    elif event == "url_changed":
                        self._current_url = msg.get("url", self._current_url)
                    elif event == "error":
                        log.debug("wv2 host error: %s", msg.get("msg"))
            except Exception as exc:
                log.error("wv2 host thread: %s", exc)

        threading.Thread(target=_run, daemon=True, name="wv2-reader").start()

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    def _send(self, msg: dict) -> None:
        if not self._ready.is_set() or not self._proc:
            return
        with self._lock:
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")  # type: ignore[union-attr]
                self._proc.stdin.flush()  # type: ignore[union-attr]
            except Exception as exc:
                log.debug("wv2 send error: %s", exc)

    def navigate(self, url: str) -> None:
        self._send({"cmd": "navigate", "url": url})

    def run_js(self, code: str) -> None:
        self._send({"cmd": "js", "code": code})

    def configure_host(self, owner_hwnd: int) -> None:
        self._send({"cmd": "configure_host", "owner_hwnd": int(owner_hwnd)})

    def sync_window(
        self,
        *,
        x: int,
        y: int,
        w: int,
        h: int,
        visible: bool,
        topmost: bool,
        no_activate: bool,
    ) -> None:
        self._send(
            {
                "cmd": "sync_window",
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "visible": bool(visible),
                "topmost": bool(topmost),
                "no_activate": bool(no_activate),
            }
        )

    def move(self, x: int, y: int) -> None:
        self._send({"cmd": "move", "x": int(x), "y": int(y)})

    def resize(self, w: int, h: int) -> None:
        self._send({"cmd": "resize", "w": int(w), "h": int(h)})

    def show(self) -> None:
        self._send({"cmd": "show"})

    def hide(self) -> None:
        self._send({"cmd": "hide"})

    def set_on_top(self, value: bool) -> None:
        self._send({"cmd": "set_on_top", "value": bool(value)})

    def quit(self) -> None:
        proc = self._proc
        if not proc:
            return
        try:
            if self._ready.is_set() and proc.poll() is None:
                self._send({"cmd": "quit"})
                proc.wait(timeout=2.0)
                return
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2.0)
                return
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


_SKIP_REEL_JS = r"""
(function () {
    var btn = document.querySelector('[aria-label="Next"]');
    if (btn) { btn.click(); return 'btn_next'; }
    var ev = new KeyboardEvent('keydown',
        {key:'ArrowDown', code:'ArrowDown', keyCode:40, which:40,
         bubbles:true, cancelable:true});
    (document.activeElement || document.body).dispatchEvent(ev);
    document.body.dispatchEvent(ev);
    var snaps = document.querySelectorAll('[style*="scroll-snap"], div[class*="reel"]');
    for (var i = 0; i < snaps.length; i++) {
        if (snaps[i].scrollHeight > snaps[i].clientHeight + 20) {
            snaps[i].scrollBy({top: window.innerHeight, behavior: 'smooth'});
            return 'snap_scroll';
        }
    }
    window.scrollBy({top: window.innerHeight, behavior: 'smooth'});
    return 'page_scroll';
})();
"""

_INJECT_OVERLAY_JS = r"""
(function () {
    if (document.getElementById('bci-wv-hud')) return;
    var el = document.createElement('div');
    el.id = 'bci-wv-hud';
    el.style.cssText = [
        'position:fixed','bottom:24px','left:50%',
        'transform:translateX(-50%)',
        'background:rgba(0,0,0,0.72)',
        'color:#fff','padding:5px 18px',
        'border-radius:20px','font-size:12px',
        'font-family:monospace','z-index:2147483647',
        'pointer-events:none','letter-spacing:.5px',
        'border:1px solid rgba(255,255,255,0.15)',
    ].join(';');
    el.textContent = 'BCI  Focus: --';
    document.body && document.body.appendChild(el);
})();
"""

_UPDATE_OVERLAY_JS = """
(function () {{
    var el = document.getElementById('bci-wv-hud');
    if (el) el.textContent = '{text}';
}})();
"""


class _EEGBar(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("IGEEGBar")
        self.setFixedHeight(26)
        self.setStyleSheet(
            f"#IGEEGBar {{ background: rgba(12,12,22,200);"
            f" border-top: 1px solid {BORDER_SUBTLE}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 12, 2)
        layout.setSpacing(20)
        self._focus_lbl = QLabel("Focus: -")
        self._status_lbl = QLabel("BCI: Inactive")
        for lbl in (self._focus_lbl, self._status_lbl):
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self._focus_lbl)
        layout.addWidget(self._status_lbl)
        layout.addStretch()

    def refresh(self, focus: float, scrolling: bool) -> None:
        self._focus_lbl.setText(f"Focus: {focus:.0f}")
        if scrolling:
            self._status_lbl.setText("Auto-skipping")
            self._status_lbl.setStyleSheet(
                f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: bold;"
            )
            return
        colour = ACCENT_CYAN if focus >= 40 else TEXT_SECONDARY
        self._status_lbl.setText("BCI Active" if focus >= 40 else "BCI: low focus")
        self._status_lbl.setStyleSheet(f"color: {colour}; font-size: 11px;")


class InstagramScreen(QWidget):
    """
    Instagram Reels viewer using Edge WebView2.

    The Qt widget provides a toolbar + black placeholder. The actual content
    is rendered in a frameless Edge window that floats over and tracks the
    content area.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._last_scroll_t: float = 0.0
        self._overlay_injected: bool = False
        self._page_active: bool = False
        self._app_active: bool = True
        self._widget_visible: bool = False
        self._host_visible: bool = False
        self._host_configured: bool = False
        self._host_owner_hwnd: Optional[int] = None
        self._last_host_rect: Optional[tuple[int, int, int, int]] = None
        self._show_retry_scheduled: bool = False
        self._shutdown: bool = False

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(150)
        self._sync_timer.timeout.connect(self._sync_position)

        self._build_ui()
        self._wv = _Wv2Process(_IG_REELS)

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {BG_PRIMARY};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setFixedHeight(46)
        toolbar.setStyleSheet(
            f"background: {BG_CARD}; border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)

        self._url_bar = QLineEdit(_IG_REELS)
        self._url_bar.setStyleSheet(
            f"background: {BG_INPUT}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 4px 8px;"
        )
        self._url_bar.returnPressed.connect(self._on_navigate)

        def _btn(label: str, color: str = ACCENT_CYAN) -> QPushButton:
            button = QPushButton(label)
            button.setStyleSheet(
                f"background: {color}; color: #fff; border-radius: 4px;"
                f" padding: 4px 10px; font-weight: bold;"
            )
            button.setFixedHeight(28)
            return button

        load_btn = _btn("Load")
        reels_btn = _btn("Reels", _ACCENT_PINK)
        home_btn = _btn("Home", ACCENT_GREEN)
        skip_btn = _btn("Skip", "#8B5CF6")

        load_btn.clicked.connect(self._on_navigate)
        reels_btn.clicked.connect(lambda: self._navigate(_IG_REELS))
        home_btn.clicked.connect(lambda: self._navigate(_IG_HOME))
        skip_btn.clicked.connect(self._bci_scroll)

        tb_layout.addWidget(self._url_bar, stretch=1)
        tb_layout.addWidget(load_btn)
        tb_layout.addWidget(reels_btn)
        tb_layout.addWidget(home_btn)
        tb_layout.addWidget(skip_btn)
        root.addWidget(toolbar)

        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._content.setStyleSheet("background: #000;")
        self._placeholder = QLabel(
            "Loading Instagram via Edge WebView2...\n\n"
            "Full H.264 video  |  Persistent login"
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; background: #000;"
        )
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._placeholder)
        root.addWidget(self._content, stretch=1)

        self._eeg_bar = _EEGBar(self)
        root.addWidget(self._eeg_bar)

    def _on_navigate(self) -> None:
        url = self._url_bar.text().strip()
        if not url.startswith("http"):
            url = "https://" + url
        self._navigate(url)

    def _navigate(self, url: str) -> None:
        self._url_bar.setText(url)
        if self._wv.ready:
            self._wv.navigate(url)

    def set_page_active(self, active: bool) -> None:
        self._page_active = bool(active)
        self._refresh_host_visibility()

    def set_app_active(self, active: bool) -> None:
        self._app_active = bool(active)
        self._refresh_host_visibility()

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self._sync_timer.stop()
        if self._wv.ready and self._host_visible:
            self._wv.hide()
            self._host_visible = False
        self._wv.quit()

    def _bci_scroll(self) -> None:
        if not self._host_can_run_js():
            return
        self._wv.run_js(_SKIP_REEL_JS)

    def on_emotions(self, data: dict) -> None:
        focus = float(data.get("focus", 0) or 0)
        now = time.monotonic()
        wants_scroll = (
            focus >= _FOCUS_SCROLL_THRESHOLD
            and (now - self._last_scroll_t) >= _SCROLL_COOLDOWN_SEC
        )
        will_scroll = wants_scroll and self._host_can_run_js()
        self._eeg_bar.refresh(focus, will_scroll)
        if will_scroll:
            self._last_scroll_t = now
            self._bci_scroll()
            log.info("BCI Instagram: focus=%.0f -> auto-skip reel", focus)
        if self._host_can_run_js() and self._overlay_injected:
            label = "Auto-Skip >" if will_scroll else f"Focus: {focus:.0f}"
            self._wv.run_js(_UPDATE_OVERLAY_JS.format(text=f"BCI  {label}"))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._widget_visible = True
        self._refresh_host_visibility()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._widget_visible = False
        self._refresh_host_visibility()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_position()

    def _schedule_try_show(self) -> None:
        if self._shutdown or self._show_retry_scheduled:
            return
        self._show_retry_scheduled = True
        QTimer.singleShot(300, self._try_show)

    def _should_host_be_visible(self) -> bool:
        if self._shutdown:
            return False
        top = self.window()
        return bool(
            self._page_active
            and self._app_active
            and self._widget_visible
            and top is not None
            and top.isVisible()
            and not top.isMinimized()
        )

    def _host_can_run_js(self) -> bool:
        return (
            self._wv.ready
            and self._host_visible
            and self._should_host_be_visible()
        )

    def _refresh_host_visibility(self) -> None:
        if self._should_host_be_visible():
            self._sync_timer.start()
            if self._wv.ready:
                if not self._sync_host_window(force=not self._host_visible):
                    self._schedule_try_show()
            else:
                self._schedule_try_show()
            return

        self._sync_timer.stop()
        if self._wv.ready and self._host_visible:
            self._wv.hide()
            self._host_visible = False
        if self._widget_visible:
            self._placeholder.show()

    def _sync_position(self) -> None:
        if not self._wv.ready or self._shutdown:
            return
        self._sync_host_window()

    def _try_show(self) -> None:
        self._show_retry_scheduled = False
        if not self._should_host_be_visible():
            return
        if self._wv.ready and self._sync_host_window(force=True):
            return
        self._schedule_try_show()

    def _ensure_host_configured(self) -> bool:
        if self._shutdown or not self._wv.ready:
            return False
        top = self.window()
        if top is None:
            return False
        try:
            owner_hwnd = int(top.winId())
        except Exception:
            return False
        if owner_hwnd <= 0:
            return False
        if self._host_configured and self._host_owner_hwnd == owner_hwnd:
            return True
        self._wv.configure_host(owner_hwnd)
        self._host_configured = True
        self._host_owner_hwnd = owner_hwnd
        self._last_host_rect = None
        return True

    def _sync_host_window(self, force: bool = False) -> bool:
        visible = self._should_host_be_visible()
        if not visible:
            if self._host_visible:
                self._wv.hide()
            self._host_visible = False
            if self._widget_visible:
                self._placeholder.show()
            return False

        if not self._ensure_host_configured():
            self._host_visible = False
            return False

        pos = self._content.mapToGlobal(QPoint(0, 0))
        width = max(self._content.width(), 200)
        height = max(self._content.height(), 200)
        rect = (pos.x(), pos.y(), width, height)
        if force or rect != self._last_host_rect:
            self._wv.move(rect[0], rect[1])
            self._wv.resize(rect[2], rect[3])
            self._last_host_rect = rect
        if force or not self._host_visible:
            self._wv.show()
        self._host_visible = True
        self._placeholder.hide()
        if not self._overlay_injected:
            self._wv.run_js(_INJECT_OVERLAY_JS)
            self._overlay_injected = True
        return True
