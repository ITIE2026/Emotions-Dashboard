import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui import _wv2_host  # noqa: E402


class _BrowserViewShowStub:
    Visible = False

    def __init__(self):
        self.show_called = False
        self.hide_called = False

    def show(self):
        self.show_called = True

    def hide(self):
        self.hide_called = True


class _WindowOpsStub:
    def __init__(self):
        self.moves = []
        self.resizes = []
        self.on_top = None

    def move(self, x, y):
        self.moves.append((x, y))

    def resize(self, w, h):
        self.resizes.append((w, h))


class Wv2HostTests(unittest.TestCase):
    def test_show_native_window_uses_pywebview_browser_show(self):
        browser_view = _BrowserViewShowStub()
        with (
            patch.object(_wv2_host, "_window_handle", return_value=(browser_view, 123)),
            patch.object(_wv2_host._USER32, "ShowWindow"),
        ):
            _wv2_host._show_native_window(object())

        self.assertTrue(browser_view.show_called)

    def test_hide_native_window_uses_pywebview_browser_hide(self):
        browser_view = _BrowserViewShowStub()
        browser_view.Visible = True
        with (
            patch.object(_wv2_host, "_window_handle", return_value=(browser_view, 123)),
            patch.object(_wv2_host._USER32, "ShowWindow"),
        ):
            _wv2_host._hide_native_window(object())

        self.assertTrue(browser_view.hide_called)

    def test_move_native_window_uses_pywebview_window_move(self):
        win = _WindowOpsStub()
        _wv2_host._move_native_window(win, 120, 340)
        self.assertEqual(win.moves, [(120, 340)])

    def test_resize_native_window_uses_pywebview_window_resize(self):
        win = _WindowOpsStub()
        _wv2_host._resize_native_window(win, 900, 700)
        self.assertEqual(win.resizes, [(900, 700)])

    def test_set_native_topmost_uses_pywebview_window_property(self):
        win = _WindowOpsStub()
        _wv2_host._set_native_topmost(win, True)
        self.assertTrue(win.on_top)


if __name__ == "__main__":
    unittest.main()
