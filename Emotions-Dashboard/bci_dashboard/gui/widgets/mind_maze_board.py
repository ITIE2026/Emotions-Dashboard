"""
Custom widgets for the Mind Maze training flow.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


def draw_balance_panel(painter: QPainter, rect: QRectF, panel: dict | None) -> None:
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

    shell = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    if muted:
        shell.setColorAt(0.0, QColor(36, 40, 50, 235))
        shell.setColorAt(1.0, QColor(24, 27, 35, 235))
        border = QColor("#798292")
    else:
        shell.setColorAt(0.0, QColor(9, 12, 20, 228))
        shell.setColorAt(1.0, QColor(6, 8, 14, 220))
        border = QColor("#5c6886")

    painter.setPen(QPen(border, 1.6))
    painter.setBrush(shell)
    painter.drawRoundedRect(rect, 24, 24)

    time_rect = QRectF(rect.left() + 18, rect.top() + 10, rect.width() - 36, 30)
    time_progress_rect = QRectF(rect.left() + 42, time_rect.bottom() + 2, rect.width() - 84, 4)
    fill_width = time_progress_rect.width() * countdown_ratio
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, 22))
    painter.drawRoundedRect(time_progress_rect, 2, 2)
    painter.setBrush(QColor("#f5f3b7") if not muted else QColor("#9ca3af"))
    painter.drawRoundedRect(QRectF(time_progress_rect.left(), time_progress_rect.top(), fill_width, time_progress_rect.height()), 2, 2)

    painter.setPen(QColor("#f8fafc"))
    timer_font = QFont()
    timer_font.setPointSize(18)
    timer_font.setBold(True)
    painter.setFont(timer_font)
    painter.drawText(time_rect, Qt.AlignCenter, timer_text)

    header_rect = QRectF(rect.left() + 16, rect.top() + 48, rect.width() - 32, 18)
    painter.setPen(QColor("#b9c8e8") if not muted else QColor("#c0c7d2"))
    header_font = QFont()
    header_font.setPointSize(9)
    painter.setFont(header_font)
    painter.drawText(header_rect, Qt.AlignCenter, headline)

    track_rect = QRectF(rect.left() + 18, rect.top() + 70, rect.width() - 36, 12)
    gradient = QLinearGradient(track_rect.topLeft(), track_rect.topRight())
    if muted:
        gradient.setColorAt(0.0, QColor("#59616d"))
        gradient.setColorAt(1.0, QColor("#59616d"))
    else:
        gradient.setColorAt(0.0, QColor("#9af7aa"))
        gradient.setColorAt(0.5, QColor("#f5f3b7"))
        gradient.setColorAt(1.0, QColor("#f76161"))

    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(track_rect, 6, 6)

    center_x = track_rect.center().x()
    painter.setPen(QPen(QColor("#d8dee9"), 2))
    painter.drawLine(QPointF(center_x, track_rect.top() - 12), QPointF(center_x, track_rect.bottom() + 12))

    marker_x = track_rect.left() + ((max(-25.0, min(25.0, balance)) + 25.0) / 50.0) * track_rect.width()
    painter.setPen(QPen(QColor("#d7e4ff"), 1.8))
    painter.setBrush(QColor("#e5f6d2") if not muted else QColor("#b0b7c2"))
    painter.drawEllipse(QPointF(marker_x, track_rect.center().y()), 9, 9)

    delta_rect = QRectF(rect.left() + 18, rect.top() + 90, rect.width() - 36, 16)
    painter.setPen(QColor("#dbe7ff") if not muted else QColor("#c6ccd8"))
    delta_font = QFont()
    delta_font.setPointSize(9)
    painter.setFont(delta_font)
    painter.drawText(delta_rect, Qt.AlignCenter, f"Conc {conc_delta:+.1f}   Relax {relax_delta:+.1f}")

    status_rect = QRectF(rect.left() + 20, rect.top() + 108, rect.width() - 40, rect.height() - 114)
    painter.setPen(QColor("#cbd5e1") if not muted else QColor("#c2c7cf"))
    painter.drawText(status_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, status)


class MindMazeBoard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = None
        self._player = (0, 0)
        self._goal = (0, 0)
        self._message = ""
        self._hint_direction = None
        self._balance_panel: dict | None = None
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(
        self,
        level,
        player,
        goal,
        message: str = "",
        hint_direction: str | None = None,
        balance_panel: dict | None = None,
    ):
        self._level = level
        self._player = player
        self._goal = goal
        self._message = message
        self._hint_direction = hint_direction
        self._balance_panel = balance_panel
        self.update()

    def set_view_state(self, view_state: dict):
        state = view_state or {}
        self.set_state(
            state.get("level"),
            state.get("player", (0, 0)),
            state.get("goal", (0, 0)),
            state.get("message", ""),
            hint_direction=state.get("hint_direction"),
            balance_panel=state.get("balance_panel"),
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
        top_reserved = 158 if self._balance_panel else 28
        bottom_reserved = 56 if self._message else 30
        cell_size = min(
            (self.width() - (padding * 2)) / max(grid_w, 1),
            max(80.0, (self.height() - top_reserved - bottom_reserved)) / max(grid_h, 1),
        )
        board_left = (self.width() - (grid_w * cell_size)) / 2
        usable_height = self.height() - top_reserved - bottom_reserved
        board_top = top_reserved + ((usable_height - (grid_h * cell_size)) / 2) - 4

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

        if self._balance_panel:
            draw_balance_panel(
                painter,
                QRectF(max(24.0, self.width() * 0.16), 18, self.width() * 0.68, 132),
                self._balance_panel,
            )

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
        self._timer_text = "00:00"
        self._countdown_ratio = 0.0
        self.setMinimumHeight(140)

    def sizeHint(self):
        return QSize(560, 140)

    def set_state(
        self,
        balance: float,
        conc_delta: float,
        relax_delta: float,
        intent_label: str,
        status: str,
        muted: bool = False,
        timer_text: str = "00:00",
        countdown_ratio: float = 0.0,
    ):
        self._balance = balance
        self._conc_delta = conc_delta
        self._relax_delta = relax_delta
        self._intent_label = intent_label
        self._status = status
        self._muted = muted
        self._timer_text = timer_text
        self._countdown_ratio = countdown_ratio
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.transparent)
        draw_balance_panel(
            painter,
            self.rect().adjusted(6, 4, -6, -4),
            {
                "timer_text": self._timer_text,
                "balance": self._balance,
                "conc_delta": self._conc_delta,
                "relax_delta": self._relax_delta,
                "headline": self._intent_label,
                "status": self._status,
                "muted": self._muted,
                "countdown_ratio": self._countdown_ratio,
            },
        )
