"""
Custom widgets for the Mind Maze training flow.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class MindMazeBoard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = None
        self._player = (0, 0)
        self._goal = (0, 0)
        self._message = ""
        self._hint_direction = None
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, level, player, goal, message: str = "", hint_direction: str | None = None):
        self._level = level
        self._player = player
        self._goal = goal
        self._message = message
        self._hint_direction = hint_direction
        self.update()

    def set_view_state(self, view_state: dict):
        state = view_state or {}
        self.set_state(
            state.get("level"),
            state.get("player", (0, 0)),
            state.get("goal", (0, 0)),
            state.get("message", ""),
            hint_direction=state.get("hint_direction"),
        )

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#050608"))

        if self._level is None:
            painter.setPen(QColor("#9ca3af"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Mind Maze will appear here")
            return

        glow = QRadialGradient(self.rect().center(), min(self.width(), self.height()) * 0.45)
        glow.setColorAt(0.0, QColor(222, 92, 26, 90))
        glow.setColorAt(0.55, QColor(132, 48, 20, 45))
        glow.setColorAt(1.0, QColor(5, 6, 8, 0))
        painter.fillRect(self.rect(), glow)

        active_cells = list(self._level.active_cells)
        min_x = min(cell[0] for cell in active_cells)
        max_x = max(cell[0] for cell in active_cells)
        min_y = min(cell[1] for cell in active_cells)
        max_y = max(cell[1] for cell in active_cells)
        grid_w = max_x - min_x + 1
        grid_h = max_y - min_y + 1

        padding = 36
        cell_size = min(
            (self.width() - (padding * 2)) / max(grid_w, 1),
            (self.height() - (padding * 2)) / max(grid_h, 1),
        )
        board_left = (self.width() - (grid_w * cell_size)) / 2
        board_top = (self.height() - (grid_h * cell_size)) / 2 - 8

        wall_pen = QPen(QColor("#f5d1b0"), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        shadow_pen = QPen(QColor(0, 0, 0, 90), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

        for cell in active_cells:
            rect = QRectF(
                board_left + ((cell[0] - min_x) * cell_size),
                board_top + ((cell[1] - min_y) * cell_size),
                cell_size,
                cell_size,
            )
            fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
            fill.setColorAt(0.0, QColor("#6b1f16"))
            fill.setColorAt(0.5, QColor("#34100d"))
            fill.setColorAt(1.0, QColor("#130807"))
            painter.fillRect(rect.adjusted(2, 2, -2, -2), fill)

            passages = self._level.passages.get(cell, frozenset())
            walls = {
                "up": (rect.topLeft(), rect.topRight()),
                "down": (rect.bottomLeft(), rect.bottomRight()),
                "left": (rect.topLeft(), rect.bottomLeft()),
                "right": (rect.topRight(), rect.bottomRight()),
            }
            for direction, points in walls.items():
                if direction in passages:
                    continue
                painter.setPen(shadow_pen)
                painter.drawLine(points[0], points[1])
                painter.setPen(wall_pen)
                painter.drawLine(points[0], points[1])

        goal_rect = self._cell_rect(board_left, board_top, cell_size, min_x, min_y, self._goal)
        painter.setPen(QPen(QColor("#ffc08a"), 4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(goal_rect.adjusted(10, 10, -10, -10), 10, 10)

        player_rect = self._cell_rect(board_left, board_top, cell_size, min_x, min_y, self._player)
        player_glow = QRadialGradient(player_rect.center(), cell_size * 0.7)
        player_glow.setColorAt(0.0, QColor(116, 226, 255, 210))
        player_glow.setColorAt(1.0, QColor(116, 226, 255, 0))
        painter.fillRect(player_rect.adjusted(-16, -16, 16, 16), player_glow)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#79e1ff"))
        painter.drawRoundedRect(player_rect.adjusted(14, 14, -14, -14), 10, 10)

        if self._hint_direction in {"up", "down", "left", "right"}:
            self._draw_direction_hint(painter, player_rect, self._hint_direction)

        if self._message:
            painter.setPen(QColor("#cbd5e1"))
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            text_rect = QRectF(20, self.height() - 42, self.width() - 40, 24)
            painter.drawText(text_rect, Qt.AlignCenter, self._message)

    def _cell_rect(self, left, top, cell_size, min_x, min_y, cell):
        return QRectF(
            left + ((cell[0] - min_x) * cell_size),
            top + ((cell[1] - min_y) * cell_size),
            cell_size,
            cell_size,
        )

    def _draw_direction_hint(self, painter: QPainter, rect: QRectF, direction: str):
        center = rect.center()
        dx, dy = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0),
        }[direction]
        end = QPointF(center.x() + (dx * rect.width() * 0.32), center.y() + (dy * rect.height() * 0.32))
        painter.setPen(QPen(QColor("#d8ff96"), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(center, end)

        wing = rect.width() * 0.10
        if direction == "up":
            p1 = QPointF(end.x() - wing, end.y() + wing)
            p2 = QPointF(end.x() + wing, end.y() + wing)
        elif direction == "down":
            p1 = QPointF(end.x() - wing, end.y() - wing)
            p2 = QPointF(end.x() + wing, end.y() - wing)
        elif direction == "left":
            p1 = QPointF(end.x() + wing, end.y() - wing)
            p2 = QPointF(end.x() + wing, end.y() + wing)
        else:
            p1 = QPointF(end.x() - wing, end.y() - wing)
            p2 = QPointF(end.x() - wing, end.y() + wing)
        painter.drawLine(end, p1)
        painter.drawLine(end, p2)


class MindMazeControlBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._balance = 0.0
        self._conc_delta = 0.0
        self._relax_delta = 0.0
        self._intent_label = "Hold steady"
        self._status = "Waiting for live concentration and relaxation."
        self._muted = False
        self.setMinimumHeight(120)

    def sizeHint(self):
        return QSize(560, 120)

    def set_state(
        self,
        balance: float,
        conc_delta: float,
        relax_delta: float,
        intent_label: str,
        status: str,
        muted: bool = False,
    ):
        self._balance = balance
        self._conc_delta = conc_delta
        self._relax_delta = relax_delta
        self._intent_label = intent_label
        self._status = status
        self._muted = muted
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.transparent)

        track_rect = QRectF(28, 28, self.width() - 56, 14)
        gradient = QLinearGradient(track_rect.topLeft(), track_rect.topRight())
        if self._muted:
            gradient.setColorAt(0.0, QColor("#59616d"))
            gradient.setColorAt(1.0, QColor("#59616d"))
        else:
            gradient.setColorAt(0.0, QColor("#9af7aa"))
            gradient.setColorAt(0.5, QColor("#f5f3b7"))
            gradient.setColorAt(1.0, QColor("#f76161"))

        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(track_rect, 7, 7)

        center_x = track_rect.center().x()
        painter.setPen(QPen(QColor("#d8dee9"), 2))
        painter.drawLine(QPointF(center_x, track_rect.top() - 18), QPointF(center_x, track_rect.bottom() + 18))

        marker_x = track_rect.left() + ((max(-25.0, min(25.0, self._balance)) + 25.0) / 50.0) * track_rect.width()
        painter.setBrush(QColor("#e5f6d2") if not self._muted else QColor("#b0b7c2"))
        painter.drawEllipse(QPointF(marker_x, track_rect.center().y()), 12, 12)

        painter.setPen(QColor("#f8fafc"))
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(0, 54, self.width(), 22), Qt.AlignCenter, self._intent_label)

        body_font = QFont()
        body_font.setPointSize(10)
        painter.setFont(body_font)
        painter.setPen(QColor("#cbd5e1"))
        painter.drawText(
            QRectF(0, 76, self.width(), 18),
            Qt.AlignCenter,
            f"Conc {self._conc_delta:+.1f}   Relax {self._relax_delta:+.1f}",
        )
        painter.drawText(QRectF(0, 96, self.width(), 18), Qt.AlignCenter, self._status)
