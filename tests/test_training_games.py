import os
import sys
import time
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.training_screen import TrainingScreen  # noqa: E402
from gui.training_games import (  # noqa: E402
    BubbleBurstController,
    CalmCurrentController,
    CandyCascadeController,
    FullRebootController,
    JumpBallController,
    NeuroRacerController,
    PatternRecallController,
    ProstheticArmController,
    SpaceShooterController,
    active_training_specs,
)
from prosthetic_arm.arduino_arm import ArduinoArmController  # noqa: E402
from prosthetic_arm.capsule_backend import CapsuleMetricAdapter  # noqa: E402

APP = QApplication.instance() or QApplication([])


class TrainingGameControllerTests(unittest.TestCase):
    def _calibrate(self, controller):
        controller.begin_calibration()
        for _ in range(20):
            snapshot = controller.add_calibration_sample(50.0, 50.0, True)
        self.assertIsNotNone(snapshot.conc_baseline)
        self.assertIsNotNone(snapshot.relax_baseline)
        controller.start_game()

    def _set_bubble_board(self, controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=8):
        padded_rows = [list(row) for row in rows]
        while len(padded_rows) < controller.VISIBLE_ROWS:
            padded_rows.append([None for _ in range(len(rows[0]))])
        controller._board = padded_rows
        controller._columns = len(rows[0])
        palette = [current_bubble, next_bubble] + [cell for row in rows for cell in row if cell is not None]
        controller._palette = list(dict.fromkeys(palette))
        controller._current_bubble = current_bubble
        controller._next_bubble = next_bubble
        controller._aim_slot = aim_slot
        controller._shots_left = shots_left
        controller._score = 0
        controller._combo = 0
        controller._best_combo = 0
        controller._danger_steps = 0
        controller._ceiling_cursor = 0
        controller._spawn_cursor = 0
        controller._overlay_kind = None
        controller._overlay_title = ""
        controller._overlay_subtitle = ""
        controller._overlay_timer = 0
        controller._pending_outcome = None
        controller._launcher_zone_row = controller.VISIBLE_ROWS - 2
        controller._star_thresholds = [2000, 4000, 6000]
        controller._score_popups = []
        controller._message = ""
        controller._view_state = controller._bubble_view_state()

    def _set_cascade_board(self, controller, rows, blockers=None, specials=None):
        controller._grid_size = len(rows)
        controller._board = [cell for row in rows for cell in row]
        controller._blockers = set(blockers or set())
        controller._specials = dict(specials or {})
        controller._legal_swaps = controller._compute_legal_swaps(controller._board)
        controller._swap_index = 0
        controller._phase = "swap_select"
        controller._cascade_depth = 0
        controller._message = ""
        controller._view_state = controller._cascade_view_state()

    def _hold_arm_state(self, controller, attention, relaxation, repetitions, elapsed_seconds):
        snapshot = None
        for _ in range(repetitions):
            snapshot = controller.update_gameplay(
                attention,
                relaxation,
                valid=True,
                stale=False,
                elapsed_seconds=elapsed_seconds,
            )
        return snapshot

    def test_active_specs_include_arcade_games(self):
        active_ids = {spec.game_id for spec in active_training_specs()}
        self.assertTrue({"space_shooter", "jump_ball", "neuro_racer", "bubble_burst"}.issubset(active_ids))
        self.assertIn("full_reboot", active_ids)
        self.assertIn("candy_cascade", active_ids)
        self.assertIn("prosthetic_arm", active_ids)

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

    def test_space_shooter_focus_and_relax_move_ship(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        start_slot = controller.view_state["ship_slot"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["ship_slot"], start_slot + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["ship_slot"], start_slot)

    def test_space_shooter_steady_burst_destroys_aligned_enemy(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._enemies = [
            {"slot": controller.view_state["ship_slot"], "y": 66.0, "hp": 1, "max_hp": 1, "drop": None, "score": 60, "speed": 0.0}
        ]
        controller._projectiles = []
        controller._view_state = controller._space_view_state()

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["destroyed"], 1)
        self.assertGreater(controller.view_state["burst_ticks"], 0)

    def test_space_shooter_pickups_modify_weapon_and_hull(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._weapon_level = 1
        controller._hull = 2
        controller._pickups = [
            {"slot": controller.view_state["ship_slot"], "y": 96.0, "kind": "weapon", "ticks": 4},
            {"slot": controller.view_state["ship_slot"], "y": 90.0, "kind": "repair", "ticks": 4},
        ]

        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(controller.view_state["weapon_level"], 2)
        self.assertEqual(controller.view_state["hull"], 3)

    def test_space_shooter_wave_clear_uses_overlay_before_progression(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._enemies = []
        controller._projectiles = []
        controller._pickups = []
        controller._view_state = controller._space_view_state()

        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "wave_clear")

        for _ in range(5):
            snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["wave_index"], 1)

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

    def test_neuro_racer_focus_and_relax_steer_between_lanes(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        start_lane = controller.view_state["lane"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["lane"], start_lane + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["lane"], start_lane)

    def test_neuro_racer_steady_nitro_consumes_charge_and_raises_speed(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._nitro = 50.0
        start_speed = controller.view_state["speed"]

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(snapshot.direction, "steady")
        self.assertGreater(controller.view_state["speed"], start_speed)
        self.assertLess(controller.view_state["nitro"], 50.0)

    def test_neuro_racer_collisions_reduce_stability_and_break_streaks(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._lane = 1
        controller._streak = 3
        controller._best_streak = 3
        controller._traffic = [{"lane": 1, "gap": 12.0, "speed": 56.0, "value": 45}]
        start_stability = controller.view_state["stability"]

        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertLess(controller.view_state["stability"], start_stability)
        self.assertEqual(controller.view_state["streak"], 0)
        self.assertEqual(controller.view_state["collisions"], 1)

    def test_neuro_racer_finish_overlay_before_progression(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._distance = controller._finish_distance
        controller._view_state = controller._racer_view_state()

        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=8.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "finish")

        for _ in range(7):
            snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=8.0)

        self.assertTrue(snapshot.level_completed)
        self.assertEqual(controller.current_level_number, 2)

    def test_space_shooter_stale_metrics_pause_progression(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        start_enemies = [dict(enemy) for enemy in controller.view_state["enemies"]]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_enemies, controller.view_state["enemies"])

    def test_neuro_racer_stale_metrics_pause_progression(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        start_distance = controller.view_state["distance"]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_distance, controller.view_state["distance"])

    def test_bubble_burst_focus_and_relax_move_aim(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        start_slot = controller.view_state["aim_slot"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["aim_slot"], start_slot + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["aim_slot"], start_slot)

    def test_bubble_burst_steady_fire_consumes_shot_and_changes_board(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [[None, None, None, None, None, None] for _ in range(controller.VISIBLE_ROWS)]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=5)
        start_board = [list(row) for row in controller.view_state["board"]]

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["shots_left"], 4)
        self.assertNotEqual(start_board, controller.view_state["board"])

    def test_bubble_burst_pops_match_and_drops_floating_cluster(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [
            ["red", None, "red", None, None, None],
            [None, "green", "green", None, None, None],
            [None, "green", None, None, None, None],
        ]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=6)

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        top_rows = controller.view_state["board"][:3]
        self.assertEqual(controller.view_state["score"], 1800)
        self.assertTrue(all(cell is None for row in top_rows for cell in row))

    def test_bubble_burst_board_clear_uses_overlay_before_completion(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [
            ["red", None, "red", None, None, None],
            [None, None, None, None, None, None],
        ]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=4)

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "board_clear")

        for _ in range(7):
            snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertTrue(snapshot.level_completed)

    def test_bubble_burst_stale_metrics_pause_progression(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        start_board = [list(row) for row in controller.view_state["board"]]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_board, controller.view_state["board"])

    def test_bubble_burst_shot_exhaustion_records_incomplete_level(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [
            [None, None, None, None, None, None],
            [None, None, None, None, None, None],
        ]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=1)

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["overlay_kind"], "failure")

        for _ in range(7):
            snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        result = controller.finish_run(None, aborted=False)
        self.assertTrue(snapshot.run_completed)
        self.assertFalse(result.level_results[0].completed)

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

    def test_candy_cascade_focus_and_relax_cycle_legal_swaps(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        start_index = controller.view_state["swap_index"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["swap_index"], (start_index + 1) % controller.view_state["legal_move_count"])

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["swap_index"], start_index)

    def test_candy_cascade_confirm_swap_clears_basic_match(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["berry", "berry", "lemon", "mint", "sky"],
            ["lemon", "mint", "berry", "peach", "sky"],
            ["peach", "berry", "mint", "sky", "lemon"],
            ["mint", "lemon", "sky", "berry", "peach"],
            ["sky", "peach", "lemon", "mint", "berry"],
        ]
        self._set_cascade_board(controller, rows)
        controller._swap_index = controller._legal_swaps.index((6, 7))

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertEqual(snapshot.direction, "confirm")
        self.assertGreater(controller.view_state["score"], 0)

    def test_candy_cascade_four_match_creates_single_striped_special(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["berry", "berry", "berry", "mint", "sky"],
            ["lemon", "mint", "sky", "berry", "peach"],
            ["peach", "lemon", "mint", "sky", "berry"],
            ["mint", "peach", "lemon", "berry", "sky"],
            ["sky", "berry", "peach", "lemon", "mint"],
        ]
        self._set_cascade_board(controller, rows)
        controller._swap_index = controller._legal_swaps.index((3, 8))

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertEqual(len(controller.view_state["special_cells"]), 1)
        self.assertEqual(controller.view_state["special_cells"][8], "row")

    def test_candy_cascade_striped_special_clears_row_and_blockers(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["sky", "peach", "mint", "lemon", "berry"],
            ["lemon", "berry", "berry", "berry", "sky"],
            ["peach", "mint", "lemon", "sky", "berry"],
            ["mint", "lemon", "sky", "berry", "peach"],
            ["berry", "sky", "peach", "mint", "lemon"],
        ]
        self._set_cascade_board(controller, rows, blockers={5, 6, 7, 8, 9}, specials={7: "row"})

        controller._resolve_board(8)
        controller._view_state = controller._cascade_view_state()

        self.assertEqual(controller.view_state["remaining_blockers"], 0)
        self.assertGreater(controller.view_state["score"], 0)

    def test_candy_cascade_level_completion_requires_zero_blockers(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["berry", "berry", "lemon", "mint", "sky"],
            ["lemon", "mint", "berry", "peach", "sky"],
            ["peach", "berry", "mint", "sky", "lemon"],
            ["mint", "lemon", "sky", "berry", "peach"],
            ["sky", "peach", "lemon", "mint", "berry"],
        ]
        self._set_cascade_board(controller, rows, blockers={24})
        controller._target_score = 20
        controller._score = 20
        controller._swap_index = controller._legal_swaps.index((6, 7))

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["remaining_blockers"], 1)

    def test_candy_cascade_rebalances_when_no_legal_moves_exist(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        controller._legal_swaps = []

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertGreater(controller.view_state["legal_move_count"], 0)

    def test_candy_cascade_stale_metrics_pause_progression(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        start_board = list(controller.view_state["candies"])
        start_score = controller.view_state["score"]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_board, controller.view_state["candies"])
        self.assertEqual(start_score, controller.view_state["score"])

    def test_prosthetic_arm_sequence_advances_and_completes_level(self):
        controller = ProstheticArmController()
        self._calibrate(controller)

        self._hold_arm_state(controller, 20.0, 58.0, 4, 2.0)
        self.assertEqual(controller.view_state["sequence_index"], 1)

        self._hold_arm_state(controller, 62.0, 24.0, 7, 8.0)
        self.assertEqual(controller.view_state["sequence_index"], 2)

        self._hold_arm_state(controller, 18.0, 60.0, 7, 14.0)
        snapshot = self._hold_arm_state(controller, 64.0, 22.0, 7, 20.0)

        self.assertTrue(snapshot.level_completed)
        self.assertGreaterEqual(controller.current_level_number, 2)

    def test_prosthetic_arm_stale_metrics_pause_sequence(self):
        controller = ProstheticArmController()
        self._calibrate(controller)
        start_index = controller.view_state["sequence_index"]

        snapshot = controller.update_gameplay(62.0, 24.0, valid=False, stale=True, elapsed_seconds=3.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_index, controller.view_state["sequence_index"])

    def test_capsule_backend_normalizes_metrics_and_arduino_falls_back_without_serial(self):
        adapter = CapsuleMetricAdapter()
        captured = []
        adapter.metrics_changed.connect(captured.append)
        adapter.ingest_productivity({"concentrationScore": 54.0, "relaxationScore": 31.0})

        self.assertEqual(captured[-1]["dominant_state"], "Focused")

        with patch("prosthetic_arm.arduino_arm.SERIAL_OK", False):
            arm = ArduinoArmController()
            self.assertFalse(arm.connect_device("COM3"))

    def test_training_screen_injects_balance_panel_and_hides_shared_footer(self):
        with patch("gui.training_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            screen = TrainingScreen()
        try:
            screen._select_game("space_shooter")
            controller = screen._controller
            self._calibrate(controller)
            screen._level_started_at = time.monotonic() - 5.0

            snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=5.0)
            screen._update_gameplay_labels(snapshot)

            state = screen._space_shooter_widget._state
            self.assertIn("balance_panel", state)
            self.assertEqual(state["balance_panel"]["timer_text"], "00:47")
            self.assertIn("status", state["balance_panel"])
            self.assertTrue(screen._game_bar.isHidden())
            self.assertTrue(screen._game_status_lbl.isHidden())
            self.assertTrue(screen._game_time_lbl.isHidden())
        finally:
            screen.close()

    def test_training_screen_exposes_prosthetic_arm_flow_and_arm_lab(self):
        with patch("gui.training_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            screen = TrainingScreen()
        try:
            screen.on_productivity({"concentrationScore": 48.0, "relaxationScore": 34.0})
            screen._show_detail("prosthetic_arm")
            self.assertFalse(screen._detail_arm_lab_btn.isHidden())

            screen._show_arm_lab()
            self.assertIs(screen._stack.currentWidget(), screen._arm_lab_page)

            controller = screen._controller
            self._calibrate(controller)
            screen._level_started_at = time.monotonic() - 4.0
            snapshot = controller.update_gameplay(24.0, 58.0, valid=True, stale=False, elapsed_seconds=4.0)
            screen._update_gameplay_labels(snapshot)

            state = screen._prosthetic_arm_widget._state
            self.assertEqual(state["backend_mode"], "capsule")
            self.assertIn("target_state", state)
            self.assertIn("history", state)
        finally:
            screen.close()


if __name__ == "__main__":
    unittest.main()
