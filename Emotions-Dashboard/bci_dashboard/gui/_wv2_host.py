"""
_wv2_host.py - standalone pywebview host process.

Run by InstagramScreen as a subprocess. Reads JSON commands from stdin,
sends JSON responses to stdout. This is required because pywebview.start()
must run on the main thread; the parent process's main thread is owned by Qt.

Protocol (newline-delimited JSON):
  Parent -> child:
    {"cmd": "navigate", "url": "https://..."}
    {"cmd": "js", "code": "...javascript..."}
    {"cmd": "configure_host", "owner_hwnd": 12345}
    {"cmd": "sync_window", "x": 100, "y": 200, "w": 800, "h": 600,
     "visible": true, "topmost": false, "no_activate": true}
    {"cmd": "move", "x": 100, "y": 200}
    {"cmd": "resize", "w": 800, "h": 600}
    {"cmd": "set_on_top", "value": true}
    {"cmd": "show"}
    {"cmd": "hide"}
    {"cmd": "quit"}

  Child -> parent:
    {"event": "ready"}
    {"event": "url_changed", "url": "https://..."}
    {"event": "error", "msg": "..."}
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
from ctypes import wintypes

import webview

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_WV_STORAGE = sys.argv[1] if len(sys.argv) > 1 else None
_INITIAL_URL = sys.argv[2] if len(sys.argv) > 2 else "https://www.instagram.com/reels/"

_win = None
_USER32 = ctypes.windll.user32
_SET_WINDOW_LONG_PTR = getattr(_USER32, "SetWindowLongPtrW", _USER32.SetWindowLongW)
_GET_WINDOW_LONG_PTR = getattr(_USER32, "GetWindowLongPtrW", _USER32.GetWindowLongW)

_GWL_EXSTYLE = -20
_GWLP_HWNDPARENT = -8
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000

_SW_HIDE = 0
_SW_SHOW = 5
_SW_SHOWNOACTIVATE = 4

_HWND_TOP = 0
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2

_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def _send(obj: dict) -> None:
    try:
        print(json.dumps(obj), flush=True)
    except Exception:
        pass


def _run_on_ui_thread(win: "webview.Window", callback) -> None:
    try:
        from System import Func, Type
        from webview.platforms.winforms import BrowserView

        browser_view = BrowserView.instances.get(win.uid)
        if browser_view is not None and getattr(browser_view, "InvokeRequired", False):
            browser_view.Invoke(Func[Type](callback))
            return
    except Exception:
        pass

    callback()


def _browser_view(win: "webview.Window"):
    from webview.platforms.winforms import BrowserView

    return BrowserView.instances.get(win.uid)


def _handle_to_int(handle) -> int:
    if handle is None:
        return 0
    if hasattr(handle, "ToInt64"):
        return int(handle.ToInt64())
    if hasattr(handle, "ToInt32"):
        return int(handle.ToInt32())
    return int(handle)


def _window_handle(win: "webview.Window") -> tuple[object | None, int]:
    browser_view = _browser_view(win)
    if browser_view is None:
        return None, 0
    return browser_view, _handle_to_int(getattr(browser_view, "Handle", None))


def _logical_xy(browser_view, x: int, y: int) -> tuple[int, int]:
    scale_factor = float(getattr(browser_view, "scale_factor", 1) or 1)
    if scale_factor != 1:
        return int(x * scale_factor), int(y * scale_factor)
    return int(x), int(y)


def _current_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = _RECT()
    if not _USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0, 0, 900, 700
    return (
        int(rect.left),
        int(rect.top),
        int(rect.right - rect.left),
        int(rect.bottom - rect.top),
    )


def _configure_native_window(win: "webview.Window", owner_hwnd: int) -> None:
    # Keep this command for protocol compatibility, but avoid native owner/style
    # mutations. The simpler high-level pywebview flow is the configuration that
    # reliably surfaces Instagram reels playback on this machine.
    return


def _sync_native_window(
    win: "webview.Window",
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    visible: bool,
    topmost: bool,
    no_activate: bool,
) -> None:
    try:
        win.move(int(x), int(y))
    except Exception:
        pass
    try:
        win.resize(int(width), int(height))
    except Exception:
        pass
    try:
        win.on_top = bool(topmost)
    except Exception:
        pass
    if visible:
        _show_native_window(win, no_activate=no_activate)
    else:
        _hide_native_window(win)


def _move_native_window(win: "webview.Window", x: int, y: int) -> None:
    win.move(int(x), int(y))


def _resize_native_window(win: "webview.Window", width: int, height: int) -> None:
    win.resize(int(width), int(height))


def _set_native_topmost(win: "webview.Window", topmost: bool) -> None:
    win.on_top = bool(topmost)


def _show_native_window(win: "webview.Window", no_activate: bool = True) -> None:
    try:
        win.show()
    except Exception:
        browser_view, hwnd = _window_handle(win)
        if hwnd <= 0:
            return
        if browser_view is not None:
            try:
                if not bool(getattr(browser_view, "Visible", False)):
                    if hasattr(browser_view, "show"):
                        browser_view.show()
                    else:
                        browser_view.Show()
            except Exception:
                pass
        _USER32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE if no_activate else _SW_SHOW)


def _hide_native_window(win: "webview.Window") -> None:
    try:
        win.hide()
    except Exception:
        browser_view, hwnd = _window_handle(win)
        if hwnd <= 0:
            return
        if browser_view is not None:
            try:
                if bool(getattr(browser_view, "Visible", False)):
                    if hasattr(browser_view, "hide"):
                        browser_view.hide()
                    else:
                        browser_view.Hide()
            except Exception:
                pass
        _USER32.ShowWindow(hwnd, _SW_HIDE)


def _stdin_loop(win: "webview.Window") -> None:
    should_exit = False
    try:
        for raw in sys.stdin:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            cmd = msg.get("cmd")
            try:
                if cmd == "navigate":
                    win.load_url(msg["url"])
                elif cmd == "js":
                    win.evaluate_js(msg["code"])
                elif cmd == "configure_host":
                    owner_hwnd = int(msg["owner_hwnd"])
                    _run_on_ui_thread(
                        win,
                        lambda owner_hwnd=owner_hwnd: _configure_native_window(win, owner_hwnd),
                    )
                elif cmd == "sync_window":
                    x = int(msg["x"])
                    y = int(msg["y"])
                    width = int(msg["w"])
                    height = int(msg["h"])
                    visible = bool(msg.get("visible", False))
                    topmost = bool(msg.get("topmost", False))
                    no_activate = bool(msg.get("no_activate", False))
                    _run_on_ui_thread(
                        win,
                        lambda x=x, y=y, width=width, height=height, visible=visible,
                        topmost=topmost, no_activate=no_activate: _sync_native_window(
                            win,
                            x=x,
                            y=y,
                            width=width,
                            height=height,
                            visible=visible,
                            topmost=topmost,
                            no_activate=no_activate,
                        ),
                    )
                elif cmd == "move":
                    x = int(msg["x"])
                    y = int(msg["y"])
                    _run_on_ui_thread(win, lambda x=x, y=y: _move_native_window(win, x, y))
                elif cmd == "resize":
                    width = int(msg["w"])
                    height = int(msg["h"])
                    _run_on_ui_thread(
                        win,
                        lambda width=width, height=height: _resize_native_window(
                            win,
                            width,
                            height,
                        ),
                    )
                elif cmd == "set_on_top":
                    value = bool(msg.get("value", False))
                    _run_on_ui_thread(
                        win,
                        lambda value=value: _set_native_topmost(win, value),
                    )
                elif cmd == "show":
                    _run_on_ui_thread(win, lambda: _show_native_window(win))
                elif cmd == "hide":
                    _run_on_ui_thread(win, lambda: _hide_native_window(win))
                elif cmd == "quit":
                    should_exit = True
                    _run_on_ui_thread(win, win.destroy)
                    break
            except Exception as exc:
                _send({"event": "error", "msg": str(exc)})
    finally:
        if not should_exit:
            try:
                _run_on_ui_thread(win, win.destroy)
            except Exception:
                pass
        os._exit(0)


def _on_ready() -> None:
    _send({"event": "ready"})
    threading.Thread(target=_stdin_loop, args=(_win,), daemon=True).start()


def _on_url_changed(url: str) -> None:
    _send({"event": "url_changed", "url": url})


def main() -> None:
    global _win
    _win = webview.create_window(
        "Instagram",
        _INITIAL_URL,
        width=900,
        height=700,
        hidden=True,
        frameless=True,
        on_top=True,
        shadow=False,
    )
    _win.events.loaded += lambda: _send({"event": "url_changed", "url": _win.get_current_url()})

    webview.start(
        func=_on_ready,
        gui="edgechromium",
        user_agent=_CHROME_UA,
        private_mode=False,
        storage_path=_WV_STORAGE,
    )


if __name__ == "__main__":
    main()
