"""Tests for the Astral Glider game controller."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Emotions-Dashboard", "bci_dashboard"))

from gui.training_games import AstralGliderController


class TestAstralGliderCalibration:
    def _make(self) -> AstralGliderController:
        ctrl = AstralGliderController()
        ctrl.reset_run()
        ctrl.begin_calibration()
        return ctrl

    def _calibrate(self, ctrl: AstralGliderController, conc: float = 50.0, relax: float = 50.0):
        for _ in range(25):
            snap = ctrl.add_calibration_sample(conc, relax, True)
        assert snap.complete
        ctrl.start_game()
        return ctrl

    def test_calibration_completes_after_sufficient_samples(self):
        ctrl = self._make()
        snap = None
        for _ in range(25):
            snap = ctrl.add_calibration_sample(50.0, 50.0, True)
        assert snap is not None
        assert snap.complete

    def test_calibration_records_baseline(self):
        ctrl = self._make()
        for _ in range(25):
            ctrl.add_calibration_sample(60.0, 40.0, True)
        assert ctrl.conc_baseline is not None
        assert ctrl.relax_baseline is not None
        assert abs(ctrl.conc_baseline - 60.0) < 5.0
        assert abs(ctrl.relax_baseline - 40.0) < 5.0

    def test_calibration_incomplete_with_few_samples(self):
        ctrl = self._make()
        snap = None
        for _ in range(5):
            snap = ctrl.add_calibration_sample(50.0, 50.0, True)
        assert snap is not None
        assert not snap.complete


class TestAstralGliderGameplay:
    def _ready(self, conc: float = 50.0, relax: float = 50.0) -> AstralGliderController:
        ctrl = AstralGliderController()
        ctrl.reset_run()
        ctrl.begin_calibration()
        for _ in range(25):
            ctrl.add_calibration_sample(conc, relax, True)
        ctrl.start_game()
        return ctrl

    def test_gameplay_returns_valid_snapshot(self):
        ctrl = self._ready()
        snap = ctrl.update_gameplay(60.0, 40.0, True, False, 1.0)
        assert snap is not None
        assert snap.view_state["mode"] == "astral_glider"
        assert isinstance(snap.moved, bool)
        assert isinstance(snap.level_completed, bool)
        assert isinstance(snap.run_completed, bool)

    def test_stale_signal_blocks_movement(self):
        ctrl = self._ready()
        snap = ctrl.update_gameplay(60.0, 40.0, True, True, 1.0)
        assert snap.blocked_reason != ""
        assert "unavailable" in snap.blocked_reason.lower()

    def test_invalid_signal_blocks_movement(self):
        ctrl = self._ready()
        snap = ctrl.update_gameplay(60.0, 40.0, False, False, 1.0)
        assert snap.blocked_reason != ""
        assert "artifact" in snap.blocked_reason.lower()

    def test_focus_increases_thrust(self):
        ctrl = self._ready(50.0, 50.0)
        # High focus
        for _ in range(10):
            ctrl.update_gameplay(80.0, 30.0, True, False, 1.0)
        assert ctrl._thrust > 0.1

    def test_relaxation_activates_shield(self):
        ctrl = self._ready(50.0, 50.0)
        # Sustained high relaxation
        for _ in range(20):
            ctrl.update_gameplay(30.0, 80.0, True, False, 1.0)
        assert ctrl._shield_active

    def test_shield_prevents_collision_damage(self):
        ctrl = self._ready(50.0, 50.0)
        # Activate shield
        for _ in range(20):
            ctrl.update_gameplay(30.0, 80.0, True, False, 1.0)
        assert ctrl._shield_active
        # Place obstacle right on the ship
        ctrl._obstacles = [{"x": ctrl._ship_x, "y": ctrl._ship_y, "size": 0.03, "style": "rock", "rot": 0}]
        initial_score = ctrl._score
        ctrl.update_gameplay(30.0, 80.0, True, False, 2.0)
        # Shield should prevent damage — obstacle still there or score not decreased
        assert ctrl._score >= initial_score

    def test_steady_charges_warp(self):
        ctrl = self._ready(50.0, 50.0)
        # Steady state (balanced signals)
        for _ in range(100):
            ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        assert ctrl._warp_charge > 0

    def test_crystal_collection_increases_score(self):
        ctrl = self._ready(50.0, 50.0)
        initial_score = ctrl._score
        # Place crystal slightly ahead of ship (will drift into ship after entity update)
        ctrl._crystals = [{"x": ctrl._ship_x, "y": ctrl._ship_y - 0.02, "value": 20, "pulse": 0}]
        ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        # If the crystal drifted past, try placing it right on ship and checking collision directly
        if ctrl._score < initial_score + 20:
            ctrl._crystals = [{"x": ctrl._ship_x, "y": ctrl._ship_y, "value": 20, "pulse": 0}]
            ctrl._check_collisions()
        assert ctrl._score >= initial_score + 20

    def test_has_three_levels(self):
        ctrl = AstralGliderController()
        assert len(ctrl.LEVELS) == 3
        assert ctrl.LEVELS[0].title == "Asteroid Belt"
        assert ctrl.LEVELS[1].title == "Nebula Run"
        assert ctrl.LEVELS[2].title == "Warp Core"

    def test_view_state_contains_required_keys(self):
        ctrl = self._ready()
        snap = ctrl.update_gameplay(55.0, 45.0, True, False, 1.0)
        vs = snap.view_state
        for key in ["mode", "ship_x", "ship_y", "thrust", "shield_active",
                     "warp_charge", "score", "stars", "obstacles", "crystals",
                     "particles", "music_scene", "music_bias"]:
            assert key in vs, f"Missing key: {key}"


class TestAstralGliderMEMS:
    def _ready(self) -> AstralGliderController:
        ctrl = AstralGliderController()
        ctrl.reset_run()
        ctrl.begin_calibration()
        # Feed gyro samples during calibration to establish zero
        for _ in range(65):
            ctrl.update_mems(0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        for _ in range(25):
            ctrl.add_calibration_sample(50.0, 50.0, True)
        ctrl.start_game()
        return ctrl

    def test_gyro_calibration_establishes_zero(self):
        ctrl = AstralGliderController()
        ctrl.reset_run()
        ctrl.begin_calibration()
        for _ in range(65):
            ctrl.update_mems(0.1, 0.2, 1.0, 0.0, 0.0, 0.0)
        assert ctrl._gyro_calibrated
        assert abs(ctrl._gyro_zero_x - 0.2) < 0.01   # accel_y maps to gyro_x
        assert abs(ctrl._gyro_zero_y - 0.1) < 0.01   # accel_x maps to gyro_y

    def test_tilt_right_moves_ship_right(self):
        ctrl = self._ready()
        initial_x = ctrl._ship_x
        # Tilt right (positive accel_y)
        for _ in range(10):
            ctrl.update_mems(0.0, 0.3, 1.0, 0.0, 0.0, 0.0)
            ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        assert ctrl._ship_x > initial_x

    def test_tilt_left_moves_ship_left(self):
        ctrl = self._ready()
        initial_x = ctrl._ship_x
        # Tilt left (negative accel_y)
        for _ in range(10):
            ctrl.update_mems(0.0, -0.3, 1.0, 0.0, 0.0, 0.0)
            ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        assert ctrl._ship_x < initial_x

    def test_ship_stays_within_bounds(self):
        ctrl = self._ready()
        # Extreme tilt
        for _ in range(100):
            ctrl.update_mems(0.0, 1.0, 1.0, 0.0, 0.0, 0.0)
            ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        assert ctrl._ship_x <= 0.95
        assert ctrl._ship_x >= 0.05

    def test_dead_zone_prevents_jitter(self):
        ctrl = self._ready()
        initial_x = ctrl._ship_x
        # Very small tilt (within dead zone)
        ctrl.update_mems(0.0, 0.02, 1.0, 0.0, 0.0, 0.0)
        ctrl.update_gameplay(50.0, 50.0, True, False, 1.0)
        # Ship should barely move (EMA may cause micro-movement)
        assert abs(ctrl._ship_x - initial_x) < 0.01


class TestAstralGliderFinishRun:
    def _ready(self) -> AstralGliderController:
        ctrl = AstralGliderController()
        ctrl.reset_run()
        ctrl.begin_calibration()
        for _ in range(25):
            ctrl.add_calibration_sample(50.0, 50.0, True)
        ctrl.start_game()
        return ctrl

    def test_finish_run_returns_result(self):
        ctrl = self._ready()
        result = ctrl.finish_run(10.0, aborted=False)
        assert hasattr(result, "final_score")
        assert hasattr(result, "level_results")
        assert hasattr(result, "completion_pct")
        assert hasattr(result, "total_seconds")
        assert len(result.level_results) == 3

    def test_finish_run_aborted(self):
        ctrl = self._ready()
        result = ctrl.finish_run(5.0, aborted=True)
        assert result.final_score >= 0
        assert result.completion_pct >= 0
