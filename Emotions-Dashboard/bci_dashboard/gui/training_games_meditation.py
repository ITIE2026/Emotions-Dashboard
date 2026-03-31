"""Meditation, relaxation, and assistive motor-control game controllers."""
from __future__ import annotations

import math

from gui.eeg_game_base import (
    GameplaySnapshot,
    LevelResult,
    TrainingLevel,
    TrainingRunResult,
)
from gui.training_games_base import BaseTrainingController, DIR_LABELS
from prosthetic_arm.arm_state import ArmStateEngine, dominant_state_for_metrics, state_label


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
            direction_label=DIR_LABELS.get(direction, "Hold steady"),
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


class NeuroMusicFlowController(BaseTrainingController):
    LEVELS = [TrainingLevel("Neuro Music Flow", 600)]
    BANDS = ("delta", "theta", "alpha", "smr", "beta")

    def __init__(self):
        self._latest_band_powers = {band: 0.0 for band in self.BANDS}
        super().__init__(self.LEVELS)

    def reset_run(self) -> None:
        self._latest_band_powers = {band: 0.0 for band in self.BANDS}
        self._band_totals = {band: 0.0 for band in self.BANDS}
        self._dominant_band_counts = {band: 0 for band in self.BANDS}
        self._sample_count = 0
        self._conc_sum = 0.0
        self._relax_sum = 0.0
        self._serenity_sum = 0.0
        self._restlessness_sum = 0.0
        self._focus_balance_sum = 0.0
        super().reset_run()

    def ingest_band_powers(self, band_powers: dict | None) -> None:
        band_powers = band_powers or {}
        for band in self.BANDS:
            incoming = max(0.0, float(band_powers.get(band, 0.0)))
            previous = self._latest_band_powers.get(band, 0.0)
            self._latest_band_powers[band] = (previous * 0.72) + (incoming * 0.28)

    def session_summary(self, total_seconds: int | float | None = None) -> dict:
        total_seconds = max(0, int(round(float(total_seconds or 0.0))))
        samples = max(1, self._sample_count)
        dominant_band = max(self._dominant_band_counts, key=self._dominant_band_counts.get)
        if self._dominant_band_counts[dominant_band] <= 0:
            dominant_band = max(self._band_totals, key=self._band_totals.get)
        return {
            "total_seconds": total_seconds,
            "avg_concentration": self._conc_sum / samples,
            "avg_relaxation": self._relax_sum / samples,
            "avg_serenity": self._serenity_sum / samples,
            "avg_restlessness": self._restlessness_sum / samples,
            "focus_balance": self._focus_balance_sum / samples,
            "dominant_band": dominant_band,
            "dominant_band_label": dominant_band.replace("_", " ").title(),
            "dominant_mode": self._dominant_mode if self._sample_count else "Balanced flow",
        }

    def finish_run(
        self,
        current_elapsed_seconds: float | None,
        aborted: bool,
    ) -> TrainingRunResult:
        elapsed_seconds = float(current_elapsed_seconds or 0.0)
        if not elapsed_seconds and self._finished:
            elapsed_seconds = float(self.current_level.target_seconds)
        elapsed_int = max(0, int(round(elapsed_seconds)))
        completion = min(1.0, elapsed_int / max(1, self.current_level.target_seconds))
        summary = self.session_summary(elapsed_int)
        score = max(0, min(100, int(round(summary["avg_serenity"]))))
        level_result = LevelResult(
            level_number=1,
            title=self.current_level.title,
            completed=bool(not aborted and elapsed_int >= self.current_level.target_seconds),
            elapsed_seconds=elapsed_int,
            target_seconds=self.current_level.target_seconds,
            score=score,
        )
        return TrainingRunResult(
            level_results=[level_result],
            final_score=score,
            completion_pct=int(round(completion * 100)),
            total_seconds=elapsed_int,
        )

    def _reset_level_state(self) -> None:
        self._serenity = 52.0
        self._restlessness = 18.0
        self._focus_balance = 0.0
        self._pulse_phase = 0.0
        self._dominant_mode = "Balanced flow"
        self._message = "Hold a steady, comfortable state and let the music adapt."
        self._view_state = self._music_view_state()

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
        moved = False
        direction = None
        recommended_label = "Balanced flow"
        control_hint = "Concentration brightens the track. Relaxation softens and deepens it."
        level_completed = False
        run_completed = False

        band_total = sum(max(0.0, value) for value in self._latest_band_powers.values())
        if band_total > 1e-9:
            normalized_bands = {band: value / band_total for band, value in self._latest_band_powers.items()}
        else:
            normalized_bands = {band: 0.0 for band in self.BANDS}

        focus_drive = (
            max(0.0, conc_delta) * 0.15
            + (normalized_bands["beta"] * 0.78)
            + (normalized_bands["smr"] * 0.54)
            + (normalized_bands["alpha"] * 0.16)
        )
        calm_drive = (
            max(0.0, relax_delta) * 0.15
            + (normalized_bands["theta"] * 0.74)
            + (normalized_bands["delta"] * 0.62)
            + (normalized_bands["alpha"] * 0.20)
        )

        self._pulse_phase = (math.sin(elapsed_seconds / 2.3) + 1.0) / 2.0

        if stale:
            blocked_reason = "Metrics are stale. Holding the current music texture."
        elif not valid:
            blocked_reason = "Artifacts detected. Holding the current music texture."
        else:
            serenity_target = 42.0 + (calm_drive * 54.0) - (focus_drive * 10.0)
            restlessness_target = 16.0 + (focus_drive * 44.0) - (calm_drive * 10.0)
            self._serenity += (max(0.0, min(100.0, serenity_target)) - self._serenity) * 0.16
            self._restlessness += (max(0.0, min(100.0, restlessness_target)) - self._restlessness) * 0.16
            self._focus_balance = max(-100.0, min(100.0, (focus_drive - calm_drive) * 100.0))
            if focus_drive > calm_drive + 0.08:
                self._dominant_mode = "Focused lift"
                self._message = "The mix is brightening. Stay clear and steady to keep the pulse alive."
                direction = "flow"
                recommended_label = "Focus lift"
            elif calm_drive > focus_drive + 0.08:
                self._dominant_mode = "Calm drift"
                self._message = "The mix is deepening. Softer breathing will keep the texture warm and wide."
                direction = "steady"
                recommended_label = "Calm drift"
            else:
                self._dominant_mode = "Balanced flow"
                self._message = "You are holding a balanced blend. Keep the state comfortable and stable."
                direction = "steady"
                recommended_label = "Balanced flow"

            dominant_band = max(self._latest_band_powers, key=self._latest_band_powers.get)
            self._dominant_band_counts[dominant_band] += 1
            for band, value in self._latest_band_powers.items():
                self._band_totals[band] += value
            self._sample_count += 1
            self._conc_sum += concentration
            self._relax_sum += relaxation
            self._serenity_sum += self._serenity
            self._restlessness_sum += self._restlessness
            self._focus_balance_sum += self._focus_balance
            moved = True

            if elapsed_seconds >= self.current_level.target_seconds:
                level_completed = True
                run_completed = True
                self._finished = True
                self._message = "Session complete. The music flow has been captured."

        self._view_state = self._music_view_state(message=blocked_reason)
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase="music_flow",
            phase_label=self.current_level.title,
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

    def _music_view_state(self, message: str = "") -> dict:
        total = sum(max(0.0, value) for value in self._latest_band_powers.values())
        if total > 1e-9:
            band_profile = {band: value / total for band, value in self._latest_band_powers.items()}
        else:
            band_profile = {band: 0.0 for band in self.BANDS}
        dominant_band = max(self._latest_band_powers, key=self._latest_band_powers.get)
        return {
            "mode": "music_flow",
            "headline": self.current_level.title,
            "serenity": self._serenity,
            "restlessness": self._restlessness,
            "focus_balance": self._focus_balance,
            "dominant_mode": self._dominant_mode,
            "dominant_band": dominant_band,
            "band_powers": dict(self._latest_band_powers),
            "band_profile": band_profile,
            "pulse_phase": self._pulse_phase,
            "session_progress": min(1.0, self._sample_count / max(1.0, self.current_level.target_seconds * 4.0)),
            "music_scene": "music_flow",
            "music_bias": max(-1.0, min(1.0, -self._focus_balance / 100.0)),
            "message": message or self._message,
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
            direction_label=DIR_LABELS.get(target_state.lower(), "Hold steady"),
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
