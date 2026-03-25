"""
Paint-only widgets for the non-maze EEG training games.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from gui.widgets.mind_maze_board import draw_balance_panel
from prosthetic_arm import hand_image_path
from prosthetic_arm.arm_state import state_label


def _star_path(center: QPointF, outer_radius: float, inner_radius: float) -> QPainterPath:
    path = QPainterPath()
    for index in range(10):
        angle = math.radians(-90 + (index * 36))
        radius = outer_radius if index % 2 == 0 else inner_radius
        point = QPointF(
            center.x() + (math.cos(angle) * radius),
            center.y() + (math.sin(angle) * radius),
        )
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def _balance_panel_rect(widget: QWidget, top: float, width_ratio: float = 0.66) -> QRectF:
    width = widget.width() * width_ratio
    left = (widget.width() - width) / 2.0
    return QRectF(max(18.0, left), top, min(width, widget.width() - 36.0), 132.0)


def _draw_widget_balance_panel(
    widget: QWidget,
    painter: QPainter,
    state: dict,
    *,
    top: float,
    width_ratio: float = 0.66,
) -> QRectF | None:
    panel = state.get("balance_panel")
    if not panel:
        return None
    rect = _balance_panel_rect(widget, top, width_ratio=width_ratio)
    draw_balance_panel(painter, rect, panel)
    return rect


class _ImmersiveGameWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self._menu_callback = None
        self._menu_button_rect = QRectF()

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def set_menu_callback(self, callback):
        self._menu_callback = callback

    def _handle_click(self, pos: QPointF) -> bool:
        return False

    def _draw_balance_panel(self, painter: QPainter, *, top: float = 78.0, width_ratio: float = 0.60) -> QRectF | None:
        return _draw_widget_balance_panel(self, painter, self._state, top=top, width_ratio=width_ratio)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            pos = event.position()
            if self._menu_button_rect.contains(pos) and self._menu_callback:
                self._menu_callback()
                event.accept()
                return
            if self._handle_click(pos):
                event.accept()
                return
        super().mouseReleaseEvent(event)


class SpaceShooterWidget(_ImmersiveGameWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(560)

    def sizeHint(self):
        return QSize(520, 720)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_backdrop(painter)

        field_height = max(1.0, float(self._state.get("field_height", 120.0)))
        corridor_width = max(1, int(self._state.get("corridor_width", 7)))
        ship_slot = int(self._state.get("ship_slot", corridor_width // 2))
        ship_y = float(self._state.get("ship_y", 104.0))
        score = int(self._state.get("score", 0))
        hull = int(self._state.get("hull", 4))
        burst_ticks = int(self._state.get("burst_ticks", 0))
        progress = float(self._state.get("star_progress", 0.0))
        wave_index = int(self._state.get("wave_index", 0))
        wave_count = max(1, int(self._state.get("wave_count", 1)))

        menu_rect = QRectF(16, 16, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(painter, menu_rect)
        self._draw_star_bar(painter, QRectF(88, 20, self.width() - 192, 40), progress)
        self._draw_score_pill(painter, QRectF(self.width() - 98, 18, 82, 42), str(score))
        balance_rect = _balance_panel_rect(self, 74.0, width_ratio=0.60) if self._state.get("balance_panel") else None
        field_top = (balance_rect.bottom() + 12.0) if balance_rect is not None else 82.0

        field_rect = QRectF(self.width() * 0.24, field_top, self.width() * 0.52, max(180.0, self.height() - field_top - 106.0))
        field_fill = QLinearGradient(field_rect.topLeft(), field_rect.bottomLeft())
        field_fill.setColorAt(0.0, QColor(18, 10, 30, 235))
        field_fill.setColorAt(1.0, QColor(8, 5, 16, 235))
        painter.setPen(QPen(QColor(112, 204, 255, 55), 2))
        painter.setBrush(field_fill)
        painter.drawRoundedRect(field_rect, 34, 34)

        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        for slot in range(1, corridor_width):
            x = field_rect.left() + ((field_rect.width() * slot) / corridor_width)
            painter.drawLine(QPointF(x, field_rect.top()), QPointF(x, field_rect.bottom()))

        slot_x = lambda slot: field_rect.left() + (((slot + 0.5) / corridor_width) * field_rect.width())
        y_to_px = lambda value: field_rect.top() + ((max(0.0, min(field_height, value)) / field_height) * field_rect.height())

        for index in range(18):
            star_x = field_rect.left() + ((index * 37) % max(20.0, field_rect.width() - 20.0)) + 10.0
            star_y = field_rect.top() + ((index * 59) % max(40.0, field_rect.height() - 20.0)) + 8.0
            painter.setBrush(QColor(166, 233, 255, 170 if index % 3 == 0 else 110))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(star_x, star_y), 1.2 + (index % 2), 1.2 + (index % 2))

        for projectile in self._state.get("projectiles", []):
            center = QPointF(slot_x(int(projectile.get("slot", 0))), y_to_px(float(projectile.get("y", 0.0))))
            power = int(projectile.get("power", 1))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#77f0ff") if power == 1 else QColor("#fff26c"))
            painter.drawEllipse(center, 3.2 + power, 7.0 + power)

        for enemy in sorted(self._state.get("enemies", []), key=lambda item: float(item.get("y", 0.0))):
            enemy_center = QPointF(slot_x(int(enemy.get("slot", 0))), y_to_px(float(enemy.get("y", 0.0))))
            self._draw_enemy(painter, enemy_center, int(enemy.get("max_hp", 1)), int(enemy.get("hp", 1)))

        for pickup in self._state.get("pickups", []):
            pickup_center = QPointF(slot_x(int(pickup.get("slot", 0))), y_to_px(float(pickup.get("y", 0.0))))
            self._draw_pickup(painter, pickup_center, str(pickup.get("kind", "weapon")))

        for effect in self._state.get("explosions", []):
            center = QPointF(slot_x(int(effect.get("slot", 0))), y_to_px(float(effect.get("y", 0.0))))
            radius = 16.0 + (float(effect.get("ticks", 0)) * 2.0)
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.0, QColor("#fff8b8"))
            glow.setColorAt(0.35, QColor("#ff934f"))
            glow.setColorAt(1.0, QColor(255, 147, 79, 0))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center, radius, radius)

        for popup in self._state.get("score_popups", []):
            popup_center = QPointF(slot_x(int(popup.get("slot", ship_slot))), y_to_px(float(popup.get("y", 0.0))))
            painter.setPen(QColor("#ffe082"))
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(popup_center.x() - 34, popup_center.y() - 24, 68, 18), Qt.AlignCenter, str(popup.get("text", "")))

        ship_center = QPointF(slot_x(ship_slot), y_to_px(ship_y))
        self._draw_ship(painter, ship_center, burst_ticks > 0)

        painter.setPen(QColor("#d8ebff"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(18, self.height() - 98, 140, 22), Qt.AlignLeft, f"Hull {hull}/4")
        painter.drawText(QRectF(self.width() - 158, self.height() - 98, 140, 22), Qt.AlignRight, f"Wave {wave_index + 1}/{wave_count}")
        painter.drawText(QRectF(0, self.height() - 72, self.width(), 22), Qt.AlignCenter, f"Weapon {self._state.get('weapon_level', 1)}   Burst {max(0, burst_ticks)}")
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#b7cae8"))
        painter.drawText(QRectF(26, self.height() - 42, self.width() - 52, 22), Qt.AlignCenter, str(self._state.get("message", "")))

        self._draw_balance_panel(painter, top=74.0, width_ratio=0.60)
        if self._state.get("overlay_kind"):
            self._draw_overlay(painter)

    def _paint_backdrop(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#08040f"))
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.0, QColor("#14091f"))
        bg.setColorAt(0.55, QColor("#0c0817"))
        bg.setColorAt(1.0, QColor("#04030b"))
        painter.fillRect(self.rect(), bg)

    def _draw_menu_button(self, painter: QPainter, rect: QRectF):
        shell = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shell.setColorAt(0.0, QColor("#3f8ff6"))
        shell.setColorAt(1.0, QColor("#1c54b4"))
        painter.setPen(QPen(QColor("#89c8ff"), 2))
        painter.setBrush(shell)
        painter.drawRoundedRect(rect, 14, 14)
        painter.setPen(QPen(QColor("#e8f5ff"), 3, Qt.SolidLine, Qt.RoundCap))
        for offset in (15, 26, 37):
            painter.drawLine(QPointF(rect.left() + 14, rect.top() + offset), QPointF(rect.right() - 14, rect.top() + offset))

    def _draw_star_bar(self, painter: QPainter, rect: QRectF, progress: float):
        painter.setPen(QPen(QColor("#4b506d"), 2))
        painter.setBrush(QColor("#2f3045"))
        painter.drawRoundedRect(rect, 20, 20)
        fill = QRectF(rect.left() + 4, rect.top() + 4, (rect.width() - 8) * max(0.0, min(1.0, progress)), rect.height() - 8)
        fill_grad = QLinearGradient(fill.topLeft(), fill.topRight())
        fill_grad.setColorAt(0.0, QColor("#11a9ff"))
        fill_grad.setColorAt(1.0, QColor("#53d3ff"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill_grad)
        painter.drawRoundedRect(fill, 16, 16)
        for index, ratio in enumerate((0.25, 0.5, 0.75)):
            filled = progress >= ratio
            center = QPointF(rect.left() + (rect.width() * ratio), rect.center().y())
            painter.setBrush(QColor("#ffd34d") if filled else QColor("#a0a4be"))
            painter.setPen(QPen(QColor(255, 255, 255, 95), 1.5))
            painter.drawPath(_star_path(center, 10.5, 4.8))

    def _draw_score_pill(self, painter: QPainter, rect: QRectF, text: str):
        pill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        pill.setColorAt(0.0, QColor("#27293d"))
        pill.setColorAt(1.0, QColor("#1a1d30"))
        painter.setPen(QPen(QColor("#5b6489"), 2))
        painter.setBrush(pill)
        painter.drawRoundedRect(rect, 18, 18)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f6fbff"))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_enemy(self, painter: QPainter, center: QPointF, max_hp: int, hp: int):
        scale = 0.92 + (max_hp * 0.16)
        body = QPainterPath()
        body.moveTo(center.x(), center.y() - (18 * scale))
        body.lineTo(center.x() + (16 * scale), center.y() - (4 * scale))
        body.lineTo(center.x() + (12 * scale), center.y() + (14 * scale))
        body.lineTo(center.x(), center.y() + (8 * scale))
        body.lineTo(center.x() - (12 * scale), center.y() + (14 * scale))
        body.lineTo(center.x() - (16 * scale), center.y() - (4 * scale))
        body.closeSubpath()
        color = QColor("#ff6f5c") if max_hp == 1 else QColor("#ffb04d")
        painter.setPen(QPen(QColor(255, 255, 255, 80), 1.5))
        painter.setBrush(color)
        painter.drawPath(body)
        painter.setBrush(QColor("#2b0f17"))
        painter.drawRect(QRectF(center.x() - (5 * scale), center.y() - (4 * scale), 10 * scale, 6 * scale))
        if hp < max_hp:
            painter.setPen(QPen(QColor("#ffe082"), 2))
            painter.drawLine(QPointF(center.x() - (12 * scale), center.y() + (18 * scale)), QPointF(center.x() + (12 * scale), center.y() + (18 * scale)))

    def _draw_pickup(self, painter: QPainter, center: QPointF, kind: str):
        color = QColor("#7df2c8") if kind == "repair" else QColor("#8ed1ff")
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(center.x() - 10, center.y() - 10, 20, 20), 6, 6)
        painter.setPen(QPen(QColor("#18334c"), 2))
        if kind == "repair":
            painter.drawLine(QPointF(center.x() - 5, center.y()), QPointF(center.x() + 5, center.y()))
            painter.drawLine(QPointF(center.x(), center.y() - 5), QPointF(center.x(), center.y() + 5))
        else:
            painter.drawLine(QPointF(center.x() - 4, center.y() - 4), QPointF(center.x() + 4, center.y() + 4))
            painter.drawLine(QPointF(center.x() + 4, center.y() - 4), QPointF(center.x() - 4, center.y() + 4))

    def _draw_ship(self, painter: QPainter, center: QPointF, bursting: bool):
        glow = QRadialGradient(center, 46)
        glow.setColorAt(0.0, QColor(122, 236, 255, 160))
        glow.setColorAt(1.0, QColor(122, 236, 255, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 44, 44)

        hull = QPainterPath()
        hull.moveTo(center.x(), center.y() - 24)
        hull.lineTo(center.x() + 18, center.y() + 12)
        hull.lineTo(center.x() + 8, center.y() + 10)
        hull.lineTo(center.x() + 2, center.y() + 22)
        hull.lineTo(center.x() - 2, center.y() + 22)
        hull.lineTo(center.x() - 8, center.y() + 10)
        hull.lineTo(center.x() - 18, center.y() + 12)
        hull.closeSubpath()
        hull_fill = QLinearGradient(center.x(), center.y() - 24, center.x(), center.y() + 22)
        hull_fill.setColorAt(0.0, QColor("#89eeff"))
        hull_fill.setColorAt(1.0, QColor("#3684ef"))
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1.5))
        painter.setBrush(hull_fill)
        painter.drawPath(hull)
        painter.setBrush(QColor("#17326f"))
        painter.drawEllipse(QPointF(center.x(), center.y() - 4), 6, 8)
        flame_color = QColor("#ffe066") if bursting else QColor("#ff8847")
        painter.setBrush(flame_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(center.x() - 6, center.y() + 24), 4, 8 if bursting else 6)
        painter.drawEllipse(QPointF(center.x() + 6, center.y() + 24), 4, 8 if bursting else 6)

    def _draw_overlay(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor(5, 3, 10, 120))
        card = QRectF(self.width() * 0.16, self.height() * 0.28, self.width() * 0.68, self.height() * 0.24)
        fill = QLinearGradient(card.topLeft(), card.bottomLeft())
        fill.setColorAt(0.0, QColor("#1d2342"))
        fill.setColorAt(1.0, QColor("#111529"))
        painter.setPen(QPen(QColor("#8bd6ff"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, 30, 30)
        painter.setPen(QColor("#f8fbff"))
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(card.left() + 20, card.top() + 26, card.width() - 40, 34), Qt.AlignCenter, str(self._state.get("overlay_title", "")))
        body_font = QFont()
        body_font.setPointSize(11)
        painter.setFont(body_font)
        painter.setPen(QColor("#b7c8ef"))
        painter.drawText(QRectF(card.left() + 24, card.top() + 72, card.width() - 48, 50), Qt.AlignCenter | Qt.TextWordWrap, str(self._state.get("overlay_subtitle", "")))


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
        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None

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
        combo_top = (balance_rect.bottom() + 10.0) if balance_rect is not None else 18.0
        painter.drawText(QRectF(0, combo_top, self.width(), 22), Qt.AlignCenter, f"Combo {combo}   Best {best_combo}")
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 22),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )
        _draw_widget_balance_panel(self, painter, self._state, top=18.0)


class NeuroRacerWidget(_ImmersiveGameWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(520)

    def sizeHint(self):
        return QSize(640, 520)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        sky = QLinearGradient(0, 0, 0, self.height())
        sky.setColorAt(0.0, QColor("#53c5ff"))
        sky.setColorAt(0.45, QColor("#8dd7ff"))
        sky.setColorAt(1.0, QColor("#cfeeff"))
        painter.fillRect(self.rect(), sky)

        cloud_glow = QRadialGradient(QPointF(self.width() * 0.72, self.height() * 0.24), self.width() * 0.34)
        cloud_glow.setColorAt(0.0, QColor(255, 255, 255, 110))
        cloud_glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(self.rect(), cloud_glow)

        progress = float(self._state.get("star_progress", 0.0))
        menu_rect = QRectF(18, 18, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(painter, menu_rect)
        self._draw_star_bar(painter, QRectF(self.width() * 0.22, 18, self.width() * 0.44, 42), progress)
        self._draw_score_pill(painter, QRectF(self.width() - 114, 18, 96, 42), str(int(self._state.get("score", 0))))
        balance_rect = _balance_panel_rect(self, 74.0, width_ratio=0.60) if self._state.get("balance_panel") else None

        road_top_y = (balance_rect.bottom() + 18.0) if balance_rect is not None else 86.0
        road_bottom_y = self.height() - 92.0
        bottom_width = self.width() * 0.58
        top_width = self.width() * 0.16
        center_x = self.width() * 0.5
        road = QPainterPath()
        road.moveTo(center_x - (bottom_width / 2), road_bottom_y)
        road.lineTo(center_x - (top_width / 2), road_top_y)
        road.lineTo(center_x + (top_width / 2), road_top_y)
        road.lineTo(center_x + (bottom_width / 2), road_bottom_y)
        road.closeSubpath()
        road_fill = QLinearGradient(0, road_top_y, 0, road_bottom_y)
        road_fill.setColorAt(0.0, QColor("#66626a"))
        road_fill.setColorAt(1.0, QColor("#2b2b32"))
        painter.setPen(QPen(QColor("#1b1c21"), 2))
        painter.setBrush(road_fill)
        painter.drawPath(road)

        for side in (-1, 1):
            for index in range(12):
                ratio0 = index / 12.0
                ratio1 = (index + 1) / 12.0
                y0 = road_top_y + ((road_bottom_y - road_top_y) * ratio0)
                y1 = road_top_y + ((road_bottom_y - road_top_y) * ratio1)
                width0 = top_width + ((bottom_width - top_width) * ratio0)
                width1 = top_width + ((bottom_width - top_width) * ratio1)
                x0 = center_x + (side * (width0 / 2))
                x1 = center_x + (side * (width1 / 2))
                stripe = QPainterPath()
                stripe.moveTo(x0, y0)
                stripe.lineTo(x1, y1)
                stripe.lineTo(x1 + (side * 16), y1)
                stripe.lineTo(x0 + (side * 10), y0)
                stripe.closeSubpath()
                painter.setBrush(QColor("#ff2d2d") if index % 2 == 0 else QColor("#f3f6ff"))
                painter.setPen(Qt.NoPen)
                painter.drawPath(stripe)

        painter.setPen(QPen(QColor(255, 255, 255, 150), 3, Qt.DashLine))
        for lane_ratio in (0.33, 0.66):
            painter.drawLine(
                QPointF(center_x - ((bottom_width / 2) - (bottom_width * lane_ratio)), road_bottom_y),
                QPointF(center_x - ((top_width / 2) - (top_width * lane_ratio)), road_top_y),
            )

        finish_distance = max(1.0, float(self._state.get("finish_distance", 1000.0)))
        progress_ratio = float(self._state.get("progress_ratio", 0.0))
        arch_width = top_width * (1.2 + (progress_ratio * 0.3))
        arch_y = road_top_y + 12
        painter.setPen(QPen(QColor("#222222"), 5))
        painter.drawLine(QPointF(center_x - (arch_width / 2), arch_y), QPointF(center_x + (arch_width / 2), arch_y))
        for side in (-1, 1):
            painter.drawLine(QPointF(center_x + (side * arch_width / 2), arch_y), QPointF(center_x + (side * arch_width / 2), arch_y + 24))

        lane = int(self._state.get("lane", 1))
        for car in self._state.get("traffic", []):
            self._draw_traffic_car(
                painter,
                center_x,
                top_width,
                bottom_width,
                road_top_y,
                road_bottom_y,
                int(car.get("lane", 1)),
                float(car.get("gap", 200.0)),
            )

        for effect in self._state.get("effects", []):
            self._draw_effect(
                painter,
                center_x,
                top_width,
                bottom_width,
                road_top_y,
                road_bottom_y,
                int(effect.get("lane", lane)),
                float(effect.get("gap", 28.0)),
                str(effect.get("kind", "spark")),
                int(effect.get("ticks", 1)),
            )

        self._draw_player_car(
            painter,
            center_x,
            bottom_width,
            road_bottom_y,
            lane,
            int(self._state.get("nitro_ticks", 0)) > 0,
        )

        self._draw_bottom_chrome(painter)

        painter.setPen(QColor("#f4fbff"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(20, self.height() - 82, 180, 22), Qt.AlignLeft, f"Speed {float(self._state.get('speed', 0.0)):.0f}")
        painter.drawText(QRectF(self.width() - 200, self.height() - 82, 180, 22), Qt.AlignRight, f"Nitro {float(self._state.get('nitro', 0.0)):.0f}")
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#234463"))
        painter.drawText(QRectF(20, self.height() - 58, 220, 20), Qt.AlignLeft, f"Stability {float(self._state.get('stability', 0.0)):.0f}")
        painter.drawText(QRectF(self.width() - 240, self.height() - 58, 220, 20), Qt.AlignRight, f"Overtakes {int(self._state.get('overtakes', 0))}")
        painter.drawText(QRectF(0, self.height() - 34, self.width(), 20), Qt.AlignCenter, str(self._state.get("message", "")))

        self._draw_balance_panel(painter, top=74.0, width_ratio=0.60)
        if self._state.get("overlay_kind"):
            self._draw_overlay(painter)

    def _draw_menu_button(self, painter: QPainter, rect: QRectF):
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#f7f7fb"))
        fill.setColorAt(1.0, QColor("#ced4e3"))
        painter.setPen(QPen(QColor("#8794ad"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 15, 15)
        painter.setPen(QPen(QColor("#525f73"), 3, Qt.SolidLine, Qt.RoundCap))
        for offset in (15, 26, 37):
            painter.drawLine(QPointF(rect.left() + 14, rect.top() + offset), QPointF(rect.right() - 14, rect.top() + offset))

    def _draw_star_bar(self, painter: QPainter, rect: QRectF, progress: float):
        painter.setPen(QPen(QColor("#6079a3"), 2))
        painter.setBrush(QColor("#dcecff"))
        painter.drawRoundedRect(rect, 20, 20)
        fill = QRectF(rect.left() + 4, rect.top() + 4, (rect.width() - 8) * max(0.0, min(1.0, progress)), rect.height() - 8)
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0.0, QColor("#1fb7ff"))
        grad.setColorAt(1.0, QColor("#6be3ff"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(fill, 16, 16)
        for index, ratio in enumerate((0.25, 0.5, 0.75)):
            painter.setBrush(QColor("#ffd348") if progress >= ratio else QColor("#9aa9c7"))
            painter.setPen(QPen(QColor(255, 255, 255, 110), 1.5))
            painter.drawPath(_star_path(QPointF(rect.left() + (rect.width() * ratio), rect.center().y()), 10.0, 4.8))

    def _draw_score_pill(self, painter: QPainter, rect: QRectF, text: str):
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#1f2937"))
        fill.setColorAt(1.0, QColor("#111827"))
        painter.setPen(QPen(QColor("#7a879d"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 18, 18)
        painter.setPen(QColor("#f9fbff"))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _lane_point(self, center_x: float, top_width: float, bottom_width: float, top_y: float, bottom_y: float, lane: int, gap: float) -> tuple[QPointF, float]:
        depth = max(0.0, min(1.0, gap / 260.0))
        y = bottom_y - ((1.0 - depth) * (bottom_y - top_y))
        road_width = top_width + ((bottom_width - top_width) * (1.0 - depth))
        lane_ratio = {0: -0.28, 1: 0.0, 2: 0.28}.get(lane, 0.0)
        x = center_x + (road_width * lane_ratio)
        return QPointF(x, y), road_width

    def _draw_traffic_car(self, painter: QPainter, center_x: float, top_width: float, bottom_width: float, top_y: float, bottom_y: float, lane: int, gap: float):
        center, road_width = self._lane_point(center_x, top_width, bottom_width, top_y, bottom_y, lane, gap)
        scale = max(0.28, min(1.0, road_width / bottom_width))
        rect = QRectF(center.x() - (26 * scale), center.y() - (42 * scale), 52 * scale, 82 * scale)
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#37d99b") if lane == 1 else (QColor("#46a9ff") if lane == 0 else QColor("#ffd74e")))
        fill.setColorAt(1.0, QColor("#0f2740"))
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 10, 10)
        painter.setBrush(QColor("#172233"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(rect.left() + (8 * scale), rect.top() + (10 * scale), rect.width() - (16 * scale), rect.height() * 0.28), 6, 6)

    def _draw_effect(self, painter: QPainter, center_x: float, top_width: float, bottom_width: float, top_y: float, bottom_y: float, lane: int, gap: float, kind: str, ticks: int):
        center, road_width = self._lane_point(center_x, top_width, bottom_width, top_y, bottom_y, lane, gap)
        radius = max(10.0, (road_width / 7.0) + (ticks * 2.0))
        glow = QRadialGradient(center, radius)
        if kind == "impact":
            glow.setColorAt(0.0, QColor("#fff0b5"))
            glow.setColorAt(0.35, QColor("#ff7a4f"))
        else:
            glow.setColorAt(0.0, QColor("#d8f8ff"))
            glow.setColorAt(0.35, QColor("#8fe7ff"))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius, radius)

    def _draw_player_car(self, painter: QPainter, center_x: float, bottom_width: float, bottom_y: float, lane: int, nitro_active: bool):
        lane_offset = {0: -0.28, 1: 0.0, 2: 0.28}.get(lane, 0.0)
        car_center = QPointF(center_x + (bottom_width * lane_offset), bottom_y - 26)
        body = QRectF(car_center.x() - 46, car_center.y() - 56, 92, 112)
        fill = QLinearGradient(body.topLeft(), body.bottomLeft())
        fill.setColorAt(0.0, QColor("#ff9c3f"))
        fill.setColorAt(0.55, QColor("#ff6d22"))
        fill.setColorAt(1.0, QColor("#7d2f12"))
        painter.setPen(QPen(QColor(255, 255, 255, 130), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(body, 24, 24)
        painter.setBrush(QColor("#1f1f22"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(body.left() + 14, body.top() + 16, body.width() - 28, 28), 10, 10)
        painter.drawRect(QRectF(body.left() + 18, body.bottom() - 28, body.width() - 36, 12))
        painter.setBrush(QColor("#222834"))
        for offset in (-28, 28):
            painter.drawEllipse(QPointF(car_center.x() + offset, body.bottom() - 10), 10, 10)
        if nitro_active:
            flame = QLinearGradient(car_center.x(), body.bottom() - 8, car_center.x(), body.bottom() + 46)
            flame.setColorAt(0.0, QColor("#a3f6ff"))
            flame.setColorAt(0.4, QColor("#2fc5ff"))
            flame.setColorAt(1.0, QColor(47, 197, 255, 0))
            painter.setBrush(flame)
            painter.drawRoundedRect(QRectF(car_center.x() - 12, body.bottom() - 6, 24, 52), 10, 10)

    def _draw_bottom_chrome(self, painter: QPainter):
        pedal = QRectF(28, self.height() - 120, 68, 72)
        wheel = QRectF(self.width() - 104, self.height() - 122, 76, 76)
        pedal_fill = QLinearGradient(pedal.topLeft(), pedal.bottomLeft())
        pedal_fill.setColorAt(0.0, QColor("#edf2ff"))
        pedal_fill.setColorAt(1.0, QColor("#b7c4d9"))
        painter.setPen(QPen(QColor("#73829c"), 2))
        painter.setBrush(pedal_fill)
        painter.drawRoundedRect(pedal, 18, 18)
        painter.drawRoundedRect(QRectF(110, self.height() - 110, 70, 56), 18, 18)
        painter.setPen(QPen(QColor("#66758a"), 3))
        for col in range(3):
            x = pedal.left() + 18 + (col * 14)
            painter.drawLine(QPointF(x, pedal.top() + 18), QPointF(x, pedal.bottom() - 18))
        painter.drawEllipse(wheel)
        painter.drawEllipse(QRectF(wheel.left() + 18, wheel.top() + 18, wheel.width() - 36, wheel.height() - 36))
        painter.drawLine(QPointF(wheel.center().x(), wheel.top() + 12), QPointF(wheel.center().x(), wheel.center().y() + 10))
        painter.drawLine(QPointF(wheel.left() + 14, wheel.center().y()), QPointF(wheel.center().x(), wheel.center().y() + 10))
        painter.drawLine(QPointF(wheel.right() - 14, wheel.center().y()), QPointF(wheel.center().x(), wheel.center().y() + 10))

    def _draw_overlay(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor(12, 19, 34, 110))
        card = QRectF(self.width() * 0.17, self.height() * 0.28, self.width() * 0.66, self.height() * 0.22)
        fill = QLinearGradient(card.topLeft(), card.bottomLeft())
        fill.setColorAt(0.0, QColor("#f6fbff"))
        fill.setColorAt(1.0, QColor("#d8ecff"))
        painter.setPen(QPen(QColor("#8db4de"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, 24, 24)
        painter.setPen(QColor("#17436d"))
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(card.left() + 20, card.top() + 24, card.width() - 40, 34), Qt.AlignCenter, str(self._state.get("overlay_title", "")))
        body_font = QFont()
        body_font.setPointSize(11)
        painter.setFont(body_font)
        painter.setPen(QColor("#4a6787"))
        painter.drawText(QRectF(card.left() + 24, card.top() + 70, card.width() - 48, 44), Qt.AlignCenter | Qt.TextWordWrap, str(self._state.get("overlay_subtitle", "")))


class NeonDriftArenaWidget(_ImmersiveGameWidget):
    COLOR_THEMES = {
        "violet": ("#b267ff", "#6a2fd1", "#f0d5ff"),
        "gold": ("#ffe36c", "#f1b726", "#fff6cb"),
        "cyan": ("#5ce8ff", "#1ba6ff", "#d6fbff"),
        "lime": ("#a4ff72", "#37d88b", "#ecffd8"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(560)

    def sizeHint(self):
        return QSize(760, 560)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_backdrop(painter)

        progress = float(self._state.get("star_progress", 0.0))
        score = int(self._state.get("score", 0))
        combo = int(self._state.get("combo", 0))
        boost = float(self._state.get("boost_meter", 0.0))
        target_collectibles = int(self._state.get("target_collectibles", 0))
        collected = int(self._state.get("collectibles", 0))

        menu_rect = QRectF(18, 18, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(painter, menu_rect)
        self._draw_star_bar(painter, QRectF(self.width() * 0.18, 18, self.width() * 0.44, 42), progress)
        self._draw_score_pill(painter, QRectF(self.width() - 114, 18, 96, 42), str(score))
        balance_rect = _balance_panel_rect(self, 76.0, width_ratio=0.60) if self._state.get("balance_panel") else None

        arena_top = (balance_rect.bottom() + 18.0) if balance_rect is not None else 92.0
        arena_rect = QRectF(26.0, arena_top, self.width() - 52.0, max(260.0, self.height() - arena_top - 110.0))
        self._draw_projected_city(painter, arena_rect)
        self._draw_projection_floor(painter, arena_rect)

        for hazard in self._state.get("hazards", []):
            self._draw_hazard_pool(painter, arena_rect, hazard)
        for pad in self._state.get("boost_pads", []):
            self._draw_boost_pad(painter, arena_rect, pad)
        for tile in self._state.get("projected_collectibles", []):
            self._draw_collectible_tile(painter, arena_rect, tile)
        for sigil in self._state.get("sigils", []):
            self._draw_sigil(painter, arena_rect, sigil)
        for popup in self._state.get("score_popups", []):
            self._draw_popup(painter, arena_rect, popup)

        self._draw_kart_trail(painter, arena_rect)
        self._draw_kart(painter, arena_rect)
        self._draw_hud(painter, arena_rect, combo, boost, collected, target_collectibles)

        painter.setPen(QColor("#f5f2ff"))
        font = QFont()
        font.setPointSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(26, self.height() - 38, self.width() - 52, 22), Qt.AlignCenter, str(self._state.get("message", "")))

        self._draw_balance_panel(painter, top=76.0, width_ratio=0.60)
        if self._state.get("overlay_kind"):
            self._draw_overlay(painter)

    def _lane_point(self, arena_rect: QRectF, lane_pos: float, gap: float) -> tuple[QPointF, float]:
        lane_count = max(2, int(self._state.get("lane_count", 5)))
        depth = max(0.0, min(1.0, float(gap) / max(1.0, float(self._state.get("field_depth", 220.0)))))
        t = 1.0 - depth
        perspective = 0.24 + (t * 0.76)
        usable_width = arena_rect.width() * (0.22 + (perspective * 0.68))
        cx = arena_rect.center().x() + math.sin((gap / 52.0) + 0.4) * (arena_rect.width() * 0.09 * (1.0 - t))
        lane_ratio = (float(lane_pos) / max(1.0, lane_count - 1)) - 0.5
        x = cx + (lane_ratio * usable_width)
        y = arena_rect.bottom() - (t * (arena_rect.height() * 0.78))
        scale = 0.38 + (perspective * 0.92)
        return QPointF(x, y), scale

    def _paint_backdrop(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#090611"))
        sky = QLinearGradient(0, 0, 0, self.height())
        sky.setColorAt(0.0, QColor("#140a27"))
        sky.setColorAt(0.34, QColor("#251342"))
        sky.setColorAt(0.72, QColor("#0f1023"))
        sky.setColorAt(1.0, QColor("#05060d"))
        painter.fillRect(self.rect(), sky)

        haze = QRadialGradient(QPointF(self.width() * 0.52, self.height() * 0.30), self.width() * 0.54)
        haze.setColorAt(0.0, QColor(233, 120, 255, 54))
        haze.setColorAt(0.46, QColor(104, 168, 255, 26))
        haze.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), haze)

    def _draw_projected_city(self, painter: QPainter, arena_rect: QRectF):
        wall_rect = QRectF(arena_rect.left(), arena_rect.top() - 18.0, arena_rect.width(), arena_rect.height() * 0.22)
        wall_fill = QLinearGradient(wall_rect.topLeft(), wall_rect.bottomLeft())
        wall_fill.setColorAt(0.0, QColor("#7a2cd7"))
        wall_fill.setColorAt(0.35, QColor("#d85bd6"))
        wall_fill.setColorAt(1.0, QColor("#ffcf6e"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(wall_fill)
        painter.drawRoundedRect(wall_rect, 18, 18)

        skyline = QPainterPath()
        skyline.moveTo(wall_rect.left(), wall_rect.bottom())
        x = wall_rect.left()
        heights = [18, 42, 24, 56, 30, 78, 32, 64, 22, 50, 28, 68, 26]
        widths = [26, 20, 30, 18, 28, 24, 34, 20, 36, 26, 32, 22, 44]
        for width, height in zip(widths, heights):
            skyline.lineTo(x, wall_rect.bottom() - height)
            skyline.lineTo(x + width, wall_rect.bottom() - height)
            x += width
            skyline.lineTo(x, wall_rect.bottom())
        skyline.lineTo(wall_rect.right(), wall_rect.bottom())
        skyline.closeSubpath()
        painter.setBrush(QColor(39, 18, 74, 170))
        painter.drawPath(skyline)

        painter.setPen(QPen(QColor(255, 217, 120, 110), 2))
        for index in range(16):
            y = wall_rect.top() + 8 + ((index % 3) * 6)
            x0 = wall_rect.left() + 18 + (index * 36)
            painter.drawLine(QPointF(x0, y), QPointF(min(wall_rect.right() - 12, x0 + 20), y))

    def _draw_projection_floor(self, painter: QPainter, arena_rect: QRectF):
        floor = QLinearGradient(arena_rect.topLeft(), arena_rect.bottomLeft())
        floor.setColorAt(0.0, QColor("#1b1731"))
        floor.setColorAt(0.48, QColor("#151327"))
        floor.setColorAt(1.0, QColor("#0b0c14"))
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.5))
        painter.setBrush(floor)
        painter.drawRoundedRect(arena_rect, 26, 26)

        painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for row in range(8):
            y = arena_rect.top() + ((row + 1) * arena_rect.height() / 9.0)
            painter.drawLine(QPointF(arena_rect.left() + 14, y), QPointF(arena_rect.right() - 14, y))

        painter.setPen(Qt.NoPen)
        for index in range(5):
            glow_center = QPointF(
                arena_rect.left() + (arena_rect.width() * (0.12 + (index * 0.19))),
                arena_rect.top() + (arena_rect.height() * (0.24 + ((index % 2) * 0.18))),
            )
            glow = QRadialGradient(glow_center, arena_rect.width() * 0.12)
            glow.setColorAt(0.0, QColor(176, 84, 255, 30))
            glow.setColorAt(0.55, QColor(80, 221, 255, 14))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(glow)
            painter.drawEllipse(glow_center, arena_rect.width() * 0.12, arena_rect.width() * 0.12)

    def _draw_collectible_tile(self, painter: QPainter, arena_rect: QRectF, tile: dict):
        center, scale = self._lane_point(arena_rect, float(tile.get("lane", 2.0)), float(tile.get("gap", 0.0)))
        light_hex, dark_hex, edge_hex = self.COLOR_THEMES.get(str(tile.get("style", "violet")), self.COLOR_THEMES["violet"])
        width = 30.0 * scale
        height = 18.0 * scale
        tile_rect = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
        glow = QRadialGradient(center, width * 1.2)
        glow.setColorAt(0.0, QColor(light_hex))
        glow.setColorAt(0.45, QColor(light_hex).lighter(112))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, width * 1.1, height * 1.35)

        fill = QLinearGradient(tile_rect.topLeft(), tile_rect.bottomLeft())
        fill.setColorAt(0.0, QColor(light_hex))
        fill.setColorAt(1.0, QColor(dark_hex))
        painter.setPen(QPen(QColor(edge_hex), max(1.2, 1.8 * scale)))
        painter.setBrush(fill)
        painter.drawRoundedRect(tile_rect, 8 * scale, 8 * scale)

        painter.setPen(QPen(QColor(255, 255, 255, 120), max(0.8, 1.2 * scale)))
        painter.drawLine(QPointF(tile_rect.left() + width * 0.18, center.y()), QPointF(tile_rect.right() - width * 0.18, center.y()))

    def _draw_sigil(self, painter: QPainter, arena_rect: QRectF, sigil: dict):
        center, scale = self._lane_point(arena_rect, float(sigil.get("lane", 2.0)), float(sigil.get("gap", 0.0)))
        light_hex, dark_hex, edge_hex = self.COLOR_THEMES.get(str(sigil.get("style", "gold")).replace("sigil_", ""), self.COLOR_THEMES["gold"])
        radius = 24.0 * scale
        glow = QRadialGradient(center, radius * 1.7)
        glow.setColorAt(0.0, QColor(light_hex))
        glow.setColorAt(0.38, QColor(light_hex).lighter(118))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 1.7, radius * 1.3)

        painter.setPen(QPen(QColor(edge_hex), max(1.3, 2.0 * scale)))
        painter.setBrush(QColor(dark_hex))
        painter.drawEllipse(center, radius, radius * 0.74)
        painter.drawPath(_star_path(center, radius * 0.56, radius * 0.26))

    def _draw_hazard_pool(self, painter: QPainter, arena_rect: QRectF, hazard: dict):
        center, scale = self._lane_point(arena_rect, float(hazard.get("lane", 2.0)), float(hazard.get("gap", 0.0)))
        width = 44.0 * scale * (0.8 + float(hazard.get("width", 0.9)))
        height = 20.0 * scale * (0.9 + float(hazard.get("width", 0.9)))
        glow = QRadialGradient(center, width * 1.1)
        glow.setColorAt(0.0, QColor(120, 0, 140, 105))
        glow.setColorAt(0.58, QColor(43, 16, 74, 75))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, width * 1.1, height * 1.2)
        painter.setBrush(QColor(14, 8, 26, 220))
        painter.drawEllipse(center, width, height)
        painter.setPen(QPen(QColor(104, 31, 146, 140), max(1.0, 1.6 * scale)))
        painter.drawEllipse(center, width * 0.78, height * 0.72)

    def _draw_boost_pad(self, painter: QPainter, arena_rect: QRectF, pad: dict):
        center, scale = self._lane_point(arena_rect, float(pad.get("lane", 2.0)), float(pad.get("gap", 0.0)))
        rect = QRectF(center.x() - (28 * scale), center.y() - (12 * scale), 56 * scale, 24 * scale)
        glow = QLinearGradient(rect.topLeft(), rect.bottomRight())
        glow.setColorAt(0.0, QColor("#ffe96f"))
        glow.setColorAt(0.45, QColor("#5effef"))
        glow.setColorAt(1.0, QColor("#d76fff"))
        painter.setPen(QPen(QColor("#fef4b3"), max(1.2, 2.0 * scale)))
        painter.setBrush(glow)
        painter.drawRoundedRect(rect, 10 * scale, 10 * scale)
        painter.setPen(QPen(QColor(32, 16, 60, 180), max(1.0, 1.6 * scale)))
        painter.drawLine(QPointF(rect.left() + rect.width() * 0.24, rect.center().y()), QPointF(rect.right() - rect.width() * 0.20, rect.center().y()))
        painter.drawLine(QPointF(rect.right() - rect.width() * 0.28, rect.top() + rect.height() * 0.22), QPointF(rect.right() - rect.width() * 0.18, rect.center().y()))
        painter.drawLine(QPointF(rect.right() - rect.width() * 0.28, rect.bottom() - rect.height() * 0.22), QPointF(rect.right() - rect.width() * 0.18, rect.center().y()))

    def _draw_popup(self, painter: QPainter, arena_rect: QRectF, popup: dict):
        center, scale = self._lane_point(arena_rect, float(popup.get("lane", 2.0)), float(popup.get("gap", 0.0)))
        font = QFont()
        font.setPointSize(max(9, int(11 * scale)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ff7a8d") if popup.get("bad") else QColor("#fff4a3"))
        painter.drawText(QRectF(center.x() - 36, center.y() - 30, 72, 20), Qt.AlignCenter, str(popup.get("text", "")))

    def _draw_kart_trail(self, painter: QPainter, arena_rect: QRectF):
        center, scale = self._lane_point(arena_rect, float(self._state.get("kart_track_pos", 2.0)), 6.0)
        trail = QPainterPath()
        trail.moveTo(center.x(), center.y() + (20 * scale))
        for step in range(1, 6):
            offset_gap = 18.0 + (step * 16.0)
            point, point_scale = self._lane_point(arena_rect, float(self._state.get("kart_track_pos", 2.0)), offset_gap)
            point.setY(point.y() + (18 * point_scale))
            trail.lineTo(point)
        glow = QLinearGradient(trail.boundingRect().topLeft(), trail.boundingRect().bottomLeft())
        glow.setColorAt(0.0, QColor("#ffe16d" if float(self._state.get("boost_ticks", 0)) > 0 else "#b55dff"))
        glow.setColorAt(1.0, QColor("#19dcff"))
        painter.setPen(QPen(glow, max(6.0, 16.0 * scale), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(trail)

    def _draw_kart(self, painter: QPainter, arena_rect: QRectF):
        center, scale = self._lane_point(arena_rect, float(self._state.get("kart_track_pos", 2.0)), 0.0)
        glow_radius = 46.0 * scale
        glow = QRadialGradient(center, glow_radius * 1.4)
        glow.setColorAt(0.0, QColor("#ffef74" if float(self._state.get("boost_ticks", 0)) > 0 else "#d767ff"))
        glow.setColorAt(0.35, QColor("#49e1ff"))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, glow_radius * 1.5, glow_radius)

        body = QRectF(center.x() - (34 * scale), center.y() - (22 * scale), 68 * scale, 44 * scale)
        fill = QLinearGradient(body.topLeft(), body.bottomLeft())
        fill.setColorAt(0.0, QColor("#fefefe"))
        fill.setColorAt(0.35, QColor("#cce6ff"))
        fill.setColorAt(1.0, QColor("#525ef2"))
        painter.setPen(QPen(QColor("#f6f8ff"), max(1.3, 1.8 * scale)))
        painter.setBrush(fill)
        painter.drawRoundedRect(body, 18 * scale, 18 * scale)
        painter.setBrush(QColor("#17182c"))
        painter.drawRoundedRect(QRectF(body.left() + (14 * scale), body.top() + (8 * scale), body.width() - (28 * scale), 13 * scale), 7 * scale, 7 * scale)
        painter.setBrush(QColor("#1b2133"))
        for offset in (-20, 20):
            painter.drawEllipse(QPointF(center.x() + (offset * scale), body.bottom() - (2 * scale)), 7 * scale, 7 * scale)
        painter.setPen(QPen(QColor("#ffe57e"), max(1.0, 1.4 * scale)))
        painter.drawLine(QPointF(body.left() + 10 * scale, center.y()), QPointF(body.left() + 20 * scale, center.y()))
        painter.drawLine(QPointF(body.right() - 20 * scale, center.y()), QPointF(body.right() - 10 * scale, center.y()))

    def _draw_hud(self, painter: QPainter, arena_rect: QRectF, combo: int, boost: float, collected: int, target_collectibles: int):
        combo_rect = QRectF(arena_rect.left() + 18, arena_rect.bottom() - 78, 136, 56)
        boost_rect = QRectF(combo_rect.right() + 16, arena_rect.bottom() - 78, 210, 56)
        target_rect = QRectF(arena_rect.right() - 182, arena_rect.bottom() - 78, 164, 56)
        for rect in (combo_rect, boost_rect, target_rect):
            shell = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            shell.setColorAt(0.0, QColor(20, 18, 38, 230))
            shell.setColorAt(1.0, QColor(12, 11, 24, 230))
            painter.setPen(QPen(QColor(255, 255, 255, 36), 1.5))
            painter.setBrush(shell)
            painter.drawRoundedRect(rect, 18, 18)

        painter.setPen(QColor("#e9eeff"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(combo_rect.adjusted(0, 6, 0, 0), Qt.AlignHCenter, "Combo")
        painter.drawText(target_rect.adjusted(0, 6, 0, 0), Qt.AlignHCenter, "Targets")
        painter.drawText(boost_rect.adjusted(16, 6, -16, 0), Qt.AlignLeft, "Boost")

        combo_font = QFont()
        combo_font.setPointSize(18)
        combo_font.setBold(True)
        painter.setFont(combo_font)
        painter.setPen(QColor("#62f7c4"))
        painter.drawText(combo_rect.adjusted(0, 18, 0, 0), Qt.AlignCenter, str(combo))

        painter.setPen(QColor("#ffe47d"))
        painter.drawText(target_rect.adjusted(0, 18, 0, 0), Qt.AlignCenter, f"{collected}/{target_collectibles}")

        bar = QRectF(boost_rect.left() + 16, boost_rect.bottom() - 18, boost_rect.width() - 32, 12)
        painter.setPen(QPen(QColor("#4d4f76"), 1.2))
        painter.setBrush(QColor("#272842"))
        painter.drawRoundedRect(bar, 8, 8)
        fill = QRectF(bar.left() + 2, bar.top() + 2, (bar.width() - 4) * max(0.0, min(1.0, boost / 100.0)), bar.height() - 4)
        fill_grad = QLinearGradient(fill.topLeft(), fill.topRight())
        fill_grad.setColorAt(0.0, QColor("#5bdeff"))
        fill_grad.setColorAt(0.55, QColor("#ffd86f"))
        fill_grad.setColorAt(1.0, QColor("#c657ff"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill_grad)
        painter.drawRoundedRect(fill, 6, 6)

    def _draw_menu_button(self, painter: QPainter, rect: QRectF):
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#7f5bff"))
        fill.setColorAt(1.0, QColor("#4721bb"))
        painter.setPen(QPen(QColor("#d8c9ff"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 15, 15)
        painter.setPen(QPen(QColor("#f8f5ff"), 3, Qt.SolidLine, Qt.RoundCap))
        for offset in (15, 26, 37):
            painter.drawLine(QPointF(rect.left() + 14, rect.top() + offset), QPointF(rect.right() - 14, rect.top() + offset))

    def _draw_star_bar(self, painter: QPainter, rect: QRectF, progress: float):
        painter.setPen(QPen(QColor("#635c8d"), 2))
        painter.setBrush(QColor("#1f1f34"))
        painter.drawRoundedRect(rect, 20, 20)
        fill = QRectF(rect.left() + 4, rect.top() + 4, (rect.width() - 8) * max(0.0, min(1.0, progress)), rect.height() - 8)
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0.0, QColor("#b64cff"))
        grad.setColorAt(0.45, QColor("#49d8ff"))
        grad.setColorAt(1.0, QColor("#ffe16d"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(fill, 16, 16)
        for ratio in (0.25, 0.5, 0.75):
            painter.setBrush(QColor("#ffd348") if progress >= ratio else QColor("#8e91ad"))
            painter.setPen(QPen(QColor(255, 255, 255, 110), 1.5))
            painter.drawPath(_star_path(QPointF(rect.left() + (rect.width() * ratio), rect.center().y()), 10.0, 4.8))

    def _draw_score_pill(self, painter: QPainter, rect: QRectF, text: str):
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#291a47"))
        fill.setColorAt(1.0, QColor("#141028"))
        painter.setPen(QPen(QColor("#8b86b3"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 18, 18)
        painter.setPen(QColor("#fefcff"))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_overlay(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor(8, 8, 18, 130))
        card = QRectF(self.width() * 0.15, self.height() * 0.27, self.width() * 0.70, self.height() * 0.24)
        fill = QLinearGradient(card.topLeft(), card.bottomLeft())
        fill.setColorAt(0.0, QColor("#1c1831"))
        fill.setColorAt(1.0, QColor("#0d1020"))
        painter.setPen(QPen(QColor("#b16dff"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, 24, 24)
        painter.setPen(QColor("#fff2c3"))
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(card.left() + 20, card.top() + 24, card.width() - 40, 34), Qt.AlignCenter, str(self._state.get("overlay_title", "")))
        body_font = QFont()
        body_font.setPointSize(11)
        painter.setFont(body_font)
        painter.setPen(QColor("#d9ddff"))
        painter.drawText(QRectF(card.left() + 26, card.top() + 70, card.width() - 52, 44), Qt.AlignCenter | Qt.TextWordWrap, str(self._state.get("overlay_subtitle", "")))


class BubbleBurstWidget(_ImmersiveGameWidget):
    COLORS = {
        "red": ("#ff5d5d", "#9f0915"),
        "green": ("#55ff4b", "#0a7f11"),
        "yellow": ("#ffe55f", "#b68b00"),
        "blue": ("#74b8ff", "#1d5eb8"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._swap_callback = None
        self._swap_button_rect = QRectF()
        self.setMinimumHeight(560)

    def sizeHint(self):
        return QSize(520, 720)

    def set_swap_callback(self, callback):
        self._swap_callback = callback

    def _handle_click(self, pos: QPointF) -> bool:
        if self._swap_button_rect.contains(pos) and self._swap_callback and self._state.get("swap_enabled", False):
            self._swap_callback()
            return True
        return False

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_backdrop(painter)

        columns = max(1, int(self._state.get("columns", 6)))
        rows = max(1, int(self._state.get("visible_rows", 10)))
        board = list(self._state.get("board", []))
        aim_slot = int(self._state.get("aim_slot", columns // 2))
        combo = int(self._state.get("combo", 0))
        best_combo = int(self._state.get("best_combo", 0))
        score = int(self._state.get("score", 0))
        shots_left = int(self._state.get("shots_left", 0))
        progress = float(self._state.get("star_progress", 0.0))
        launcher_zone_row = int(self._state.get("launcher_zone_row", rows - 2))

        menu_rect = QRectF(18, 18, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(painter, menu_rect)
        self._draw_star_bar(painter, QRectF(96, 18, self.width() - 208, 42), progress)
        self._draw_score_pill(painter, QRectF(self.width() - 102, 18, 86, 42), str(score))
        balance_rect = _balance_panel_rect(self, 78.0, width_ratio=0.60) if self._state.get("balance_panel") else None

        launcher_center = QPointF(self.width() * 0.50, self.height() - 178)
        board_top = (balance_rect.bottom() + 14.0) if balance_rect is not None else 90.0
        board_height = max(160.0, launcher_center.y() - 44.0 - board_top)
        board_rect = QRectF(self.width() * 0.18, board_top, self.width() * 0.64, board_height)
        bubble_step = min(board_rect.width() / (columns + 0.55), board_rect.height() / (rows + 0.25))
        radius = max(12.0, bubble_step * 0.36)
        row_offset = bubble_step * 0.5
        left_pad = bubble_step * 0.52
        top_pad = bubble_step * 0.36

        if 0 <= launcher_zone_row < rows:
            zone_top = board_rect.top() + top_pad + (launcher_zone_row * bubble_step) - (bubble_step * 0.5)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 80, 120, 38))
            painter.drawRoundedRect(QRectF(board_rect.left(), zone_top, board_rect.width(), board_rect.bottom() - zone_top), 24, 24)

        for row_index, row in enumerate(board):
            for col_index, token in enumerate(row):
                if token is None:
                    continue
                center_x = board_rect.left() + left_pad + (col_index * bubble_step)
                if row_index % 2:
                    center_x += row_offset
                center_y = board_rect.top() + top_pad + (row_index * bubble_step)
                self._draw_bubble(painter, QPointF(center_x, center_y), radius, str(token))

        for popup in self._state.get("score_popups", []):
            popup_row = float(popup.get("row", 0.0))
            popup_col = int(popup.get("col", 0))
            popup_x = board_rect.left() + left_pad + (popup_col * bubble_step) + (row_offset if int(popup_row) % 2 else 0)
            popup_y = board_rect.top() + top_pad + (popup_row * bubble_step)
            painter.setPen(QColor("#ffd347"))
            font = QFont()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(popup_x - 34, popup_y - 18, 68, 20), Qt.AlignCenter, str(popup.get("text", "")))

        target_x = board_rect.left() + left_pad + (aim_slot * bubble_step)
        target_y = board_rect.top() + min(board_rect.height() * 0.55, board_rect.height() - 28)
        painter.setPen(QPen(QColor(132, 138, 240, 150), 4, Qt.DotLine, Qt.RoundCap))
        painter.drawLine(launcher_center, QPointF(target_x, target_y))
        painter.setPen(QPen(QColor(132, 138, 240, 90), 2))
        painter.drawLine(QPointF(target_x - 10, target_y - 16), QPointF(target_x, target_y - 28))
        painter.drawLine(QPointF(target_x, target_y - 28), QPointF(target_x + 10, target_y - 16))

        current_token = str(self._state.get("current_bubble", "red"))
        next_token = str(self._state.get("next_bubble", "green"))
        self._draw_shot_badge(painter, QRectF(launcher_center.x() - 112, launcher_center.y() + 52, 66, 34), shots_left)
        self._draw_bubble(painter, launcher_center, radius * 1.18, current_token)
        next_center = QPointF(launcher_center.x() + 62, launcher_center.y() + 10)
        self._swap_button_rect = QRectF(next_center.x() - 38, next_center.y() - 28, 76, 56)
        self._draw_swap_button(painter, self._swap_button_rect, next_center, next_token, bool(self._state.get("swap_enabled", False)))
        self._draw_booster_bar(painter)

        painter.setPen(QColor("#263a6c"))
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, self.height() - 102, self.width(), 24), Qt.AlignCenter, f"Combo {combo}   Best {best_combo}")
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(24, self.height() - 74, self.width() - 48, 22), Qt.AlignCenter, str(self._state.get("message", "")))

        self._draw_balance_panel(painter, top=78.0, width_ratio=0.60)
        if self._state.get("overlay_kind"):
            self._draw_overlay(painter)

    def _draw_bubble(self, painter: QPainter, center: QPointF, radius: float, token: str):
        light_hex, dark_hex = self.COLORS.get(token, ("#f8fafc", "#475569"))
        glow = QRadialGradient(center, radius * 1.35)
        glow.setColorAt(0.0, QColor(light_hex))
        glow.setColorAt(1.0, QColor(dark_hex))
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1.5))
        painter.setBrush(glow)
        painter.drawEllipse(center, radius, radius)
        painter.setBrush(QColor(255, 255, 255, 76))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(center.x() - (radius * 0.28), center.y() - (radius * 0.28)), radius * 0.26, radius * 0.22)

    def _paint_backdrop(self, painter: QPainter):
        sky = QLinearGradient(0, 0, 0, self.height())
        sky.setColorAt(0.0, QColor("#8fa8ff"))
        sky.setColorAt(0.48, QColor("#b2c2ff"))
        sky.setColorAt(1.0, QColor("#8fa9ff"))
        painter.fillRect(self.rect(), sky)
        haze = QRadialGradient(QPointF(self.width() * 0.45, self.height() * 0.35), self.width() * 0.7)
        haze.setColorAt(0.0, QColor(255, 255, 255, 60))
        haze.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(self.rect(), haze)
        painter.fillRect(QRectF(0, 0, self.width(), 72), QColor(41, 52, 101, 170))

    def _draw_menu_button(self, painter: QPainter, rect: QRectF):
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#3c9bff"))
        fill.setColorAt(1.0, QColor("#2067cf"))
        painter.setPen(QPen(QColor("#92d0ff"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 15, 15)
        painter.setPen(QPen(QColor("#eff7ff"), 3, Qt.SolidLine, Qt.RoundCap))
        for offset in (15, 26, 37):
            painter.drawLine(QPointF(rect.left() + 14, rect.top() + offset), QPointF(rect.right() - 14, rect.top() + offset))

    def _draw_star_bar(self, painter: QPainter, rect: QRectF, progress: float):
        painter.setPen(QPen(QColor("#6f7eb6"), 2))
        painter.setBrush(QColor("#3e466f"))
        painter.drawRoundedRect(rect, 20, 20)
        fill = QRectF(rect.left() + 4, rect.top() + 4, (rect.width() - 8) * max(0.0, min(1.0, progress)), rect.height() - 8)
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0.0, QColor("#00b7ff"))
        grad.setColorAt(1.0, QColor("#47d8ff"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(fill, 16, 16)
        for ratio in (0.25, 0.5, 0.75):
            painter.setBrush(QColor("#ffd349") if progress >= ratio else QColor("#c1c9e7"))
            painter.setPen(QPen(QColor(255, 255, 255, 120), 1.4))
            painter.drawPath(_star_path(QPointF(rect.left() + (rect.width() * ratio), rect.center().y()), 10.5, 4.8))

    def _draw_score_pill(self, painter: QPainter, rect: QRectF, text: str):
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#2b3150"))
        fill.setColorAt(1.0, QColor("#1f243d"))
        painter.setPen(QPen(QColor("#7d88bc"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 18, 18)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_shot_badge(self, painter: QPainter, rect: QRectF, shots_left: int):
        badge_fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        badge_fill.setColorAt(0.0, QColor("#7359ff"))
        badge_fill.setColorAt(1.0, QColor("#4a3bcc"))
        painter.setPen(QPen(QColor("#887cff"), 2))
        painter.setBrush(badge_fill)
        painter.drawRoundedRect(rect, 18, 18)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect, Qt.AlignCenter, str(shots_left))

    def _draw_swap_button(self, painter: QPainter, rect: QRectF, next_center: QPointF, token: str, enabled: bool):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 50 if enabled else 28))
        painter.drawRoundedRect(rect, 24, 24)
        self._draw_bubble(painter, next_center, 18, token)
        painter.setPen(QPen(QColor("#e9f1ff" if enabled else "#c8cfe8"), 2.4, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(QRectF(rect.left() + 8, rect.top() + 6, rect.width() - 16, rect.height() - 12), 35 * 16, 115 * 16)
        painter.drawArc(QRectF(rect.left() + 8, rect.top() + 6, rect.width() - 16, rect.height() - 12), 215 * 16, 115 * 16)

    def _draw_booster_bar(self, painter: QPainter):
        base_y = self.height() - 130
        left = self.width() * 0.24
        tiles = [
            (QRectF(left - 52, base_y, 84, 56), QColor("#8fd8f5"), "bomb", "1"),
            (QRectF(left + 56, base_y, 84, 56), QColor("#8ee6ff"), "mix", "2"),
            (QRectF(left + 164, base_y, 84, 56), QColor("#b2c4ff"), "wave", "+"),
        ]
        for rect, tint, kind, badge in tiles:
            fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            fill.setColorAt(0.0, tint.lighter(125))
            fill.setColorAt(1.0, tint.darker(108))
            painter.setPen(QPen(QColor("#5b6fb5"), 2))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 16, 16)
            if kind == "bomb":
                painter.setBrush(QColor("#293647"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(rect.center().x(), rect.center().y() + 2), 11, 11)
                painter.setPen(QPen(QColor("#ffd27c"), 2))
                painter.drawLine(QPointF(rect.center().x() + 6, rect.top() + 12), QPointF(rect.center().x() + 12, rect.top() + 6))
            elif kind == "mix":
                self._draw_bubble(painter, QPointF(rect.center().x() - 12, rect.center().y() + 2), 8, "green")
                self._draw_bubble(painter, QPointF(rect.center().x(), rect.center().y() - 8), 8, "blue")
                self._draw_bubble(painter, QPointF(rect.center().x() + 12, rect.center().y() + 2), 8, "red")
            else:
                painter.setPen(QPen(QColor("#dbe7ff"), 2))
                painter.drawArc(QRectF(rect.center().x() - 16, rect.center().y() - 10, 32, 20), 0, 180 * 16)
                painter.drawArc(QRectF(rect.center().x() - 10, rect.center().y() - 4, 20, 20), 0, 180 * 16)
            badge_rect = QRectF(rect.right() - 18, rect.bottom() - 10, 28, 28)
            badge_fill = QLinearGradient(badge_rect.topLeft(), badge_rect.bottomLeft())
            badge_fill.setColorAt(0.0, QColor("#db4cff"))
            badge_fill.setColorAt(1.0, QColor("#b42be2"))
            painter.setPen(QPen(QColor("#f9d7ff"), 1.5))
            painter.setBrush(badge_fill)
            painter.drawEllipse(badge_rect)
            font = QFont()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge_rect, Qt.AlignCenter, badge)

    def _draw_overlay(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor(36, 43, 88, 90))
        card = QRectF(self.width() * 0.11, self.height() * 0.30, self.width() * 0.78, self.height() * 0.24)
        fill = QLinearGradient(card.topLeft(), card.bottomLeft())
        fill.setColorAt(0.0, QColor("#f8fbff"))
        fill.setColorAt(1.0, QColor("#dbe6ff"))
        painter.setPen(QPen(QColor("#a3b6f8"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, 24, 24)
        burst_center = QPointF(card.center().x(), card.top() - 18)
        painter.setBrush(QColor("#ffd84a"))
        painter.setPen(QPen(QColor("#ffef9e"), 2))
        painter.drawPath(_star_path(burst_center, 42, 18))
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#b11ad5"))
        painter.drawText(QRectF(card.left() + 20, card.top() + 34, card.width() - 40, 54), Qt.AlignCenter | Qt.TextWordWrap, str(self._state.get("overlay_title", "")).upper())
        body_font = QFont()
        body_font.setPointSize(11)
        body_font.setBold(True)
        painter.setFont(body_font)
        painter.setPen(QColor("#576591"))
        painter.drawText(QRectF(card.left() + 30, card.top() + 108, card.width() - 60, 34), Qt.AlignCenter | Qt.TextWordWrap, str(self._state.get("overlay_subtitle", "")))


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
        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None

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
        content_top = (balance_rect.bottom() + 14.0) if balance_rect is not None else 0.0

        moon_center = QPointF(self.width() * 0.72, 96.0 + content_top)
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
            y = 54 + content_top + ((index * 23) % 170)
            radius = 1.5 + ((index % 3) * 0.6)
            alpha = 95 + int((serenity / 100.0) * 120)
            painter.setBrush(QColor(214, 231, 255, alpha))
            painter.drawEllipse(QPointF(x, y), radius, radius)

        ring_scale = 0.90 + (breath_phase * 0.35)
        ring_alpha = 80 + int((serenity / 100.0) * 80)
        center = QPointF(self.width() * 0.5, (self.height() * 0.55) + (content_top * 0.18))
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
        if balance_rect is None:
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
        _draw_widget_balance_panel(self, painter, self._state, top=18.0)


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
        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None
        river_top = (balance_rect.bottom() + 18.0) if balance_rect is not None else 40.0

        rect = QRectF(40, river_top, self.width() - 80, max(180.0, self.height() - river_top - 100.0))
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
        _draw_widget_balance_panel(self, painter, self._state, top=18.0)


class NeuroMusicFlowWidget(QWidget):
    _BAND_COLORS = {
        "delta": QColor("#8E6DFF"),
        "theta": QColor("#5D7CFF"),
        "alpha": QColor("#6EE7D8"),
        "smr": QColor("#B9F27C"),
        "beta": QColor("#F7B35F"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self.setMinimumHeight(400)

    def sizeHint(self):
        return QSize(560, 500)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#04060d"))

        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None
        content_top = (balance_rect.bottom() + 18.0) if balance_rect is not None else 28.0

        background = QLinearGradient(0, 0, 0, self.height())
        background.setColorAt(0.0, QColor("#0b1221"))
        background.setColorAt(0.5, QColor("#07101b"))
        background.setColorAt(1.0, QColor("#05070d"))
        painter.fillRect(self.rect(), background)

        serenity = float(self._state.get("serenity", 50.0))
        restlessness = float(self._state.get("restlessness", 20.0))
        focus_balance = float(self._state.get("focus_balance", 0.0))
        pulse_phase = float(self._state.get("pulse_phase", 0.0))
        dominant_mode = str(self._state.get("dominant_mode", "Balanced flow"))
        dominant_band = str(self._state.get("dominant_band", "alpha")).replace("_", " ").title()
        band_profile = dict(self._state.get("band_profile", {}))
        message = str(self._state.get("message", ""))
        progress = max(0.0, min(1.0, float(self._state.get("session_progress", 0.0))))

        center = QPointF(self.width() * 0.5, content_top + (self.height() - content_top) * 0.40)
        aura_radius = min(self.width(), self.height()) * (0.30 + (serenity / 1000.0))
        orb_gradient = QRadialGradient(center, aura_radius)
        if focus_balance >= 8.0:
            orb_gradient.setColorAt(0.0, QColor(246, 187, 83, 215))
            orb_gradient.setColorAt(0.45, QColor(246, 187, 83, 80))
        elif focus_balance <= -8.0:
            orb_gradient.setColorAt(0.0, QColor(110, 231, 216, 215))
            orb_gradient.setColorAt(0.45, QColor(110, 231, 216, 80))
        else:
            orb_gradient.setColorAt(0.0, QColor(138, 179, 255, 215))
            orb_gradient.setColorAt(0.45, QColor(138, 179, 255, 80))
        orb_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(orb_gradient)
        painter.drawEllipse(center, aura_radius, aura_radius)

        for ring_index in range(4):
            ring_radius = 52 + (ring_index * 28) + (pulse_phase * 10.0 * (ring_index + 1))
            ring_alpha = 135 - (ring_index * 20) + int((serenity - restlessness) * 0.35)
            ring_color = QColor("#93c5fd")
            if focus_balance > 8.0:
                ring_color = QColor("#f6bd60")
            elif focus_balance < -8.0:
                ring_color = QColor("#72f1d7")
            ring_color.setAlpha(max(20, min(180, ring_alpha)))
            painter.setPen(QPen(ring_color, 2.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, ring_radius, ring_radius)

        for particle_index in range(18):
            orbit = 86 + ((particle_index % 6) * 24)
            wobble = (pulse_phase * 0.9) + (particle_index * 0.32)
            angle = wobble + (particle_index * 0.44)
            x = center.x() + (math.cos(angle) * orbit)
            y = center.y() + (math.sin(angle * 1.2) * (orbit * 0.55))
            radius = 3.0 + ((particle_index % 3) * 1.4)
            glow = QColor("#dbeafe")
            if particle_index % 5 == 0:
                glow = QColor("#f6bd60")
            elif particle_index % 4 == 0:
                glow = QColor("#72f1d7")
            glow.setAlpha(70 + int((serenity / 100.0) * 120))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x, y), radius, radius)

        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(QRectF(0, content_top, self.width(), 28), Qt.AlignCenter, "Neuro Music Flow")

        body_font = QFont()
        body_font.setPointSize(11)
        painter.setFont(body_font)
        painter.setPen(QColor("#cdd7e7"))
        painter.drawText(
            QRectF(0, content_top + 28, self.width(), 22),
            Qt.AlignCenter,
            f"{dominant_mode}   •   Dominant band {dominant_band}",
        )

        progress_rect = QRectF(self.width() * 0.19, content_top + 66, self.width() * 0.62, 12)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(progress_rect, 6, 6)
        fill_rect = QRectF(progress_rect.left(), progress_rect.top(), progress_rect.width() * progress, progress_rect.height())
        fill_gradient = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
        fill_gradient.setColorAt(0.0, QColor("#72f1d7"))
        fill_gradient.setColorAt(1.0, QColor("#f6bd60"))
        painter.setBrush(fill_gradient)
        painter.drawRoundedRect(fill_rect, 6, 6)

        stat_card = QRectF(self.width() * 0.16, self.height() - 170, self.width() * 0.68, 92)
        painter.setPen(QPen(QColor(132, 148, 175, 90), 1.6))
        painter.setBrush(QColor(13, 18, 29, 196))
        painter.drawRoundedRect(stat_card, 24, 24)

        stat_font = QFont()
        stat_font.setPointSize(11)
        stat_font.setBold(True)
        painter.setFont(stat_font)
        painter.setPen(QColor("#f8fafc"))
        concentration = float(self._state.get("concentration", 0.0))
        relaxation = float(self._state.get("relaxation", 0.0))
        painter.drawText(
            QRectF(stat_card.left() + 18, stat_card.top() + 18, stat_card.width() - 36, 18),
            Qt.AlignLeft,
            f"Concentration {concentration:.1f}   Relaxation {relaxation:.1f}",
        )
        stat_font.setBold(False)
        painter.setFont(stat_font)
        painter.setPen(QColor("#d4deee"))
        painter.drawText(
            QRectF(stat_card.left() + 18, stat_card.top() + 42, stat_card.width() - 36, 18),
            Qt.AlignLeft,
            f"Serenity {serenity:.0f}   Restlessness {restlessness:.0f}   Balance {focus_balance:+.1f}",
        )
        painter.drawText(
            QRectF(stat_card.left() + 18, stat_card.top() + 64, stat_card.width() - 36, 18),
            Qt.AlignLeft | Qt.TextWordWrap,
            message,
        )

        bar_base_y = self.height() - 56
        bar_width = 34.0
        gap = 18.0
        total_width = (bar_width * len(self._BAND_COLORS)) + (gap * (len(self._BAND_COLORS) - 1))
        start_x = (self.width() - total_width) / 2.0
        label_font = QFont()
        label_font.setPointSize(9)
        label_font.setBold(True)
        painter.setFont(label_font)
        for index, band in enumerate(("delta", "theta", "alpha", "smr", "beta")):
            left = start_x + (index * (bar_width + gap))
            ratio = max(0.0, min(1.0, float(band_profile.get(band, 0.0)) * 2.4))
            height = 22.0 + (ratio * 84.0)
            rect = QRectF(left, bar_base_y - height, bar_width, height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawRoundedRect(QRectF(left, bar_base_y - 92, bar_width, 92), 14, 14)
            color = QColor(self._BAND_COLORS[band])
            color.setAlpha(210)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 14, 14)
            painter.setPen(QColor("#ecf2ff"))
            painter.drawText(QRectF(left - 8, bar_base_y + 6, bar_width + 16, 16), Qt.AlignCenter, band.upper())

        _draw_widget_balance_panel(self, painter, self._state, top=18.0)


class ProstheticArmWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}
        self._images = {
            "OPEN": QPixmap(hand_image_path("OPEN")),
            "NEUTRAL": QPixmap(hand_image_path("NEUTRAL")),
            "CLOSED": QPixmap(hand_image_path("CLOSED")),
        }
        self.setMinimumHeight(400)

    def sizeHint(self):
        return QSize(560, 480)

    def set_state(self, view_state: dict):
        self._state = view_state or {}
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#05070c"))
        glow = QRadialGradient(self.rect().center(), min(self.width(), self.height()) * 0.62)
        glow.setColorAt(0.0, QColor(77, 138, 102, 110))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)
        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None

        target_state = str(self._state.get("target_state", "OPEN")).upper()
        current_state = str(self._state.get("current_state", "OPEN")).upper()
        hold_progress = max(0.0, min(1.0, float(self._state.get("hold_progress", 0.0))))
        sequence_index = int(self._state.get("sequence_index", 0))
        sequence_total = max(1, int(self._state.get("sequence_total", 1)))
        headline = str(self._state.get("headline", "Prosthetic Arm"))
        history = list(self._state.get("history", []))
        backend_mode = str(self._state.get("backend_mode", "capsule")).title()
        backend_status = str(self._state.get("backend_status", "Using live metrics."))
        arm_connected = bool(self._state.get("arm_connected", False))
        dominant_state = str(self._state.get("dominant_state", "Balanced"))
        attention = float(self._state.get("attention", 0.0))
        relaxation = float(self._state.get("relaxation", 0.0))
        message = str(self._state.get("message", ""))

        top = (balance_rect.bottom() + 14.0) if balance_rect is not None else 22.0
        target_rect = QRectF(30, top, self.width() - 60, 64)
        fill = QLinearGradient(target_rect.topLeft(), target_rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#1f3a2c"))
        fill.setColorAt(1.0, QColor("#102116"))
        painter.setPen(QPen(QColor("#9de9b8"), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(target_rect, 24, 24)
        painter.setPen(QColor("#f8fafc"))
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(target_rect.left() + 18, target_rect.top() + 14, target_rect.width() - 36, 18), Qt.AlignLeft, headline)
        body_font = QFont()
        body_font.setPointSize(20)
        body_font.setBold(True)
        painter.setFont(body_font)
        painter.drawText(target_rect.adjusted(18, 0, -18, 0), Qt.AlignVCenter | Qt.AlignLeft, f"Target {state_label(target_state)}")
        body_font.setPointSize(11)
        body_font.setBold(False)
        painter.setFont(body_font)
        painter.drawText(target_rect.adjusted(18, 0, -18, 0), Qt.AlignVCenter | Qt.AlignRight, f"Step {min(sequence_index + 1, sequence_total)}/{sequence_total}")

        art_top = target_rect.bottom() + 18
        art_rect = QRectF(40, art_top, self.width() * 0.42, min(230.0, self.height() - art_top - 118.0))
        painter.setPen(QPen(QColor("#4e5c74"), 2))
        painter.setBrush(QColor("#0f131a"))
        painter.drawRoundedRect(art_rect, 32, 32)
        pixmap = self._images.get(current_state)
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                int(art_rect.width() * 0.72),
                int(art_rect.height() * 0.72),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            target = QRectF(
                art_rect.center().x() - (scaled.width() / 2),
                art_rect.center().y() - (scaled.height() / 2),
                scaled.width(),
                scaled.height(),
            )
            painter.drawPixmap(target.toRect(), scaled)
        else:
            painter.setPen(QColor("#d9f5e3"))
            fallback_font = QFont()
            fallback_font.setPointSize(18)
            fallback_font.setBold(True)
            painter.setFont(fallback_font)
            painter.drawText(art_rect, Qt.AlignCenter, state_label(current_state))

        painter.setPen(QColor("#d9f5e3"))
        painter.setFont(title_font)
        painter.drawText(QRectF(art_rect.left(), art_rect.bottom() + 8, art_rect.width(), 22), Qt.AlignCenter, f"Current {state_label(current_state)}")

        stats_rect = QRectF(art_rect.right() + 18, art_top, self.width() - art_rect.right() - 58, art_rect.height())
        painter.setPen(QPen(QColor("#3d475a"), 2))
        painter.setBrush(QColor("#10151d"))
        painter.drawRoundedRect(stats_rect, 28, 28)

        label_font = QFont()
        label_font.setPointSize(10)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(QColor("#dce7f5"))
        painter.drawText(QRectF(stats_rect.left() + 18, stats_rect.top() + 18, stats_rect.width() - 36, 18), Qt.AlignLeft, "Hold Progress")
        bar_rect = QRectF(stats_rect.left() + 18, stats_rect.top() + 46, stats_rect.width() - 36, 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 24))
        painter.drawRoundedRect(bar_rect, 8, 8)
        fill_rect = QRectF(bar_rect.left(), bar_rect.top(), bar_rect.width() * hold_progress, bar_rect.height())
        painter.setBrush(QColor("#79d89c"))
        painter.drawRoundedRect(fill_rect, 8, 8)

        body_font.setPointSize(11)
        painter.setFont(body_font)
        painter.setPen(QColor("#d0d9e8"))
        painter.drawText(QRectF(stats_rect.left() + 18, stats_rect.top() + 78, stats_rect.width() - 36, 20), Qt.AlignLeft, f"Backend  {backend_mode}")
        painter.drawText(QRectF(stats_rect.left() + 18, stats_rect.top() + 102, stats_rect.width() - 36, 20), Qt.AlignLeft, f"Arm Output  {'Hardware' if arm_connected else 'Simulation'}")
        painter.drawText(QRectF(stats_rect.left() + 18, stats_rect.top() + 126, stats_rect.width() - 36, 20), Qt.AlignLeft, f"Dominant  {dominant_state}")
        painter.drawText(QRectF(stats_rect.left() + 18, stats_rect.top() + 150, stats_rect.width() - 36, 20), Qt.AlignLeft, f"Attention  {attention:.1f}")
        painter.drawText(QRectF(stats_rect.left() + 18, stats_rect.top() + 174, stats_rect.width() - 36, 20), Qt.AlignLeft, f"Relaxation  {relaxation:.1f}")
        painter.drawText(
            QRectF(stats_rect.left() + 18, stats_rect.bottom() - 52, stats_rect.width() - 36, 38),
            Qt.AlignLeft | Qt.TextWordWrap,
            backend_status,
        )

        history_rect = QRectF(40, self.height() - 102, self.width() - 80, 34)
        painter.setPen(QPen(QColor("#3d475a"), 1.5))
        painter.setBrush(QColor("#11161d"))
        painter.drawRoundedRect(history_rect, 18, 18)
        painter.setPen(QColor("#f4f6fb"))
        painter.setFont(body_font)
        history_text = " -> ".join(state_label(item) for item in history[-6:]) if history else "Waiting for stable states"
        painter.drawText(history_rect.adjusted(16, 0, -16, 0), Qt.AlignVCenter | Qt.AlignLeft, history_text)

        painter.setPen(QColor("#d2d8e3"))
        painter.drawText(QRectF(0, self.height() - 46, self.width(), 24), Qt.AlignCenter, message)
        _draw_widget_balance_panel(self, painter, self._state, top=18.0)


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
        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None

        grid_size = int(self._state.get("grid_size", 4))
        total_cells = max(grid_size * grid_size, len(self._state.get("symbols", [])), 1)
        active_cells = len(self._state.get("symbols", [])) or total_cells
        board_top = (balance_rect.bottom() + 18.0) if balance_rect is not None else 86.0
        board_size = max(120.0, min(self.width() - 140, self.height() - board_top - 80.0))
        cell = board_size / max(grid_size, 1)
        left = (self.width() - board_size) / 2.0
        top = board_top
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

        if balance_rect is None:
            self._draw_memory_header(painter)
        self._draw_memory_footer(painter)
        _draw_widget_balance_panel(self, painter, self._state, top=18.0)

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


class CandyCascadeWidget(QWidget):
    COLORS = {
        "berry": QColor("#ff5d8f"),
        "lemon": QColor("#ffd166"),
        "mint": QColor("#4ade80"),
        "sky": QColor("#60a5fa"),
        "peach": QColor("#fb923c"),
    }

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
        painter.fillRect(self.rect(), QColor("#120712"))
        balance_rect = _balance_panel_rect(self, 18.0) if self._state.get("balance_panel") else None

        glow = QRadialGradient(self.rect().center(), min(self.width(), self.height()) * 0.58)
        glow.setColorAt(0.0, QColor(146, 66, 106, 96))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)

        grid_size = max(1, int(self._state.get("grid_size", 5)))
        candies = list(self._state.get("candies", []))
        blockers = set(self._state.get("blocker_cells", []))
        highlight_pair = set(self._state.get("highlight_pair", []))
        special_cells = dict(self._state.get("special_cells", {}))
        score = int(self._state.get("score", 0))
        target_score = int(self._state.get("target_score", 0))
        cascade_depth = int(self._state.get("cascade_depth", 0))
        remaining_blockers = int(self._state.get("remaining_blockers", 0))

        hud_top = (balance_rect.bottom() + 8.0) if balance_rect is not None else 18.0
        board_top = (balance_rect.bottom() + 58.0) if balance_rect is not None else 74.0
        board_size = max(120.0, min(self.width() - 180, self.height() - board_top - 70.0))
        cell = board_size / grid_size
        left = (self.width() - board_size) / 2.0
        top = board_top

        painter.setPen(QPen(QColor("#ffd8ec"), 2))
        painter.setBrush(QColor(35, 10, 28, 170))
        painter.drawRoundedRect(QRectF(left - 18, top - 18, board_size + 36, board_size + 36), 28, 28)

        for index, token in enumerate(candies):
            row, col = divmod(index, grid_size)
            rect = QRectF(left + (col * cell), top + (row * cell), cell - 8, cell - 8)
            color = self.COLORS.get(token, QColor("#e5e7eb"))
            painter.setPen(QPen(QColor(255, 255, 255, 42), 1.5))
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 14, 14)

            if index in highlight_pair:
                painter.setPen(QPen(QColor("#f8fafc"), 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 12, 12)

            if index in blockers:
                painter.setPen(QPen(QColor("#1f2937"), 3))
                painter.drawLine(rect.topLeft() + QPointF(8, 8), rect.bottomRight() - QPointF(8, 8))
                painter.drawLine(rect.topRight() + QPointF(-8, 8), rect.bottomLeft() + QPointF(8, -8))

            special_kind = special_cells.get(index)
            if special_kind:
                self._draw_special_marker(painter, rect, special_kind)

        painter.setPen(QColor("#fff1f7"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(18, hud_top, 180, 22), Qt.AlignLeft, f"Score {score}")
        painter.drawText(QRectF(self.width() - 198, hud_top, 180, 22), Qt.AlignRight, f"Target {target_score}")
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(18, hud_top + 24, 220, 20), Qt.AlignLeft, f"Blockers {remaining_blockers}")
        painter.drawText(QRectF(self.width() - 238, hud_top + 24, 220, 20), Qt.AlignRight, f"Cascade {cascade_depth}")
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 22),
            Qt.AlignCenter,
            self._state.get("message", ""),
        )
        _draw_widget_balance_panel(self, painter, self._state, top=18.0)

    def _draw_special_marker(self, painter: QPainter, rect: QRectF, kind: str):
        painter.setPen(QPen(QColor("#fff7ed"), 2))
        if kind == "row":
            for offset in (-8, 0, 8):
                painter.drawLine(
                    QPointF(rect.left() + 8, rect.center().y() + offset),
                    QPointF(rect.right() - 8, rect.center().y() + offset),
                )
        else:
            for offset in (-8, 0, 8):
                painter.drawLine(
                    QPointF(rect.center().x() + offset, rect.top() + 8),
                    QPointF(rect.center().x() + offset, rect.bottom() - 8),
                )
