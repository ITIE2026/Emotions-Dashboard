"""
Multiplayer Maze Race – 2-player shared-maze race.

Both players navigate the SAME maze simultaneously.
Concentration moves toward the goal, relaxation retreats.
First player to reach the goal wins.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from gui.eeg_game_base import (
    CALIBRATION_SAMPLES,
    READY_DELTA_THRESHOLD,
    READY_STREAK_TARGET,
    TrainingLevel,
)

# ── Types ─────────────────────────────────────────────────────────
Coord = tuple[int, int]

DIR_VECTORS: dict[str, Coord] = {
    "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),
}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}

# Thresholds (from MindMazeController)
VERTICAL_BALANCE_THRESHOLD = 1.1
HORIZONTAL_BALANCE_THRESHOLD = 0.9
VERTICAL_DELTA_THRESHOLD = 0.2
HORIZONTAL_DELTA_THRESHOLD = 0.1
INTENT_STREAK_NEEDED = 2


# ── MazeLevel dataclass (frozen, compatible with MindMazeBoard) ──
class MazeLevel(TrainingLevel):
    """Lightweight maze level compatible with MindMazeBoard widget."""

    def __init__(self, title: str, target_seconds: int, width: int, height: int,
                 active_cells: frozenset, passages: dict, start: Coord, goal: Coord):
        super().__init__(title, target_seconds)
        self.width = width
        self.height = height
        self.active_cells = active_cells
        self.passages = passages
        self.start = start
        self.goal = goal


def _direction_between(src: Coord, dst: Coord) -> str:
    dx = dst[0] - src[0]
    dy = dst[1] - src[1]
    for d, (vx, vy) in DIR_VECTORS.items():
        if (vx, vy) == (dx, dy):
            return d
    raise ValueError(f"Not adjacent: {src} -> {dst}")


def _build_level(title: str, start: Coord, goal: Coord,
                 target_seconds: int, edges: list[tuple[Coord, Coord]]) -> MazeLevel:
    passages: dict[Coord, set[str]] = defaultdict(set)
    active: set[Coord] = {start, goal}
    max_x = max_y = 0
    for src, dst in edges:
        direction = _direction_between(src, dst)
        passages[src].add(direction)
        passages[dst].add(OPPOSITE[direction])
        active.update((src, dst))
        max_x = max(max_x, src[0], dst[0])
        max_y = max(max_y, src[1], dst[1])
    for cell in active:
        passages.setdefault(cell, set())
    frozen = {c: frozenset(d) for c, d in passages.items()}
    return MazeLevel(
        title=title, target_seconds=target_seconds,
        width=max_x + 1, height=max_y + 1,
        active_cells=frozenset(active), passages=frozen,
        start=start, goal=goal,
    )


# ── Predefined maze levels ───────────────────────────────────────
MP_MAZE_LEVELS = [
    _build_level("Sprint", (0, 4), (4, 0), 45, [
        ((0, 4), (0, 3)), ((0, 3), (0, 2)), ((0, 2), (1, 2)),
        ((1, 2), (2, 2)), ((2, 2), (2, 1)), ((2, 1), (3, 1)),
        ((3, 1), (4, 1)), ((4, 1), (4, 0)),
        ((1, 2), (1, 3)), ((1, 3), (2, 3)), ((2, 3), (3, 3)),
        ((3, 3), (3, 2)), ((3, 2), (4, 2)),
        ((0, 2), (0, 1)), ((0, 1), (1, 1)),
    ]),
    _build_level("Marathon", (0, 5), (5, 0), 60, [
        ((0, 5), (1, 5)), ((1, 5), (1, 4)), ((1, 4), (1, 3)),
        ((1, 3), (2, 3)), ((2, 3), (3, 3)), ((3, 3), (3, 2)),
        ((3, 2), (4, 2)), ((4, 2), (4, 1)), ((4, 1), (5, 1)),
        ((5, 1), (5, 0)),
        ((1, 4), (2, 4)), ((2, 4), (3, 4)), ((3, 4), (4, 4)),
        ((4, 4), (4, 3)),
        ((2, 3), (2, 2)), ((2, 2), (1, 2)), ((1, 2), (1, 1)),
        ((1, 1), (2, 1)), ((4, 2), (5, 2)),
    ]),
]


class _MazePlayerState:
    def __init__(self, start: Coord):
        self.pos: Coord = start
        self.intent_streak_label: str | None = None
        self.intent_streak_count: int = 0
        self.move_count: int = 0


class MultiplayerMazeRaceController:
    """Authoritative controller for 2-player Maze Race.

    Both players navigate the same maze.  First to reach the goal wins.
    """

    def __init__(self, p1_name: str = "Player 1", p2_name: str = "Player 2"):
        self._p1_name = p1_name
        self._p2_name = p2_name
        self._level_index = 0
        self._level: MazeLevel = MP_MAZE_LEVELS[0]
        self._started_at: float | None = None

        self._ps = {
            0: _MazePlayerState(self._level.start),
            1: _MazePlayerState(self._level.start),
        }

        # Per-player calibration
        self._cal = {
            0: {"samples": [], "baseline_conc": None, "baseline_relax": None,
                "ready_streak": 0, "complete": False},
            1: {"samples": [], "baseline_conc": None, "baseline_relax": None,
                "ready_streak": 0, "complete": False},
        }

    # ── Calibration ───────────────────────────────────────────────
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
        self._started_at = time.monotonic()
        for ps in self._ps.values():
            ps.pos = self._level.start

    # ── Game tick ─────────────────────────────────────────────────
    def tick(self, p1_metrics: dict, p2_metrics: dict) -> dict:
        elapsed = time.monotonic() - (self._started_at or time.monotonic())

        self._tick_player(0, p1_metrics)
        self._tick_player(1, p2_metrics)

        p1_at_goal = self._ps[0].pos == self._level.goal
        p2_at_goal = self._ps[1].pos == self._level.goal
        run_completed = p1_at_goal or p2_at_goal

        winner = None
        message = "Race to the goal!"
        if p1_at_goal and p2_at_goal:
            winner = "draw"
            message = "Both reached the goal at once!"
        elif p1_at_goal:
            winner = "player1"
            message = f"{self._p1_name} reached the goal first!"
        elif p2_at_goal:
            winner = "player2"
            message = f"{self._p2_name} reached the goal first!"

        return {
            "mode": "mp_maze_race",
            "level": self._level,
            "player": self._ps[0].pos,
            "player2": self._ps[1].pos,
            "goal": self._level.goal,
            "hint_direction": None,
            "player1_name": self._p1_name,
            "player2_name": self._p2_name,
            "player1_moves": self._ps[0].move_count,
            "player2_moves": self._ps[1].move_count,
            "message": message,
            "run_completed": run_completed,
            "winner": winner,
            "elapsed_seconds": round(elapsed, 1),
        }

    # ── Per-player tick ───────────────────────────────────────────
    def _tick_player(self, pid: int, metrics: dict):
        ps = self._ps[pid]
        if ps.pos == self._level.goal:
            return

        conc = metrics.get("concentration", 0.0)
        relax = metrics.get("relaxation", 0.0)
        valid = metrics.get("valid", False)
        stale = metrics.get("stale", False)

        if not valid or stale:
            return

        base_c = self._cal[pid].get("baseline_conc") or 0.0
        base_r = self._cal[pid].get("baseline_relax") or 0.0
        conc_delta = conc - base_c
        relax_delta = relax - base_r

        valid_exits = tuple(sorted(self._level.passages.get(ps.pos, frozenset())))
        recommended = self._recommended_direction(ps.pos)

        # Determine phase
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

        raw_intent = self._compute_intent(conc_delta, relax_delta, phase,
                                          valid_exits, recommended)
        intent = self._stabilise(ps, raw_intent)

        if intent and intent in valid_exits:
            dx, dy = DIR_VECTORS[intent]
            new_pos = (ps.pos[0] + dx, ps.pos[1] + dy)
            if new_pos in self._level.active_cells:
                ps.pos = new_pos
                ps.move_count += 1

    @staticmethod
    def _compute_intent(conc_delta: float, relax_delta: float, phase: str,
                        valid_exits: tuple, recommended: str | None) -> str | None:
        balance = conc_delta - relax_delta
        exits = set(valid_exits)

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

        # Free phase
        if recommended in {"up", "right"} and balance >= HORIZONTAL_BALANCE_THRESHOLD:
            if recommended in exits:
                return recommended
        if recommended in {"down", "left"} and balance <= -HORIZONTAL_BALANCE_THRESHOLD:
            if recommended in exits:
                return recommended
        if "up" in exits and balance >= VERTICAL_BALANCE_THRESHOLD and conc_delta >= VERTICAL_DELTA_THRESHOLD:
            return "up"
        if "right" in exits and balance >= HORIZONTAL_BALANCE_THRESHOLD and conc_delta >= HORIZONTAL_DELTA_THRESHOLD:
            return "right"
        if "left" in exits and balance <= -HORIZONTAL_BALANCE_THRESHOLD and relax_delta >= HORIZONTAL_DELTA_THRESHOLD:
            return "left"
        if "down" in exits and balance <= -VERTICAL_BALANCE_THRESHOLD and relax_delta >= VERTICAL_DELTA_THRESHOLD:
            return "down"
        return None

    @staticmethod
    def _stabilise(ps: _MazePlayerState, raw: str | None) -> str | None:
        if raw is None:
            ps.intent_streak_label = None
            ps.intent_streak_count = 0
            return None
        if raw == ps.intent_streak_label:
            ps.intent_streak_count += 1
        else:
            ps.intent_streak_label = raw
            ps.intent_streak_count = 1
        if ps.intent_streak_count >= INTENT_STREAK_NEEDED:
            ps.intent_streak_count = 0
            return raw
        return None

    # ── Pathfinding ───────────────────────────────────────────────
    def _recommended_direction(self, pos: Coord) -> str | None:
        goal = self._level.goal
        if pos == goal:
            return None
        queue: deque[tuple[Coord, Coord | None]] = deque([(pos, None)])
        visited = {pos}
        parent: dict[Coord, Coord | None] = {pos: None}
        while queue:
            cell, _ = queue.popleft()
            if cell == goal:
                break
            for direction in self._level.passages.get(cell, frozenset()):
                dx, dy = DIR_VECTORS[direction]
                nb = (cell[0] + dx, cell[1] + dy)
                if nb in visited:
                    continue
                visited.add(nb)
                parent[nb] = cell
                queue.append((nb, cell))
        if goal not in parent:
            return None
        cursor = goal
        while parent[cursor] != pos:
            p = parent[cursor]
            if p is None:
                return None
            cursor = p
        return _direction_between(pos, cursor)
