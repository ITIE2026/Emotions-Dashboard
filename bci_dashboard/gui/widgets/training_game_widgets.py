"""
Paint-only widgets for the non-maze EEG training games.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class SpaceShooterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#02050b"))

        sky = QLinearGradient(0, 0, self.width(), self.height())
        sky.setColorAt(0.0, QColor("#0b1f3c"))
        sky.setColorAt(0.55, QColor("#08111d"))
        sky.setColorAt(1.0, QColor("#02050b"))
        painter.fillRect(self.rect(), sky)

        progress = float(self._state.get("progress", 0.0))
        track_length = float(self._state.get("track_length", 100.0))
        ship_lane = int(self._state.get("ship_lane", 1))
        charge = float(self._state.get("charge", 0.0))
        shield = float(self._state.get("shield", 0.0))
        integrity = float(self._state.get("integrity", 100.0))
        enemies = list(self._state.get("enemies", []))

        left = 72.0
        right = self.width() - 72.0
        top = 40.0
        bottom = self.height() - 70.0
        painter.setPen(QPen(QColor("#9fd3ff"), 2))
        painter.drawRoundedRect(QRectF(left, top, right - left, bottom - top), 20, 20)

        for idx in range(1, 5):
            y = top + ((bottom - top) * idx / 5.0)
            painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
            painter.drawLine(QPointF(left, y), QPointF(right, y))

        lane_positions = [
            top + ((bottom - top) * 0.2),
            top + ((bottom - top) * 0.5),
            top + ((bottom - top) * 0.8),
        ]

        for enemy in enemies:
            distance = max(0.0, float(enemy.get("progress_mark", 0.0)) - progress)
            x = right - (min(distance, 28.0) / 28.0) * (right - left - 120.0)
            lane = max(0, min(2, int(enemy.get("lane", 1))))
            center_y = lane_positions[lane]
            danger = QColor("#ff9d7d") if distance <= 10.0 else QColor("#ffc08a")
            painter.setPen(QPen(danger, 3))
            painter.setBrush(QColor(120, 34, 20, 190))
            painter.drawRoundedRect(QRectF(x - 20.0, center_y - 18.0, 40.0, 36.0), 12, 12)
            painter.drawLine(QPointF(x - 28.0, center_y), QPointF(x + 28.0, center_y))

        ship_x = left + 84.0
        ship_y = lane_positions[max(0, min(2, ship_lane))]
        glow = QRadialGradient(QPointF(ship_x, ship_y), 40)
        glow.setColorAt(0.0, QColor(164, 224, 255, 220))
        glow.setColorAt(1.0, QColor(164, 224, 255, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(ship_x, ship_y), 36, 36)

        painter.setBrush(QColor("#f4f6fb"))
        points = [
            QPointF(ship_x - 18, ship_y + 8),
            QPointF(ship_x + 12, ship_y),
            QPointF(ship_x - 18, ship_y - 8),
            QPointF(ship_x - 10, ship_y),
        ]
        painter.drawPolygon(points)

        if shield > 4.0:
            painter.setPen(QPen(QColor("#9be7ff"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(ship_x, ship_y), 26 + (shield * 0.04), 26 + (shield * 0.04))

        self._draw_meter(
            painter,
            QRectF(left, 16, 160, 10),
            QColor("#66b8ff"),
            charge / 100.0,
            "Charge",
        )
        self._draw_meter(
            painter,
            QRectF(right - 160, 16, 160, 10),
            QColor("#8cf0cb"),
            shield / 100.0,
            "Shield",
            align_right=True,
        )

        painter.setPen(QColor("#d9e7f6"))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(0, self.height() - 56, self.width(), 20), Qt.AlignCenter, f"Hull {integrity:.0f}%")
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 22),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )

    def _draw_meter(
        self,
        painter: QPainter,
        rect: QRectF,
        color: QColor,
        ratio: float,
        label: str,
        align_right: bool = False,
    ):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(rect, 5, 5)
        fill_rect = QRectF(rect.left(), rect.top(), rect.width() * max(0.0, min(1.0, ratio)), rect.height())
        painter.setBrush(color)
        painter.drawRoundedRect(fill_rect, 5, 5)
        painter.setPen(QColor("#d9e7f6"))
        text_rect = QRectF(rect.left(), rect.bottom() + 4, rect.width(), 18)
        painter.drawText(text_rect, Qt.AlignRight if align_right else Qt.AlignLeft, label)


class JumpBallWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0c0904"))

        sky = QLinearGradient(0, 0, 0, self.height())
        sky.setColorAt(0.0, QColor("#3a1707"))
        sky.setColorAt(1.0, QColor("#090603"))
        painter.fillRect(self.rect(), sky)

        progress = float(self._state.get("progress", 0.0))
        track_length = float(self._state.get("track_length", 100.0))
        ball_height = float(self._state.get("ball_height", 0.0))
        combo = int(self._state.get("combo", 0))
        best_combo = int(self._state.get("best_combo", 0))
        obstacles = list(self._state.get("obstacles", []))

        ground_y = self.height() - 92.0
        track_rect = QRectF(54, ground_y, self.width() - 108, 18)
        painter.setPen(QPen(QColor("#ffc784"), 2))
        painter.setBrush(QColor("#5b2a0d"))
        painter.drawRoundedRect(track_rect, 9, 9)

        for obstacle in obstacles:
            distance = max(0.0, float(obstacle.get("progress_mark", 0.0)) - progress)
            x = track_rect.left() + 120.0 + (distance / max(track_length * 0.35, 1.0)) * (track_rect.width() - 170.0)
            if x > self.width() - 40:
                continue
            height = float(obstacle.get("required_height", 24.0))
            top = ground_y - min(132.0, height * 1.6)
            painter.setPen(QPen(QColor("#ffe2b3"), 2))
            painter.setBrush(QColor("#d46f24"))
            painter.drawRoundedRect(QRectF(x, top, 30, ground_y - top), 10, 10)

        ball_x = track_rect.left() + 78.0
        ball_y = ground_y - 12.0 - min(150.0, ball_height * 1.8)
        glow = QRadialGradient(QPointF(ball_x, ball_y), 34)
        glow.setColorAt(0.0, QColor("#ffe59f"))
        glow.setColorAt(1.0, QColor(255, 229, 159, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(ball_x, ball_y), 32, 32)
        painter.setBrush(QColor("#ffd166"))
        painter.drawEllipse(QPointF(ball_x, ball_y), 18, 18)

        painter.setPen(QColor("#fff2d5"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 18, self.width(), 22), Qt.AlignCenter, f"Combo {combo}   Best {best_combo}")
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 22),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )


class NeuroRacerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#050307"))

        glow = QRadialGradient(self.rect().center(), min(self.width(), self.height()) * 0.55)
        glow.setColorAt(0.0, QColor(118, 53, 142, 70))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)

        lane = int(self._state.get("lane", 1))
        speed = float(self._state.get("speed", 58.0))
        stability = float(self._state.get("stability", 80.0))
        combo = int(self._state.get("combo", 0))
        hazards = list(self._state.get("hazards", []))
        progress = float(self._state.get("progress", 0.0))

        road = QPainterPath()
        road.moveTo(self.width() * 0.28, self.height() - 40)
        road.lineTo(self.width() * 0.18, 50)
        road.lineTo(self.width() * 0.82, 50)
        road.lineTo(self.width() * 0.72, self.height() - 40)
        road.closeSubpath()
        painter.setPen(QPen(QColor("#cab3ff"), 2))
        painter.setBrush(QColor("#17131d"))
        painter.drawPath(road)

        for divider in (1, 2):
            ratio = divider / 3.0
            x1 = (self.width() * 0.28) + ((self.width() * 0.44) * ratio)
            x2 = (self.width() * 0.18) + ((self.width() * 0.64) * ratio)
            painter.setPen(QPen(QColor(255, 255, 255, 40), 2, Qt.DashLine))
            painter.drawLine(QPointF(x1, self.height() - 40), QPointF(x2, 50))

        lane_centers = [
            self.width() * 0.38,
            self.width() * 0.50,
            self.width() * 0.62,
        ]
        car_x = lane_centers[max(0, min(2, lane))]
        car_rect = QRectF(car_x - 20, self.height() - 94, 40, 64)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ff5f6d"))
        painter.drawRoundedRect(car_rect, 14, 14)

        for hazard in hazards:
            distance = max(0.0, float(hazard.get("progress_mark", 0.0)) - progress)
            y = self.height() - 130.0 - min(230.0, distance * 8.0)
            if y < 40:
                continue
            hazard_lane = max(0, min(2, int(hazard.get("lane", 1))))
            hazard_x = lane_centers[hazard_lane]
            width = 24.0 + max(0.0, (230.0 - (self.height() - 130.0 - y)) * 0.04)
            rect = QRectF(hazard_x - width / 2.0, y, width, width * 1.25)
            painter.setPen(QPen(QColor("#ffc2c2"), 2))
            painter.setBrush(QColor("#8f2230"))
            painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QColor("#f5eaff"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(26, 18, 180, 22), Qt.AlignLeft, f"Speed {speed:.0f}")
        painter.drawText(QRectF(self.width() - 206, 18, 180, 22), Qt.AlignRight, f"Stability {stability:.0f}")
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(0, self.height() - 56, self.width(), 20), Qt.AlignCenter, f"Combo {combo}")
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 20),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )


class FullRebootWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#04050a"))

        sky = QLinearGradient(0, 0, 0, self.height())
        sky.setColorAt(0.0, QColor("#0e1933"))
        sky.setColorAt(0.55, QColor("#090f1c"))
        sky.setColorAt(1.0, QColor("#04050a"))
        painter.fillRect(self.rect(), sky)

        serenity = float(self._state.get("serenity", 50.0))
        restlessness = float(self._state.get("restlessness", 25.0))
        calm_depth = float(self._state.get("calm_depth", 0.0))
        target_depth = max(1.0, float(self._state.get("target_depth", 100.0)))
        breath_phase = float(self._state.get("breath_phase", 0.0))
        stage_title = self._state.get("headline", "Full Reboot")

        moon_center = QPointF(self.width() * 0.72, 96.0)
        glow = QRadialGradient(moon_center, 96)
        glow.setColorAt(0.0, QColor(233, 236, 255, 185))
        glow.setColorAt(1.0, QColor(233, 236, 255, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(moon_center, 90, 90)
        painter.setBrush(QColor("#f5f0db"))
        painter.drawEllipse(moon_center, 30, 30)

        for index in range(28):
            x = 52 + ((index * 37) % max(60, self.width() - 110))
            y = 54 + ((index * 23) % 170)
            radius = 1.5 + ((index % 3) * 0.6)
            alpha = 95 + int((serenity / 100.0) * 120)
            painter.setBrush(QColor(214, 231, 255, alpha))
            painter.drawEllipse(QPointF(x, y), radius, radius)

        ring_scale = 0.90 + (breath_phase * 0.35)
        ring_alpha = 80 + int((serenity / 100.0) * 80)
        center = QPointF(self.width() * 0.5, self.height() * 0.55)
        for idx in range(3):
            radius = (58 + (idx * 28)) * ring_scale
            painter.setPen(QPen(QColor(168, 223, 255, ring_alpha - (idx * 18)), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, radius, radius)

        bed_rect = QRectF(self.width() * 0.18, self.height() * 0.72, self.width() * 0.64, 26)
        painter.setPen(QPen(QColor("#5f6886"), 2))
        painter.setBrush(QColor("#101521"))
        painter.drawRoundedRect(bed_rect, 14, 14)

        progress = calm_depth / target_depth
        progress_rect = QRectF(self.width() * 0.22, self.height() * 0.78, self.width() * 0.56, 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 24))
        painter.drawRoundedRect(progress_rect, 6, 6)
        fill = QRectF(progress_rect.left(), progress_rect.top(), progress_rect.width() * max(0.0, min(1.0, progress)), progress_rect.height())
        painter.setBrush(QColor("#8edcc7"))
        painter.drawRoundedRect(fill, 6, 6)

        painter.setPen(QColor("#ecf1ff"))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 18, self.width(), 26), Qt.AlignCenter, stage_title)

        font.setBold(False)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, self.height() - 62, self.width(), 22),
            Qt.AlignCenter,
            f"Serenity {serenity:.0f}   Restlessness {restlessness:.0f}",
        )
        painter.drawText(
            QRectF(0, self.height() - 36, self.width(), 20),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )


class CalmCurrentWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#04100d"))

        rect = QRectF(40, 40, self.width() - 80, self.height() - 100)
        river = QLinearGradient(rect.topLeft(), rect.bottomRight())
        river.setColorAt(0.0, QColor("#0f6c73"))
        river.setColorAt(1.0, QColor("#072126"))
        painter.setBrush(river)
        painter.setPen(QPen(QColor("#8ff5d0"), 2))
        painter.drawRoundedRect(rect, 44, 44)

        turbulence = float(self._state.get("turbulence", 0.0))
        for idx in range(4):
            wave_y = rect.top() + 48 + (idx * 54)
            painter.setPen(QPen(QColor(255, 255, 255, 30 + int(turbulence * 10)), 2))
            painter.drawArc(QRectF(rect.left() + 30, wave_y, rect.width() - 60, 42), 0, 180 * 16)

        distance = float(self._state.get("distance", 0.0))
        target = max(1.0, float(self._state.get("target_distance", 100.0)))
        progress = distance / target
        lantern_x = rect.left() + (rect.width() * progress)
        lantern_y = rect.center().y() + (turbulence * 2.5)
        glow = QRadialGradient(QPointF(lantern_x, lantern_y), 32)
        glow.setColorAt(0.0, QColor(255, 214, 127, 220))
        glow.setColorAt(1.0, QColor(255, 214, 127, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(lantern_x, lantern_y), 28, 28)
        painter.setBrush(QColor("#ffeab0"))
        painter.drawRoundedRect(QRectF(lantern_x - 10, lantern_y - 12, 20, 24), 10, 10)

        painter.setPen(QColor("#d7f7ef"))
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, self.height() - 62, self.width(), 24),
            Qt.AlignCenter,
            f"Calm streak {self._state.get('calm_streak', 0)}   Best {self._state.get('best_streak', 0)}",
        )
        font.setBold(False)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 22),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )


class MemoryGridWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(380)

    def sizeHint(self):
        return QSize(520, 460)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#09060f"))

        grid_size = int(self._state.get("grid_size", 4))
        total_cells = max(grid_size * grid_size, len(self._state.get("symbols", [])), 1)
        active_cells = len(self._state.get("symbols", [])) or total_cells
        board_size = min(self.width() - 140, self.height() - 160)
        cell = board_size / max(grid_size, 1)
        left = (self.width() - board_size) / 2.0
        top = 86.0
        mode = self._state.get("mode", "pattern")
        selected = int(self._state.get("selected_index", 0))
        preview_cells = set(self._state.get("preview_cells", []))
        confirmed_cells = set(self._state.get("confirmed_cells", []))
        candidate_cells = set(self._state.get("candidate_cells", []))
        revealed_cells = set(self._state.get("revealed_cells", []))
        symbols = list(self._state.get("symbols", []))

        self._draw_background_glow(painter, mode)

        for idx in range(active_cells):
            row = idx // grid_size
            col = idx % grid_size
            rect = QRectF(left + (col * cell), top + (row * cell), cell - 10, cell - 10)
            fill = QColor("#251635")
            if idx == selected and mode != "trail":
                fill = QColor("#8f67cf")
            if idx in candidate_cells:
                fill = QColor("#3d4a89")
            if idx in confirmed_cells:
                fill = QColor("#3db28c")
            if idx in preview_cells:
                fill = QColor("#d0b1ff")
            if mode == "pairs" and idx not in revealed_cells and idx not in preview_cells and idx not in confirmed_cells:
                fill = QColor("#1f1729")
            painter.setPen(QPen(QColor("#e2d7f6"), 2))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 18, 18)

            if mode == "pairs":
                label = "?" if idx not in preview_cells and idx not in revealed_cells and idx not in confirmed_cells else symbols[idx]
                self._draw_cell_label(painter, rect, label)
            elif idx in preview_cells or idx in confirmed_cells or idx == selected:
                self._draw_cell_label(painter, rect, str(idx + 1))

        if mode == "trail":
            self._draw_path_lines(painter, left, top, cell, self._state.get("path_lines", []), QColor("#7fe7de"))
            if selected in candidate_cells:
                self._highlight_cell_outline(painter, left, top, cell, selected, QColor("#d9f99d"))
            current_path = self._state.get("confirmed_cells", [])
            if current_path:
                self._highlight_cell_outline(painter, left, top, cell, current_path[-1], QColor("#8ad8ff"))

        self._draw_memory_header(painter)
        self._draw_memory_footer(painter)

    def _draw_background_glow(self, painter: QPainter, mode: str):
        tint = {
            "pattern": QColor(129, 89, 219, 70),
            "stack": QColor(91, 110, 228, 70),
            "trail": QColor(50, 157, 134, 70),
            "pairs": QColor(191, 125, 66, 70),
        }.get(mode, QColor(129, 89, 219, 70))
        glow = QRadialGradient(self.rect().center(), min(self.width(), self.height()) * 0.48)
        glow.setColorAt(0.0, tint)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)

    def _draw_cell_label(self, painter: QPainter, rect: QRectF, text: str):
        painter.setPen(QColor("#f3edf9"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _highlight_cell_outline(self, painter: QPainter, left: float, top: float, cell: float, idx: int, color: QColor):
        grid_size = int(self._state.get("grid_size", 4))
        row = idx // grid_size
        col = idx % grid_size
        rect = QRectF(left + (col * cell), top + (row * cell), cell - 10, cell - 10)
        painter.setPen(QPen(color, 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 14, 14)

    def _draw_path_lines(self, painter: QPainter, left: float, top: float, cell: float, path: list[int], color: QColor):
        if len(path) < 2:
            return
        grid_size = int(self._state.get("grid_size", 4))
        painter.setPen(QPen(color, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for index in range(len(path) - 1):
            src = path[index]
            dst = path[index + 1]
            src_row, src_col = divmod(src, grid_size)
            dst_row, dst_col = divmod(dst, grid_size)
            src_center = QPointF(left + (src_col * cell) + ((cell - 10) / 2), top + (src_row * cell) + ((cell - 10) / 2))
            dst_center = QPointF(left + (dst_col * cell) + ((cell - 10) / 2), top + (dst_row * cell) + ((cell - 10) / 2))
            painter.drawLine(src_center, dst_center)

    def _draw_memory_header(self, painter: QPainter):
        painter.setPen(QColor("#f3edf9"))
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        headline = self._state.get("headline", "Memory")
        painter.drawText(QRectF(0, 20, self.width(), 24), Qt.AlignCenter, headline)

        font.setBold(False)
        font.setPointSize(10)
        painter.setFont(font)
        phase = self._state.get("phase", "").replace("_", " ").title()
        chunk_index = int(self._state.get("chunk_index", 0))
        painter.drawText(QRectF(0, 48, self.width(), 20), Qt.AlignCenter, f"{phase}   Chunk {chunk_index + 1}")

    def _draw_memory_footer(self, painter: QPainter):
        painter.setPen(QColor("#f3edf9"))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)

        preview_ticks = int(self._state.get("preview_ticks", 0))
        mistakes = int(self._state.get("mistakes", 0))
        confirmed = int(self._state.get("confirmed_count", 0))
        message = self._state.get("message", "")
        footer = f"Confirmed {confirmed}   Mistakes {mistakes}"
        if "reveal_budget" in self._state:
            footer += f"   Budget {self._state['reveal_budget']}"
        if preview_ticks > 0:
            footer = f"Preview {preview_ticks}   " + footer
        painter.drawText(QRectF(0, self.height() - 58, self.width(), 22), Qt.AlignCenter, footer)
        painter.drawText(QRectF(0, self.height() - 32, self.width(), 20), Qt.AlignCenter, message)


class PatternRecallWidget(MemoryGridWidget):
    pass
