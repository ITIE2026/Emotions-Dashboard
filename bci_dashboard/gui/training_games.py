"""
Registry and concrete controllers for EEG training games.
"""
from __future__ import annotations

import math

from gui.eeg_game_base import (
    CALIBRATION_SAMPLES,
    READY_DELTA_THRESHOLD,
    READY_STREAK_TARGET,
    CalibrationSnapshot,
    GameplaySnapshot,
    LevelResult,
    TrainingGameSpec,
    TrainingLevel,
    TrainingRunResult,
)
from gui.mind_maze_controller import MindMazeController
from prosthetic_arm.arm_state import ArmStateEngine, dominant_state_for_metrics, state_label


DIR_LABELS = {
    None: "Hold steady",
    "left": "Backtrack",
    "right": "Advance",
    "open": "Open",
    "neutral": "Neutral",
    "closed": "Close",
    "flow": "Flow",
    "confirm": "Confirm",
    "boost": "Boost",
    "shield": "Shield",
    "fire": "Fire",
    "jump": "Jump",
    "land": "Land",
    "steady": "Hold line",
    "brake": "Brake",
}

MEMORY_MOVE_BALANCE_THRESHOLD = 0.7
MEMORY_MOVE_DELTA_THRESHOLD = 0.1
MEMORY_CONFIRM_DEAD_ZONE = 0.35

ARCADE_BALANCE_THRESHOLD = 0.8
ARCADE_DELTA_THRESHOLD = 0.15
ARCADE_STEADY_DEAD_ZONE = 0.35


class BaseTrainingController:
    def __init__(self, levels: list[TrainingLevel]):
        self._levels = levels
        self.reset_run()

    @property
    def current_level(self) -> TrainingLevel:
        return self._levels[self._level_index]

    @property
    def current_level_number(self) -> int:
        return self._level_index + 1

    @property
    def conc_baseline(self) -> float | None:
        return self._conc_baseline

    @property
    def relax_baseline(self) -> float | None:
        return self._relax_baseline

    @property
    def view_state(self) -> dict:
        return self._view_state

    def reset_run(self) -> None:
        self._calibration_values: list[tuple[float, float]] = []
        self._ready_streak = 0
        self._conc_baseline: float | None = None
        self._relax_baseline: float | None = None
        self._level_index = 0
        self._results: list[LevelResult | None] = [None] * len(self._levels)
        self._finished = False
        self._last_intent: str | None = None
        self._intent_streak = 0
        self._view_state: dict = {}
        self._reset_level_state()

    def begin_calibration(self) -> None:
        self._calibration_values = []
        self._ready_streak = 0
        self._conc_baseline = None
        self._relax_baseline = None

    def add_calibration_sample(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
    ) -> CalibrationSnapshot:
        if not valid:
            self._ready_streak = 0
            return CalibrationSnapshot(
                progress=len(self._calibration_values) / CALIBRATION_SAMPLES,
                sample_count=len(self._calibration_values),
                samples_needed=CALIBRATION_SAMPLES,
                ready_streak=0,
                conc_baseline=self._conc_baseline,
                relax_baseline=self._relax_baseline,
                ready_delta=0.0,
                complete=False,
                status="Waiting for clean signal to calibrate.",
            )

        if len(self._calibration_values) < CALIBRATION_SAMPLES:
            self._calibration_values.append((concentration, relaxation))

        if len(self._calibration_values) >= CALIBRATION_SAMPLES and self._conc_baseline is None:
            conc_total = sum(sample[0] for sample in self._calibration_values)
            relax_total = sum(sample[1] for sample in self._calibration_values)
            self._conc_baseline = conc_total / len(self._calibration_values)
            self._relax_baseline = relax_total / len(self._calibration_values)

        progress = min(1.0, len(self._calibration_values) / CALIBRATION_SAMPLES)
        ready_delta = 0.0
        status = "Collecting baseline samples..."
        complete = False

        if self._conc_baseline is not None and self._relax_baseline is not None:
            ready_delta = (relaxation - self._relax_baseline) - (
                concentration - self._conc_baseline
            )
            if ready_delta >= READY_DELTA_THRESHOLD:
                self._ready_streak += 1
                status = "Signal stable. Hold steady to start the training."
            else:
                self._ready_streak = 0
                status = "Relax slightly more and keep the signal steady."
            complete = self._ready_streak >= READY_STREAK_TARGET

        return CalibrationSnapshot(
            progress=progress,
            sample_count=len(self._calibration_values),
            samples_needed=CALIBRATION_SAMPLES,
            ready_streak=self._ready_streak,
            conc_baseline=self._conc_baseline,
            relax_baseline=self._relax_baseline,
            ready_delta=ready_delta,
            complete=complete,
            status=status,
        )

    def start_game(self) -> None:
        self._level_index = 0
        self._results = [None] * len(self._levels)
        self._finished = False
        self._last_intent = None
        self._intent_streak = 0
        self._reset_level_state()

    def finish_run(
        self,
        current_elapsed_seconds: float | None,
        aborted: bool,
    ) -> TrainingRunResult:
        if aborted and not self._finished:
            self._record_level_result(
                completed=False,
                elapsed_seconds=current_elapsed_seconds or 0.0,
                score_override=0,
            )

        normalized_results: list[LevelResult] = []
        for index, existing in enumerate(self._results):
            if existing is None:
                level = self._levels[index]
                existing = LevelResult(
                    level_number=index + 1,
                    title=level.title,
                    completed=False,
                    elapsed_seconds=0,
                    target_seconds=level.target_seconds,
                    score=0,
                )
            normalized_results.append(existing)

        completed_count = sum(1 for item in normalized_results if item.completed)
        total_seconds = sum(item.elapsed_seconds for item in normalized_results)
        final_score = round(sum(item.score for item in normalized_results) / len(normalized_results))
        completion_pct = round((completed_count / len(normalized_results)) * 100)
        return TrainingRunResult(
            level_results=normalized_results,
            final_score=final_score,
            completion_pct=completion_pct,
            total_seconds=total_seconds,
        )

    def _stabilize_intent(self, intent: str | None) -> bool:
        if intent is None:
            self._last_intent = None
            self._intent_streak = 0
            return False
        if intent == self._last_intent:
            self._intent_streak += 1
        else:
            self._last_intent = intent
            self._intent_streak = 1
        if self._intent_streak >= 2:
            self._last_intent = None
            self._intent_streak = 0
            return True
        return False

    def _advance_level(self) -> bool:
        if self._level_index == len(self._levels) - 1:
            self._finished = True
            return True
        self._level_index += 1
        self._last_intent = None
        self._intent_streak = 0
        self._reset_level_state()
        return False

    def _record_level_result(
        self,
        completed: bool,
        elapsed_seconds: float,
        score_override: int | float | None = None,
    ) -> None:
        index = self._level_index
        if self._results[index] is not None:
            return
        level = self._levels[index]
        elapsed_int = max(0, int(round(elapsed_seconds)))
        score = 0
        if completed:
            if score_override is not None:
                score = max(20, min(100, int(round(score_override))))
            else:
                penalty = max(0, elapsed_int - level.target_seconds)
                score = max(20, 100 - penalty)
        self._results[index] = LevelResult(
            level_number=index + 1,
            title=level.title,
            completed=completed,
            elapsed_seconds=elapsed_int,
            target_seconds=level.target_seconds,
            score=score,
        )

    def _reset_level_state(self) -> None:
        raise NotImplementedError


class NeuroflowPlaceholderController(BaseTrainingController):
    LEVELS = [TrainingLevel("Neuroflow", 120)]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        self._view_state = {
            "mode": "neuroflow",
            "message": "Neuroflow uses its own embedded launcher page.",
        }

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        return GameplaySnapshot(
            level_number=1,
            phase="neuroflow",
            phase_label="Neuroflow",
            recommended_direction=None,
            recommended_label="",
            control_hint="Use the Neuroflow launcher page instead of the standard gameplay shell.",
            direction=None,
            direction_label=DIR_LABELS[None],
            moved=False,
            blocked_reason="",
            conc_delta=0.0,
            relax_delta=0.0,
            balance=0.0,
            level_completed=False,
            run_completed=False,
            view_state=self._view_state,
        )


class CalmCurrentController(BaseTrainingController):
    LEVELS = [
        TrainingLevel("Level 1", 45),
        TrainingLevel("Level 2", 55),
        TrainingLevel("Level 3", 65),
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        self._distance = 0.0
        self._target_distance = 92.0 + (self._level_index * 18.0)
        self._turbulence = 0.0
        self._calm_streak = 0
        self._best_streak = 0
        self._view_state = {
            "mode": "current",
            "distance": self._distance,
            "target_distance": self._target_distance,
            "turbulence": self._turbulence,
            "calm_streak": self._calm_streak,
            "best_streak": self._best_streak,
            "music_scene": "calm_flow",
            "music_bias": 0.0,
            "serenity": 56.0,
            "restlessness": 18.0,
            "message": "",
        }

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        balance = conc_delta - relax_delta
        blocked_reason = ""
        direction = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = "Relax to deepen the current. Concentration spikes make the water choppy."

        if stale:
            blocked_reason = "Metrics are stale. Current paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Current paused."
        else:
            calm_bias = relax_delta - conc_delta
            if calm_bias >= 0.8 and relax_delta >= 0.1:
                direction = "flow"
                if self._stabilize_intent(direction):
                    self._distance += 5.0 + calm_bias
                    self._turbulence = max(0.0, self._turbulence - 1.6)
                    self._calm_streak += 1
                    moved = True
            elif balance >= 0.8 and conc_delta >= 0.2:
                direction = "storm"
                if self._stabilize_intent(direction):
                    self._distance += 1.5
                    self._turbulence = min(10.0, self._turbulence + 2.0)
                    self._calm_streak = 0
                    moved = True
            else:
                self._stabilize_intent(None)
                self._distance += 2.2
                self._turbulence = max(0.0, self._turbulence - 0.4)
                self._calm_streak = max(0, self._calm_streak - 1)

            self._best_streak = max(self._best_streak, self._calm_streak)
            self._distance = min(self._target_distance, self._distance)

            if self._distance >= self._target_distance:
                serenity = 100 - (self._turbulence * 6.0)
                streak_bonus = min(20.0, self._best_streak * 2.0)
                time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
                score = serenity + streak_bonus - time_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

        view_state = {
            "mode": "current",
            "distance": self._distance,
            "target_distance": self._target_distance,
            "turbulence": self._turbulence,
            "calm_streak": self._calm_streak,
            "best_streak": self._best_streak,
            "music_scene": "calm_flow",
            "music_bias": relax_delta - conc_delta,
            "serenity": max(0.0, min(100.0, 68.0 - (self._turbulence * 4.0) + (self._best_streak * 2.5))),
            "restlessness": max(0.0, min(100.0, self._turbulence * 9.0)),
            "message": blocked_reason,
        }
        self._view_state = view_state
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase="current",
            phase_label="Calm Flow",
            recommended_direction=direction,
            recommended_label="Deep Calm",
            control_hint=blocked_reason or control_hint,
            direction=direction,
            direction_label=DIR_LABELS[direction],
            moved=moved,
            blocked_reason=blocked_reason,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            balance=balance,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=view_state,
        )


class FullRebootController(BaseTrainingController):
    LEVELS = [
        TrainingLevel("Breathe Down", 300),
        TrainingLevel("Body Drift", 480),
        TrainingLevel("Sleep Descent", 720),
    ]
    CONFIGS = [
        {"target_depth": 92.0, "scene": "breathe_down", "hint": "Relax your jaw, lengthen the exhale, and let the rings open slowly."},
        {"target_depth": 112.0, "scene": "body_drift", "hint": "Let the body feel heavy. Relaxed control should melt the stage forward."},
        {"target_depth": 132.0, "scene": "sleep_descent", "hint": "Keep the signal quiet and calm. Deep relaxation should dim the bright layers."},
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._target_depth = config["target_depth"]
        self._scene = config["scene"]
        self._stage_hint = config["hint"]
        self._calm_depth = 0.0
        self._serenity = 48.0 + (self._level_index * 8.0)
        self._restlessness = max(6.0, 30.0 - (self._level_index * 6.0))
        self._steady_hold = 0
        self._best_hold = 0
        self._breath_phase = 0.0
        self._view_state = self._sleep_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        balance = conc_delta - relax_delta
        calm_bias = relax_delta - conc_delta
        blocked_reason = ""
        direction = None
        moved = False
        level_completed = False
        run_completed = False
        self._breath_phase = (math.sin(elapsed_seconds / 3.4) + 1.0) / 2.0
        control_hint = self._stage_hint

        if stale:
            blocked_reason = "Metrics are stale. Wind-down paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Wind-down paused."
        else:
            if calm_bias >= 0.8 and relax_delta >= 0.1:
                direction = "flow"
                if self._stabilize_intent(direction):
                    gain = 4.4 + calm_bias + (self._steady_hold * 0.12)
                    self._calm_depth += gain
                    self._serenity = min(100.0, self._serenity + 4.6 + calm_bias)
                    self._restlessness = max(0.0, self._restlessness - 4.2)
                    self._steady_hold += 1
                    moved = True
            elif abs(balance) <= 0.35:
                direction = "steady"
                if self._stabilize_intent(direction):
                    self._calm_depth += 2.8
                    self._serenity = min(100.0, self._serenity + 2.1)
                    self._restlessness = max(0.0, self._restlessness - 1.8)
                    self._steady_hold += 1
                    moved = True
            elif balance >= 0.8 and conc_delta >= 0.2:
                self._stabilize_intent(None)
                self._calm_depth += 0.6
                self._serenity = max(0.0, self._serenity - 2.8)
                self._restlessness = min(100.0, self._restlessness + 4.0)
                self._steady_hold = 0
                control_hint = "Soften the focus. Relaxation should feel heavier than concentration here."
            else:
                self._stabilize_intent(None)
                self._calm_depth += 1.4
                self._serenity = min(100.0, self._serenity + 0.4)
                self._restlessness = max(0.0, self._restlessness - 0.7)
                self._steady_hold = max(0, self._steady_hold - 1)

            self._best_hold = max(self._best_hold, self._steady_hold)
            self._calm_depth = min(self._target_depth, self._calm_depth)

            if self._calm_depth >= self._target_depth:
                serenity_score = self._serenity * 0.42
                hold_bonus = min(24.0, self._best_hold * 2.6)
                restlessness_penalty = self._restlessness * 0.9
                time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
                score = 42 + serenity_score + hold_bonus - restlessness_penalty - time_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

        self._view_state = self._sleep_view_state(message=blocked_reason, music_bias=calm_bias)
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase=self._scene,
            phase_label=self.current_level.title,
            recommended_direction=direction,
            recommended_label=self._recommended_sleep_label(),
            control_hint=blocked_reason or control_hint,
            direction=direction,
            direction_label=DIR_LABELS.get(direction, "Hold steady"),
            moved=moved,
            blocked_reason=blocked_reason,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            balance=balance,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=self._view_state,
        )

    def _recommended_sleep_label(self) -> str:
        if self._scene == "breathe_down":
            return "Slow exhale"
        if self._scene == "body_drift":
            return "Soften body"
        return "Drift deeper"

    def _sleep_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "full_reboot",
            "headline": self.current_level.title,
            "calm_depth": self._calm_depth,
            "target_depth": self._target_depth,
            "serenity": self._serenity,
            "restlessness": self._restlessness,
            "steady_hold": self._steady_hold,
            "best_hold": self._best_hold,
            "breath_phase": self._breath_phase,
            "music_scene": self._scene,
            "music_bias": max(-1.0, min(1.0, music_bias / 3.0)),
            "message": message,
        }


class ArcadeTrainingController(BaseTrainingController):
    def _arcade_intent(self, conc_delta: float, relax_delta: float) -> str | None:
        balance = conc_delta - relax_delta
        if balance >= ARCADE_BALANCE_THRESHOLD and conc_delta >= ARCADE_DELTA_THRESHOLD:
            return "focus"
        if balance <= -ARCADE_BALANCE_THRESHOLD and relax_delta >= ARCADE_DELTA_THRESHOLD:
            return "relax"
        if abs(balance) <= ARCADE_STEADY_DEAD_ZONE:
            return "steady"
        return None

    def _arcade_snapshot(
        self,
        *,
        phase: str,
        phase_label: str,
        direction: str | None,
        blocked_reason: str,
        control_hint: str,
        conc_delta: float,
        relax_delta: float,
        moved: bool,
        level_completed: bool,
        run_completed: bool,
        recommended_label: str,
    ) -> GameplaySnapshot:
        balance = conc_delta - relax_delta
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase=phase,
            phase_label=phase_label,
            recommended_direction=direction,
            recommended_label=recommended_label,
            control_hint=blocked_reason or control_hint,
            direction=direction,
            direction_label=DIR_LABELS.get(direction, "Hold steady"),
            moved=moved,
            blocked_reason=blocked_reason,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            balance=balance,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=self._view_state,
        )


class SpaceShooterController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Sector 1", 52),
        TrainingLevel("Sector 2", 62),
        TrainingLevel("Sector 3", 72),
    ]
    CONFIGS = [
        {
            "star_thresholds": [280, 520, 760],
            "wave_speed": 6.4,
            "waves": [
                [(1, -4.0, 1, None, 60), (3, -18.0, 1, None, 60), (5, -32.0, 1, "repair", 70)],
                [(2, -8.0, 1, None, 70), (4, -20.0, 1, "weapon", 80), (2, -34.0, 1, None, 70), (4, -46.0, 1, None, 70)],
                [(1, -10.0, 2, None, 120), (3, -22.0, 1, None, 80), (5, -34.0, 2, None, 120)],
            ],
        },
        {
            "star_thresholds": [360, 640, 920],
            "wave_speed": 7.2,
            "waves": [
                [(0, -6.0, 1, None, 70), (3, -20.0, 1, None, 70), (6, -34.0, 1, None, 70), (3, -48.0, 2, "weapon", 120)],
                [(1, -8.0, 1, None, 80), (2, -18.0, 1, None, 80), (4, -28.0, 1, None, 80), (5, -38.0, 1, "repair", 90), (3, -54.0, 2, None, 130)],
                [(2, -10.0, 2, None, 140), (3, -26.0, 3, None, 180), (4, -42.0, 2, None, 140)],
            ],
        },
        {
            "star_thresholds": [440, 760, 1080],
            "wave_speed": 8.0,
            "waves": [
                [(1, -4.0, 1, None, 80), (3, -16.0, 1, None, 80), (5, -28.0, 1, None, 80), (3, -40.0, 2, None, 130)],
                [(0, -8.0, 1, None, 90), (2, -20.0, 2, None, 120), (4, -32.0, 2, "weapon", 120), (6, -44.0, 1, None, 90)],
                [(1, -10.0, 2, None, 140), (3, -24.0, 3, "repair", 200), (5, -38.0, 2, None, 140), (3, -56.0, 3, None, 220)],
            ],
        },
    ]
    FIELD_WIDTH = 7
    FIELD_HEIGHT = 120.0
    SHIP_Y = 104.0

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._star_thresholds = list(config["star_thresholds"])
        self._wave_speed = float(config["wave_speed"])
        self._wave_scripts = config["waves"]
        self._wave_index = 0
        self._wave_count = len(self._wave_scripts)
        self._ship_slot = self.FIELD_WIDTH // 2
        self._weapon_level = 1
        self._burst_ticks = 0
        self._hull = 4
        self._score = 0
        self._score_popups: list[dict] = []
        self._shots_fired = 0
        self._destroyed = 0
        self._pickups_collected = 0
        self._hits_taken = 0
        self._wave_score = 0
        self._streak = 0
        self._best_streak = 0
        self._overlay_kind: str | None = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_timer = 0
        self._pending_outcome: str | None = None
        self._message = "Glide the ship, keep the burst ready, and clear every wave."
        self._enemies: list[dict] = []
        self._projectiles: list[dict] = []
        self._pickups: list[dict] = []
        self._explosions: list[dict] = []
        self._spawn_wave(self._wave_index)
        self._view_state = self._space_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = "Concentrate to drift right, relax to drift left, and hold steady to trigger a burst volley."

        if self._overlay_kind is not None:
            level_completed, run_completed = self._tick_overlay(elapsed_seconds)
        elif stale:
            blocked_reason = "Metrics are stale. Space Shooter paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Space Shooter paused."
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                if self._stabilize_intent(intent):
                    self._ship_slot = min(self.FIELD_WIDTH - 1, self._ship_slot + 1)
                    self._message = "Shifted into the right corridor."
                    action = "right"
                    moved = True
            elif intent == "relax":
                if self._stabilize_intent(intent):
                    self._ship_slot = max(0, self._ship_slot - 1)
                    self._message = "Drifted back toward the left."
                    action = "left"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    self._burst_ticks = max(self._burst_ticks, 4)
                    self._message = "Burst cannons engaged."
                    action = "fire"
                    moved = True
            else:
                self._stabilize_intent(None)

            self._spawn_auto_fire()
            self._advance_projectiles()
            self._advance_pickups()
            self._advance_enemies()
            self._tick_effects()
            if self._hull <= 0 and self._overlay_kind is None:
                self._start_failure_overlay("Hull breached before the next wave.")
            elif not self._enemies and self._overlay_kind is None:
                self._start_wave_overlay()

        self._view_state = self._space_view_state(message=blocked_reason, music_bias=relax_delta - conc_delta)
        recommended_label = self._space_recommendation(action)
        return self._arcade_snapshot(
            phase="space_shooter",
            phase_label="Space Shooter",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _spawn_wave(self, wave_index: int) -> None:
        self._enemies = []
        for slot, y_pos, hp, drop, score in self._wave_scripts[wave_index]:
            self._enemies.append(
                {
                    "slot": slot,
                    "y": y_pos,
                    "hp": hp,
                    "max_hp": hp,
                    "drop": drop,
                    "score": score,
                    "speed": self._wave_speed + (0.35 * max(0, hp - 1)),
                }
            )
        self._projectiles = []
        self._pickups = []
        self._explosions = []
        self._wave_score = 0

    def _tick_overlay(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._tick_effects()
        if self._overlay_timer > 0:
            self._overlay_timer -= 1
        if self._overlay_timer > 0:
            return False, False

        outcome = self._pending_outcome
        self._overlay_kind = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._pending_outcome = None
        if outcome == "wave":
            self._wave_index += 1
            self._message = f"Wave {self._wave_index + 1} incoming."
            self._spawn_wave(self._wave_index)
            return False, False
        if outcome == "failure":
            self._record_level_result(False, elapsed_seconds, score_override=0)
            self._finished = True
            return False, True
        if outcome == "level_complete":
            time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
            score = (
                46
                + min(32.0, self._score / 28.0)
                + (self._hull * 6.0)
                + min(16.0, self._best_streak * 2.0)
                - (self._hits_taken * 5.0)
                - time_penalty
            )
            self._record_level_result(True, elapsed_seconds, score_override=score)
            level_completed = True
            run_completed = self._advance_level()
            return level_completed, run_completed
        return False, False

    def _spawn_auto_fire(self) -> None:
        slots = {self._ship_slot}
        if self._weapon_level >= 2:
            slots.add(max(0, self._ship_slot - 1))
        if self._weapon_level >= 3:
            slots.add(min(self.FIELD_WIDTH - 1, self._ship_slot + 1))
        if self._burst_ticks > 0:
            slots.add(max(0, self._ship_slot - 1))
            slots.add(min(self.FIELD_WIDTH - 1, self._ship_slot + 1))
            power = 2
            self._burst_ticks -= 1
        else:
            power = 1
        for slot in sorted(slots):
            self._projectiles.append({"slot": slot, "y": self.SHIP_Y - 10.0, "power": power})
            self._shots_fired += 1

    def _advance_projectiles(self) -> None:
        survivors = []
        for projectile in self._projectiles:
            projectile["y"] -= 15.0
            target = None
            for enemy in self._enemies:
                if enemy["slot"] == projectile["slot"] and abs(enemy["y"] - projectile["y"]) <= 8.0:
                    target = enemy
                    break
            if target is not None:
                target["hp"] -= projectile["power"]
                if target["hp"] <= 0:
                    self._destroy_enemy(target)
                continue
            if projectile["y"] > -10.0:
                survivors.append(projectile)
        self._projectiles = survivors

    def _destroy_enemy(self, enemy: dict) -> None:
        if enemy not in self._enemies:
            return
        self._enemies.remove(enemy)
        self._destroyed += 1
        self._wave_score += int(enemy["score"])
        self._score += int(enemy["score"])
        self._streak += 1
        self._best_streak = max(self._best_streak, self._streak)
        self._explosions.append({"slot": enemy["slot"], "y": enemy["y"], "ticks": 5})
        self._score_popups.append({"slot": enemy["slot"], "y": enemy["y"], "text": f"+{int(enemy['score'])}", "ticks": 6})
        if enemy["drop"] is not None:
            self._pickups.append({"slot": enemy["slot"], "y": enemy["y"], "kind": enemy["drop"], "ticks": 18})

    def _advance_pickups(self) -> None:
        survivors = []
        for pickup in self._pickups:
            pickup["y"] += 7.0
            pickup["ticks"] = max(0, pickup["ticks"] - 1)
            if pickup["slot"] == self._ship_slot and abs(pickup["y"] - self.SHIP_Y) <= 9.0:
                self._collect_pickup(pickup["kind"])
                continue
            if pickup["y"] <= self.FIELD_HEIGHT + 10.0 and pickup["ticks"] > 0:
                survivors.append(pickup)
        self._pickups = survivors

    def _collect_pickup(self, kind: str) -> None:
        self._pickups_collected += 1
        self._score += 25
        self._score_popups.append({"slot": self._ship_slot, "y": self.SHIP_Y - 12.0, "text": "+25", "ticks": 5})
        if kind == "weapon":
            self._weapon_level = min(3, self._weapon_level + 1)
            self._message = "Weapon upgrade collected."
        else:
            self._hull = min(4, self._hull + 1)
            self._message = "Hull repair collected."

    def _advance_enemies(self) -> None:
        survivors = []
        for enemy in self._enemies:
            enemy["y"] += enemy["speed"]
            if enemy["y"] >= self.SHIP_Y - 4.0:
                if enemy["slot"] == self._ship_slot:
                    self._hull = max(0, self._hull - 1)
                    self._hits_taken += 1
                    self._streak = 0
                    self._explosions.append({"slot": enemy["slot"], "y": self.SHIP_Y - 8.0, "ticks": 6})
                    self._message = "Incoming hit. Recover and clear the lane."
                    continue
                if enemy["y"] <= self.FIELD_HEIGHT + 10.0:
                    continue
            if enemy["y"] <= self.FIELD_HEIGHT + 8.0:
                survivors.append(enemy)
        self._enemies = survivors

    def _tick_effects(self) -> None:
        for group_name in ("_explosions", "_score_popups"):
            trimmed = []
            for item in getattr(self, group_name):
                updated = dict(item)
                updated["ticks"] = max(0, int(updated.get("ticks", 0)) - 1)
                updated["y"] = float(updated.get("y", 0.0)) - 1.5
                if updated["ticks"] > 0:
                    trimmed.append(updated)
            setattr(self, group_name, trimmed)

    def _start_wave_overlay(self) -> None:
        if self._wave_index < self._wave_count - 1:
            self._overlay_kind = "wave_clear"
            self._overlay_title = f"Wave {self._wave_index + 1} cleared"
            self._overlay_subtitle = "Next formation sliding in."
            self._overlay_timer = 5
            self._pending_outcome = "wave"
            self._message = self._overlay_title
            return
        self._overlay_kind = "level_complete"
        self._overlay_title = "Sector cleared"
        self._overlay_subtitle = "Star corridor secured."
        self._overlay_timer = 7
        self._pending_outcome = "level_complete"
        self._message = self._overlay_title

    def _start_failure_overlay(self, subtitle: str) -> None:
        self._overlay_kind = "failure"
        self._overlay_title = "Ship down"
        self._overlay_subtitle = subtitle
        self._overlay_timer = 7
        self._pending_outcome = "failure"
        self._message = subtitle

    def _space_recommendation(self, action: str | None) -> str:
        if action == "right":
            return "Slide right"
        if action == "left":
            return "Slide left"
        if action == "fire":
            return "Burst volley"
        for enemy in self._enemies:
            lane_diff = enemy["slot"] - self._ship_slot
            if abs(lane_diff) <= 1:
                if lane_diff > 0:
                    return "Track the right flank"
                if lane_diff < 0:
                    return "Drift left for cover"
                return "Hold steady to burst"
        return "Read the next wave"

    def _space_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        star_ceiling = max(1.0, float(self._star_thresholds[-1]))
        return {
            "mode": "space_shooter",
            "corridor_width": self.FIELD_WIDTH,
            "field_height": self.FIELD_HEIGHT,
            "ship_slot": self._ship_slot,
            "ship_y": self.SHIP_Y,
            "weapon_level": self._weapon_level,
            "burst_ticks": self._burst_ticks,
            "hull": self._hull,
            "score": self._score,
            "star_progress": max(0.0, min(1.0, self._score / star_ceiling)),
            "star_thresholds": list(self._star_thresholds),
            "streak": self._streak,
            "best_streak": self._best_streak,
            "shots_fired": self._shots_fired,
            "destroyed": self._destroyed,
            "pickups_collected": self._pickups_collected,
            "wave_index": self._wave_index,
            "wave_count": self._wave_count,
            "enemies": [dict(enemy) for enemy in self._enemies],
            "projectiles": [dict(projectile) for projectile in self._projectiles],
            "pickups": [dict(pickup) for pickup in self._pickups],
            "explosions": [dict(explosion) for explosion in self._explosions],
            "score_popups": [dict(popup) for popup in self._score_popups],
            "overlay_kind": self._overlay_kind,
            "overlay_title": self._overlay_title,
            "overlay_subtitle": self._overlay_subtitle,
            "overlay_timer": self._overlay_timer,
            "menu_button_rect": [18, 18, 54, 42],
            "music_scene": "space_arcade",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 56.0 + (self._hull * 8.0) + (self._best_streak * 2.0))),
            "restlessness": max(0.0, min(100.0, 22.0 + (self._hits_taken * 16.0))),
            "message": message or self._message,
        }


class JumpBallController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Run 1", 45),
        TrainingLevel("Run 2", 55),
        TrainingLevel("Run 3", 65),
    ]
    CONFIGS = [
        {"track_length": 92.0, "obstacles": [(18.0, 28.0), (36.0, 46.0), (54.0, 38.0), (74.0, 54.0)]},
        {"track_length": 108.0, "obstacles": [(16.0, 32.0), (30.0, 52.0), (46.0, 40.0), (64.0, 62.0), (86.0, 48.0)]},
        {
            "track_length": 124.0,
            "obstacles": [(14.0, 36.0), (28.0, 58.0), (42.0, 44.0), (58.0, 68.0), (78.0, 52.0), (100.0, 72.0)],
        },
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._track_length = config["track_length"]
        self._progress = 0.0
        self._ball_height = 18.0
        self._combo = 0
        self._best_combo = 0
        self._cleared = 0
        self._misses = 0
        self._obstacles = [
            {"progress_mark": mark, "required_height": height, "status": "active"}
            for mark, height in config["obstacles"]
        ]
        self._view_state = self._jump_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = (
            "Concentrate to build jump height, relax to settle back to the track, and hold steady to protect your combo."
        )

        if stale:
            blocked_reason = "Metrics are stale. Runner paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Runner paused."
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                self._progress += 4.2 + min(0.8, self._combo * 0.06)
                self._ball_height = min(100.0, self._ball_height + 12.0)
                if self._stabilize_intent(intent):
                    self._ball_height = min(100.0, self._ball_height + 16.0)
                    action = "jump"
                    moved = True
            elif intent == "relax":
                self._progress += 3.6
                self._ball_height = max(0.0, self._ball_height - 12.0)
                if self._stabilize_intent(intent):
                    self._ball_height = max(0.0, self._ball_height - 12.0)
                    action = "land"
                    moved = True
            elif intent == "steady":
                self._progress += 4.5 + min(1.0, self._combo * 0.08)
                if self._stabilize_intent(intent):
                    action = "steady"
                    moved = True
            else:
                self._stabilize_intent(None)
                self._progress += 3.4

            gravity = 2.0 if intent == "focus" else 7.5
            self._ball_height = max(0.0, self._ball_height - gravity)
            self._resolve_obstacles()
            self._progress = min(self._track_length, self._progress)

            if self._progress >= self._track_length:
                total_obstacles = max(1, len(self._obstacles))
                clear_ratio = self._cleared / total_obstacles
                combo_bonus = min(18.0, self._best_combo * 2.4)
                miss_penalty = self._misses * 6.0
                time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
                score = 48 + (clear_ratio * 36.0) + combo_bonus - miss_penalty - time_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

        self._view_state = self._jump_view_state(message=blocked_reason, music_bias=relax_delta - conc_delta)
        recommended_label = self._jump_recommendation(action)
        return self._arcade_snapshot(
            phase="jump_ball",
            phase_label="Jump Ball",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _resolve_obstacles(self) -> None:
        for obstacle in self._obstacles:
            if obstacle["status"] != "active":
                continue
            if obstacle["progress_mark"] > self._progress:
                continue
            if self._ball_height >= obstacle["required_height"]:
                obstacle["status"] = "cleared"
                self._cleared += 1
                self._combo += 1
                self._best_combo = max(self._best_combo, self._combo)
            else:
                obstacle["status"] = "missed"
                self._misses += 1
                self._combo = 0
                self._ball_height = max(0.0, self._ball_height - 12.0)
                self._progress = max(0.0, self._progress - 1.8)

    def _jump_recommendation(self, action: str | None) -> str:
        if action == "jump":
            return "Jump charged"
        if action == "land":
            return "Settle the landing"
        if action == "steady":
            return "Preserve the combo"
        for obstacle in self._obstacles:
            if obstacle["status"] != "active":
                continue
            distance = obstacle["progress_mark"] - self._progress
            if distance <= 16.0:
                if self._ball_height + 8.0 < obstacle["required_height"]:
                    return "Build jump"
                if self._ball_height > obstacle["required_height"] + 14.0:
                    return "Land clean"
                return "Hold rhythm"
            break
        return "Stay smooth"

    def _jump_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "jump_ball",
            "progress": self._progress,
            "track_length": self._track_length,
            "ball_height": self._ball_height,
            "combo": self._combo,
            "best_combo": self._best_combo,
            "cleared": self._cleared,
            "misses": self._misses,
            "music_scene": "jump_flow",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 58.0 + (self._best_combo * 4.0) - (self._misses * 10.0))),
            "restlessness": max(0.0, min(100.0, 18.0 + (self._misses * 12.0))),
            "obstacles": [dict(obstacle) for obstacle in self._obstacles if obstacle["status"] == "active"],
            "message": message,
        }


class NeuroRacerController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Track 1", 54),
        TrainingLevel("Track 2", 64),
        TrainingLevel("Track 3", 74),
    ]
    CONFIGS = [
        {
            "finish_distance": 980.0,
            "base_speed": 60.0,
            "star_thresholds": [260, 440, 620],
            "traffic": [
                (0.0, 1, 190.0, 54.0, 45),
                (110.0, 2, 210.0, 56.0, 55),
                (220.0, 0, 220.0, 53.0, 55),
                (360.0, 1, 210.0, 57.0, 65),
                (520.0, 2, 200.0, 58.0, 70),
                (710.0, 0, 210.0, 55.0, 75),
                (820.0, 1, 230.0, 52.0, 90),
            ],
        },
        {
            "finish_distance": 1180.0,
            "base_speed": 62.0,
            "star_thresholds": [320, 560, 780],
            "traffic": [
                (0.0, 1, 190.0, 55.0, 50),
                (90.0, 0, 205.0, 57.0, 55),
                (190.0, 2, 215.0, 58.0, 60),
                (300.0, 1, 225.0, 54.0, 70),
                (410.0, 0, 215.0, 60.0, 80),
                (540.0, 2, 210.0, 59.0, 80),
                (710.0, 1, 225.0, 53.0, 95),
                (860.0, 0, 220.0, 56.0, 95),
                (980.0, 2, 230.0, 54.0, 110),
            ],
        },
        {
            "finish_distance": 1340.0,
            "base_speed": 64.0,
            "star_thresholds": [380, 660, 920],
            "traffic": [
                (0.0, 1, 185.0, 56.0, 55),
                (80.0, 2, 198.0, 57.0, 60),
                (165.0, 0, 205.0, 58.0, 65),
                (250.0, 1, 215.0, 55.0, 75),
                (360.0, 2, 205.0, 59.0, 85),
                (500.0, 0, 215.0, 58.0, 85),
                (680.0, 1, 225.0, 54.0, 100),
                (830.0, 2, 214.0, 60.0, 105),
                (980.0, 0, 218.0, 59.0, 105),
                (1120.0, 1, 240.0, 55.0, 130),
            ],
        },
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._finish_distance = float(config["finish_distance"])
        self._base_speed = float(config["base_speed"])
        self._star_thresholds = list(config["star_thresholds"])
        self._traffic_schedule = [
            {
                "spawn_at": spawn_at,
                "lane": lane,
                "gap": gap,
                "speed": speed,
                "value": value,
            }
            for spawn_at, lane, gap, speed, value in config["traffic"]
        ]
        self._traffic: list[dict] = []
        self._distance = 0.0
        self._lane = 1
        self._speed = self._base_speed
        self._stability = 100.0
        self._nitro = 42.0
        self._nitro_ticks = 0
        self._line_lock_ticks = 0
        self._score = 0
        self._overtakes = 0
        self._collisions = 0
        self._streak = 0
        self._best_streak = 0
        self._effects: list[dict] = []
        self._overlay_kind: str | None = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_timer = 0
        self._pending_outcome: str | None = None
        self._message = "Thread the sky ramp, steer through traffic, and save nitro for clear runs."
        self._view_state = self._racer_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = "Concentrate to steer right, relax to steer left, and hold steady to trigger nitro or lock the line."

        if self._overlay_kind is not None:
            level_completed, run_completed = self._tick_overlay(elapsed_seconds)
        elif stale:
            blocked_reason = "Metrics are stale. Neuro Racer paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Neuro Racer paused."
        else:
            self._spawn_traffic()
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                if self._stabilize_intent(intent):
                    self._lane = min(2, self._lane + 1)
                    self._speed = min(96.0, self._speed + 3.5)
                    self._message = "Cutting into the right lane."
                    action = "right"
                    moved = True
            elif intent == "relax":
                if self._stabilize_intent(intent):
                    self._lane = max(0, self._lane - 1)
                    self._speed = max(38.0, self._speed - 4.5)
                    self._stability = min(100.0, self._stability + 3.0)
                    self._message = "Settled left to reset the line."
                    action = "left"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    action = "steady"
                    moved = True
                    if self._nitro >= 30.0:
                        self._nitro = max(0.0, self._nitro - 30.0)
                        self._nitro_ticks = 4
                        self._speed = min(100.0, self._speed + 10.0)
                        self._effects.append({"lane": self._lane, "gap": 32.0, "kind": "nitro", "ticks": 5})
                        self._message = "Nitro engaged."
                    else:
                        self._line_lock_ticks = 3
                        self._stability = min(100.0, self._stability + 4.0)
                        self._message = "Stable racing line locked."
            else:
                self._stabilize_intent(None)

            if self._nitro_ticks > 0:
                self._speed = min(100.0, self._speed + 4.0)
                self._nitro_ticks -= 1
            elif self._line_lock_ticks > 0:
                self._line_lock_ticks -= 1
                self._speed = min(92.0, self._speed + 1.2)
                self._stability = min(100.0, self._stability + 1.0)
            elif self._speed > self._base_speed:
                self._speed -= 1.6
            elif self._speed < self._base_speed:
                self._speed += 1.0

            self._nitro = min(100.0, self._nitro + 0.9 + min(1.2, self._best_streak * 0.08))
            self._distance = min(self._finish_distance, self._distance + (self._speed * 2.15))
            self._advance_traffic()
            self._tick_effects()

            if self._stability <= 0 and self._overlay_kind is None:
                self._start_failure_overlay("The racer lost stability on the sky ramp.")
            elif self._distance >= self._finish_distance and self._overlay_kind is None:
                self._start_finish_overlay()

        self._view_state = self._racer_view_state(message=blocked_reason, music_bias=relax_delta - conc_delta)
        recommended_label = self._racer_recommendation(action)
        return self._arcade_snapshot(
            phase="neuro_racer",
            phase_label="Neuro Racer",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _tick_overlay(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._tick_effects()
        if self._overlay_timer > 0:
            self._overlay_timer -= 1
        if self._overlay_timer > 0:
            return False, False

        outcome = self._pending_outcome
        self._overlay_kind = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._pending_outcome = None
        if outcome == "failure":
            self._record_level_result(False, elapsed_seconds, score_override=0)
            self._finished = True
            return False, True
        if outcome == "level_complete":
            time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
            score = (
                48
                + min(30.0, self._score / 20.0)
                + min(16.0, self._best_streak * 2.2)
                + (self._stability * 0.12)
                - (self._collisions * 6.0)
                - time_penalty
            )
            self._record_level_result(True, elapsed_seconds, score_override=score)
            level_completed = True
            run_completed = self._advance_level()
            return level_completed, run_completed
        return False, False

    def _spawn_traffic(self) -> None:
        while self._traffic_schedule and self._distance >= float(self._traffic_schedule[0]["spawn_at"]):
            next_car = self._traffic_schedule.pop(0)
            self._traffic.append(
                {
                    "lane": int(next_car["lane"]),
                    "gap": float(next_car["gap"]),
                    "speed": float(next_car["speed"]),
                    "value": int(next_car["value"]),
                }
            )

    def _advance_traffic(self) -> None:
        survivors = []
        for car in self._traffic:
            car["gap"] -= max(9.0, ((self._speed - car["speed"]) * 0.38) + 10.0)
            if car["gap"] <= 18.0:
                if car["lane"] == self._lane:
                    self._register_collision(car)
                else:
                    self._register_overtake(car)
                continue
            survivors.append(car)
        self._traffic = survivors
        self._spawn_traffic()

    def _register_overtake(self, car: dict) -> None:
        self._overtakes += 1
        self._streak += 1
        self._best_streak = max(self._best_streak, self._streak)
        self._nitro = min(100.0, self._nitro + 10.0)
        gain = int(car["value"] + min(26, self._streak * 4))
        self._score += gain
        self._effects.append({"lane": car["lane"], "gap": 22.0, "kind": "spark", "ticks": 5})
        self._message = "Clean overtake. Keep the streak alive."

    def _register_collision(self, car: dict) -> None:
        self._collisions += 1
        self._stability = max(0.0, self._stability - 24.0)
        self._speed = max(36.0, self._speed - 14.0)
        self._nitro = max(0.0, self._nitro - 12.0)
        self._streak = 0
        self._effects.append({"lane": car["lane"], "gap": 18.0, "kind": "impact", "ticks": 6})
        self._message = "Traffic contact. Recover before the next crest."

    def _tick_effects(self) -> None:
        trimmed = []
        for effect in self._effects:
            updated = dict(effect)
            updated["ticks"] = max(0, int(updated.get("ticks", 0)) - 1)
            updated["gap"] = max(0.0, float(updated.get("gap", 0.0)) - 4.0)
            if updated["ticks"] > 0:
                trimmed.append(updated)
        self._effects = trimmed

    def _start_finish_overlay(self) -> None:
        self._overlay_kind = "finish"
        self._overlay_title = "Finish line"
        self._overlay_subtitle = f"{self._overtakes} overtakes on the sky ramp."
        self._overlay_timer = 7
        self._pending_outcome = "level_complete"
        self._message = self._overlay_title

    def _start_failure_overlay(self, subtitle: str) -> None:
        self._overlay_kind = "crash"
        self._overlay_title = "Race interrupted"
        self._overlay_subtitle = subtitle
        self._overlay_timer = 7
        self._pending_outcome = "failure"
        self._message = subtitle

    def _racer_recommendation(self, action: str | None) -> str:
        if action == "right":
            return "Move right"
        if action == "left":
            return "Move left"
        if action == "steady":
            return "Trigger nitro"
        nearest = min(self._traffic, key=lambda car: car["gap"], default=None)
        if nearest is not None and nearest["lane"] == self._lane:
            if self._lane == 0:
                return "Move right to pass"
            if self._lane == 2:
                return "Move left to pass"
            return "Pick the clearer side"
        if self._nitro >= 30.0:
            return "Hold steady for nitro"
        return "Build a clean overtake"

    def _racer_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        progress = max(0.0, min(1.0, self._distance / max(1.0, self._finish_distance)))
        return {
            "mode": "neuro_racer",
            "lane": self._lane,
            "speed": self._speed,
            "stability": self._stability,
            "nitro": self._nitro,
            "nitro_ticks": self._nitro_ticks,
            "distance": self._distance,
            "finish_distance": self._finish_distance,
            "progress_ratio": progress,
            "road_phase": "finish" if progress > 0.78 else ("crest" if progress > 0.42 else "climb"),
            "score": self._score,
            "star_progress": max(0.0, min(1.0, self._score / max(1, self._star_thresholds[-1]))),
            "star_thresholds": list(self._star_thresholds),
            "overtakes": self._overtakes,
            "collisions": self._collisions,
            "streak": self._streak,
            "best_streak": self._best_streak,
            "traffic": [dict(car) for car in self._traffic],
            "effects": [dict(effect) for effect in self._effects],
            "overlay_kind": self._overlay_kind,
            "overlay_title": self._overlay_title,
            "overlay_subtitle": self._overlay_subtitle,
            "overlay_timer": self._overlay_timer,
            "menu_button_rect": [18, 18, 54, 42],
            "music_scene": "sky_racer",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, self._stability + (self._best_streak * 2.0))),
            "restlessness": max(0.0, min(100.0, 18.0 + (self._collisions * 18.0))),
            "message": message or self._message,
        }


class BubbleBurstController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Wave 1", 60),
        TrainingLevel("Wave 2", 75),
        TrainingLevel("Wave 3", 90),
    ]
    CONFIGS = [
        {
            "columns": 6,
            "palette": ["red", "green"],
            "shots_left": 20,
            "star_thresholds": [2200, 3800, 5400],
            "layout": [".GGGG.", "GGRRGG", ".RRRR.", "R.GG.R", ".G..G."],
        },
        {
            "columns": 7,
            "palette": ["red", "green", "yellow"],
            "shots_left": 18,
            "star_thresholds": [3200, 5100, 7200],
            "layout": [".GGYGG.", "GGRRRGG", ".RRYRR.", "R.GYG.R", ".GGYGG.", "..Y.Y.."],
        },
        {
            "columns": 8,
            "palette": ["red", "green", "yellow", "blue"],
            "shots_left": 17,
            "star_thresholds": [4200, 6600, 9200],
            "layout": [".GGYYGG.", "GGRRRRGG", ".RYYBBR.", "RRGBBGRR", ".GYYBBG.", "..G..G.."],
        },
    ]
    TOKEN_MAP = {".": None, "R": "red", "G": "green", "Y": "yellow", "B": "blue"}
    VISIBLE_ROWS = 10

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._columns = config["columns"]
        self._palette = list(config["palette"])
        self._shots_left = int(config["shots_left"])
        self._star_thresholds = list(config["star_thresholds"])
        self._layout = list(config["layout"])
        self._board: list[list[str | None]] = [
            [None for _ in range(self._columns)] for _ in range(self.VISIBLE_ROWS)
        ]
        self._spawn_cursor = 0
        self._ceiling_cursor = self._level_index * 5
        self._danger_steps = 0
        self._score = 0
        self._combo = 0
        self._best_combo = 0
        self._score_popups: list[dict] = []
        self._aim_slot = self._columns // 2
        self._overlay_kind: str | None = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_timer = 0
        self._pending_outcome: str | None = None
        self._launcher_zone_row = self.VISIBLE_ROWS - 2
        self._message = "Clear the whole cluster before the launcher gets crowded."
        self._seed_board()
        self._current_bubble = self._next_spawn()
        self._next_bubble = self._next_spawn()
        self._view_state = self._bubble_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = "Concentrate to nudge the aim right, relax to nudge it left, and hold steady to fire."

        if self._overlay_kind is not None:
            level_completed, run_completed = self._tick_overlay(elapsed_seconds)
        elif stale:
            blocked_reason = "Metrics are stale. Bubble Burst paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Bubble Burst paused."
        else:
            self._tick_score_popups()
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                if self._stabilize_intent(intent):
                    self._aim_slot = min(self._columns - 1, self._aim_slot + 1)
                    self._message = "Aim shifted right."
                    action = "right"
                    moved = True
            elif intent == "relax":
                if self._stabilize_intent(intent):
                    self._aim_slot = max(0, self._aim_slot - 1)
                    self._message = "Aim shifted left."
                    action = "left"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    action = "fire"
                    moved = True
                    level_completed, run_completed = self._fire_bubble(elapsed_seconds)
            else:
                self._stabilize_intent(None)

        message = blocked_reason or self._message
        self._view_state = self._bubble_view_state(
            message=message,
            music_bias=relax_delta - conc_delta,
        )
        recommended_label = self._bubble_recommendation(action)
        return self._arcade_snapshot(
            phase="bubble_burst",
            phase_label="Bubble Burst",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _seed_board(self) -> None:
        for row_index, row_pattern in enumerate(self._layout):
            for col_index, char in enumerate(row_pattern):
                self._board[row_index][col_index] = self.TOKEN_MAP[char]

    def _next_spawn(self) -> str:
        color = self._palette[(self._spawn_cursor + self._level_index) % len(self._palette)]
        self._spawn_cursor += 1
        return color

    def _fire_bubble(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._shots_left = max(0, self._shots_left - 1)
        placed = self._place_current_bubble()
        if placed is None:
            self._message = "No landing slot. The ceiling drops."
            self._drop_ceiling_row()
            self._cycle_bubble_queue()
            if self._launcher_zone_reached():
                self._start_failure_overlay("Bubbles reached the launcher.")
                return False, False
            if self._shots_left == 0:
                self._start_failure_overlay("Out of shots before the board cleared.")
                return False, False
            return False, False

        row, col = placed
        popped_cells = self._resolve_burst(row, col)
        self._cycle_bubble_queue()

        if popped_cells:
            self._combo += 1
            self._best_combo = max(self._best_combo, self._combo)
            burst_score = (len(popped_cells) * 300) + max(0, (self._combo - 1) * 90)
            self._score += burst_score
            self._score_popups.append(
                {"row": row, "col": col, "text": str(burst_score), "ticks": 7}
            )
            self._message = f"Burst {len(popped_cells)} bubbles."
        else:
            self._combo = 0
            self._message = "No match. The ceiling drops."
            self._drop_ceiling_row()
            if self._launcher_zone_reached():
                self._start_failure_overlay("Bubbles reached the launcher.")
                return False, False

        if self._board_empty():
            self._start_success_overlay()
            return False, False
        if self._shots_left == 0:
            self._start_failure_overlay("Out of shots before the board cleared.")
            return False, False
        return False, False

    def _place_current_bubble(self) -> tuple[int, int] | None:
        for col in self._column_scan_order(self._aim_slot):
            row = self._landing_row(col)
            if row is not None:
                self._board[row][col] = self._current_bubble
                return row, col
        return None

    def _column_scan_order(self, center: int) -> list[int]:
        order = [center]
        for distance in range(1, self._columns):
            left = center - distance
            right = center + distance
            if left >= 0:
                order.append(left)
            if right < self._columns:
                order.append(right)
        return order

    def _landing_row(self, col: int) -> int | None:
        for row in range(self.VISIBLE_ROWS):
            if self._board[row][col] is None:
                return row
        return None

    def _resolve_burst(self, row: int, col: int) -> set[tuple[int, int]]:
        cluster = self._color_cluster(row, col)
        if len(cluster) < 3:
            return set()

        removed = set(cluster)
        self._clear_cells(cluster)
        floating = self._floating_cells()
        if floating:
            removed.update(floating)
            self._clear_cells(floating)
        return removed

    def _color_cluster(self, row: int, col: int) -> set[tuple[int, int]]:
        color = self._board[row][col]
        if color is None:
            return set()
        cluster = set()
        stack = [(row, col)]
        while stack:
            cell = stack.pop()
            if cell in cluster:
                continue
            r, c = cell
            if self._board[r][c] != color:
                continue
            cluster.add(cell)
            for neighbor in self._neighbors(r, c):
                if neighbor not in cluster:
                    stack.append(neighbor)
        return cluster

    def _floating_cells(self) -> set[tuple[int, int]]:
        anchored = set()
        stack = [(0, col) for col in range(self._columns) if self._board[0][col] is not None]
        while stack:
            cell = stack.pop()
            if cell in anchored:
                continue
            anchored.add(cell)
            r, c = cell
            for neighbor in self._neighbors(r, c):
                nr, nc = neighbor
                if self._board[nr][nc] is not None and neighbor not in anchored:
                    stack.append(neighbor)

        floating = set()
        for row in range(self.VISIBLE_ROWS):
            for col in range(self._columns):
                if self._board[row][col] is not None and (row, col) not in anchored:
                    floating.add((row, col))
        return floating

    def _neighbors(self, row: int, col: int) -> list[tuple[int, int]]:
        if row % 2 == 0:
            offsets = [(0, -1), (0, 1), (-1, -1), (-1, 0), (1, -1), (1, 0)]
        else:
            offsets = [(0, -1), (0, 1), (-1, 0), (-1, 1), (1, 0), (1, 1)]

        neighbors = []
        for row_delta, col_delta in offsets:
            next_row = row + row_delta
            next_col = col + col_delta
            if 0 <= next_row < self.VISIBLE_ROWS and 0 <= next_col < self._columns:
                neighbors.append((next_row, next_col))
        return neighbors

    def _clear_cells(self, cells: set[tuple[int, int]]) -> None:
        for row, col in cells:
            self._board[row][col] = None

    def _cycle_bubble_queue(self) -> None:
        self._current_bubble = self._next_bubble
        self._next_bubble = self._next_spawn()

    def _drop_ceiling_row(self) -> None:
        self._danger_steps += 1
        new_row = [
            (
                None
                if self._columns >= 7 and ((self._ceiling_cursor + col) % 5 == 0)
                else self._palette[(self._ceiling_cursor + col + self._level_index) % len(self._palette)]
            )
            for col in range(self._columns)
        ]
        self._ceiling_cursor += 1
        self._board = [new_row] + [row[:] for row in self._board[:-1]]

    def _board_empty(self) -> bool:
        return all(cell is None for row in self._board for cell in row)

    def _launcher_zone_reached(self) -> bool:
        for row in range(self._launcher_zone_row, self.VISIBLE_ROWS):
            if any(cell is not None for cell in self._board[row]):
                return True
        return False

    def _tick_score_popups(self) -> None:
        trimmed = []
        for popup in self._score_popups:
            updated = dict(popup)
            updated["ticks"] = max(0, int(updated.get("ticks", 0)) - 1)
            updated["row"] = max(0.0, float(updated.get("row", 0.0)) - 0.12)
            if updated["ticks"] > 0:
                trimmed.append(updated)
        self._score_popups = trimmed

    def swap_bubbles(self) -> bool:
        if self._overlay_kind is not None:
            return False
        self._current_bubble, self._next_bubble = self._next_bubble, self._current_bubble
        self._message = "Bubble queue swapped."
        self._view_state = self._bubble_view_state()
        return True

    def _start_success_overlay(self) -> None:
        self._overlay_kind = "board_clear"
        self._overlay_title = "You popped all bubbles"
        self._overlay_subtitle = "Level completed!"
        self._overlay_timer = 7
        self._pending_outcome = "level_complete"
        self._message = self._overlay_title

    def _start_failure_overlay(self, subtitle: str) -> None:
        self._overlay_kind = "failure"
        self._overlay_title = "Bubble run over"
        self._overlay_subtitle = subtitle
        self._overlay_timer = 7
        self._pending_outcome = "failure"
        self._message = subtitle

    def _tick_overlay(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._tick_score_popups()
        if self._overlay_timer > 0:
            self._overlay_timer -= 1
        if self._overlay_timer > 0:
            return False, False

        outcome = self._pending_outcome
        self._overlay_kind = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._pending_outcome = None
        if outcome == "failure":
            self._record_level_result(False, elapsed_seconds, score_override=0)
            self._finished = True
            return False, True
        if outcome == "level_complete":
            time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
            score = (
                50
                + min(34.0, self._score / 180.0)
                + min(12.0, self._shots_left * 1.2)
                + min(12.0, self._best_combo * 2.0)
                - time_penalty
            )
            self._record_level_result(True, elapsed_seconds, score_override=score)
            level_completed = True
            run_completed = self._advance_level()
            return level_completed, run_completed
        return False, False

    def _bubble_recommendation(self, action: str | None) -> str:
        if action == "right":
            return "Track right"
        if action == "left":
            return "Track left"
        if action == "fire":
            return "Burst cluster"
        if self._nearest_reachable_match() == self._current_bubble:
            return "Build the center cluster"
        return "Stabilize the shot"

    def _nearest_reachable_match(self) -> str | None:
        for col in self._column_scan_order(self._aim_slot):
            row = self._landing_row(col)
            if row is None:
                continue
            for neighbor in self._neighbors(row, col):
                nr, nc = neighbor
                if self._board[nr][nc] is not None:
                    return self._board[nr][nc]
        return None

    def _bubble_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "bubble_burst",
            "columns": self._columns,
            "visible_rows": self.VISIBLE_ROWS,
            "board": [list(row) for row in self._board],
            "aim_slot": self._aim_slot,
            "current_bubble": self._current_bubble,
            "next_bubble": self._next_bubble,
            "shots_left": self._shots_left,
            "score": self._score,
            "combo": self._combo,
            "best_combo": self._best_combo,
            "danger_steps": self._danger_steps,
            "launcher_zone_row": self._launcher_zone_row,
            "score_popups": [dict(popup) for popup in self._score_popups],
            "swap_enabled": self._overlay_kind is None,
            "star_progress": max(0.0, min(1.0, self._score / max(1, self._star_thresholds[-1]))),
            "star_thresholds": list(self._star_thresholds),
            "overlay_kind": self._overlay_kind,
            "overlay_title": self._overlay_title,
            "overlay_subtitle": self._overlay_subtitle,
            "overlay_timer": self._overlay_timer,
            "menu_button_rect": [18, 18, 54, 42],
            "swap_button_rect": [0, 0, 0, 0],
            "music_scene": "bubble_arcade",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 60.0 + (self._shots_left * 1.5) + (self._best_combo * 4.0))),
            "restlessness": max(0.0, min(100.0, 16.0 + (self._danger_steps * 12.0))),
            "message": message or self._message,
        }


class MemoryGameController(BaseTrainingController):
    def _reset_level_state(self) -> None:
        raise NotImplementedError

    def _memory_intent(self, conc_delta: float, relax_delta: float) -> str | None:
        balance = conc_delta - relax_delta
        if balance >= MEMORY_MOVE_BALANCE_THRESHOLD and conc_delta >= MEMORY_MOVE_DELTA_THRESHOLD:
            return "right"
        if balance <= -MEMORY_MOVE_BALANCE_THRESHOLD and relax_delta >= MEMORY_MOVE_DELTA_THRESHOLD:
            return "left"
        if abs(balance) <= MEMORY_CONFIRM_DEAD_ZONE:
            return "confirm"
        return None

    def _preview_active(self) -> bool:
        return self._preview_ticks > 0

    def _advance_preview(self) -> int:
        self._preview_ticks = max(0, self._preview_ticks - 1)
        return self._preview_cursor()

    def _preview_cursor(self) -> int:
        if not self._preview_order:
            return 0
        elapsed = max(0, self._preview_total_ticks - self._preview_ticks)
        return min(len(self._preview_order) - 1, elapsed // self._preview_step_ticks)

    def _base_memory_snapshot(
        self,
        *,
        phase: str,
        phase_label: str,
        direction: str | None,
        blocked_reason: str,
        control_hint: str,
        conc_delta: float,
        relax_delta: float,
        moved: bool,
        level_completed: bool,
        run_completed: bool,
        recommended_label: str = "Confirm",
    ) -> GameplaySnapshot:
        balance = conc_delta - relax_delta
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase=phase,
            phase_label=phase_label,
            recommended_direction=direction,
            recommended_label=recommended_label,
            control_hint=blocked_reason or control_hint,
            direction=direction,
            direction_label=DIR_LABELS.get(direction, "Hold steady"),
            moved=moved,
            blocked_reason=blocked_reason,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            balance=balance,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=self._view_state,
        )


class PatternRecallController(MemoryGameController):
    LEVELS = [
        TrainingLevel("Level 1", 55),
        TrainingLevel("Level 2", 65),
        TrainingLevel("Level 3", 75),
    ]
    CONFIGS = [
        {"grid_size": 3, "sequence": [0, 4, 8, 2], "chunk_size": 2, "distractor": []},
        {"grid_size": 4, "sequence": [1, 5, 6, 10, 15], "chunk_size": 2, "distractor": []},
        {"grid_size": 4, "sequence": [0, 5, 10, 15, 14, 9], "chunk_size": 2, "distractor": [3, 7, 11, 6]},
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._grid_size = config["grid_size"]
        self._sequence = list(config["sequence"])
        self._chunk_size = config["chunk_size"]
        self._distractor = list(config["distractor"])
        self._preview_order = self._sequence + self._distractor
        self._preview_step_ticks = 2
        self._preview_total_ticks = len(self._preview_order) * self._preview_step_ticks
        self._preview_ticks = self._preview_total_ticks
        self._confirmed: list[int] = []
        self._mistakes = 0
        self._chunk_anchor = 0
        self._selected_index = self._sequence[0]
        self._phase = "preview"
        self._view_state = self._pattern_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        direction = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = (
            "Concentrate to move forward, relax to move backward, and hold balanced to confirm the current tile."
        )

        if stale:
            blocked_reason = "Metrics are stale. Recall paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Recall paused."
        elif self._preview_active():
            self._phase = "preview"
            self._advance_preview()
            control_hint = "Preview the target pattern. A distractor pass may appear before recall begins."
        else:
            self._phase = "recall"
            direction = self._memory_intent(conc_delta, relax_delta)
            if direction == "right":
                if self._stabilize_intent(direction):
                    self._selected_index = (self._selected_index + 1) % (self._grid_size ** 2)
                    moved = True
            elif direction == "left":
                if self._stabilize_intent(direction):
                    self._selected_index = (self._selected_index - 1) % (self._grid_size ** 2)
                    moved = True
            elif direction == "confirm":
                if self._stabilize_intent(direction):
                    expected = self._sequence[len(self._confirmed)]
                    if self._selected_index == expected:
                        self._confirmed.append(self._selected_index)
                        if len(self._confirmed) % self._chunk_size == 0:
                            self._chunk_anchor = len(self._confirmed)
                    else:
                        self._mistakes += 1
                        self._confirmed = self._confirmed[: self._chunk_anchor]
                        self._phase = "chunk_retry"
                        retry_index = min(self._chunk_anchor, len(self._sequence) - 1)
                        self._selected_index = self._sequence[retry_index]
                        control_hint = "Wrong tile. Rebuild the current chunk from the last checkpoint."
                    moved = True
            else:
                self._stabilize_intent(None)

            if len(self._confirmed) == len(self._sequence):
                self._phase = "completed"
                accuracy = max(0.0, 1.0 - (self._mistakes / max(1, len(self._sequence))))
                time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
                score = 55 + (accuracy * 45) - time_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

        self._view_state = self._pattern_view_state()
        phase_labels = {
            "preview": "Preview Pattern",
            "recall": "Recall Sequence",
            "chunk_retry": "Chunk Retry",
            "completed": "Sequence Locked",
        }
        return self._base_memory_snapshot(
            phase=self._phase,
            phase_label=phase_labels[self._phase],
            direction=direction,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
        )

    def _pattern_view_state(self) -> dict:
        preview_cursor = self._preview_cursor() if self._preview_order else 0
        preview_cells = []
        if self._preview_active() and self._preview_order:
            preview_cells = [self._preview_order[preview_cursor]]
        return {
            "mode": "pattern",
            "grid_size": self._grid_size,
            "sequence": list(self._sequence),
            "selected_index": self._selected_index,
            "confirmed_count": len(self._confirmed),
            "confirmed_cells": list(self._confirmed),
            "preview_ticks": self._preview_ticks,
            "preview_cells": preview_cells,
            "mistakes": self._mistakes,
            "chunk_index": self._chunk_anchor // self._chunk_size,
            "music_scene": "pattern_memory",
            "music_bias": 0.0,
            "serenity": max(0.0, min(100.0, 62.0 - (self._mistakes * 8.0))),
            "restlessness": max(0.0, min(100.0, 16.0 + (self._mistakes * 10.0))),
            "message": "",
            "phase": self._phase,
            "headline": "Pattern Recall Pro",
        }


class CandyCascadeController(MemoryGameController):
    LEVELS = [
        TrainingLevel("Board 1", 65),
        TrainingLevel("Board 2", 80),
        TrainingLevel("Board 3", 95),
    ]
    CONFIGS = [
        {"grid_size": 5, "color_count": 4, "target_score": 180, "blockers": []},
        {
            "grid_size": 6,
            "color_count": 5,
            "target_score": 240,
            "blockers": [(1, 1), (1, 4), (2, 2), (2, 3), (3, 2), (3, 3), (4, 1), (4, 4)],
        },
        {
            "grid_size": 6,
            "color_count": 5,
            "target_score": 300,
            "blockers": [
                (1, 1),
                (1, 4),
                (2, 1),
                (2, 4),
                (3, 1),
                (3, 4),
                (4, 1),
                (4, 4),
                (2, 2),
                (3, 3),
            ],
        },
    ]
    PALETTE = ["berry", "lemon", "mint", "sky", "peach"]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._grid_size = config["grid_size"]
        self._color_count = config["color_count"]
        self._target_score = config["target_score"]
        self._palette = self.PALETTE[: self._color_count]
        self._board = self._generate_seed_board()
        self._blockers = {(row * self._grid_size) + col for row, col in config["blockers"]}
        self._specials: dict[int, str] = {}
        self._score = 0
        self._cascade_depth = 0
        self._phase = "swap_select"
        self._message = "Swap for cascades and clear the blockers."
        self._reshuffles = 0
        self._refill_cursor = self._level_index * 5
        self._legal_swaps = self._compute_legal_swaps(self._board)
        if not self._legal_swaps:
            self._reshuffle_until_playable()
            self._legal_swaps = self._compute_legal_swaps(self._board)
        self._swap_index = 0
        self._view_state = self._cascade_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        direction = None
        moved = False
        level_completed = False
        run_completed = False
        self._phase = "swap_select"
        self._cascade_depth = 0
        control_hint = (
            "Concentrate to cycle forward, relax to cycle backward, and hold balanced to confirm the highlighted swap."
        )

        if stale:
            blocked_reason = "Metrics are stale. Candy Cascade paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Candy Cascade paused."
        else:
            if not self._legal_swaps:
                self._reshuffle_until_playable()
                self._legal_swaps = self._compute_legal_swaps(self._board)
            direction = self._memory_intent(conc_delta, relax_delta)
            if direction == "right":
                if self._stabilize_intent(direction):
                    if self._legal_swaps:
                        self._swap_index = (self._swap_index + 1) % len(self._legal_swaps)
                    self._message = "Highlighted the next swap."
                    moved = True
            elif direction == "left":
                if self._stabilize_intent(direction):
                    if self._legal_swaps:
                        self._swap_index = (self._swap_index - 1) % len(self._legal_swaps)
                    self._message = "Highlighted the previous swap."
                    moved = True
            elif direction == "confirm":
                if self._stabilize_intent(direction):
                    moved = True
                    level_completed, run_completed = self._confirm_swap(elapsed_seconds)
            else:
                self._stabilize_intent(None)

        message = blocked_reason or self._message
        self._view_state = self._cascade_view_state(
            message=message,
            music_bias=conc_delta - relax_delta,
        )
        recommended_label = self._cascade_recommendation(direction)
        return self._base_memory_snapshot(
            phase=self._phase,
            phase_label="Candy Cascade",
            direction=direction,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _generate_seed_board(self) -> list[str]:
        cell_count = self._grid_size ** 2
        for attempt in range(cell_count + self._color_count):
            board: list[str] = []
            for index in range(cell_count):
                start = index + self._level_index + attempt
                color = self._seed_color_for_cell(board, index, start)
                board.append(color)
            if not self._find_match_groups(board) and self._compute_legal_swaps(board):
                return board
        return [self._palette[(index + self._level_index) % self._color_count] for index in range(cell_count)]

    def _seed_color_for_cell(self, board: list[str], index: int, start: int) -> str:
        for offset in range(self._color_count):
            color = self._palette[(start + offset) % self._color_count]
            if not self._creates_immediate_match(board, index, color):
                return color
        return self._palette[start % self._color_count]

    def _creates_immediate_match(self, board: list[str], index: int, color: str) -> bool:
        row, col = divmod(index, self._grid_size)
        if col >= 2 and board[index - 1] == color and board[index - 2] == color:
            return True
        if row >= 2:
            above = index - self._grid_size
            above_twice = index - (self._grid_size * 2)
            if board[above] == color and board[above_twice] == color:
                return True
        return False

    def _compute_legal_swaps(self, board: list[str]) -> list[tuple[int, int]]:
        swaps = []
        cell_count = self._grid_size ** 2
        for index in range(cell_count):
            row, col = divmod(index, self._grid_size)
            if col < self._grid_size - 1 and self._swap_creates_match(board, index, index + 1):
                swaps.append((index, index + 1))
            if row < self._grid_size - 1 and self._swap_creates_match(board, index, index + self._grid_size):
                swaps.append((index, index + self._grid_size))
        return swaps

    def _swap_creates_match(self, board: list[str], left: int, right: int) -> bool:
        if board[left] == board[right]:
            return False
        trial = list(board)
        trial[left], trial[right] = trial[right], trial[left]
        return bool(self._find_match_groups(trial))

    def _find_match_groups(self, board: list[str]) -> list[tuple[str, list[int]]]:
        groups: list[tuple[str, list[int]]] = []
        for row in range(self._grid_size):
            run_color = None
            run_indices: list[int] = []
            for col in range(self._grid_size):
                index = (row * self._grid_size) + col
                color = board[index]
                if color == run_color:
                    run_indices.append(index)
                else:
                    if run_color is not None and len(run_indices) >= 3:
                        groups.append(("row", list(run_indices)))
                    run_color = color
                    run_indices = [index]
            if run_color is not None and len(run_indices) >= 3:
                groups.append(("row", list(run_indices)))

        for col in range(self._grid_size):
            run_color = None
            run_indices = []
            for row in range(self._grid_size):
                index = (row * self._grid_size) + col
                color = board[index]
                if color == run_color:
                    run_indices.append(index)
                else:
                    if run_color is not None and len(run_indices) >= 3:
                        groups.append(("column", list(run_indices)))
                    run_color = color
                    run_indices = [index]
            if run_color is not None and len(run_indices) >= 3:
                groups.append(("column", list(run_indices)))
        return groups

    def _confirm_swap(self, elapsed_seconds: float) -> tuple[bool, bool]:
        if not self._legal_swaps:
            self._message = "No legal swaps. Rebalancing the board."
            self._reshuffle_until_playable()
            self._legal_swaps = self._compute_legal_swaps(self._board)
            return False, False

        pair = self._legal_swaps[self._swap_index]
        if pair not in self._compute_legal_swaps(self._board):
            self._legal_swaps = self._compute_legal_swaps(self._board)
            self._swap_index = 0
            self._message = "The highlighted move changed. Try again."
            return False, False

        self._swap_cells(pair[0], pair[1])
        cleared = self._resolve_board(pair[1])
        self._legal_swaps = self._compute_legal_swaps(self._board)
        if not self._legal_swaps:
            self._reshuffle_until_playable()
            self._legal_swaps = self._compute_legal_swaps(self._board)
        if self._legal_swaps:
            self._swap_index %= len(self._legal_swaps)
        else:
            self._swap_index = 0

        if cleared:
            self._message = (
                f"Cascade x{self._cascade_depth}."
                if self._cascade_depth > 1
                else "Swap confirmed."
            )
        else:
            self._message = "Swap resolved with no clear."

        if self._score >= self._target_score and not self._blockers:
            time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
            score = 52 + min(36.0, self._score / 8.0) + max(0.0, 12.0 - (self._reshuffles * 2.0)) - time_penalty
            self._record_level_result(True, elapsed_seconds, score_override=score)
            level_completed = True
            run_completed = self._advance_level()
            return level_completed, run_completed
        return False, False

    def _swap_cells(self, left: int, right: int) -> None:
        self._board[left], self._board[right] = self._board[right], self._board[left]
        left_special = self._specials.pop(left, None)
        right_special = self._specials.pop(right, None)
        if left_special is not None:
            self._specials[right] = left_special
        if right_special is not None:
            self._specials[left] = right_special

    def _resolve_board(self, spawn_index: int) -> bool:
        cleared_any = False
        while True:
            groups = self._find_match_groups(self._board)
            if not groups:
                break
            cleared_any = True
            self._phase = "cascade"
            self._cascade_depth += 1
            clear_indices = set()
            special_kind = None
            for axis, group in groups:
                clear_indices.update(group)
                if special_kind is None and len(group) == 4:
                    special_kind = "row" if axis == "row" else "column"

            if special_kind is not None:
                clear_indices.discard(spawn_index)
                self._specials.pop(spawn_index, None)
                self._specials[spawn_index] = special_kind
                self._blockers.discard(spawn_index)

            expanded_clear = set(clear_indices)
            pending = [index for index in list(expanded_clear) if index in self._specials]
            triggered = set()
            while pending:
                current = pending.pop()
                if current in triggered:
                    continue
                triggered.add(current)
                for index in self._special_clear_indices(current, self._specials[current]):
                    if index not in expanded_clear:
                        expanded_clear.add(index)
                        if index in self._specials:
                            pending.append(index)

            blockers_removed = len(self._blockers & expanded_clear)
            self._blockers.difference_update(expanded_clear)
            for index in expanded_clear:
                self._board[index] = None
                self._specials.pop(index, None)

            self._score += len(expanded_clear) * 20
            self._score += blockers_removed * 25
            self._score += max(0, self._cascade_depth - 1) * 10
            self._apply_gravity_and_refill()

        return cleared_any

    def _special_clear_indices(self, index: int, kind: str) -> set[int]:
        row, col = divmod(index, self._grid_size)
        if kind == "row":
            return {(row * self._grid_size) + target_col for target_col in range(self._grid_size)}
        return {(target_row * self._grid_size) + col for target_row in range(self._grid_size)}

    def _apply_gravity_and_refill(self) -> None:
        new_board: list[str | None] = [None] * (self._grid_size ** 2)
        new_specials: dict[int, str] = {}
        for col in range(self._grid_size):
            column_items = []
            for row in range(self._grid_size - 1, -1, -1):
                index = (row * self._grid_size) + col
                if self._board[index] is not None:
                    column_items.append((self._board[index], self._specials.get(index)))

            write_row = self._grid_size - 1
            for color, special in column_items:
                index = (write_row * self._grid_size) + col
                new_board[index] = color
                if special is not None:
                    new_specials[index] = special
                write_row -= 1

            while write_row >= 0:
                index = (write_row * self._grid_size) + col
                new_board[index] = self._next_refill_color()
                write_row -= 1

        self._board = [cell for cell in new_board if cell is not None]
        self._specials = new_specials

    def _next_refill_color(self) -> str:
        color = self._palette[(self._refill_cursor + self._level_index) % self._color_count]
        self._refill_cursor += 1
        return color

    def _reshuffle_until_playable(self) -> None:
        items = [(self._board[index], self._specials.get(index)) for index in range(len(self._board))]
        item_count = len(items)
        for shift in range(1, item_count + 1):
            offset = (shift + self._reshuffles) % item_count
            rotated = items[offset:] + items[:offset]
            board = [color for color, _special in rotated]
            specials = {
                index: special
                for index, (_color, special) in enumerate(rotated)
                if special is not None
            }
            if not self._find_match_groups(board) and self._compute_legal_swaps(board):
                self._board = board
                self._specials = specials
                self._reshuffles += 1
                self._message = "Board reshuffled."
                return

        self._board = self._generate_seed_board()
        self._specials = {}
        self._reshuffles += 1
        self._message = "Board reset into a fresh shuffle."

    def _cascade_recommendation(self, direction: str | None) -> str:
        if direction == "right":
            return "Cycle forward"
        if direction == "left":
            return "Cycle backward"
        if direction == "confirm":
            return "Confirm swap"
        if self._blockers:
            return "Clear blockers first"
        return "Chase the next cascade"

    def _highlight_pair(self) -> list[int]:
        if not self._legal_swaps:
            return []
        left, right = self._legal_swaps[self._swap_index]
        return [left, right]

    def _cascade_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "candy_cascade",
            "grid_size": self._grid_size,
            "candies": list(self._board),
            "blocker_cells": sorted(self._blockers),
            "highlight_pair": self._highlight_pair(),
            "score": self._score,
            "target_score": self._target_score,
            "cascade_depth": self._cascade_depth,
            "remaining_blockers": len(self._blockers),
            "special_cells": dict(self._specials),
            "legal_move_count": len(self._legal_swaps),
            "swap_index": self._swap_index,
            "music_scene": "candy_memory",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 60.0 + (self._score / 8.0) - (len(self._blockers) * 4.0))),
            "restlessness": max(0.0, min(100.0, 20.0 + (len(self._blockers) * 5.0) + (self._reshuffles * 6.0))),
            "message": message,
            "phase": self._phase,
            "headline": "Candy Cascade",
        }


class ProstheticArmController(BaseTrainingController):
    LEVELS = [
        TrainingLevel("Grip Acquisition", 40),
        TrainingLevel("Neutral Control", 48),
        TrainingLevel("Mixed Sequence", 60),
    ]
    ROUTINES = [
        ["OPEN", "CLOSED", "OPEN", "CLOSED"],
        ["NEUTRAL", "OPEN", "NEUTRAL", "CLOSED", "NEUTRAL"],
        ["OPEN", "CLOSED", "NEUTRAL", "CLOSED", "OPEN", "NEUTRAL"],
    ]
    HOLD_TARGETS_MS = [1000, 1200, 1500]

    def __init__(self):
        self._state_engine = ArmStateEngine()
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        self._state_engine.reset()
        self._routine = list(self.ROUTINES[self._level_index])
        self._hold_target_ms = self.HOLD_TARGETS_MS[self._level_index]
        self._sequence_index = 0
        self._hold_progress_ms = 0
        self._tick_clock_ms = 0
        self._successes = 0
        self._misses = 0
        self._stable_history: list[str] = []
        self._last_logged_state = None
        self._last_penalized_state = None
        self._message = "Guide the arm to the first target."
        self._view_state = self._arm_view_state(
            concentration=0.0,
            relaxation=0.0,
            current_state="OPEN",
            target_state=self._routine[0],
            blocked_reason="",
        )

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        self._tick_clock_ms += 250
        arm_snapshot = self._state_engine.update(
            concentration,
            relaxation,
            now_ms=self._tick_clock_ms,
        )
        current_state = arm_snapshot.state
        target_state = self._routine[min(self._sequence_index, len(self._routine) - 1)]
        phase_label = self.current_level.title
        blocked_reason = ""
        moved = False
        level_completed = False
        run_completed = False

        if current_state != self._last_logged_state:
            self._stable_history.append(current_state)
            self._stable_history = self._stable_history[-8:]
            self._last_logged_state = current_state

        control_hint = (
            "Focus to close the arm, soften attention to open it, and stay between the thresholds for neutral."
        )

        if stale:
            blocked_reason = "Metrics are stale. Arm sequence paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Arm sequence paused."
        else:
            if current_state == target_state:
                self._last_penalized_state = None
                self._hold_progress_ms = min(self._hold_target_ms, self._hold_progress_ms + 250)
                self._message = f"{state_label(target_state)} engaged. Hold steady."
                moved = True
                if self._hold_progress_ms >= self._hold_target_ms:
                    self._successes += 1
                    self._sequence_index += 1
                    self._hold_progress_ms = 0
                    if self._sequence_index >= len(self._routine):
                        accuracy_bonus = max(0.0, 18.0 - (self._misses * 3.0))
                        speed_bonus = max(0.0, (self.current_level.target_seconds - elapsed_seconds) * 0.75)
                        score = 58.0 + (self._successes * 6.0) + accuracy_bonus + speed_bonus
                        self._record_level_result(True, elapsed_seconds, score_override=score)
                        level_completed = True
                        run_completed = self._advance_level()
                    else:
                        next_target = self._routine[self._sequence_index]
                        self._message = (
                            f"{state_label(target_state)} locked. Next target: {state_label(next_target)}."
                        )
            else:
                if current_state != self._last_penalized_state and arm_snapshot.debounce_ratio >= 1.0:
                    self._misses += 1
                    self._last_penalized_state = current_state
                self._hold_progress_ms = max(0, self._hold_progress_ms - 125)
                self._message = f"Guide the arm to {state_label(target_state)}."

        balance = concentration - relaxation
        conc_delta = concentration - (self._conc_baseline if self._conc_baseline is not None else 50.0)
        relax_delta = relaxation - (self._relax_baseline if self._relax_baseline is not None else 50.0)
        view_state = self._arm_view_state(
            concentration=concentration,
            relaxation=relaxation,
            current_state=current_state,
            target_state=target_state,
            blocked_reason=blocked_reason,
        )
        self._view_state = view_state
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase="prosthetic_arm",
            phase_label=phase_label,
            recommended_direction=target_state.lower(),
            recommended_label=state_label(target_state),
            control_hint=blocked_reason or control_hint,
            direction=target_state.lower(),
            direction_label=DIR_LABELS[target_state.lower()],
            moved=moved,
            blocked_reason=blocked_reason,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            balance=balance,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=view_state,
        )

    def _arm_view_state(
        self,
        *,
        concentration: float,
        relaxation: float,
        current_state: str,
        target_state: str,
        blocked_reason: str,
    ) -> dict:
        return {
            "mode": "prosthetic_arm",
            "headline": self.current_level.title,
            "target_state": target_state,
            "current_state": current_state,
            "hold_progress": self._hold_progress_ms / max(1, self._hold_target_ms),
            "hold_target_ms": self._hold_target_ms,
            "hold_ms": self._hold_progress_ms,
            "sequence_index": min(self._sequence_index, len(self._routine)),
            "sequence_total": len(self._routine),
            "history": list(self._stable_history),
            "successes": self._successes,
            "misses": self._misses,
            "attention": concentration,
            "relaxation": relaxation,
            "dominant_state": dominant_state_for_metrics(concentration, relaxation),
            "message": blocked_reason or self._message,
            "music_scene": "assistive_focus",
            "music_bias": max(-1.0, min(1.0, (concentration - relaxation) / 50.0)),
            "serenity": max(0.0, min(100.0, relaxation)),
            "restlessness": max(0.0, min(100.0, concentration)),
            "arm_connected": False,
            "backend_mode": "capsule",
            "backend_status": "Using live Capsule productivity metrics.",
        }


TRAINING_SPECS: list[TrainingGameSpec] = [
    TrainingGameSpec(
        game_id="calm_current",
        section="Reduce stress and tension",
        eyebrow="Calm river",
        card_title="Calm Current",
        detail_title="A river game for relaxation",
        duration="8 min",
        description="Ease the current by staying relaxed and let the lantern drift through calmer water.",
        detail_body=(
            "Calm Current trains relaxation control by turning clean, steady calmness into forward momentum. "
            "Spikes in concentration make the river choppy, so the strongest runs come from sustained relaxed control."
        ),
        instructions=(
            "During gameplay, relax to deepen the current and increase flow. Strong concentration spikes increase "
            "turbulence and slow the lantern down."
        ),
        calibration_copy="Relax and settle into a smooth baseline before the river begins to move.",
        preview_label="RIVER",
        colors=("#1d4f53", "#7fd8b3"),
        enabled=True,
        controller_factory=CalmCurrentController,
        widget_kind="calm_current",
        music_profile="calm",
    ),
    TrainingGameSpec(
        game_id="neuroflow",
        section="Improve concentration",
        eyebrow="Focus launcher",
        card_title="Neuroflow Launcher",
        detail_title="A staged focus-to-launch workflow driven by raw EEG and PSD",
        duration="Continuous",
        description="Move through device detection, resistance check, quick calibration, EEG streaming, spectral analysis, and focus-triggered app launch.",
        detail_body=(
            "Neuroflow is not a short mini-game. It is a staged launcher flow that mirrors the original Neuroflow "
            "logic: resistances must pass, quick calibration must complete, the concentration index is computed from "
            "raw PSD band powers, and sustained focus launches the selected desktop app."
        ),
        instructions=(
            "Keep the headset connected, pass the resistance check, run quick calibration, and then sustain the "
            "focus threshold until the dwell bar completes. Neuroflow uses Beta / (Theta + Alpha) with hysteresis "
            "and cooldown, just like the original launcher."
        ),
        calibration_copy="Neuroflow uses the embedded quick-calibration flow and then transitions directly into focus launch mode.",
        preview_label="NEUROFLOW",
        colors=("#18314f", "#40b6ff"),
        enabled=True,
        controller_factory=NeuroflowPlaceholderController,
        widget_kind="neuroflow",
        soundtrack_enabled=False,
        music_profile="concentration",
    ),
    TrainingGameSpec(
        game_id="mind_maze",
        section="Improve concentration",
        eyebrow="Mind Maze",
        card_title="A maze game for concentration",
        detail_title="A maze game for concentration",
        duration="10 min",
        description="Navigate a glowing maze using concentration and relaxation in real time.",
        detail_body=(
            "Mind Maze trains attention switching and steady control. Concentration climbs the maze, relaxation "
            "drops through lower corridors, and once you reach horizontal routes the same signals steer right and left."
        ),
        instructions=(
            "Calibrate first. During play, follow the on-screen hint: concentration climbs or advances right when the "
            "maze calls for focus, and relaxation drops or backtracks when the route needs a calmer state."
        ),
        calibration_copy="Relax and hold the indicator in the ready zone to unlock the maze.",
        preview_label="MAZE",
        colors=("#7b2d1d", "#db9054"),
        enabled=True,
        controller_factory=MindMazeController,
        widget_kind="mind_maze",
        music_profile="concentration",
    ),
    TrainingGameSpec(
        game_id="prosthetic_arm",
        section="Assistive motor control",
        eyebrow="Assistive control",
        card_title="Prosthetic Arm Lab",
        detail_title="A target-sequence prosthetic arm trainer with live control and Arm Lab diagnostics",
        duration="12 min",
        description="Practice open, neutral, and close arm states while the live control panel mirrors the arm in simulation or hardware.",
        detail_body=(
            "Prosthetic Arm Lab adapts the supplied Phaseon arm-control concept into Training Lab. The scored training "
            "routine prompts open, neutral, and close targets in sequence, while Arm Lab shows the same control stream "
            "through live metrics, BrainBit diagnostics, and Arduino output when hardware is connected."
        ),
        instructions=(
            "Focus to close the arm, soften attention to open it, and hover between the thresholds for neutral. "
            "During training, follow the highlighted state, hold it until the sequence advances, and use Arm Lab for "
            "BrainBit diagnostics or Arduino setup when needed."
        ),
        calibration_copy="Relax into a clean baseline before the first grip sequence starts.",
        preview_label="ARM",
        colors=("#2d4737", "#87d2a1"),
        enabled=True,
        controller_factory=ProstheticArmController,
        widget_kind="prosthetic_arm",
        soundtrack_enabled=False,
        music_profile="concentration",
    ),
    TrainingGameSpec(
        game_id="full_reboot",
        section="Relax before sleep",
        eyebrow="Deep wind-down",
        card_title="Full reboot",
        detail_title="A guided sleep wind-down with breathing, body settling, and deep descent",
        duration="25 min",
        description="Ease into sleep through three guided stages that reward steady relaxation and quiet the signal over time.",
        detail_body=(
            "Full reboot is a guided neurofeedback session designed for bedtime. It starts with breath pacing, then "
            "moves into body settling and finally a deeper sleep-descent stage where concentration spikes are gently "
            "discouraged and sustained relaxation makes the scene and music softer."
        ),
        instructions=(
            "Calibrate first, then let the session guide you. Relaxation deepens each stage, balanced steadiness "
            "helps hold transitions, and concentration spikes raise restlessness and slow the wind-down."
        ),
        calibration_copy="Relax your breathing and settle into a clean baseline before the wind-down begins.",
        preview_label="SLEEP",
        colors=("#22304f", "#9caedb"),
        enabled=True,
        controller_factory=FullRebootController,
        widget_kind="full_reboot",
        music_profile="sleep",
    ),
    TrainingGameSpec(
        game_id="space_shooter",
        section="Arcade neurofeedback",
        eyebrow="Neuro arcade",
        card_title="Space Shooter",
        detail_title="A retro vertical shooter for lateral control, burst timing, and wave clears",
        duration="9 min",
        description="Sweep a star corridor, burst through enemy waves, and grab key pickups before the sector closes.",
        detail_body=(
            "Space Shooter now plays like a portrait arcade rush. Concentration slides the ship right, relaxation "
            "slides it left, and a balanced steady hold triggers a short burst-fire window while the ship keeps "
            "shooting automatically. Clear each descending wave, collect weapon and repair pickups, and protect your hull."
        ),
        instructions=(
            "Concentrate to move right, relax to move left, and hold a balanced steady state to trigger burst fire. "
            "Stay aligned with incoming formations, collect pickups, and clear all three waves in each sector."
        ),
        calibration_copy="Settle into a stable baseline so lateral movement and burst timing stay readable.",
        preview_label="SPACE",
        colors=("#10294e", "#57b8ff"),
        enabled=True,
        controller_factory=SpaceShooterController,
        widget_kind="space_shooter",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="jump_ball",
        section="Arcade neurofeedback",
        eyebrow="Rhythm runner",
        card_title="Jump Ball",
        detail_title="A rolling jump game for focus timing and controlled recovery",
        duration="8 min",
        description="Charge jumps over obstacle towers, settle landings cleanly, and preserve a smooth combo rhythm.",
        detail_body=(
            "Jump Ball turns concentration into jump height and relaxation into clean landings. It works well with EEG "
            "because the course moves forward automatically, letting the player focus on steady lift, recovery, and "
            "momentum instead of twitch steering."
        ),
        instructions=(
            "Concentrate to build jump height, relax to settle back to the track, and hold a balanced steady state to "
            "protect momentum through clean sections."
        ),
        calibration_copy="Hold a clean baseline so jump charge and landing recovery stay responsive during the run.",
        preview_label="JUMP",
        colors=("#5c2d0d", "#ffbe55"),
        enabled=True,
        controller_factory=JumpBallController,
        widget_kind="jump_ball",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="neuro_racer",
        section="Arcade neurofeedback",
        eyebrow="Focus speedway",
        card_title="Neuro Racer",
        detail_title="A sky-ramp racer for steering, nitro timing, and calm recovery",
        duration="10 min",
        description="Overtake traffic on a floating speedway, save nitro for clean stretches, and recover after impacts.",
        detail_body=(
            "Neuro Racer now presents a behind-the-car sky-ramp view. Concentration steers toward the right lane, "
            "relaxation steers left into recovery space, and a balanced steady hold triggers nitro when charged or "
            "locks the racing line when you need a calmer correction. The goal is to chain clean overtakes without losing stability."
        ),
        instructions=(
            "Concentrate to steer right, relax to steer left, and hold a balanced steady state to activate nitro when "
            "the meter is ready. Avoid traffic, protect stability, and reach the finish arch on every track."
        ),
        calibration_copy="Build a stable baseline first so steering and nitro cues stay readable.",
        preview_label="RACE",
        colors=("#27144b", "#f04868"),
        enabled=True,
        controller_factory=NeuroRacerController,
        widget_kind="neuro_racer",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="bubble_burst",
        section="Arcade neurofeedback",
        eyebrow="Arcade puzzler",
        card_title="Bubble Burst",
        detail_title="A glossy bubble puzzler for shot timing, queue swaps, and full-board clears",
        duration="9 min",
        description="Clear the hanging cluster with a limited shot budget, swap the queue, and keep bubbles out of the launcher zone.",
        detail_body=(
            "Bubble Burst now follows a glossy mobile-style bubble shooter flow. Concentration nudges the launcher "
            "right, relaxation nudges it left, and a balanced steady hold fires the current bubble. Optional queue swapping "
            "helps rescue awkward shots, but the core goal is simple: clear every bubble before you run out of shots or crowd the launcher."
        ),
        instructions=(
            "Concentrate to move the aim right, relax to move it left, and hold a balanced steady state to fire. "
            "Match groups of three or more, use the swap button when needed, and clear the whole board before the shot budget runs out."
        ),
        calibration_copy="Settle into a stable baseline so aim movement and burst timing feel consistent.",
        preview_label="BUBBLE",
        colors=("#214f86", "#7de0ff"),
        enabled=True,
        controller_factory=BubbleBurstController,
        widget_kind="bubble_burst",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="pattern_recall",
        section="Memory and cognitive control",
        eyebrow="Memory loop",
        card_title="Pattern Recall Pro",
        detail_title="A layered pattern game for focus and chunked recall",
        duration="9 min",
        description="Memorize longer patterns, survive distractor previews, and rebuild the sequence chunk by chunk.",
        detail_body=(
            "Pattern Recall Pro deepens the original memory loop with longer sequences, chunk checkpoints, and a "
            "distractor preview on the final stage. It rewards steady EEG control and strong working-memory retention."
        ),
        instructions=(
            "Watch the pattern, then rebuild it. Concentrate to move forward, relax to move backward, and hold a "
            "balanced steady state to confirm the highlighted tile."
        ),
        calibration_copy="Build a neutral baseline first so balanced confirm holds stay reliable during recall.",
        preview_label="PATTERN",
        colors=("#5a3578", "#caa6ff"),
        enabled=True,
        controller_factory=PatternRecallController,
        widget_kind="memory",
        music_profile="memory",
    ),
    TrainingGameSpec(
        game_id="candy_cascade",
        section="Memory and cognitive control",
        eyebrow="Cascade logic",
        card_title="Candy Cascade",
        detail_title="A match-3 board for swap selection, cascades, and blocker clearing",
        duration="10 min",
        description="Cycle through legal swaps, lock in the best move, and clear blockers through cascading matches.",
        detail_body=(
            "Candy Cascade adapts match-3 play to EEG control. Concentration cycles forward through legal swaps, "
            "relaxation cycles backward, and a balanced confirm hold commits the highlighted move and resolves the board."
        ),
        instructions=(
            "Concentrate to cycle forward through legal swaps, relax to cycle backward, and hold a balanced steady "
            "state to confirm the highlighted move. Clear blockers while building enough score to finish the board."
        ),
        calibration_copy="Build a neutral baseline first so swap cycling and confirm holds stay reliable.",
        preview_label="MATCH",
        colors=("#7a2f52", "#ffc978"),
        enabled=True,
        controller_factory=CandyCascadeController,
        widget_kind="candy_cascade",
        music_profile="memory",
    ),
]


def active_training_specs() -> list[TrainingGameSpec]:
    return [spec for spec in TRAINING_SPECS if spec.enabled]
