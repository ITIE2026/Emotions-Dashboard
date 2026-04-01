"""
Multiplayer Tug of War – 2-player authoritative controller.

Player 1's concentration pulls the rope LEFT (toward P1 zone).
Player 2's concentration pulls the rope RIGHT (toward P2 zone).
No AI – purely human vs human.
"""
from __future__ import annotations

import time
from gui.eeg_game_base import (
    CALIBRATION_SAMPLES,
    READY_DELTA_THRESHOLD,
    READY_STREAK_TARGET,
    CalibrationSnapshot,
    TrainingLevel,
)

# Level tuning for multiplayer (single level, longer duration)
MP_LEVELS = [
    TrainingLevel("Head to Head", 120),
    TrainingLevel("Intensity Rising", 120),
]

LEVEL_CONFIGS = [
    {
        "capture_target": 10,
        "velocity_decay": 0.80,
        "drive_scale": 0.030,
        "force_scale": 26.0,
        "relax_penalty_scale": 10.0,
    },
    {
        "capture_target": 12,
        "velocity_decay": 0.76,
        "drive_scale": 0.035,
        "force_scale": 30.0,
        "relax_penalty_scale": 14.0,
    },
]

CAPTURE_THRESHOLD = 0.72


class MultiplayerTugOfWarController:
    """Authoritative controller for 2-player Tug of War.

    The server holds one instance.  It receives metrics from both
    players and computes the shared game state every tick.
    """

    def __init__(self, p1_name: str = "Player 1", p2_name: str = "Player 2"):
        self._p1_name = p1_name
        self._p2_name = p2_name
        self._levels = MP_LEVELS
        self._level_index = 0
        self._started_at: float | None = None

        # Per-player calibration state
        self._cal = {
            0: {"samples": [], "baseline_conc": None, "baseline_relax": None,
                "ready_streak": 0, "complete": False},
            1: {"samples": [], "baseline_conc": None, "baseline_relax": None,
                "ready_streak": 0, "complete": False},
        }

        self._reset_level_state()

    # ── Calibration (per-player) ──────────────────────────────────
    def add_calibration_sample_for(self, player_id: int, conc: float,
                                   relax: float, valid: bool) -> dict:
        cal = self._cal[player_id]
        if not valid:
            cal["ready_streak"] = 0
            return self._cal_snapshot(cal)

        if len(cal["samples"]) < CALIBRATION_SAMPLES:
            cal["samples"].append((conc, relax))

        if len(cal["samples"]) >= CALIBRATION_SAMPLES and cal["baseline_conc"] is None:
            cal["baseline_conc"] = sum(s[0] for s in cal["samples"]) / len(cal["samples"])
            cal["baseline_relax"] = sum(s[1] for s in cal["samples"]) / len(cal["samples"])

        if cal["baseline_conc"] is not None:
            ready_delta = (relax - cal["baseline_relax"]) - (conc - cal["baseline_conc"])
            if ready_delta >= READY_DELTA_THRESHOLD:
                cal["ready_streak"] += 1
            else:
                cal["ready_streak"] = 0
            cal["complete"] = cal["ready_streak"] >= READY_STREAK_TARGET

        return self._cal_snapshot(cal)

    @staticmethod
    def _cal_snapshot(cal: dict) -> dict:
        progress = min(1.0, len(cal["samples"]) / CALIBRATION_SAMPLES)
        return {
            "progress": progress,
            "sample_count": len(cal["samples"]),
            "samples_needed": CALIBRATION_SAMPLES,
            "complete": cal["complete"],
            "baseline_conc": cal["baseline_conc"],
            "baseline_relax": cal["baseline_relax"],
        }

    # ── Lifecycle ─────────────────────────────────────────────────
    def start_game(self):
        self._level_index = 0
        self._started_at = time.monotonic()
        self._reset_level_state()

    def _reset_level_state(self):
        cfg = LEVEL_CONFIGS[min(self._level_index, len(LEVEL_CONFIGS) - 1)]
        self._capture_target = cfg["capture_target"]
        self._velocity_decay = cfg["velocity_decay"]
        self._drive_scale = cfg["drive_scale"]
        self._force_scale = cfg["force_scale"]
        self._relax_penalty = cfg["relax_penalty_scale"]

        self._rope_position = 0.0
        self._rope_velocity = 0.0
        self._capture_streak = 0
        self._capture_owner: str | None = None
        self._p1_score = 0.0
        self._p2_score = 0.0
        self._p1_force = 0.0
        self._p2_force = 0.0
        self._rope_tension = 0.0
        self._arena_energy = 38.0
        self._spark_intensity = 14.0
        self._advantage_side = "neutral"
        self._message = "Focus to pull the rope to your side!"
        self._finished = False

    # ── Game tick ─────────────────────────────────────────────────
    def tick(self, p1_metrics: dict, p2_metrics: dict) -> dict:
        """Compute one game tick and return the full view_state dict."""
        elapsed = time.monotonic() - (self._started_at or time.monotonic())

        p1_conc = p1_metrics.get("concentration", 0.0)
        p1_relax = p1_metrics.get("relaxation", 0.0)
        p1_valid = p1_metrics.get("valid", False)
        p1_stale = p1_metrics.get("stale", False)

        p2_conc = p2_metrics.get("concentration", 0.0)
        p2_relax = p2_metrics.get("relaxation", 0.0)
        p2_valid = p2_metrics.get("valid", False)
        p2_stale = p2_metrics.get("stale", False)

        base1_c = self._cal[0].get("baseline_conc") or 0.0
        base1_r = self._cal[0].get("baseline_relax") or 0.0
        base2_c = self._cal[1].get("baseline_conc") or 0.0
        base2_r = self._cal[1].get("baseline_relax") or 0.0

        p1_conc_delta = p1_conc - base1_c
        p1_relax_delta = p1_relax - base1_r
        p2_conc_delta = p2_conc - base2_c
        p2_relax_delta = p2_relax - base2_r

        blocked = ""
        if p1_stale and p2_stale:
            blocked = "Both players' metrics are stale. Game paused."
        elif not p1_valid and not p2_valid:
            blocked = "Artifacts on both headbands. Game paused."

        run_completed = False
        level_completed = False

        if not blocked and not self._finished:
            # P1 focus pulls rope LEFT (negative), P2 focus pulls RIGHT (positive)
            p1_push = max(0.0, p1_conc_delta) * self._force_scale if p1_valid and not p1_stale else 0.0
            p2_push = max(0.0, p2_conc_delta) * self._force_scale if p2_valid and not p2_stale else 0.0

            # Relaxation weakens your pull (penalty)
            p1_push -= max(0.0, p1_relax_delta) * self._relax_penalty if p1_valid else 0.0
            p2_push -= max(0.0, p2_relax_delta) * self._relax_penalty if p2_valid else 0.0

            self._p1_force = max(0.0, min(100.0, p1_push))
            self._p2_force = max(0.0, min(100.0, p2_push))

            # Positive balance = rope moves toward P2 side (right)
            tug_balance = max(-1.35, min(1.35, (self._p2_force - self._p1_force) / 100.0))

            self._p1_score += self._p1_force * 0.085
            self._p2_score += self._p2_force * 0.085

            self._rope_velocity = (self._rope_velocity * self._velocity_decay) + (tug_balance * self._drive_scale)
            self._rope_position = max(-1.0, min(1.0, self._rope_position + self._rope_velocity))

            self._rope_tension = max(0.0, min(1.0,
                abs(self._rope_velocity) * 7.5 + abs(self._rope_position) * 0.35))
            self._arena_energy = max(22.0, min(100.0,
                30.0 + max(self._p1_force, self._p2_force) * 0.45 + abs(self._rope_position) * 28.0))
            self._spark_intensity = max(8.0, min(100.0,
                10.0 + self._rope_tension * 56.0 + (self._capture_streak / max(1, self._capture_target)) * 18.0))

            capture_owner = self._capture_owner_for_position()
            if capture_owner is not None:
                if capture_owner == self._capture_owner:
                    self._capture_streak += 1
                else:
                    self._capture_owner = capture_owner
                    self._capture_streak = 1
                side_name = self._p1_name if capture_owner == "player1" else self._p2_name
                self._message = f"{side_name} is capturing the rope!"
            else:
                self._capture_owner = None
                self._capture_streak = max(0, self._capture_streak - 1)

            if self._capture_streak >= self._capture_target:
                self._finished = True
                run_completed = True
                level_completed = True

            self._advantage_side = self._current_advantage()

        winner = None
        if run_completed:
            if self._capture_owner == "player1":
                winner = "player1"
                self._message = f"{self._p1_name} wins the Tug of War!"
            elif self._capture_owner == "player2":
                winner = "player2"
                self._message = f"{self._p2_name} wins the Tug of War!"
            else:
                winner = "draw"
                self._message = "It's a draw!"

        return self._build_view_state(
            message=blocked or self._message,
            run_completed=run_completed,
            winner=winner,
            elapsed=elapsed,
        )

    def _capture_owner_for_position(self) -> str | None:
        if self._rope_position <= -CAPTURE_THRESHOLD:
            return "player1"
        if self._rope_position >= CAPTURE_THRESHOLD:
            return "player2"
        return None

    def _current_advantage(self) -> str:
        if self._capture_owner is not None:
            return self._capture_owner
        if self._rope_position <= -0.12:
            return "player1"
        if self._rope_position >= 0.12:
            return "player2"
        return "neutral"

    def _build_view_state(self, *, message: str, run_completed: bool,
                          winner: str | None, elapsed: float) -> dict:
        return {
            "mode": "mp_tug_of_war",
            "headline": self._levels[self._level_index].title,
            "rope_position": self._rope_position,
            "rope_tension": self._rope_tension,
            "player_force": self._p1_force,
            "system_force": self._p2_force,
            "player1_name": self._p1_name,
            "player2_name": self._p2_name,
            "player1_force": self._p1_force,
            "player2_force": self._p2_force,
            "player1_score": int(round(self._p1_score)),
            "player2_score": int(round(self._p2_score)),
            "player_score": int(round(self._p1_score)),
            "system_score": int(round(self._p2_score)),
            "capture_progress": min(1.0, self._capture_streak / max(1.0, float(self._capture_target))),
            "advantage_side": self._advantage_side,
            "pressure_level": 50.0,
            "arena_energy": self._arena_energy,
            "spark_intensity": self._spark_intensity,
            "music_scene": "arcade",
            "music_bias": max(-1.0, min(1.0, (self._p2_force - self._p1_force) / 100.0)),
            "message": message,
            "run_completed": run_completed,
            "winner": winner,
            "elapsed_seconds": round(elapsed, 1),
        }
