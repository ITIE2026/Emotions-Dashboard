"""
Multiplayer Bubble Battle – 2-player competitive bubble-burst.

Both players have identical starting boards.
Clearing combos of 4+ sends a garbage row to the opponent.
Game ends when one player's bubbles reach the launcher zone.
"""
from __future__ import annotations

import random
import time
from gui.eeg_game_base import (
    CALIBRATION_SAMPLES,
    READY_DELTA_THRESHOLD,
    READY_STREAK_TARGET,
    TrainingLevel,
)

ARCADE_BALANCE_THRESHOLD = 0.8
ARCADE_DELTA_THRESHOLD = 0.15
ARCADE_STEADY_DEAD_ZONE = 0.35

COLUMNS = 6
VISIBLE_ROWS = 10
LAUNCHER_ZONE_ROW = 8
PALETTE = ["red", "green", "yellow"]
INITIAL_SHOTS = 18
GARBAGE_COMBO_THRESHOLD = 4  # Clear 4+ to send garbage
INTENT_STREAK_NEEDED = 2


def _make_initial_board(columns: int, fill_rows: int, palette: list[str],
                        seed: int) -> list[list[str | None]]:
    """Deterministic initial board (same for both players)."""
    rng = random.Random(seed)
    board: list[list[str | None]] = []
    for r in range(VISIBLE_ROWS):
        if r < fill_rows:
            board.append([rng.choice(palette) for _ in range(columns)])
        else:
            board.append([None] * columns)
    return board


class _BubblePlayerState:
    """Mutable per-player bubble-burst state."""

    def __init__(self, board: list[list[str | None]], palette: list[str], seed: int):
        self._rng = random.Random(seed)
        self.board = [row[:] for row in board]
        self.palette = palette
        self.aim_slot: int = COLUMNS // 2
        self.current_bubble: str = self._rng.choice(palette)
        self.next_bubble: str = self._rng.choice(palette)
        self.shots_left: int = INITIAL_SHOTS
        self.score: int = 0
        self.combo: int = 0
        self.best_combo: int = 0
        self.danger_steps: int = 0
        self.ceiling_cursor: int = 0
        self.finished: bool = False
        self.lost: bool = False
        self.message: str = "Focus for right, relax for left, hold steady to fire."
        self.score_popups: list[dict] = []

        # Pending garbage rows from opponent
        self.pending_garbage: int = 0

        # Intent stabilisation
        self.intent_streak_label: str | None = None
        self.intent_streak_count: int = 0


class MultiplayerBubbleBattleController:
    """Authoritative controller for 2-player Bubble Battle.

    Two parallel boards.  Clearing 4+ bubbles sends a garbage row
    to the opponent.  First to reach the launcher zone loses.
    """

    def __init__(self, p1_name: str = "Player 1", p2_name: str = "Player 2"):
        self._p1_name = p1_name
        self._p2_name = p2_name
        self._started_at: float | None = None

        seed = int(time.monotonic() * 1000) & 0xFFFFFFFF
        board = _make_initial_board(COLUMNS, 4, PALETTE, seed)

        self._players = {
            0: _BubblePlayerState(board, PALETTE, seed + 1),
            1: _BubblePlayerState(board, PALETTE, seed + 2),
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

    # ── Game tick ─────────────────────────────────────────────────
    def tick(self, p1_metrics: dict, p2_metrics: dict) -> dict:
        elapsed = time.monotonic() - (self._started_at or time.monotonic())

        self._tick_player(0, p1_metrics)
        self._tick_player(1, p2_metrics)

        p0 = self._players[0]
        p1 = self._players[1]
        run_completed = p0.finished or p1.finished

        winner = None
        if run_completed:
            if p0.lost and p1.lost:
                winner = "draw"
            elif p0.lost:
                winner = "player2"
            elif p1.lost:
                winner = "player1"
            elif p0.score > p1.score:
                winner = "player1"
            elif p1.score > p0.score:
                winner = "player2"
            else:
                winner = "draw"

        return {
            "mode": "mp_bubble_battle",
            "player_views": {
                "0": self._view_state(0),
                "1": self._view_state(1),
            },
            "player1_name": self._p1_name,
            "player2_name": self._p2_name,
            "player1_score": p0.score,
            "player2_score": p1.score,
            "run_completed": run_completed,
            "winner": winner,
            "elapsed_seconds": round(elapsed, 1),
        }

    # ── Per-player tick ───────────────────────────────────────────
    def _tick_player(self, pid: int, metrics: dict):
        ps = self._players[pid]
        if ps.finished:
            return

        # Apply pending garbage first
        while ps.pending_garbage > 0:
            ps.pending_garbage -= 1
            self._drop_garbage_row(ps)
            if self._launcher_zone_reached(ps):
                ps.finished = True
                ps.lost = True
                ps.message = "Garbage overload! Board lost."
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

        raw_intent = self._arcade_intent(conc_delta, relax_delta)
        intent = self._stabilise(ps, raw_intent)

        if intent == "focus":
            ps.aim_slot = min(COLUMNS - 1, ps.aim_slot + 1)
            ps.message = "Aiming right."
        elif intent == "relax":
            ps.aim_slot = max(0, ps.aim_slot - 1)
            ps.message = "Aiming left."
        elif intent == "steady":
            self._fire_bubble(pid)

        # Decay score popups
        ps.score_popups = [p for p in ps.score_popups if (p.update(ticks=p["ticks"] - 1) or True) and p["ticks"] > 0]

    @staticmethod
    def _arcade_intent(conc_delta: float, relax_delta: float) -> str | None:
        balance = conc_delta - relax_delta
        if balance >= ARCADE_BALANCE_THRESHOLD and conc_delta >= ARCADE_DELTA_THRESHOLD:
            return "focus"
        if balance <= -ARCADE_BALANCE_THRESHOLD and relax_delta >= ARCADE_DELTA_THRESHOLD:
            return "relax"
        if abs(balance) <= ARCADE_STEADY_DEAD_ZONE:
            return "steady"
        return None

    @staticmethod
    def _stabilise(ps: _BubblePlayerState, raw: str | None) -> str | None:
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

    # ── Fire ──────────────────────────────────────────────────────
    def _fire_bubble(self, pid: int):
        ps = self._players[pid]
        opponent = self._players[1 - pid]

        ps.shots_left = max(0, ps.shots_left - 1)
        placed = self._place_bubble(ps)

        if placed is None:
            ps.message = "No landing slot. The ceiling drops."
            self._drop_ceiling_row(ps)
            self._cycle_queue(ps)
            if self._launcher_zone_reached(ps):
                ps.finished = True
                ps.lost = True
                ps.message = "Bubbles reached the launcher zone!"
                return
            if ps.shots_left == 0:
                ps.finished = True
                ps.lost = True
                ps.message = "Out of shots!"
            return

        row, col = placed
        popped = self._resolve_burst(ps, row, col)
        self._cycle_queue(ps)

        if popped:
            ps.combo += 1
            ps.best_combo = max(ps.best_combo, ps.combo)
            burst_score = len(popped) * 300 + max(0, (ps.combo - 1) * 90)
            ps.score += burst_score
            ps.score_popups.append({
                "row": float(row), "col": col,
                "text": str(burst_score), "ticks": 7,
            })
            ps.message = f"Burst {len(popped)} bubbles!"

            # Garbage mechanic
            if len(popped) >= GARBAGE_COMBO_THRESHOLD:
                garbage_rows = (len(popped) - GARBAGE_COMBO_THRESHOLD) // 2 + 1
                opponent.pending_garbage += garbage_rows
        else:
            ps.combo = 0
            ps.message = "No match. The ceiling drops."
            self._drop_ceiling_row(ps)
            if self._launcher_zone_reached(ps):
                ps.finished = True
                ps.lost = True
                ps.message = "Bubbles reached the launcher zone!"
                return

        if self._board_empty(ps):
            ps.score += 1000
            ps.finished = True
            ps.message = "Board cleared!"
            return
        if ps.shots_left == 0:
            ps.finished = True
            ps.lost = True
            ps.message = "Out of shots!"

    # ── Board operations ──────────────────────────────────────────
    def _place_bubble(self, ps: _BubblePlayerState) -> tuple[int, int] | None:
        for col in self._column_scan_order(ps.aim_slot):
            row = self._landing_row(ps, col)
            if row is not None:
                ps.board[row][col] = ps.current_bubble
                return (row, col)
        return None

    @staticmethod
    def _column_scan_order(center: int) -> list[int]:
        order = [center]
        for dist in range(1, COLUMNS):
            left = center - dist
            right = center + dist
            if left >= 0:
                order.append(left)
            if right < COLUMNS:
                order.append(right)
        return order

    @staticmethod
    def _landing_row(ps: _BubblePlayerState, col: int) -> int | None:
        for row in range(VISIBLE_ROWS):
            if ps.board[row][col] is None:
                return row
        return None

    def _resolve_burst(self, ps: _BubblePlayerState, row: int, col: int) -> set[tuple[int, int]]:
        cluster = self._color_cluster(ps, row, col)
        if len(cluster) < 3:
            return set()
        removed = set(cluster)
        self._clear_cells(ps, cluster)
        floating = self._floating_cells(ps)
        if floating:
            removed.update(floating)
            self._clear_cells(ps, floating)
        return removed

    @staticmethod
    def _color_cluster(ps: _BubblePlayerState, row: int, col: int) -> set[tuple[int, int]]:
        color = ps.board[row][col]
        if color is None:
            return set()
        cluster: set[tuple[int, int]] = set()
        stack = [(row, col)]
        while stack:
            r, c = stack.pop()
            if (r, c) in cluster:
                continue
            if r < 0 or r >= VISIBLE_ROWS or c < 0 or c >= COLUMNS:
                continue
            if ps.board[r][c] != color:
                continue
            cluster.add((r, c))
            # Hex neighbours
            if r % 2 == 0:
                offsets = [(0, -1), (0, 1), (-1, -1), (-1, 0), (1, -1), (1, 0)]
            else:
                offsets = [(0, -1), (0, 1), (-1, 0), (-1, 1), (1, 0), (1, 1)]
            for dr, dc in offsets:
                nr, nc = r + dr, c + dc
                if 0 <= nr < VISIBLE_ROWS and 0 <= nc < COLUMNS and (nr, nc) not in cluster:
                    stack.append((nr, nc))
        return cluster

    @staticmethod
    def _floating_cells(ps: _BubblePlayerState) -> set[tuple[int, int]]:
        anchored: set[tuple[int, int]] = set()
        stack = [(0, c) for c in range(COLUMNS) if ps.board[0][c] is not None]
        while stack:
            cell = stack.pop()
            if cell in anchored:
                continue
            anchored.add(cell)
            r, c = cell
            if r % 2 == 0:
                offsets = [(0, -1), (0, 1), (-1, -1), (-1, 0), (1, -1), (1, 0)]
            else:
                offsets = [(0, -1), (0, 1), (-1, 0), (-1, 1), (1, 0), (1, 1)]
            for dr, dc in offsets:
                nr, nc = r + dr, c + dc
                if 0 <= nr < VISIBLE_ROWS and 0 <= nc < COLUMNS:
                    if ps.board[nr][nc] is not None and (nr, nc) not in anchored:
                        stack.append((nr, nc))
        floating: set[tuple[int, int]] = set()
        for r in range(VISIBLE_ROWS):
            for c in range(COLUMNS):
                if ps.board[r][c] is not None and (r, c) not in anchored:
                    floating.add((r, c))
        return floating

    @staticmethod
    def _clear_cells(ps: _BubblePlayerState, cells: set[tuple[int, int]]):
        for r, c in cells:
            ps.board[r][c] = None

    @staticmethod
    def _board_empty(ps: _BubblePlayerState) -> bool:
        return all(cell is None for row in ps.board for cell in row)

    @staticmethod
    def _launcher_zone_reached(ps: _BubblePlayerState) -> bool:
        for row in range(LAUNCHER_ZONE_ROW, VISIBLE_ROWS):
            if any(cell is not None for cell in ps.board[row]):
                return True
        return False

    @staticmethod
    def _drop_ceiling_row(ps: _BubblePlayerState):
        ps.danger_steps += 1
        new_row = [
            ps.palette[(ps.ceiling_cursor + c) % len(ps.palette)]
            for c in range(COLUMNS)
        ]
        ps.ceiling_cursor += 1
        ps.board = [new_row] + [row[:] for row in ps.board[:-1]]

    def _drop_garbage_row(self, ps: _BubblePlayerState):
        """Push a mixed-color garbage row from the top."""
        ps.danger_steps += 1
        rng = ps._rng
        new_row = [rng.choice(ps.palette) for _ in range(COLUMNS)]
        ps.board = [new_row] + [row[:] for row in ps.board[:-1]]

    @staticmethod
    def _cycle_queue(ps: _BubblePlayerState):
        ps.current_bubble = ps.next_bubble
        ps.next_bubble = ps._rng.choice(ps.palette)

    # ── View state ────────────────────────────────────────────────
    def _view_state(self, pid: int) -> dict:
        ps = self._players[pid]
        return {
            "mode": "bubble_burst",
            "columns": COLUMNS,
            "visible_rows": VISIBLE_ROWS,
            "board": [row[:] for row in ps.board],
            "aim_slot": ps.aim_slot,
            "current_bubble": ps.current_bubble,
            "next_bubble": ps.next_bubble,
            "shots_left": ps.shots_left,
            "score": ps.score,
            "combo": ps.combo,
            "best_combo": ps.best_combo,
            "danger_steps": ps.danger_steps,
            "launcher_zone_row": LAUNCHER_ZONE_ROW,
            "score_popups": [dict(p) for p in ps.score_popups],
            "swap_enabled": False,
            "star_progress": min(1.0, ps.score / 5400.0),
            "star_thresholds": [2200, 3800, 5400],
            "overlay_kind": None,
            "overlay_title": "",
            "overlay_subtitle": "",
            "overlay_timer": 0,
            "menu_button_rect": [18, 18, 54, 42],
            "swap_button_rect": [0, 0, 0, 0],
            "music_scene": "bubble_arcade",
            "music_bias": 0.0,
            "serenity": max(0.0, min(100.0, ps.shots_left * 4.5 + ps.best_combo * 8.0)),
            "restlessness": max(0.0, min(100.0, ps.danger_steps * 12.0)),
            "message": ps.message,
        }
