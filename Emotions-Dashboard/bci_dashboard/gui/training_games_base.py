"""Base controller and shared constants for EEG training games."""
from __future__ import annotations

from gui.eeg_game_base import (
    CALIBRATION_SAMPLES,
    READY_DELTA_THRESHOLD,
    READY_STREAK_TARGET,
    CalibrationSnapshot,
    GameplaySnapshot,
    LevelResult,
    TrainingLevel,
    TrainingRunResult,
)


DIR_LABELS = {
    None: "Hold steady",
    "left": "Backtrack",
    "right": "Advance",
    "focus": "Focus pull",
    "calm": "Calm pull",
    "player": "Player pull",
    "system": "System push",
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
    "storm": "Storm",
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
            direction_label=DIR_LABELS.get(None, "Hold steady"),
            moved=False,
            blocked_reason="",
            conc_delta=0.0,
            relax_delta=0.0,
            balance=0.0,
            level_completed=False,
            run_completed=False,
            view_state=self._view_state,
        )
