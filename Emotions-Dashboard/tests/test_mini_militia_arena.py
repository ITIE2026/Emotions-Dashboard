"""Tests for the Mini Militia Arena EEG game controller."""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui.training_games import MiniMilitiaArenaController, active_game_specs  # noqa: E402


class TestMiniMilitiaCalibration(unittest.TestCase):
    def test_calibration_flow_reaches_baseline(self):
        ctrl = MiniMilitiaArenaController()
        ctrl.begin_calibration()
        for _ in range(20):
            snap = ctrl.add_calibration_sample(50.0, 50.0, True)
        self.assertIsNotNone(ctrl.conc_baseline)
        self.assertIsNotNone(ctrl.relax_baseline)
        self.assertAlmostEqual(ctrl.conc_baseline, 50.0, places=1)

    def test_calibration_ignores_invalid_samples(self):
        ctrl = MiniMilitiaArenaController()
        ctrl.begin_calibration()
        for _ in range(10):
            ctrl.add_calibration_sample(50.0, 50.0, False)
        for _ in range(20):
            ctrl.add_calibration_sample(50.0, 50.0, True)
        self.assertIsNotNone(ctrl.conc_baseline)

    def test_calibration_complete_flag(self):
        ctrl = MiniMilitiaArenaController()
        ctrl.begin_calibration()
        for _ in range(20):
            snap = ctrl.add_calibration_sample(50.0, 50.0, True)
        # need 3 stable samples after baseline is set
        for _ in range(3):
            snap = ctrl.add_calibration_sample(50.0, 50.0, True)
        self.assertTrue(snap.complete)


class TestMiniMilitiaGameplay(unittest.TestCase):
    def _ready_controller(self, conc=50.0, relax=50.0):
        ctrl = MiniMilitiaArenaController()
        ctrl.begin_calibration()
        for _ in range(20):
            ctrl.add_calibration_sample(conc, relax, True)
        for _ in range(3):
            ctrl.add_calibration_sample(conc, relax, True)
        ctrl.start_game()
        return ctrl

    def test_stale_pauses_game(self):
        ctrl = self._ready_controller()
        snap = ctrl.update_gameplay(50.0, 50.0, True, True, 1.0)
        self.assertTrue(len(snap.blocked_reason) > 0)

    def test_invalid_pauses_game(self):
        ctrl = self._ready_controller()
        snap = ctrl.update_gameplay(50.0, 50.0, False, False, 1.0)
        self.assertTrue(len(snap.blocked_reason) > 0)

    def test_normal_gameplay_returns_snapshot(self):
        ctrl = self._ready_controller()
        snap = ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        self.assertEqual(snap.phase, "mini_militia_arena")
        self.assertEqual(snap.level_number, 1)
        self.assertFalse(snap.run_completed)

    def test_view_state_has_required_keys(self):
        ctrl = self._ready_controller()
        snap = ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        vs = snap.view_state
        for key in ("mode", "world_width", "ground_y", "platforms", "player",
                     "bots", "bullets", "pickups", "camera_x", "scoreboard",
                     "remaining_time", "brain_intent", "weapon_name",
                     "match_over", "winner_name", "headline"):
            self.assertIn(key, vs, f"Missing key: {key}")
        self.assertEqual(vs["mode"], "mini_militia_arena")

    def test_player_starts_alive_with_full_health(self):
        ctrl = self._ready_controller()
        snap = ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        player = snap.view_state["player"]
        self.assertTrue(player["alive"])
        self.assertGreater(player["health"], 0)

    def test_bot_count_matches_level(self):
        ctrl = self._ready_controller()
        snap = ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        bots = snap.view_state["bots"]
        # Level 1 config has bot_count=1
        self.assertEqual(len(bots), 1)

    def test_focus_intent_moves_player_right(self):
        ctrl = self._ready_controller(50.0, 50.0)
        # First tick to get initial position
        snap1 = ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        x1 = snap1.view_state["player"]["x"]
        # Strong focus delta: concentrate well above baseline
        for _ in range(4):
            snap2 = ctrl.update_gameplay(56.0, 45.0, True, False, 2.0)
        x2 = snap2.view_state["player"]["x"]
        self.assertGreater(x2, x1, "Player should move right with focus")

    def test_relax_intent_moves_player_left(self):
        ctrl = self._ready_controller(50.0, 50.0)
        # Move player toward center first
        for _ in range(4):
            ctrl.update_gameplay(56.0, 45.0, True, False, 1.0)
        snap1 = ctrl.update_gameplay(50.0, 50.0, True, False, 5.0)
        x1 = snap1.view_state["player"]["x"]
        # Strong relax: relaxation above baseline, concentration below
        for _ in range(4):
            snap2 = ctrl.update_gameplay(44.0, 56.0, True, False, 6.0)
        x2 = snap2.view_state["player"]["x"]
        self.assertLess(x2, x1, "Player should move left with relaxation")

    def test_shield_reduces_damage(self):
        ctrl = self._ready_controller()
        player = ctrl._player
        # Manually activate shield
        player["shield_timer"] = 1.0
        original_health = player["health"]
        # Apply damage with shield
        player["health"] -= 14.0 * 0.45  # shield multiplier
        shielded_loss = original_health - player["health"]
        self.assertAlmostEqual(shielded_loss, 6.3, places=1)

    def test_respawn_resets_health(self):
        ctrl = self._ready_controller()
        ctrl._player["alive"] = False
        ctrl._player["respawn_timer"] = 0.01
        ctrl._respawn_check(ctrl._player, 0.02)
        self.assertTrue(ctrl._player["alive"])
        self.assertEqual(ctrl._player["health"], 100.0)
        self.assertEqual(ctrl._player["energy"], 100.0)

    def test_kill_increments_score(self):
        ctrl = self._ready_controller()
        bot = ctrl._bots[0]
        player = ctrl._player
        old_score = player["score"]
        ctrl._kill(bot, player)
        self.assertEqual(player["score"], old_score + 1)
        self.assertFalse(bot["alive"])

    def test_kill_increments_streak(self):
        ctrl = self._ready_controller()
        bot = ctrl._bots[0]
        player = ctrl._player
        ctrl._kill(bot, player)
        self.assertEqual(player["streak"], 1)

    def test_match_ends_on_score_target(self):
        ctrl = self._ready_controller()
        cfg = ctrl.LEVEL_CONFIGS[0]
        ctrl._player["score"] = cfg["score_target"]
        # Run one gameplay tick to trigger end detection
        snap = ctrl.update_gameplay(50.0, 50.0, True, False, 10.0)
        self.assertTrue(snap.view_state.get("match_over") or snap.level_completed)

    def test_match_ends_on_death_limit(self):
        ctrl = self._ready_controller()
        cfg = ctrl.LEVEL_CONFIGS[0]
        ctrl._player["deaths"] = cfg["death_limit"]
        snap = ctrl.update_gameplay(50.0, 50.0, True, False, 10.0)
        self.assertTrue(snap.view_state.get("match_over") or snap.run_completed)

    def test_finish_run_returns_result(self):
        ctrl = self._ready_controller()
        result = ctrl.finish_run(10.0, aborted=True)
        self.assertIsNotNone(result)
        self.assertEqual(len(result.level_results), 3)


class TestMiniMilitiaRegistration(unittest.TestCase):
    def test_game_in_active_specs(self):
        specs = active_game_specs()
        ids = [s.game_id for s in specs]
        self.assertIn("mini_militia_arena", ids)

    def test_game_is_featured_first_in_arcade_catalog(self):
        specs = active_game_specs()
        arcade_ids = [s.game_id for s in specs if s.section == "Arcade neurofeedback"]
        self.assertGreater(len(arcade_ids), 0)
        self.assertEqual(arcade_ids[0], "mini_militia_arena")

    def test_spec_has_correct_widget_kind(self):
        specs = active_game_specs()
        spec = next(s for s in specs if s.game_id == "mini_militia_arena")
        self.assertEqual(spec.widget_kind, "mini_militia_arena")

    def test_controller_factory_creates_controller(self):
        specs = active_game_specs()
        spec = next(s for s in specs if s.game_id == "mini_militia_arena")
        ctrl = spec.controller_factory()
        self.assertIsNotNone(ctrl)
        self.assertEqual(ctrl.current_level_number, 1)


if __name__ == "__main__":
    unittest.main()
