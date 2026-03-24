import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui.mind_maze_controller import MindMazeController  # noqa: E402


class MindMazeControllerTests(unittest.TestCase):
    def _calibrate(self, controller: MindMazeController):
        controller.begin_calibration()
        for _ in range(20):
            snapshot = controller.add_calibration_sample(50.0, 50.0, True)
        self.assertIsNotNone(snapshot.conc_baseline)
        self.assertIsNotNone(snapshot.relax_baseline)
        return snapshot

    def test_calibration_requires_relaxed_ready_streak(self):
        controller = MindMazeController()
        self._calibrate(controller)

        snap = controller.add_calibration_sample(52.5, 50.0, True)
        self.assertFalse(snap.complete)
        snap = controller.add_calibration_sample(51.5, 50.0, True)
        self.assertFalse(snap.complete)
        snap = controller.add_calibration_sample(51.0, 50.0, True)
        self.assertFalse(snap.complete)
        snap = controller.add_calibration_sample(50.5, 50.0, True)
        self.assertTrue(snap.complete)

    def test_compute_intent_respects_phase_and_balance(self):
        controller = MindMazeController()
        self.assertEqual(
            controller.compute_intent(0.6, -0.8, phase="vertical", valid_exits=("up",)),
            "up",
        )
        self.assertEqual(
            controller.compute_intent(-0.8, 0.9, phase="vertical", valid_exits=("down",)),
            "down",
        )
        self.assertEqual(
            controller.compute_intent(0.5, -0.5, phase="horizontal", valid_exits=("left", "right")),
            "right",
        )
        self.assertEqual(
            controller.compute_intent(-0.5, 0.5, phase="horizontal", valid_exits=("left", "right")),
            "left",
        )
        self.assertIsNone(
            controller.compute_intent(0.2, 0.2, phase="horizontal", valid_exits=("left", "right"))
        )

    def test_upper_corridor_switches_to_horizontal_phase(self):
        controller = MindMazeController()
        self._calibrate(controller)
        controller.start_game()
        controller._player = (2, 1)

        phase, valid_exits, recommended, hint = controller.movement_policy()
        self.assertEqual(phase, "horizontal")
        self.assertIn("right", valid_exits)
        self.assertEqual(recommended, "right")
        self.assertIn("right", hint.lower())

    def test_goal_reach_advances_to_next_level(self):
        controller = MindMazeController()
        self._calibrate(controller)
        controller.start_game()
        controller._player = controller.current_level.goal

        snap = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=5.0)
        self.assertTrue(snap.level_completed)
        self.assertEqual(controller.current_level_number, 2)
        self.assertEqual(controller.player, controller.current_level.start)

    def test_stale_metrics_freeze_movement(self):
        controller = MindMazeController()
        self._calibrate(controller)
        controller.start_game()
        start_pos = controller.player

        snap = controller.update_gameplay(70.0, 50.0, valid=True, stale=True, elapsed_seconds=1.0)
        self.assertEqual(controller.player, start_pos)
        self.assertIn("stale", snap.blocked_reason.lower())

    def test_run_result_records_cancelled_level(self):
        controller = MindMazeController()
        self._calibrate(controller)
        controller.start_game()

        result = controller.finish_run(current_elapsed_seconds=12.0, aborted=True)
        self.assertEqual(len(result.level_results), 3)
        self.assertFalse(result.level_results[0].completed)
        self.assertEqual(result.level_results[0].score, 0)


if __name__ == "__main__":
    unittest.main()
