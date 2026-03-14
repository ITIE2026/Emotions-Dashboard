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


DIR_LABELS = {
    None: "Hold steady",
    "left": "Backtrack",
    "right": "Advance",
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
        TrainingLevel("Sector 1", 50),
        TrainingLevel("Sector 2", 60),
        TrainingLevel("Sector 3", 70),
    ]
    CONFIGS = [
        {"track_length": 96.0, "enemies": [(16.0, 1), (30.0, 0), (44.0, 2), (58.0, 1), (72.0, 0), (86.0, 2)]},
        {
            "track_length": 118.0,
            "enemies": [(14.0, 1), (26.0, 2), (38.0, 0), (50.0, 1), (64.0, 2), (78.0, 0), (92.0, 1), (108.0, 2)],
        },
        {
            "track_length": 138.0,
            "enemies": [
                (12.0, 1),
                (24.0, 0),
                (34.0, 2),
                (46.0, 1),
                (58.0, 0),
                (70.0, 2),
                (82.0, 1),
                (94.0, 0),
                (108.0, 2),
                (124.0, 1),
            ],
        },
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._track_length = config["track_length"]
        self._progress = 0.0
        self._ship_lane = 1
        self._charge = 26.0
        self._shield = 12.0
        self._integrity = 100.0
        self._shots_fired = 0
        self._destroyed = 0
        self._blocked = 0
        self._damage_taken = 0
        self._streak = 0
        self._best_streak = 0
        self._enemies = [
            {"progress_mark": mark, "lane": lane, "status": "active"}
            for mark, lane in config["enemies"]
        ]
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
        control_hint = (
            "Concentrate to climb and charge, relax to descend and build shield, and hold steady to fire when an enemy lines up."
        )

        if stale:
            blocked_reason = "Metrics are stale. Shooter paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Shooter paused."
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                self._progress += 4.4
                if self._stabilize_intent(intent):
                    self._ship_lane = max(0, self._ship_lane - 1)
                    self._charge = min(100.0, self._charge + 24.0)
                    self._shield = max(0.0, self._shield - 6.0)
                    action = "boost"
                    moved = True
            elif intent == "relax":
                self._progress += 3.7
                if self._stabilize_intent(intent):
                    self._ship_lane = min(2, self._ship_lane + 1)
                    self._shield = min(100.0, self._shield + 22.0)
                    self._charge = max(0.0, self._charge - 4.0)
                    action = "shield"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    action = "fire"
                    moved = True
                    self._fire_if_aligned()
                self._progress += 3.9
                self._charge = max(0.0, self._charge - 1.5)
                self._shield = max(0.0, self._shield - 1.0)
            else:
                self._stabilize_intent(None)
                self._progress += 3.2
                self._charge = max(0.0, self._charge - 0.7)
                self._shield = max(0.0, self._shield - 0.6)

            self._resolve_passed_enemies()
            self._progress = min(self._track_length, self._progress)

            if self._progress >= self._track_length:
                total_enemies = max(1, len(self._enemies))
                combat_ratio = (self._destroyed + (self._blocked * 0.7)) / total_enemies
                integrity_bonus = self._integrity * 0.22
                streak_bonus = min(18.0, self._best_streak * 2.4)
                damage_penalty = self._damage_taken * 2.0
                time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
                score = 40 + (combat_ratio * 35.0) + integrity_bonus + streak_bonus - damage_penalty - time_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

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

    def _fire_if_aligned(self) -> None:
        self._shots_fired += 1
        if self._charge < 18.0:
            self._streak = 0
            return

        for enemy in self._enemies:
            if enemy["status"] != "active":
                continue
            distance = enemy["progress_mark"] - self._progress
            if 0.0 <= distance <= 8.0 and enemy["lane"] == self._ship_lane:
                enemy["status"] = "destroyed"
                self._charge = max(0.0, self._charge - 18.0)
                self._destroyed += 1
                self._streak += 1
                self._best_streak = max(self._best_streak, self._streak)
                return

        self._streak = 0

    def _resolve_passed_enemies(self) -> None:
        for enemy in self._enemies:
            if enemy["status"] != "active":
                continue
            if enemy["progress_mark"] > (self._progress - 4.0):
                continue
            if enemy["lane"] == self._ship_lane:
                if self._shield >= 16.0:
                    enemy["status"] = "blocked"
                    self._shield = max(0.0, self._shield - 16.0)
                    self._blocked += 1
                else:
                    enemy["status"] = "hit"
                    self._integrity = max(0.0, self._integrity - 14.0)
                    self._damage_taken += 1
                    self._streak = 0
            else:
                enemy["status"] = "passed"

    def _space_recommendation(self, action: str | None) -> str:
        if action == "boost":
            return "Charge high lane"
        if action == "shield":
            return "Shield low lane"
        if action == "fire":
            return "Fire window"
        for enemy in self._enemies:
            if enemy["status"] != "active":
                continue
            lane_diff = enemy["lane"] - self._ship_lane
            distance = enemy["progress_mark"] - self._progress
            if distance <= 12.0 and abs(lane_diff) <= 1:
                if lane_diff < 0:
                    return "Climb to target"
                if lane_diff > 0:
                    return "Drop to shield"
                return "Hold steady to fire"
            break
        return "Build charge"

    def _space_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "space_shooter",
            "ship_lane": self._ship_lane,
            "charge": self._charge,
            "shield": self._shield,
            "integrity": self._integrity,
            "progress": self._progress,
            "track_length": self._track_length,
            "streak": self._streak,
            "best_streak": self._best_streak,
            "shots_fired": self._shots_fired,
            "destroyed": self._destroyed,
            "blocked": self._blocked,
            "music_scene": "space_run",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, self._integrity - (self._damage_taken * 4.0))),
            "restlessness": max(0.0, min(100.0, 24.0 + (self._damage_taken * 9.0))),
            "enemies": [dict(enemy) for enemy in self._enemies if enemy["status"] == "active"],
            "message": message,
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
        TrainingLevel("Lap 1", 50),
        TrainingLevel("Lap 2", 60),
        TrainingLevel("Lap 3", 70),
    ]
    CONFIGS = [
        {"track_length": 104.0, "hazards": [(18.0, 1, 64.0), (36.0, 0, 72.0), (56.0, 2, 58.0), (80.0, 1, 66.0)]},
        {
            "track_length": 122.0,
            "hazards": [(16.0, 1, 62.0), (30.0, 0, 74.0), (46.0, 2, 60.0), (66.0, 1, 68.0), (90.0, 0, 76.0)],
        },
        {
            "track_length": 140.0,
            "hazards": [(14.0, 1, 64.0), (28.0, 0, 76.0), (42.0, 2, 58.0), (58.0, 1, 70.0), (78.0, 0, 78.0), (104.0, 2, 62.0)],
        },
    ]

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._track_length = config["track_length"]
        self._progress = 0.0
        self._lane = 1
        self._speed = 58.0
        self._stability = 86.0
        self._combo = 0
        self._best_combo = 0
        self._clears = 0
        self._penalties = 0
        self._hazards = [
            {"progress_mark": mark, "lane": lane, "speed_limit": speed_limit, "status": "active"}
            for mark, lane, speed_limit in config["hazards"]
        ]
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
        control_hint = (
            "Concentrate to boost toward the fast line, relax to brake and recentre, and hold steady to keep the clean racing line."
        )

        if stale:
            blocked_reason = "Metrics are stale. Race paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Race paused."
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                if self._stabilize_intent(intent):
                    self._lane = max(0, self._lane - 1)
                    self._speed = min(100.0, self._speed + 10.0)
                    self._stability = max(0.0, self._stability - 2.0)
                    action = "boost"
                    moved = True
            elif intent == "relax":
                if self._stabilize_intent(intent):
                    self._lane = min(2, self._lane + 1)
                    self._speed = max(32.0, self._speed - 10.0)
                    self._stability = min(100.0, self._stability + 6.0)
                    action = "brake"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    self._speed = min(90.0, self._speed + 2.0)
                    self._stability = min(100.0, self._stability + 2.0)
                    action = "steady"
                    moved = True
            else:
                self._stabilize_intent(None)
                if self._speed > 62.0:
                    self._speed -= 2.5
                elif self._speed < 56.0:
                    self._speed += 1.5

            self._progress += self._speed / 14.0
            self._resolve_hazards()
            self._progress = min(self._track_length, self._progress)

            if self._progress >= self._track_length:
                total_hazards = max(1, len(self._hazards))
                clear_ratio = self._clears / total_hazards
                stability_bonus = self._stability * 0.24
                combo_bonus = min(18.0, self._best_combo * 2.2)
                penalty_cost = self._penalties * 5.0
                time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
                score = 42 + (clear_ratio * 34.0) + stability_bonus + combo_bonus - penalty_cost - time_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

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

    def _resolve_hazards(self) -> None:
        for hazard in self._hazards:
            if hazard["status"] != "active":
                continue
            if hazard["progress_mark"] > self._progress:
                continue
            if self._lane == hazard["lane"] and self._speed > hazard["speed_limit"]:
                hazard["status"] = "impact"
                self._penalties += 1
                self._stability = max(0.0, self._stability - 18.0)
                self._speed = max(34.0, self._speed - 12.0)
                self._combo = 0
            else:
                hazard["status"] = "clear"
                self._clears += 1
                self._combo += 1
                self._best_combo = max(self._best_combo, self._combo)
                self._stability = min(100.0, self._stability + 3.0)

    def _racer_recommendation(self, action: str | None) -> str:
        if action == "boost":
            return "Push the fast line"
        if action == "brake":
            return "Brake and recover"
        if action == "steady":
            return "Hold the line"
        for hazard in self._hazards:
            if hazard["status"] != "active":
                continue
            distance = hazard["progress_mark"] - self._progress
            if distance <= 18.0:
                if self._lane == hazard["lane"] and self._speed > hazard["speed_limit"]:
                    return "Brake now"
                if self._lane > hazard["lane"]:
                    return "Boost left lane"
                if self._lane < hazard["lane"]:
                    return "Relax to recover"
                return "Hold centre"
            break
        return "Build pace"

    def _racer_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "neuro_racer",
            "lane": self._lane,
            "speed": self._speed,
            "stability": self._stability,
            "progress": self._progress,
            "track_length": self._track_length,
            "combo": self._combo,
            "best_combo": self._best_combo,
            "clears": self._clears,
            "penalties": self._penalties,
            "music_scene": "arcade_race",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, self._stability)),
            "restlessness": max(0.0, min(100.0, 20.0 + (self._penalties * 12.0))),
            "hazards": [dict(hazard) for hazard in self._hazards if hazard["status"] == "active"],
            "message": message,
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
        detail_title="A lane shooter driven by focus, shield timing, and steady firing",
        duration="9 min",
        description="Climb, descend, and time clean shots as waves of enemies cross your flight lane.",
        detail_body=(
            "Space Shooter is an EEG-assisted arcade run built around reliable neurofeedback actions. Concentration "
            "pulls the ship upward and charges stronger shots, relaxation drops you lower and builds shield, and a "
            "balanced steady state turns that setup into precise firing windows."
        ),
        instructions=(
            "Concentrate to climb and charge. Relax to descend and build shield. When an enemy lines up in your lane, "
            "hold a balanced steady state to fire cleanly."
        ),
        calibration_copy="Settle into a stable baseline so lane changes, charge, and fire windows feel consistent.",
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
        detail_title="A lane racer for boost control, braking, and stable pacing",
        duration="10 min",
        description="Push into the fast line with focus, recover with calm braking, and hold the clean racing line.",
        detail_body=(
            "Neuro Racer uses EEG for speed management instead of twitch steering. Concentration boosts toward the fast "
            "line, relaxation brakes and recentres the car, and balanced control helps the player hold efficient pace "
            "through traffic and hazard zones."
        ),
        instructions=(
            "Concentrate to boost into the fast lane, relax to brake and recover, and hold a balanced steady state to "
            "keep the clean racing line through safer sections."
        ),
        calibration_copy="Build a stable baseline first so boost, brake, and line-holding cues stay readable.",
        preview_label="RACE",
        colors=("#27144b", "#f04868"),
        enabled=True,
        controller_factory=NeuroRacerController,
        widget_kind="neuro_racer",
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
]


def active_training_specs() -> list[TrainingGameSpec]:
    return [spec for spec in TRAINING_SPECS if spec.enabled]
