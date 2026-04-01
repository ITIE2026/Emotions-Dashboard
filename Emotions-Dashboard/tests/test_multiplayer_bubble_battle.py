import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.multiplayer_bubble_battle import (  # noqa: E402
    MultiplayerBubbleBattleController,
    COLUMNS,
    VISIBLE_ROWS,
    LAUNCHER_ZONE_ROW,
    INITIAL_SHOTS,
    GARBAGE_COMBO_THRESHOLD,
    PALETTE,
    INTENT_STREAK_NEEDED,
)
from gui.eeg_game_base import CALIBRATION_SAMPLES, READY_STREAK_TARGET  # noqa: E402


def _valid_metrics(conc=0.5, relax=0.3):
    return {"concentration": conc, "relaxation": relax, "valid": True, "stale": False}


def _invalid_metrics():
    return {"concentration": 0.0, "relaxation": 0.0, "valid": False, "stale": False}


def _calibrated_controller():
    ctrl = MultiplayerBubbleBattleController("Alice", "Bob")
    for pid in (0, 1):
        for _ in range(CALIBRATION_SAMPLES):
            ctrl.add_calibration_sample_for(pid, 0.50, 0.30, valid=True)
        for _ in range(READY_STREAK_TARGET + 2):
            ctrl.add_calibration_sample_for(pid, 0.1, 0.9, valid=True)
    ctrl.start_game()
    return ctrl


class TestCalibration(unittest.TestCase):
    def test_sample_collection(self):
        ctrl = MultiplayerBubbleBattleController("A", "B")
        snap = ctrl.add_calibration_sample_for(0, 0.5, 0.3, valid=True)
        self.assertEqual(snap["sample_count"], 1)
        self.assertFalse(snap["complete"])

    def test_invalid_sample_not_counted(self):
        ctrl = MultiplayerBubbleBattleController()
        ctrl.add_calibration_sample_for(0, 0.5, 0.3, valid=True)
        snap = ctrl.add_calibration_sample_for(0, 0.0, 0.0, valid=False)
        self.assertEqual(snap["sample_count"], 1)


class TestBubbleBattleTick(unittest.TestCase):
    def test_tick_returns_player_views(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertIn("player_views", state)
        self.assertIn("0", state["player_views"])
        self.assertIn("1", state["player_views"])

    def test_tick_returns_required_keys(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        for key in ("mode", "player1_name", "player2_name",
                     "run_completed", "winner"):
            self.assertIn(key, state)

    def test_mode_value(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertEqual(state["mode"], "mp_bubble_battle")

    def test_player_names(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertEqual(state["player1_name"], "Alice")
        self.assertEqual(state["player2_name"], "Bob")

    def test_player_view_has_game_keys(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        pv = state["player_views"]["0"]
        for key in ("board", "aim_slot", "current_bubble", "shots_left"):
            self.assertIn(key, pv, f"Missing key: {key}")

    def test_initial_shots(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertEqual(state["player_views"]["0"]["shots_left"], INITIAL_SHOTS)
        self.assertEqual(state["player_views"]["1"]["shots_left"], INITIAL_SHOTS)

    def test_game_not_completed_initially(self):
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertFalse(state["run_completed"])

    def test_constants_valid(self):
        self.assertGreater(COLUMNS, 0)
        self.assertGreater(VISIBLE_ROWS, 0)
        self.assertGreater(LAUNCHER_ZONE_ROW, 0)
        self.assertGreater(INITIAL_SHOTS, 0)
        self.assertGreater(GARBAGE_COMBO_THRESHOLD, 0)
        self.assertGreater(len(PALETTE), 0)
        self.assertGreater(INTENT_STREAK_NEEDED, 0)

    def test_both_boards_identical_initially(self):
        """Both players should start with identical boards."""
        ctrl = _calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        board0 = state["player_views"]["0"]["board"]
        board1 = state["player_views"]["1"]["board"]
        self.assertEqual(board0, board1)


if __name__ == "__main__":
    unittest.main()
