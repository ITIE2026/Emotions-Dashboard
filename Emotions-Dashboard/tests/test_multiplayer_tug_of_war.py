import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.multiplayer_tug_of_war import (  # noqa: E402
    MultiplayerTugOfWarController,
    CAPTURE_THRESHOLD,
)


def _valid_metrics(conc=0.5, relax=0.3):
    return {"concentration": conc, "relaxation": relax, "valid": True, "stale": False}


def _invalid_metrics():
    return {"concentration": 0.0, "relaxation": 0.0, "valid": False, "stale": False}


class TestCalibration(unittest.TestCase):
    """Per-player calibration collects samples and computes baseline."""

    def test_sample_collection(self):
        ctrl = MultiplayerTugOfWarController("A", "B")
        snap = ctrl.add_calibration_sample_for(0, 0.5, 0.3, valid=True)
        self.assertEqual(snap["sample_count"], 1)
        self.assertFalse(snap["complete"])

    def test_invalid_sample_not_counted(self):
        ctrl = MultiplayerTugOfWarController()
        ctrl.add_calibration_sample_for(0, 0.5, 0.3, valid=True)
        snap = ctrl.add_calibration_sample_for(0, 0.0, 0.0, valid=False)
        self.assertEqual(snap["sample_count"], 1)

    def test_both_players_calibrate_independently(self):
        ctrl = MultiplayerTugOfWarController()
        for _ in range(5):
            ctrl.add_calibration_sample_for(0, 0.55, 0.30, valid=True)

        snap0 = ctrl.add_calibration_sample_for(0, 0.55, 0.30, valid=True)
        snap1 = ctrl.add_calibration_sample_for(1, 0.60, 0.25, valid=True)

        self.assertGreater(snap0["sample_count"], snap1["sample_count"])


class TestGameTick(unittest.TestCase):
    """MultiplayerTugOfWarController.tick() returns valid view_state."""

    def _calibrated_controller(self) -> MultiplayerTugOfWarController:
        ctrl = MultiplayerTugOfWarController("Alice", "Bob")
        from gui.eeg_game_base import CALIBRATION_SAMPLES, READY_STREAK_TARGET

        for pid in (0, 1):
            for _ in range(CALIBRATION_SAMPLES):
                ctrl.add_calibration_sample_for(pid, 0.50, 0.30, valid=True)
            # Push through the ready streak
            for _ in range(READY_STREAK_TARGET + 2):
                ctrl.add_calibration_sample_for(pid, 0.1, 0.9, valid=True)

        ctrl.start_game()
        return ctrl

    def test_tick_returns_required_keys(self):
        ctrl = self._calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        required = {
            "mode", "headline", "rope_position", "rope_tension",
            "player_force", "system_force", "player1_name", "player2_name",
            "player1_force", "player2_force", "player1_score", "player2_score",
            "capture_progress", "advantage_side", "message",
            "run_completed", "winner",
        }
        self.assertTrue(required.issubset(state.keys()), f"Missing: {required - state.keys()}")

    def test_rope_stays_centred_with_equal_metrics(self):
        ctrl = self._calibrated_controller()
        for _ in range(10):
            state = ctrl.tick(_valid_metrics(0.6, 0.3), _valid_metrics(0.6, 0.3))
        self.assertAlmostEqual(state["rope_position"], 0.0, places=1)

    def test_dominant_player_shifts_rope(self):
        ctrl = self._calibrated_controller()
        for _ in range(50):
            state = ctrl.tick(
                _valid_metrics(conc=0.95, relax=0.1),
                _valid_metrics(conc=0.10, relax=0.1),
            )
        # P1 is dominant → rope should move LEFT (negative)
        self.assertLess(state["rope_position"], 0.0)

    def test_invalid_metrics_pause_game(self):
        ctrl = self._calibrated_controller()
        state = ctrl.tick(_invalid_metrics(), _invalid_metrics())
        self.assertIn("Artifact", state["message"])

    def test_game_names_propagated(self):
        ctrl = self._calibrated_controller()
        state = ctrl.tick(_valid_metrics(), _valid_metrics())
        self.assertEqual(state["player1_name"], "Alice")
        self.assertEqual(state["player2_name"], "Bob")


class TestCaptureThreshold(unittest.TestCase):
    def test_threshold_in_valid_range(self):
        self.assertGreater(CAPTURE_THRESHOLD, 0.0)
        self.assertLessEqual(CAPTURE_THRESHOLD, 1.0)


if __name__ == "__main__":
    unittest.main()
