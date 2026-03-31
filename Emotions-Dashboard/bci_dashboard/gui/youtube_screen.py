"""
YouTubeScreen – embedded web browser panel for watching YouTube while tracking EEG metrics.

Requires PySide6-WebEngine (pip install PySide6-WebEngine).
Falls back gracefully to an "Open in Browser" button if QtWebEngineWidgets is unavailable.
"""
from __future__ import annotations

import time
import webbrowser
import logging

from PySide6.QtCore import Qt, QUrl, QTimer, QPoint, QPointF
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
    ACCENT_RED,
    BG_CARD,
    BG_INPUT,
    BG_PRIMARY,
    BORDER_SUBTLE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

log = logging.getLogger(__name__)

# ── Bootstrap PySide6 WebEngine addons (short-path install at C:\p6) ──────────
# PySide6_Addons must be at C:\p6 when the normal user install fails due to
# Windows MAX_PATH (260-char) limits.  main.py does this first; this block is
# a safety net when youtube_screen is imported standalone (e.g. tests).
_P6_ADDONS = r"C:\p6\PySide6"
import os as _os
if _os.path.isdir(_P6_ADDONS):
    try:
        _exe = _os.path.join(_P6_ADDONS, "QtWebEngineProcess.exe")
        _res = _os.path.join(_P6_ADDONS, "resources")
        _trans = _os.path.join(_P6_ADDONS, "translations")
        if _os.path.isfile(_exe):
            _os.environ.setdefault("QTWEBENGINEPROCESS_PATH", _exe)
        if _os.path.isdir(_res):
            _os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", _res)
        if _os.path.isdir(_trans):
            _os.environ.setdefault("QTWEBENGINE_LOCALES_PATH",
                                   _os.path.join(_trans, "qtwebengine_locales"))
        _os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu"
        )
        import PySide6 as _pyside6_bootstrap
        if _P6_ADDONS not in _pyside6_bootstrap.__path__:
            _pyside6_bootstrap.__path__.insert(0, _P6_ADDONS)
        _main_pyside = _os.path.dirname(_pyside6_bootstrap.__file__)
        _os.add_dll_directory(_main_pyside)
        _os.add_dll_directory(_P6_ADDONS)
        # QtWebEngineProcess.exe is a separate subprocess – it inherits PATH,
        # not os.add_dll_directory.  Add both PySide6 dirs to PATH so it can
        # find Qt6Core.dll + Qt6WebEngineCore.dll at runtime.
        _path = _os.environ.get("PATH", "")
        for _d in (_P6_ADDONS, _main_pyside):
            if _d not in _path:
                _os.environ["PATH"] = _d + _os.pathsep + _path
                _path = _os.environ["PATH"]
    except Exception:
        pass

# ── Try to import QWebEngineView ──────────────────────────────────────────────
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

    _WEB_ENGINE_AVAILABLE = True
except ImportError:
    _WEB_ENGINE_AVAILABLE = False
    log.warning(
        "PySide6 WebEngine not available – YouTube screen will use fallback mode."
    )

# ── YouTube URL helpers ───────────────────────────────────────────────────────
_YT_HOME = "https://www.youtube.com"

# ── BCI Shorts control thresholds ─────────────────────────────────────────────
# When FOCUS exceeds this value while watching Shorts, auto-scroll to next.
_FOCUS_SCROLL_THRESHOLD = 60
# Minimum seconds between auto-scrolls to prevent rapid-fire skipping.
_SCROLL_COOLDOWN_SEC = 6.0


def _normalize_url(raw: str) -> str:
    """Ensure the input is a proper URL. Adds https:// if missing."""
    raw = raw.strip()
    if not raw:
        return _YT_HOME
    if not raw.startswith("http"):
        # If it looks like a search query (contains spaces), use YouTube search
        if " " in raw:
            from urllib.parse import quote_plus
            return f"https://www.youtube.com/results?search_query={quote_plus(raw)}"
        raw = "https://" + raw
    return raw


# ── Floating EEG overlay ──────────────────────────────────────────────────────

class _EEGOverlay(QFrame):
    """Small floating widget showing live EEG scores on top of the video."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setObjectName("EEGOverlay")
        self.setStyleSheet(
            f"#EEGOverlay {{ background: rgba(10,10,20,210); border-radius: 12px;"
            f" border: 1px solid {BORDER_SUBTLE}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(18)

        self._focus_lbl = self._make_chip("🧠", "Focus", ACCENT_GREEN)
        self._relax_lbl = self._make_chip("😌", "Relax", ACCENT_CYAN)
        self._stress_lbl = self._make_chip("⚡", "Stress", ACCENT_RED)
        self._mode_lbl = QLabel("")
        self._mode_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"
        )

        layout.addWidget(self._focus_lbl)
        layout.addWidget(self._relax_lbl)
        layout.addWidget(self._stress_lbl)
        layout.addWidget(self._mode_lbl)

        self.adjustSize()
        self._hidden_timer = QTimer(self)
        self._hidden_timer.setSingleShot(True)
        self._hidden_timer.timeout.connect(self.hide)
        self.hide()

    def _make_chip(self, icon: str, label: str, color: str) -> QLabel:
        lbl = QLabel(f"{icon} {label}: —")
        lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 600;"
            f" background: transparent;"
        )
        return lbl

    def _update_chip(self, lbl: QLabel, icon: str, label: str, value, color: str):
        if value is None:
            text = f"{icon} {label}: —"
        else:
            text = f"{icon} {label}: {int(value)}"
        lbl.setText(text)

    def update_metrics(self, focus=None, relax=None, stress=None, mode_text=""):
        """Update displayed values. Shows overlay and auto-hides after 5 s."""
        self._update_chip(self._focus_lbl, "🧠", "Focus", focus, ACCENT_GREEN)
        self._update_chip(self._relax_lbl, "😌", "Relax", relax, ACCENT_CYAN)
        self._update_chip(self._stress_lbl, "⚡", "Stress", stress, ACCENT_RED)
        self._mode_lbl.setText(mode_text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._hidden_timer.start(5000)

    def _reposition(self):
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            margin = 16
            self.move(margin, ph - self.height() - margin)


# ── Main screen ───────────────────────────────────────────────────────────────

class YouTubeScreen(QWidget):
    """
    Full-screen YouTube / web panel with an EEG metric overlay.

    Public API (called from MainWindow):
        on_emotions(data: dict)
        on_productivity(data: dict)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ───────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(
            f"background: {BG_CARD}; border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)

        yt_icon = QLabel("▶")
        yt_icon.setStyleSheet(f"color: {ACCENT_RED}; font-size: 20px; background: transparent;")
        yt_icon.setFixedWidth(26)
        tb_layout.addWidget(yt_icon)

        # Back / Forward navigation
        self._back_btn = self._toolbar_btn("◀", TEXT_PRIMARY)
        self._back_btn.setFixedWidth(36)
        self._back_btn.setToolTip("Back")
        self._back_btn.clicked.connect(self._go_back)
        tb_layout.addWidget(self._back_btn)

        self._fwd_btn = self._toolbar_btn("▶", TEXT_PRIMARY)
        self._fwd_btn.setFixedWidth(36)
        self._fwd_btn.setToolTip("Forward")
        self._fwd_btn.clicked.connect(self._go_forward)
        tb_layout.addWidget(self._fwd_btn)

        self._refresh_btn = self._toolbar_btn("⟳", TEXT_PRIMARY)
        self._refresh_btn.setFixedWidth(36)
        self._refresh_btn.setToolTip("Reload")
        self._refresh_btn.clicked.connect(self._reload_page)
        tb_layout.addWidget(self._refresh_btn)

        self._url_bar = QLineEdit()
        self._url_bar.setPlaceholderText(
            "Search YouTube or paste a URL…"
        )
        self._url_bar.setStyleSheet(
            f"QLineEdit {{ background: {BG_INPUT}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
            f" padding: 4px 12px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT_GREEN}; }}"
        )
        self._url_bar.returnPressed.connect(self._load_url)
        tb_layout.addWidget(self._url_bar, stretch=1)

        self._go_btn = self._toolbar_btn("▶  Load", ACCENT_GREEN)
        self._go_btn.setFixedWidth(90)
        self._go_btn.clicked.connect(self._load_url)
        tb_layout.addWidget(self._go_btn)

        self._yt_home_btn = self._toolbar_btn("YouTube", ACCENT_RED)
        self._yt_home_btn.setFixedWidth(90)
        self._yt_home_btn.clicked.connect(self._open_yt_home)
        tb_layout.addWidget(self._yt_home_btn)

        self._browser_btn = self._toolbar_btn("🌐 Browser", ACCENT_CYAN)
        self._browser_btn.setFixedWidth(100)
        self._browser_btn.setToolTip("Open current URL in system browser")
        self._browser_btn.clicked.connect(self._open_in_browser)
        tb_layout.addWidget(self._browser_btn)

        self._skip_btn = self._toolbar_btn("⏭ Skip", ACCENT_GREEN)
        self._skip_btn.setFixedWidth(80)
        self._skip_btn.setToolTip("Manually skip to next Short (test BCI scroll)")
        self._skip_btn.clicked.connect(self._scroll_to_next_short)
        tb_layout.addWidget(self._skip_btn)

        root.addWidget(toolbar)

        # ── Content area ──────────────────────────────────────────────
        self._content_container = QWidget()
        self._content_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(self._content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root.addWidget(self._content_container, stretch=1)

        if _WEB_ENGINE_AVAILABLE:
            self._setup_web_view(content_layout)
        else:
            self._setup_fallback(content_layout)

        # ── EEG overlay (sits on top of content container) ────────────
        self._overlay = _EEGOverlay(self._content_container)

        # ── BCI Shorts auto-scroll state ──────────────────────────────
        self._last_scroll_time: float = 0.0
        self._bci_enabled = True

    # ── Internal helpers ──────────────────────────────────────────────

    def _toolbar_btn(self, text: str, color: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {color};"
            f" border: 1px solid {color}; border-radius: 8px;"
            f" padding: 4px 10px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {color}; color: #0A0A14; }}"
        )
        return btn

    def _setup_web_view(self, layout: QVBoxLayout):
        # Use default profile so cookies/storage persist between sessions
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        from PySide6.QtWebEngineCore import QWebEnginePage
        page = QWebEnginePage(profile, self)

        self._web_view = QWebEngineView()
        self._web_view.setPage(page)

        # Enable features YouTube needs
        settings = self._web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        self._web_view.urlChanged.connect(self._on_url_changed)
        self._web_view.loadStarted.connect(
            lambda: log.info("YouTubeScreen: page load started")
        )
        self._web_view.loadFinished.connect(self._on_load_finished)
        layout.addWidget(self._web_view)
        self._load_yt_home()

    def _on_load_finished(self, ok: bool):
        url = self._web_view.url().toString() if self._web_view else "?"
        log.info("YouTubeScreen: load finished ok=%s  url=%s", ok, url)

    def _setup_fallback(self, layout: QVBoxLayout):
        """Shown when PySide6-WebEngine is not installed."""
        self._web_view = None
        container = QFrame()
        container.setStyleSheet(f"background: {BG_PRIMARY};")
        inner = QVBoxLayout(container)
        inner.setAlignment(Qt.AlignCenter)
        inner.setSpacing(16)

        icon = QLabel("▶")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: 56px; color: {ACCENT_RED}; background: transparent;")

        msg = QLabel(
            "<b>YouTube / Web panel requires PySide6-WebEngine.</b><br><br>"
            "Install it by running:<br>"
            "<code style='color:#00E5FF;'>pip install PySide6-WebEngine</code><br><br>"
            "Then restart the dashboard.<br><br>"
            "In the meantime you can open URLs in your system browser below."
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; background: transparent; line-height: 1.6;"
        )

        open_btn = QPushButton("🌐  Open YouTube in Browser")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setFixedWidth(260)
        open_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_RED}; color: #fff; border: none;"
            f" border-radius: 10px; padding: 10px 20px; font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #FF3333; }}"
        )
        open_btn.clicked.connect(lambda: webbrowser.open(_YT_HOME))

        inner.addWidget(icon)
        inner.addWidget(msg)
        inner.addWidget(open_btn, alignment=Qt.AlignCenter)
        layout.addWidget(container)

    def _load_yt_home(self):
        if self._web_view:
            self._web_view.load(QUrl(_YT_HOME))

    def _load_url(self):
        raw = self._url_bar.text().strip()
        if not raw:
            self._load_yt_home()
            return
        target = _normalize_url(raw)
        log.info("YouTubeScreen: loading %s", target)
        if self._web_view:
            self._web_view.load(QUrl(target))
        else:
            webbrowser.open(target)

    def _go_back(self):
        if self._web_view:
            self._web_view.back()

    def _go_forward(self):
        if self._web_view:
            self._web_view.forward()

    def _reload_page(self):
        if self._web_view:
            self._web_view.reload()

    def _open_yt_home(self):
        self._url_bar.clear()
        if self._web_view:
            self._load_yt_home()
        else:
            webbrowser.open(_YT_HOME)

    def _open_in_browser(self):
        if self._web_view:
            current = self._web_view.url().toString()
        else:
            raw = self._url_bar.text().strip()
            current = _normalize_url(raw) if raw else _YT_HOME
        if current:
            webbrowser.open(current)

    def _on_url_changed(self, url: QUrl):
        self._url_bar.setText(url.toString())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep overlay in the bottom-left of the content container
        if hasattr(self, "_overlay"):
            self._overlay._reposition()

    # ── Public API ────────────────────────────────────────────────────

    def _is_shorts_page(self) -> bool:
        """Return True if the current URL is a YouTube Shorts page."""
        if not self._web_view:
            return False
        return "/shorts" in self._web_view.url().toString()

    def _scroll_to_next_short(self):
        """Skip to the next YouTube Short by scrolling the reel in-place.

        Uses JavaScript to dispatch keyboard / scroll events that YouTube
        Shorts already handles natively.  No page navigation or reload.
        """
        if not self._web_view:
            return
        log.info("BCI Shorts: _scroll_to_next_short called")

        js = r"""
        (function() {
            // Strategy 1 — click YouTube's own "Down" navigation button
            var downBtn = document.querySelector(
                '#navigation-button-down button, ' +
                'ytd-shorts [aria-label="Next video"], ' +
                'button.navigation-button-down');
            if (downBtn) {
                downBtn.click();
                return 'clicked-nav-button';
            }

            // Strategy 2 — dispatch ArrowDown keydown on the active player
            //   YouTube Shorts listens for ArrowDown to advance the reel.
            var target = document.activeElement || document.body;
            var ev = new KeyboardEvent('keydown', {
                key: 'ArrowDown', code: 'ArrowDown',
                keyCode: 40, which: 40,
                bubbles: true, cancelable: true
            });
            target.dispatchEvent(ev);

            // Strategy 3 — scroll the snap container by one viewport height
            var containers = document.querySelectorAll(
                'ytd-shorts, #shorts-container, ' +
                'ytd-reel-video-renderer, [id="shorts-inner-container"]');
            for (var i = 0; i < containers.length; i++) {
                var c = containers[i];
                if (c.scrollHeight > c.clientHeight) {
                    c.scrollBy({top: window.innerHeight, behavior: 'smooth'});
                    return 'scrolled-container+keydown';
                }
            }

            // Strategy 4 — scroll the whole page as last resort
            window.scrollBy({top: window.innerHeight, behavior: 'smooth'});
            return 'scrollBy-page+keydown';
        })();
        """
        self._web_view.page().runJavaScript(
            js, 0,
            lambda r: log.info("BCI Shorts: scroll result = %s", r),
        )

    def on_emotions(self, data: dict):
        """Receive emotion states and drive BCI Shorts control.

        Uses emotions 'attention' (0-100) and 'relaxation' (0-100) which are
        the same values shown in the Cognitive States window.
        """
        if not data:
            return
        focus = data.get("attention")   # 0-100 scale
        relax = data.get("relaxation")  # 0-100 scale
        stress = data.get("cognitiveLoad")

        mode_text = ""
        on_shorts = self._is_shorts_page()

        if on_shorts and self._bci_enabled:
            now = time.monotonic()
            cooldown_ok = (now - self._last_scroll_time) >= _SCROLL_COOLDOWN_SEC

            if focus is not None:
                # Throttle logging to once every 2 seconds
                if not hasattr(self, '_last_log_time') or \
                        (now - self._last_log_time) >= 2.0:
                    log.info(
                        "BCI Shorts: attention=%.1f relax=%.1f threshold=%s cooldown_ok=%s",
                        focus, relax or 0, _FOCUS_SCROLL_THRESHOLD, cooldown_ok,
                    )
                    self._last_log_time = now
                if focus >= _FOCUS_SCROLL_THRESHOLD and cooldown_ok:
                    log.info("BCI Shorts: ATTENTION HIGH (%.1f) → skipping!", focus)
                    self._scroll_to_next_short()
                    self._last_scroll_time = now
                    mode_text = "⏭ SKIPPED (focused)"
                elif focus < _FOCUS_SCROLL_THRESHOLD and relax is not None and relax > focus:
                    mode_text = "▶ WATCHING (relaxed)"
                else:
                    mode_text = "🎯 BCI Shorts active"
        elif on_shorts:
            mode_text = "⏸ BCI paused"

        self._overlay.update_metrics(
            focus=focus, relax=relax, stress=stress, mode_text=mode_text
        )

    def on_productivity(self, data: dict):
        """Receive productivity metrics (overlay only, scroll uses emotions)."""
        pass
