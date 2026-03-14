"""
Shared datatypes and controller contract for EEG training games.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


CALIBRATION_SAMPLES = 20
READY_STREAK_TARGET = 3
READY_DELTA_THRESHOLD = -2.0


@dataclass(frozen=True)
class TrainingLevel:
    title: str
    target_seconds: int


@dataclass(frozen=True)
class CalibrationSnapshot:
    progress: float
    sample_count: int
    samples_needed: int
    ready_streak: int
    conc_baseline: float | None
    relax_baseline: float | None
    ready_delta: float
    complete: bool
    status: str


@dataclass(frozen=True)
class GameplaySnapshot:
    level_number: int
    phase: str
    phase_label: str
    recommended_direction: str | None
    recommended_label: str
    control_hint: str
    direction: str | None
    direction_label: str
    moved: bool
    blocked_reason: str
    conc_delta: float
    relax_delta: float
    balance: float
    level_completed: bool
    run_completed: bool
    view_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LevelResult:
    level_number: int
    title: str
    completed: bool
    elapsed_seconds: int
    target_seconds: int
    score: int


@dataclass(frozen=True)
class TrainingRunResult:
    level_results: list[LevelResult]
    final_score: int
    completion_pct: int
    total_seconds: int


class EEGGameController(Protocol):
    @property
    def current_level(self) -> TrainingLevel: ...

    @property
    def current_level_number(self) -> int: ...

    @property
    def conc_baseline(self) -> float | None: ...

    @property
    def relax_baseline(self) -> float | None: ...

    def reset_run(self) -> None: ...

    def begin_calibration(self) -> None: ...

    def add_calibration_sample(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
    ) -> CalibrationSnapshot: ...

    def start_game(self) -> None: ...

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot: ...

    def finish_run(
        self,
        current_elapsed_seconds: float | None,
        aborted: bool,
    ) -> TrainingRunResult: ...


@dataclass(frozen=True)
class TrainingGameSpec:
    game_id: str
    section: str
    eyebrow: str
    card_title: str
    detail_title: str
    duration: str
    description: str
    detail_body: str
    instructions: str
    calibration_copy: str
    preview_label: str
    colors: tuple[str, str]
    enabled: bool
    controller_factory: Callable[[], EEGGameController]
    widget_kind: str
    soundtrack_enabled: bool = True
    music_profile: str = "focus"
