import os
import sys
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.games_screen import GamesScreen  # noqa: E402
from gui.games_window import GamesWindow  # noqa: E402


APP = QApplication.instance() or QApplication([])


class GamesSmokeTests(unittest.TestCase):
    def test_games_screen_treats_mini_militia_as_immersive_arcade_game(self):
        with patch("gui.games_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            screen = GamesScreen()
        try:
            screen.show()
            APP.processEvents()

            self.assertIn("mini_militia_arena", screen._game_widget_map)
            self.assertIn("mini_militia_arena", screen.IMMERSIVE_GAME_IDS)

            screen._show_detail("mini_militia_arena")
            self.assertEqual(
                screen._detail_title_lbl.text(),
                "A 2D jetpack arena shooter controlled by focus and relaxation",
            )

            screen._controller.begin_calibration()
            screen._controller.start_game()
            screen._stack.setCurrentWidget(screen._gameplay_page)
            screen._switch_game_widget()
            APP.processEvents()

            self.assertIs(screen._game_views.currentWidget(), screen._mini_militia_widget)
            self.assertTrue(screen._game_cancel_btn.isHidden())
            self.assertTrue(screen._game_device_badge.isHidden())
            self.assertTrue(screen._game_level_lbl.isHidden())
        finally:
            screen.close()
            APP.processEvents()

    def test_games_window_close_hides_and_returns_to_catalog(self):
        with patch("gui.games_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            window = GamesWindow()
        try:
            window.show()
            APP.processEvents()
            self.assertTrue(window._screen._view_active)

            window._screen._show_detail("mini_militia_arena")
            self.assertIs(window._screen._stack.currentWidget(), window._screen._detail_page)

            window.close()
            APP.processEvents()

            self.assertFalse(window.isVisible())
            self.assertFalse(window._screen._view_active)
            self.assertIs(window._screen._stack.currentWidget(), window._screen._catalog_page)

            window.show()
            APP.processEvents()
            self.assertTrue(window.isVisible())
            self.assertTrue(window._screen._view_active)
        finally:
            window.shutdown()
            APP.processEvents()


if __name__ == "__main__":
    unittest.main()
