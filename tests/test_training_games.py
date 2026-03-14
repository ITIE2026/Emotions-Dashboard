import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui.training_games import (  # noqa: E402
    CalmCurrentController,
    FullRebootController,
    JumpBallController,
    NeuroRacerController,
    PatternRecallController,
    SpaceShooterController,
    active_training_specs,
)


class TrainingGameControllerTests(unittest.TestCase):
    def _calibrate(self, controller):
        controller.begin_calibration()
        for _ in range(20):
            snapshot = controller.add_calibration_sample(50.0, 50.0, True)
        self.assertIsNotNone(snapshot.conc_baseline)
        self.assertIsNotNone(snapshot.relax_baseline)
        controller.start_game()

    def test_active_specs_include_arcade_games(self):
        active_ids = {spec.game_id for spec in active_training_specs()}
        self.assertTrue({"space_shooter", "jump_ball", "neuro_racer"}.issubset(active_ids))
        self.assertIn("full_reboot", active_ids)

    def test_calm_current_rewards_relaxation(self):
        controller = CalmCurrentController()
        self._calibrate(controller)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertEqual(snapshot.direction, "flow")
        self.assertGreater(controller.view_state["distance"], 0.0)

    def test_calm_current_artifacts_pause_progression(self):
        controller = CalmCurrentController()
        self._calibrate(controller)
        start_distance = controller.view_state["distance"]

        snapshot = controller.update_gameplay(49.0, 53.0, valid=False, stale=False, elapsed_seconds=1.0)
        self.assertIn("artifacts", snapshot.blocked_reason.lower())
        self.assertEqual(start_distance, controller.view_state["distance"])

    def test_full_reboot_relaxation_advances_sleep_stage(self):
        controller = FullRebootController()
        self._calibrate(controller)
        controller._calm_depth = controller._target_depth - 6.0

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=6.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=6.0)

        self.assertEqual(snapshot.direction, "flow")
        self.assertTrue(snapshot.level_completed)

    def test_full_reboot_stale_metrics_pause_progression(self):
        controller = FullRebootController()
        self._calibrate(controller)
        start_depth = controller.view_state["calm_depth"]

        snapshot = controller.update_gameplay(49.0, 52.0, valid=False, stale=True, elapsed_seconds=2.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_depth, controller.view_state["calm_depth"])

    def test_full_reboot_focus_spikes_raise_restlessness(self):
        controller = FullRebootController()
        self._calibrate(controller)
        start_restlessness = controller.view_state["restlessness"]

        controller.update_gameplay(53.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)
        snapshot = controller.update_gameplay(53.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertGreater(controller.view_state["restlessness"], start_restlessness)
        self.assertIn("soften", snapshot.control_hint.lower())

    def test_space_shooter_focus_moves_ship_up_and_charges(self):
        controller = SpaceShooterController()
        self._calibrate(controller)

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(snapshot.direction, "boost")
        self.assertEqual(controller.view_state["ship_lane"], 0)
        self.assertGreater(controller.view_state["charge"], 26.0)

    def test_space_shooter_balanced_hold_fires_when_enemy_aligned(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._progress = 12.0
        controller._charge = 36.0

        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["destroyed"], 1)

    def test_jump_ball_focus_clears_obstacle(self):
        controller = JumpBallController()
        self._calibrate(controller)
        controller._progress = 15.0

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertIn(snapshot.recommended_label, {"Jump charged", "Land clean", "Preserve the combo", "Hold rhythm"})
        self.assertGreaterEqual(controller.view_state["cleared"], 1)

    def test_neuro_racer_relaxation_brakes_and_recenters(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._lane = 0
        controller._speed = 72.0

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(snapshot.direction, "brake")
        self.assertEqual(controller.view_state["lane"], 1)
        self.assertLess(controller.view_state["speed"], 72.0)

    def test_space_shooter_stale_metrics_pause_progression(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        start_progress = controller.view_state["progress"]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_progress, controller.view_state["progress"])

    def test_pattern_recall_preview_blocks_input(self):
        controller = PatternRecallController()
        self._calibrate(controller)

        snapshot = controller.update_gameplay(55.0, 48.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.phase, "preview")
        self.assertIn("preview", snapshot.control_hint.lower())

    def test_pattern_recall_chunk_retry_resets_only_current_chunk(self):
        controller = PatternRecallController()
        self._calibrate(controller)
        controller._preview_ticks = 0
        controller._selected_index = controller._sequence[0]
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller._selected_index = controller._sequence[1]
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(controller.view_state["confirmed_count"], 2)

        controller._selected_index = 6
        controller.update_gameplay(50.2, 50.1, valid=True, stale=False, elapsed_seconds=4.0)
        snapshot = controller.update_gameplay(50.2, 50.1, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertEqual(snapshot.phase, "chunk_retry")
        self.assertEqual(controller.view_state["confirmed_count"], 2)


if __name__ == "__main__":
    unittest.main()
