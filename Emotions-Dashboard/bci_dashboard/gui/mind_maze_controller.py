"""
Mind Maze gameplay and calibration logic.

This module is intentionally Qt-free so the core rules can be tested without
rendering the UI.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import DefaultDict

from gui.eeg_game_base import (
    CalibrationSnapshot,
    GameplaySnapshot,
    LevelResult,
    TrainingLevel,
    TrainingRunResult,
)


Coord = tuple[int, int]

DIR_VECTORS: dict[str, Coord] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

DIR_LABELS = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    None: "Hold steady",
}

OPPOSITE = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}

CALIBRATION_SAMPLES = 20
READY_STREAK_TARGET = 3
READY_DELTA_THRESHOLD = -2.0
VERTICAL_BALANCE_THRESHOLD = 1.1
HORIZONTAL_BALANCE_THRESHOLD = 0.9
VERTICAL_DELTA_THRESHOLD = 0.2
HORIZONTAL_DELTA_THRESHOLD = 0.1

PHASE_LABELS = {
    "vertical": "Vertical Ascent",
    "horizontal": "Horizontal Navigation",
    "free": "Adaptive Turn",
}

MindMazeRunResult = TrainingRunResult


@dataclass(frozen=True)
class MazeLevel(TrainingLevel):
    width: int
    height: int
    active_cells: frozenset[Coord]
    passages: dict[Coord, frozenset[str]]
    start: Coord
    goal: Coord


def _direction_between(src: Coord, dst: Coord) -> str:
    dx = dst[0] - src[0]
    dy = dst[1] - src[1]
    for name, vector in DIR_VECTORS.items():
        if vector == (dx, dy):
            return name
    raise ValueError(f"Cells {src} and {dst} are not orthogonal neighbors")


def _build_level(
    title: str,
    start: Coord,
    goal: Coord,
    target_seconds: int,
    edges: list[tuple[Coord, Coord]],
) -> MazeLevel:
    passages: DefaultDict[Coord, set[str]] = defaultdict(set)
    active = {start, goal}
    max_x = 0
    max_y = 0
    for src, dst in edges:
        direction = _direction_between(src, dst)
        passages[src].add(direction)
        passages[dst].add(OPPOSITE[direction])
        active.add(src)
        active.add(dst)
        max_x = max(max_x, src[0], dst[0])
        max_y = max(max_y, src[1], dst[1])
    for cell in active:
        passages.setdefault(cell, set())
    frozen_passages = {cell: frozenset(ways) for cell, ways in passages.items()}
    return MazeLevel(
        title=title,
        width=max_x + 1,
        height=max_y + 1,
        active_cells=frozenset(active),
        passages=frozen_passages,
        start=start,
        goal=goal,
        target_seconds=target_seconds,
    )


DEFAULT_LEVELS = [
    _build_level(
        title="Level 1",
        start=(0, 4),
        goal=(4, 0),
        target_seconds=45,
        edges=[
            ((0, 4), (0, 3)),
            ((0, 3), (0, 2)),
            ((0, 2), (1, 2)),
            ((1, 2), (2, 2)),
            ((2, 2), (2, 1)),
            ((2, 1), (3, 1)),
            ((3, 1), (4, 1)),
            ((4, 1), (4, 0)),
            ((1, 2), (1, 3)),
            ((1, 3), (2, 3)),
            ((2, 3), (3, 3)),
            ((3, 3), (3, 2)),
            ((3, 2), (4, 2)),
            ((0, 2), (0, 1)),
            ((0, 1), (1, 1)),
        ],
    ),
    _build_level(
        title="Level 2",
        start=(0, 5),
        goal=(5, 0),
        target_seconds=60,
        edges=[
            ((0, 5), (1, 5)),
            ((1, 5), (1, 4)),
            ((1, 4), (1, 3)),
            ((1, 3), (2, 3)),
            ((2, 3), (3, 3)),
            ((3, 3), (3, 2)),
            ((3, 2), (4, 2)),
            ((4, 2), (4, 1)),
            ((4, 1), (5, 1)),
            ((5, 1), (5, 0)),
            ((1, 4), (2, 4)),
            ((2, 4), (3, 4)),
            ((3, 4), (4, 4)),
            ((4, 4), (4, 3)),
            ((2, 3), (2, 2)),
            ((2, 2), (1, 2)),
            ((1, 2), (1, 1)),
            ((1, 1), (2, 1)),
            ((4, 2), (5, 2)),
        ],
    ),
    _build_level(
        title="Level 3",
        start=(0, 6),
        goal=(6, 0),
        target_seconds=75,
        edges=[
            ((0, 6), (0, 5)),
            ((0, 5), (1, 5)),
            ((1, 5), (2, 5)),
            ((2, 5), (2, 4)),
            ((2, 4), (2, 3)),
            ((2, 3), (3, 3)),
            ((3, 3), (4, 3)),
            ((4, 3), (4, 2)),
            ((4, 2), (5, 2)),
            ((5, 2), (5, 1)),
            ((5, 1), (6, 1)),
            ((6, 1), (6, 0)),
            ((1, 5), (1, 4)),
            ((1, 4), (0, 4)),
            ((2, 4), (3, 4)),
            ((3, 4), (4, 4)),
            ((4, 4), (5, 4)),
            ((5, 4), (5, 3)),
            ((3, 3), (3, 2)),
            ((3, 2), (2, 2)),
            ((2, 2), (2, 1)),
            ((2, 1), (3, 1)),
            ((3, 1), (4, 1)),
            ((5, 2), (6, 2)),
        ],
    ),
]


class MindMazeController:
    def __init__(self, levels: list[MazeLevel] | None = None):
        self._levels = levels or DEFAULT_LEVELS
        self.reset_run()

    def reset_run(self):
        self._calibration_values: list[tuple[float, float]] = []
        self._ready_streak = 0
        self._conc_baseline: float | None = None
        self._relax_baseline: float | None = None
        self._level_index = 0
        self._player = self._levels[0].start
        self._last_intent: str | None = None
        self._intent_streak = 0
        self._last_phase: str | None = None
        self._results: list[LevelResult | None] = [None] * len(self._levels)
        self._finished = False
        self._view_state = {
            "level": self._levels[0],
            "player": self._levels[0].start,
            "goal": self._levels[0].goal,
            "hint_direction": None,
            "message": "",
        }

    @property
    def current_level(self) -> MazeLevel:
        return self._levels[self._level_index]

    @property
    def current_level_number(self) -> int:
        return self._level_index + 1

    @property
    def player(self) -> Coord:
        return self._player

    @property
    def goal(self) -> Coord:
        return self.current_level.goal

    @property
    def view_state(self) -> dict:
        return self._view_state

    @property
    def conc_baseline(self) -> float | None:
        return self._conc_baseline

    @property
    def relax_baseline(self) -> float | None:
        return self._relax_baseline

    def begin_calibration(self):
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
                status = "Signal stable. Hold steady to start the maze."
            else:
                self._ready_streak = 0
                status = "Relax slightly more and keep the signal steady to unlock the maze."
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

    def start_game(self):
        self._level_index = 0
        self._player = self._levels[0].start
        self._last_intent = None
        self._intent_streak = 0
        self._last_phase = None
        self._results = [None] * len(self._levels)
        self._finished = False
        self._view_state = {
            "level": self.current_level,
            "player": self._player,
            "goal": self.current_level.goal,
            "hint_direction": None,
            "message": "",
        }

    def compute_intent(
        self,
        conc_delta: float,
        relax_delta: float,
        phase: str = "free",
        valid_exits: tuple[str, ...] | None = None,
        recommended_direction: str | None = None,
    ) -> str | None:
        balance = conc_delta - relax_delta
        exits = set(valid_exits or ("up", "down", "left", "right"))
        if phase == "horizontal":
            if "right" in exits and balance >= HORIZONTAL_BALANCE_THRESHOLD and conc_delta >= HORIZONTAL_DELTA_THRESHOLD:
                return "right"
            if "left" in exits and balance <= -HORIZONTAL_BALANCE_THRESHOLD and relax_delta >= HORIZONTAL_DELTA_THRESHOLD:
                return "left"
            return None
        if phase == "vertical":
            if "up" in exits and balance >= VERTICAL_BALANCE_THRESHOLD and conc_delta >= VERTICAL_DELTA_THRESHOLD:
                return "up"
            if "down" in exits and balance <= -VERTICAL_BALANCE_THRESHOLD and relax_delta >= VERTICAL_DELTA_THRESHOLD:
                return "down"
            return None

        if recommended_direction in {"up", "right"} and balance >= HORIZONTAL_BALANCE_THRESHOLD:
            if recommended_direction in exits:
                return recommended_direction
        if recommended_direction in {"down", "left"} and balance <= -HORIZONTAL_BALANCE_THRESHOLD:
            if recommended_direction in exits:
                return recommended_direction
        if "up" in exits and balance >= VERTICAL_BALANCE_THRESHOLD and conc_delta >= VERTICAL_DELTA_THRESHOLD:
            return "up"
        if "right" in exits and balance >= HORIZONTAL_BALANCE_THRESHOLD and conc_delta >= HORIZONTAL_DELTA_THRESHOLD:
            return "right"
        if "left" in exits and balance <= -HORIZONTAL_BALANCE_THRESHOLD and relax_delta >= HORIZONTAL_DELTA_THRESHOLD:
            return "left"
        if "down" in exits and balance <= -VERTICAL_BALANCE_THRESHOLD and relax_delta >= VERTICAL_DELTA_THRESHOLD:
            return "down"
        return None

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
        phase, valid_exits, recommended_direction, control_hint = self.movement_policy()
        direction = None
        moved = False
        blocked_reason = ""
        level_completed = False
        run_completed = False

        if phase != self._last_phase:
            self._intent_streak = 0
            self._last_intent = None
            self._last_phase = phase

        if stale:
            self._intent_streak = 0
            self._last_intent = None
            blocked_reason = "Metrics are stale. Hold position."
        elif not valid:
            self._intent_streak = 0
            self._last_intent = None
            blocked_reason = "Artifacts detected. Movement paused."
        else:
            direction = self.compute_intent(
                conc_delta,
                relax_delta,
                phase=phase,
                valid_exits=valid_exits,
                recommended_direction=recommended_direction,
            )
            if direction is None:
                self._intent_streak = 0
                self._last_intent = None
            else:
                if direction == self._last_intent:
                    self._intent_streak += 1
                else:
                    self._last_intent = direction
                    self._intent_streak = 1

                if self._intent_streak >= 2:
                    moved = self._attempt_move(direction)
                    self._intent_streak = 0
                    self._last_intent = None
                    if not moved:
                        blocked_reason = "Blocked corridor. Follow the highlighted direction hint."

            if self._player == self.current_level.goal:
                level_completed = True
                self._record_level_result(completed=True, elapsed_seconds=elapsed_seconds)
                if self._level_index == len(self._levels) - 1:
                    self._finished = True
                    run_completed = True
                else:
                    self._level_index += 1
                    self._player = self.current_level.start
                    self._intent_streak = 0
                    self._last_intent = None
                    self._last_phase = None

        if level_completed and not run_completed:
            phase, valid_exits, recommended_direction, control_hint = self.movement_policy()

        view_state = {
            "level": self.current_level,
            "player": self._player,
            "goal": self.current_level.goal,
            "hint_direction": recommended_direction,
            "message": blocked_reason,
        }
        self._view_state = view_state
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase=phase,
            phase_label=PHASE_LABELS[phase],
            recommended_direction=recommended_direction,
            recommended_label=DIR_LABELS[recommended_direction],
            control_hint=control_hint,
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

    def finish_run(
        self,
        current_elapsed_seconds: float | None,
        aborted: bool,
    ) -> MindMazeRunResult:
        if aborted and not self._finished:
            self._record_level_result(completed=False, elapsed_seconds=current_elapsed_seconds or 0.0)

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
        return MindMazeRunResult(
            level_results=normalized_results,
            final_score=final_score,
            completion_pct=completion_pct,
            total_seconds=total_seconds,
        )

    def movement_policy(self) -> tuple[str, tuple[str, ...], str | None, str]:
        valid_exits = tuple(sorted(self.current_level.passages.get(self._player, frozenset())))
        recommended = self._recommended_direction()
        horizontal = {"left", "right"} & set(valid_exits)
        vertical = {"up", "down"} & set(valid_exits)

        if recommended in horizontal:
            phase = "horizontal"
        elif recommended in vertical:
            phase = "vertical"
        elif horizontal and not vertical:
            phase = "horizontal"
        elif vertical and not horizontal:
            phase = "vertical"
        else:
            phase = "free"

        return phase, valid_exits, recommended, self._control_hint(phase, recommended, valid_exits)

    def _neighbors(self, cell: Coord) -> list[Coord]:
        neighbors = []
        for direction in self.current_level.passages.get(cell, frozenset()):
            dx, dy = DIR_VECTORS[direction]
            next_cell = (cell[0] + dx, cell[1] + dy)
            if next_cell in self.current_level.active_cells:
                neighbors.append(next_cell)
        return neighbors

    def _recommended_direction(self) -> str | None:
        if self._player == self.current_level.goal:
            return None
        queue = deque([(self._player, None)])
        visited = {self._player}
        parent: dict[Coord, Coord | None] = {self._player: None}
        while queue:
            cell, _ = queue.popleft()
            if cell == self.current_level.goal:
                break
            for neighbor in self._neighbors(cell):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                parent[neighbor] = cell
                queue.append((neighbor, cell))
        if self.current_level.goal not in parent:
            return None
        cursor = self.current_level.goal
        while parent[cursor] != self._player:
            cursor_parent = parent[cursor]
            if cursor_parent is None:
                return None
            cursor = cursor_parent
        return _direction_between(self._player, cursor)

    def _control_hint(self, phase: str, recommended: str | None, valid_exits: tuple[str, ...]) -> str:
        if phase == "horizontal":
            if recommended == "right":
                return "Move right: concentrate to advance, relax to drift left."
            if recommended == "left":
                return "Move left: relax to backtrack, concentrate to return right."
            return "Horizontal corridor: concentrate for right, relax for left."
        if phase == "vertical":
            if recommended == "up":
                return "Climb the corridor: concentrate to move up."
            if recommended == "down":
                return "Turn down: relax to drop through the corridor."
            return "Vertical corridor: concentrate for up, relax for down."
        if recommended is not None:
            return f"Adaptive turn: aim for {DIR_LABELS[recommended]} with a stable balance shift."
        if len(valid_exits) == 1:
            return f"Only {DIR_LABELS[valid_exits[0]]} is open from this cell."
        return "Adaptive turn: use concentration and relaxation to pick the next corridor."

    def _attempt_move(self, direction: str) -> bool:
        current_passages = self.current_level.passages.get(self._player, frozenset())
        if direction not in current_passages:
            return False
        dx, dy = DIR_VECTORS[direction]
        next_cell = (self._player[0] + dx, self._player[1] + dy)
        if next_cell not in self.current_level.active_cells:
            return False
        self._player = next_cell
        return True

    def _record_level_result(self, completed: bool, elapsed_seconds: float):
        index = self._level_index
        if self._results[index] is not None:
            return
        level = self._levels[index]
        elapsed_int = max(0, int(round(elapsed_seconds)))
        score = 0
        if completed:
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
