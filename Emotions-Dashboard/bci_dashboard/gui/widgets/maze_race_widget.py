"""
MazeRaceWidget – extends MindMazeBoard to render two players.

Player 1 is cyan (original), Player 2 is orange.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QRadialGradient

from gui.widgets.mind_maze_board import MindMazeBoard


class MazeRaceWidget(MindMazeBoard):
    """MindMazeBoard with an additional player-2 marker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player2 = (0, 0)

    def set_view_state(self, view_state: dict):
        state = view_state or {}
        self._player2 = tuple(state.get("player2", (0, 0)))
        super().set_view_state(state)

    def paintEvent(self, event):  # noqa: N802
        # Let base class draw the entire maze + player 1
        super().paintEvent(event)

        # Now paint player 2 on top
        if self._level is None:
            return

        from PySide6.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        active_cells = list(self._level.active_cells)
        min_x = min(c[0] for c in active_cells)
        max_x = max(c[0] for c in active_cells)
        min_y = min(c[1] for c in active_cells)
        max_y = max(c[1] for c in active_cells)
        grid_w = max_x - min_x + 1
        grid_h = max_y - min_y + 1

        padding = 36
        top_reserved = 158 if self._balance_panel else 28
        bottom_reserved = 56 if self._message else 30
        cell_size = min(
            (self.width() - (padding * 2)) / max(grid_w, 1),
            max(80.0, (self.height() - top_reserved - bottom_reserved)) / max(grid_h, 1),
        )
        board_left = (self.width() - (grid_w * cell_size)) / 2
        usable_height = self.height() - top_reserved - bottom_reserved
        board_top = top_reserved + ((usable_height - (grid_h * cell_size)) / 2) - 4

        p2_rect = self._cell_rect(board_left, board_top, cell_size, min_x, min_y, self._player2)

        # Orange glow for player 2
        p2_glow = QRadialGradient(p2_rect.center(), cell_size * 0.7)
        p2_glow.setColorAt(0.0, QColor(255, 165, 80, 180))
        p2_glow.setColorAt(1.0, QColor(255, 165, 80, 0))
        painter.fillRect(p2_rect.adjusted(-16, -16, 16, 16), p2_glow)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffa550"))
        painter.drawRoundedRect(p2_rect.adjusted(14, 14, -14, -14), 10, 10)

        painter.end()
