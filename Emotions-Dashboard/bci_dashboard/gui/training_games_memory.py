"""Memory and puzzle game controllers (pattern recall, cascades)."""
from __future__ import annotations

from gui.eeg_game_base import GameplaySnapshot, TrainingLevel
from gui.training_games_base import (
    BaseTrainingController,
    DIR_LABELS,
    MEMORY_MOVE_BALANCE_THRESHOLD,
    MEMORY_MOVE_DELTA_THRESHOLD,
    MEMORY_CONFIRM_DEAD_ZONE,
)


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
