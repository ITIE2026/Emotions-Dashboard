import os
import sys
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.instagram_screen import InstagramScreen  # noqa: E402


APP = QApplication.instance() or QApplication([])


class InstagramScreenTests(unittest.TestCase):
    def test_instagram_screen_prefers_reels_playback_host(self):
        screen = InstagramScreen()
        try:
            self.assertTrue(
                hasattr(screen, "_wv"),
                "Instagram screen should expose the reels playback host",
            )
            self.assertFalse(
                hasattr(screen, "_web_view"),
                "Instagram screen should not use the embedded Qt web view for reels playback",
            )
        finally:
            if hasattr(screen, "shutdown"):
                screen.shutdown()
            screen.close()


if __name__ == "__main__":
    unittest.main()
