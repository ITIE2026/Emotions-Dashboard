from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, DefaultDict

import pygame


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
    return MazeLevel(
        title=title,
        width=max_x + 1,
        height=max_y + 1,
        active_cells=frozenset(active),
        passages={cell: frozenset(ways) for cell, ways in passages.items()},
        start=start,
        goal=goal,
        target_seconds=target_seconds,
    )


DEFAULT_LEVELS = [
    _build_level(
        "Level 1",
        (0, 4),
        (4, 0),
        45,
        [
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
        "Level 2",
        (0, 5),
        (5, 0),
        60,
        [
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
        "Level 3",
        (0, 6),
        (6, 0),
        75,
        [
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

    def reset_run(self) -> None:
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
    def view_state(self) -> dict[str, Any]:
        return self._view_state

    @property
    def conc_baseline(self) -> float | None:
        return self._conc_baseline

    @property
    def relax_baseline(self) -> float | None:
        return self._relax_baseline

    def begin_calibration(self) -> None:
        self._calibration_values = []
        self._ready_streak = 0
        self._conc_baseline = None
        self._relax_baseline = None

    def bootstrap_demo_baseline(self, concentration: float = 50.0, relaxation: float = 52.0) -> None:
        self._conc_baseline = concentration
        self._relax_baseline = relaxation
        self._ready_streak = READY_STREAK_TARGET

    def add_calibration_sample(self, concentration: float, relaxation: float, valid: bool) -> CalibrationSnapshot:
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
            ready_delta = (relaxation - self._relax_baseline) - (concentration - self._conc_baseline)
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

    def start_game(self) -> None:
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
        if recommended_direction in {"up", "right"} and balance >= HORIZONTAL_BALANCE_THRESHOLD and recommended_direction in exits:
            return recommended_direction
        if recommended_direction in {"down", "left"} and balance <= -HORIZONTAL_BALANCE_THRESHOLD and recommended_direction in exits:
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

            level_completed, run_completed = self._check_completion(elapsed_seconds)

        if level_completed and not run_completed:
            phase, valid_exits, recommended_direction, control_hint = self.movement_policy()

        view_state = self._build_view_state(recommended_direction, blocked_reason)
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

    def manual_move(self, direction: str, elapsed_seconds: float) -> GameplaySnapshot:
        moved = self._attempt_move(direction)
        blocked_reason = "" if moved else "Blocked corridor. Follow the highlighted direction hint."
        level_completed, run_completed = self._check_completion(elapsed_seconds)
        phase, _, recommended_direction, control_hint = self.movement_policy()
        view_state = self._build_view_state(recommended_direction, blocked_reason)
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
            conc_delta=0.0,
            relax_delta=0.0,
            balance=0.0,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=view_state,
        )

    def finish_run(self, current_elapsed_seconds: float | None, aborted: bool) -> TrainingRunResult:
        if aborted and not self._finished:
            self._record_level_result(False, current_elapsed_seconds or 0.0)
        normalized_results: list[LevelResult] = []
        for index, existing in enumerate(self._results):
            if existing is None:
                level = self._levels[index]
                existing = LevelResult(index + 1, level.title, False, 0, level.target_seconds, 0)
            normalized_results.append(existing)
        completed_count = sum(1 for item in normalized_results if item.completed)
        total_seconds = sum(item.elapsed_seconds for item in normalized_results)
        final_score = round(sum(item.score for item in normalized_results) / len(normalized_results))
        completion_pct = round((completed_count / len(normalized_results)) * 100)
        return TrainingRunResult(normalized_results, final_score, completion_pct, total_seconds)

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
        queue = deque([self._player])
        visited = {self._player}
        parent: dict[Coord, Coord | None] = {self._player: None}
        while queue:
            cell = queue.popleft()
            if cell == self.current_level.goal:
                break
            for neighbor in self._neighbors(cell):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                parent[neighbor] = cell
                queue.append(neighbor)
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

    def _check_completion(self, elapsed_seconds: float) -> tuple[bool, bool]:
        level_completed = False
        run_completed = False
        if self._player == self.current_level.goal:
            level_completed = True
            self._record_level_result(True, elapsed_seconds)
            if self._level_index == len(self._levels) - 1:
                self._finished = True
                run_completed = True
            else:
                self._level_index += 1
                self._player = self.current_level.start
                self._intent_streak = 0
                self._last_intent = None
                self._last_phase = None
        return level_completed, run_completed

    def _build_view_state(self, recommended_direction: str | None, blocked_reason: str) -> dict[str, Any]:
        self._view_state = {
            "level": self.current_level,
            "player": self._player,
            "goal": self.current_level.goal,
            "hint_direction": recommended_direction,
            "message": blocked_reason,
        }
        return self._view_state

    def _record_level_result(self, completed: bool, elapsed_seconds: float) -> None:
        index = self._level_index
        if self._results[index] is not None:
            return
        level = self._levels[index]
        elapsed_int = max(0, int(round(elapsed_seconds)))
        score = 0
        if completed:
            penalty = max(0, elapsed_int - level.target_seconds)
            score = max(20, 100 - penalty)
        self._results[index] = LevelResult(index + 1, level.title, completed, elapsed_int, level.target_seconds, score)


def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_text_lines(
    surface: pygame.Surface,
    font: pygame.font.Font,
    lines: list[str],
    color: tuple[int, int, int],
    origin: tuple[int, int],
    line_gap: int = 4,
) -> None:
    x, y = origin
    for line in lines:
        rendered = font.render(line, True, color)
        surface.blit(rendered, (x, y))
        y += rendered.get_height() + line_gap


def draw_balance_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    panel: dict[str, Any] | None,
    fonts: dict[str, pygame.font.Font],
) -> None:
    if not panel:
        return

    muted = bool(panel.get("muted", False))
    balance = float(panel.get("balance", 0.0))
    conc_delta = float(panel.get("conc_delta", 0.0))
    relax_delta = float(panel.get("relax_delta", 0.0))
    timer_text = str(panel.get("timer_text", "00:00"))
    headline = str(panel.get("headline", "Hold steady"))
    status = str(panel.get("status", "Waiting for live concentration and relaxation."))
    countdown_ratio = max(0.0, min(1.0, float(panel.get("countdown_ratio", 0.0))))

    bg = (35, 40, 50) if muted else (9, 12, 20)
    border = (121, 130, 146) if muted else (92, 104, 134)
    text_primary = (248, 250, 252)
    text_secondary = (192, 199, 210) if muted else (185, 200, 232)

    pygame.draw.rect(surface, bg, rect, border_radius=24)
    pygame.draw.rect(surface, border, rect, width=2, border_radius=24)

    timer_surface = fonts["timer"].render(timer_text, True, text_primary)
    timer_rect = timer_surface.get_rect(center=(rect.centerx, rect.y + 26))
    surface.blit(timer_surface, timer_rect)

    progress_rect = pygame.Rect(rect.x + 42, rect.y + 48, rect.width - 84, 6)
    pygame.draw.rect(surface, (255, 255, 255, 24), progress_rect, border_radius=4)
    fill_width = int(progress_rect.width * countdown_ratio)
    if fill_width > 0:
        fill_rect = pygame.Rect(progress_rect.x, progress_rect.y, fill_width, progress_rect.height)
        pygame.draw.rect(surface, (245, 243, 183) if not muted else (156, 163, 175), fill_rect, border_radius=4)

    header_surface = fonts["small"].render(headline, True, text_secondary)
    header_rect = header_surface.get_rect(center=(rect.centerx, rect.y + 70))
    surface.blit(header_surface, header_rect)

    track_rect = pygame.Rect(rect.x + 18, rect.y + 92, rect.width - 36, 14)
    left_rect = pygame.Rect(track_rect.x, track_rect.y, track_rect.width // 2, track_rect.height)
    right_rect = pygame.Rect(track_rect.centerx, track_rect.y, track_rect.width - track_rect.width // 2, track_rect.height)
    left_color = (89, 97, 109) if muted else (154, 247, 170)
    mid_color = (89, 97, 109) if muted else (245, 243, 183)
    right_color = (89, 97, 109) if muted else (247, 97, 97)
    pygame.draw.rect(surface, left_color, left_rect, border_radius=7)
    pygame.draw.rect(surface, right_color, right_rect, border_radius=7)
    pygame.draw.rect(surface, mid_color, pygame.Rect(track_rect.centerx - 6, track_rect.y, 12, track_rect.height), border_radius=6)
    pygame.draw.line(surface, (216, 222, 233), (track_rect.centerx, track_rect.y - 10), (track_rect.centerx, track_rect.bottom + 10), 2)

    marker_x = track_rect.left + int(((max(-25.0, min(25.0, balance)) + 25.0) / 50.0) * track_rect.width)
    pygame.draw.circle(surface, (229, 246, 210) if not muted else (176, 183, 194), (marker_x, track_rect.centery), 9)
    pygame.draw.circle(surface, (215, 228, 255), (marker_x, track_rect.centery), 9, width=2)

    delta_text = fonts["small"].render(f"Conc {conc_delta:+.1f}   Relax {relax_delta:+.1f}", True, (219, 231, 255) if not muted else (198, 204, 216))
    delta_rect = delta_text.get_rect(center=(rect.centerx, rect.y + 122))
    surface.blit(delta_text, delta_rect)

    status_lines = _wrap_text(fonts["small"], status, rect.width - 40)
    _draw_text_lines(surface, fonts["small"], status_lines, (203, 213, 225) if not muted else (194, 199, 207), (rect.x + 20, rect.y + 142))


def draw_mind_maze(
    surface: pygame.Surface,
    rect: pygame.Rect,
    view_state: dict[str, Any] | None,
    fonts: dict[str, pygame.font.Font],
) -> None:
    pygame.draw.rect(surface, (5, 6, 8), rect, border_radius=28)
    level = (view_state or {}).get("level")
    player = (view_state or {}).get("player", (0, 0))
    goal = (view_state or {}).get("goal", (0, 0))
    message = str((view_state or {}).get("message", ""))
    hint_direction = (view_state or {}).get("hint_direction")
    balance_panel = (view_state or {}).get("balance_panel")

    if level is None:
        placeholder = fonts["body"].render("Mind Maze will appear here", True, (156, 163, 175))
        placeholder_rect = placeholder.get_rect(center=rect.center)
        surface.blit(placeholder, placeholder_rect)
        return

    top_reserved = 180 if balance_panel else 28
    bottom_reserved = 60 if message else 30
    active_cells = list(level.active_cells)
    min_x = min(cell[0] for cell in active_cells)
    max_x = max(cell[0] for cell in active_cells)
    min_y = min(cell[1] for cell in active_cells)
    max_y = max(cell[1] for cell in active_cells)
    grid_w = max_x - min_x + 1
    grid_h = max_y - min_y + 1

    padding = 36
    available_w = rect.width - (padding * 2)
    available_h = rect.height - top_reserved - bottom_reserved
    cell_size = int(min(available_w / max(grid_w, 1), max(80.0, available_h) / max(grid_h, 1)))
    board_left = rect.x + int((rect.width - (grid_w * cell_size)) / 2)
    board_top = rect.y + top_reserved + int((available_h - (grid_h * cell_size)) / 2)

    if balance_panel:
        panel_rect = pygame.Rect(rect.x + int(rect.width * 0.16), rect.y + 18, int(rect.width * 0.68), 166)
        draw_balance_panel(surface, panel_rect, balance_panel, fonts)

    for cell in active_cells:
        cell_rect = pygame.Rect(
            board_left + ((cell[0] - min_x) * cell_size),
            board_top + ((cell[1] - min_y) * cell_size),
            cell_size,
            cell_size,
        )
        pygame.draw.rect(surface, (52, 16, 13), cell_rect.inflate(-4, -4), border_radius=10)
        pygame.draw.rect(surface, (107, 31, 22), cell_rect.inflate(-4, -4), width=1, border_radius=10)

        passages = level.passages.get(cell, frozenset())
        walls = {
            "up": ((cell_rect.left, cell_rect.top), (cell_rect.right, cell_rect.top)),
            "down": ((cell_rect.left, cell_rect.bottom), (cell_rect.right, cell_rect.bottom)),
            "left": ((cell_rect.left, cell_rect.top), (cell_rect.left, cell_rect.bottom)),
            "right": ((cell_rect.right, cell_rect.top), (cell_rect.right, cell_rect.bottom)),
        }
        for direction, points in walls.items():
            if direction in passages:
                continue
            pygame.draw.line(surface, (0, 0, 0), points[0], points[1], 8)
            pygame.draw.line(surface, (245, 209, 176), points[0], points[1], 4)

    goal_rect = pygame.Rect(
        board_left + ((goal[0] - min_x) * cell_size),
        board_top + ((goal[1] - min_y) * cell_size),
        cell_size,
        cell_size,
    ).inflate(-22, -22)
    pygame.draw.rect(surface, (255, 192, 138), goal_rect, width=4, border_radius=10)

    player_rect = pygame.Rect(
        board_left + ((player[0] - min_x) * cell_size),
        board_top + ((player[1] - min_y) * cell_size),
        cell_size,
        cell_size,
    )
    pygame.draw.circle(surface, (116, 226, 255), player_rect.center, max(12, cell_size // 5))
    pygame.draw.circle(surface, (215, 228, 255), player_rect.center, max(16, cell_size // 4), width=2)

    if hint_direction in {"up", "down", "left", "right"}:
        _draw_hint_arrow(surface, player_rect, hint_direction)

    if message:
        message_surface = fonts["small"].render(message, True, (203, 213, 225))
        message_rect = message_surface.get_rect(center=(rect.centerx, rect.bottom - 22))
        surface.blit(message_surface, message_rect)


def _draw_hint_arrow(surface: pygame.Surface, rect: pygame.Rect, direction: str) -> None:
    center = pygame.Vector2(rect.center)
    dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
    end = center + pygame.Vector2(dx * rect.width * 0.28, dy * rect.height * 0.28)
    pygame.draw.line(surface, (216, 255, 150), center, end, 5)

    wing = rect.width * 0.08
    if direction == "up":
        p1 = end + pygame.Vector2(-wing, wing)
        p2 = end + pygame.Vector2(wing, wing)
    elif direction == "down":
        p1 = end + pygame.Vector2(-wing, -wing)
        p2 = end + pygame.Vector2(wing, -wing)
    elif direction == "left":
        p1 = end + pygame.Vector2(wing, -wing)
        p2 = end + pygame.Vector2(wing, wing)
    else:
        p1 = end + pygame.Vector2(-wing, -wing)
        p2 = end + pygame.Vector2(-wing, wing)
    pygame.draw.line(surface, (216, 255, 150), end, p1, 5)
    pygame.draw.line(surface, (216, 255, 150), end, p2, 5)
