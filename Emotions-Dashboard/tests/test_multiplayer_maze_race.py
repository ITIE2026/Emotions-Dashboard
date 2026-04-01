import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.multiplayer_maze_race import (  # noqa: E402
    MultiplayerMazeRaceController,
    MazeLevel,
    INTENT_STREAK_NEEDED,
)
from gui.eeg_game_base import CALIBRATION_SAMPLES, READY_STREAK_TARGET  # noqa: E402


def _valid_metrics(conc=0.5, relax=0.3):
    return {"concentration": conc, "relaxation": relax, "valid": True, "stale": False}


def _invalid_metrics():
    return {"concentration": 0.0, "relaxation": 0.0, "valid": False, "stale": False}


def _calibrated_controller():
    ctrl = MultiplayerMazeRaceController("Alice", "Bob")
    for pid in (0, 1):
        for _ in range(CALIBRATION_SAMPLES):
            ctrl.add_calibration_sample_for(pid, 0.50, 0.30, valid=True)
        for _ in range(READY_STREAK_TARGET + 2):
            ctrl.add_calibration_sample_for(pid, 0.1, 0.9, valid=True)
    ctrl.start_game()
    return ctrl


class TestCalibration(unittest.TestCase):
    def test_sample_collection(self):
        ctrl = MultiplayerMazeRaceController("A", "B")
        snap = ctrl.add_calibration_sample_for(0, 0.5, 0.3, valid=True)
        self.assertEqual(snap["sample_count"], 1)
        self.assertFalse(snap["complete"])

    def test_invalid_sample_not_counted(self):
        ctrl = MultiplayerMazeRaceController()
        ctrl.add_calibration_sample_for(0, 0.5, 0.3, valid=True)
        snap = ctrl.add_calibration_sample_for(0, 0.0, 0.0, valid=False)
        self.assertEqual(snap["sample_count"], 1)


class TestMazeRaceTick(unittest.TestCase):
    def test_tick_returns_required_keys(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        for key in ("mode", "player1_name", "player2_name",
                     "run_completed", "winner", "player", "player2", "goal"):
            self.assertIn(key, state, f"Missing key: {key}")

    def test_mode_value(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertEqual(state["mode"], "mp_maze_race")

    def test_player_names(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertEqual(state["player1_name"], "Alice")
        self.assertEqual(state["player2_name"], "Bob")

    def test_shared_view_no_player_views(self):
        """Maze Race is shared-view, should NOT have player_views dict."""
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertNotIn("player_views", state)

    def test_players_start_at_valid_positions(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        p1 = state["player"]
        p2 = state["player2"]
        self.assertIsInstance(p1, (list, tuple))
        self.assertIsInstance(p2, (list, tuple))
        self.assertEqual(len(p1), 2)
        self.assertEqual(len(p2), 2)

    def test_game_not_completed_initially(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertFalse(state["run_completed"])

    def test_has_level_info(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertIn("level", state)

    def test_move_counts_present(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertIn("player1_moves", state)
        self.assertIn("player2_moves", state)

    def test_constants_valid(self):
        self.assertGreater(INTENT_STREAK_NEEDED, 0)


if __name__ == "__main__":
    unittest.main()
