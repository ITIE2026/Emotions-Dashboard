"""Neural Drive – EEG-steered perspective road runner widget.

The player's car drives automatically forward through scrolling brick-wall
gates.  Concentration drifts the car right, relaxation drifts it left.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget

from gui.widgets.training_game_widgets import _ImmersiveGameWidget

# ── colour palette ────────────────────────────────────────────────────
_SKY_TOP   = QColor(8, 10, 28)
_SKY_BOT   = QColor(20, 28, 56)
_ROAD_CLR  = QColor(32, 34, 42)
_ROAD_EDGE = QColor(22, 24, 30)
_HORIZON_GLOW = QColor(60, 90, 200, 50)
_LANE_CLR  = QColor(255, 255, 255, 90)
_GRASS_CLR = QColor(28, 60, 30)

_BRICK_LIGHT  = QColor(195, 80, 35)
_BRICK_DARK   = QColor(130, 48, 18)
_MORTAR       = QColor(230, 210, 170, 70)

_CAR_BODY     = QColor(230, 240, 255)
_CAR_WINDOW   = QColor(60, 130, 210, 210)
_CAR_ACCENT   = QColor(80, 210, 255)
_CAR_WHEEL    = QColor(20, 20, 22)

_HUD_CLR    = QColor(225, 235, 255, 220)
_HINT_CLR   = QColor(170, 190, 255, 130)
_CRASH_TINT = QColor(210, 25, 25, 85)
_CLEAR_TINT = QColor(60, 220, 90, 70)
_OVERLAY_BG = QColor(0, 0, 0, 165)


class NeuralDriveWidget(_ImmersiveGameWidget):
    """3D-perspective road with brick-wall gates; EEG steers the car."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(560)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(600, 700)

    # ── perspective helpers ───────────────────────────────────────────

    @staticmethod
    def _road_constants(w: float, h: float):
        """Return (horizon_y, road_top_half, road_bot_half)."""
        horizon_y  = h * 0.38
        top_half   = w * 0.03   # road half-width at horizon
        bot_half   = w * 0.50   # road half-width at bottom
        return horizon_y, top_half, bot_half

    def _road_row(self, y_frac: float, w: float, h: float):
        """Screen (sy, left_x, row_width) for normalised depth y_frac."""
        hy, th, bh = self._road_constants(w, h)
        sy   = hy + y_frac * (h - hy)
        half = th + y_frac * (bh - th)
        cx   = w / 2.0
        return sy, cx - half, half * 2.0

    # ── main paint ────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        s = self._state

        self._draw_sky(painter, w, h)
        self._draw_road(painter, w, h, s)
        self._draw_gates(painter, w, h, s)
        self._draw_car(painter, w, h, s)

        # flash overlay
        if s.get("stun_ticks", 0) > 0:
            painter.fillRect(self.rect(), _CRASH_TINT)
        elif s.get("cleared_ticks", 0) > 0:
            painter.fillRect(self.rect(), _CLEAR_TINT)

        self._draw_hud(painter, w, h, s)
        self._draw_balance_panel(painter, top=76.0, width_ratio=0.54)

        if s.get("overlay_kind"):
            self._draw_overlay(painter)

    # ── sky ───────────────────────────────────────────────────────────

    def _draw_sky(self, p: QPainter, w: float, h: float) -> None:
        hy, _, _ = self._road_constants(w, h)
        grad = QLinearGradient(0, 0, 0, hy)
        grad.setColorAt(0.0, _SKY_TOP)
        grad.setColorAt(1.0, _SKY_BOT)
        p.fillRect(QRectF(0, 0, w, hy + 2), grad)

        # subtle horizon glow
        hg = QLinearGradient(0, hy - 12, 0, hy + 8)
        hg.setColorAt(0.0, QColor(0, 0, 0, 0))
        hg.setColorAt(0.5, _HORIZON_GLOW)
        hg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, hy - 12, w, 20), hg)

    # ── road + grass + lanes ──────────────────────────────────────────

    def _draw_road(self, p: QPainter, w: float, h: float, s: dict) -> None:
        hy, th, bh = self._road_constants(w, h)
        cx = w / 2.0

        # grass / shoulder strips (full width below horizon)
        p.setPen(Qt.NoPen)
        p.setBrush(_GRASS_CLR)
        p.drawRect(QRectF(0, hy, w, h - hy))

        # road trapezoid
        path = QPainterPath()
        path.moveTo(cx - th, hy)
        path.lineTo(cx + th, hy)
        path.lineTo(cx + bh, h)
        path.lineTo(cx - bh, h)
        path.closeSubpath()

        road_grad = QLinearGradient(0, hy, 0, h)
        road_grad.setColorAt(0.0, _ROAD_EDGE)
        road_grad.setColorAt(0.3, _ROAD_CLR)
        road_grad.setColorAt(1.0, _ROAD_CLR.darker(120))
        p.setBrush(road_grad)
        p.drawPath(path)

        # centre dashed lane markings (scroll with tick)
        tick = int(s.get("tick", 0))
        p.setPen(Qt.NoPen)
        n = 14
        for i in range(n):
            y_f = ((i / n) + tick * 0.010) % 1.0
            sy, rl, rw = self._road_row(y_f, w, h)
            sx = rl + rw * 0.5
            dash_h = max(2.0, y_f * 12.0)
            dash_w = max(1.0, y_f * 3.5)
            alpha = int(60 + y_f * 130)
            p.setBrush(QColor(255, 255, 255, alpha))
            p.drawRect(QRectF(sx - dash_w / 2, sy - dash_h / 2, dash_w, dash_h))

    # ── gates ─────────────────────────────────────────────────────────

    def _draw_gates(self, p: QPainter, w: float, h: float, s: dict) -> None:
        for g in s.get("gates", []):
            self._draw_one_gate(p, w, h, g)

    def _draw_one_gate(self, p: QPainter, w: float, h: float, g: dict) -> None:
        y_f = float(g.get("y", 0.0))
        if y_f < 0.01 or y_f > 1.05:
            return

        gap_c = float(g.get("gap_center", 0.5))
        gap_w = float(g.get("gap_width", 0.4))
        sy, rl, rw = self._road_row(y_f, w, h)

        gap_px_start = rl + (gap_c - gap_w / 2) * rw
        gap_px_end   = rl + (gap_c + gap_w / 2) * rw

        # bar thickness scales with perspective depth
        bar_h = max(5.0, y_f * 26.0)
        alpha = int(min(255, 70 + y_f * 185))

        bl = QColor(_BRICK_LIGHT.red(), _BRICK_LIGHT.green(), _BRICK_LIGHT.blue(), alpha)
        bd = QColor(_BRICK_DARK.red(),  _BRICK_DARK.green(),  _BRICK_DARK.blue(),  alpha)

        for x0, x1 in ((rl, gap_px_start), (gap_px_end, rl + rw)):
            wall_w = x1 - x0
            if wall_w <= 0.5:
                continue

            # gradient across wall for slight 3-D look
            wg = QLinearGradient(x0, 0, x1, 0)
            wg.setColorAt(0.0, bd)
            wg.setColorAt(0.45, bl)
            wg.setColorAt(1.0, bd)
            p.setPen(Qt.NoPen)
            p.setBrush(wg)
            p.drawRect(QRectF(x0, sy - bar_h / 2, wall_w, bar_h))

            # horizontal mortar joints
            n_rows = max(2, int(bar_h / 5))
            if y_f > 0.30:
                p.setPen(QPen(_MORTAR, max(0.5, y_f * 1.2)))
                for row in range(1, n_rows):
                    my = sy - bar_h / 2 + row * (bar_h / n_rows)
                    p.drawLine(QPointF(x0, my), QPointF(x1, my))

    # ── car ───────────────────────────────────────────────────────────

    def _draw_car(self, p: QPainter, w: float, h: float, s: dict) -> None:
        car_x  = float(s.get("car_x", 0.5))
        y_f    = 0.82
        sy, rl, rw = self._road_row(y_f, w, h)

        cx = rl + car_x * rw

        # stun wobble
        if s.get("stun_ticks", 0) > 0:
            tick = int(s.get("tick", 0))
            cx += math.sin(tick * 1.8) * 4.0

        car_w = rw * 0.13
        car_h = car_w * 1.75

        p.setPen(Qt.NoPen)

        # car body
        body = QRectF(cx - car_w / 2, sy - car_h * 0.55, car_w, car_h)
        p.setBrush(_CAR_BODY)
        p.drawRoundedRect(body, car_w * 0.20, car_w * 0.20)

        # windshield
        win_w = car_w * 0.62
        win_h = car_h * 0.24
        win_rect = QRectF(cx - win_w / 2, sy - car_h * 0.40, win_w, win_h)
        p.setBrush(_CAR_WINDOW)
        p.drawRoundedRect(win_rect, 3, 3)

        # headlights (front)
        for dx in (-car_w * 0.28, car_w * 0.28):
            p.setBrush(_CAR_ACCENT)
            p.drawEllipse(QPointF(cx + dx, sy - car_h * 0.49), car_w * 0.11, car_w * 0.09)

        # wheels
        wh_rx, wh_ry = car_w * 0.13, car_w * 0.16
        for dx in (-car_w * 0.40, car_w * 0.40):
            for dy in (-car_h * 0.28, car_h * 0.26):
                p.setBrush(_CAR_WHEEL)
                p.drawEllipse(QPointF(cx + dx, sy + dy), wh_rx, wh_ry)

    # ── HUD ───────────────────────────────────────────────────────────

    def _draw_hud(self, p: QPainter, w: float, h: float, s: dict) -> None:
        # menu button (top-left)
        menu_rect = QRectF(16, 16, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(p, menu_rect)

        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(_HUD_CLR)

        score   = int(s.get("score", 0))
        crashes = int(s.get("crashes", 0))
        passes  = int(s.get("passes", 0))
        target  = int(s.get("target_passes", 8))

        p.drawText(QRectF(84, 22, 150, 28), Qt.AlignLeft | Qt.AlignVCenter,
                   f"Score  {score}")
        p.drawText(QRectF(250, 22, 160, 28), Qt.AlignLeft | Qt.AlignVCenter,
                   f"\u2713 {passes} / {target}")
        p.drawText(QRectF(w - 100, 22, 90, 28), Qt.AlignRight | Qt.AlignVCenter,
                   f"x{crashes} crash")

        # control hint bar
        font.setPointSize(9)
        font.setBold(False)
        p.setFont(font)
        p.setPen(_HINT_CLR)
        p.drawText(QRectF(0, h - 46, w, 20), Qt.AlignCenter,
                   "Concentrate  \u2192  Right    \u2022    Relax  \u2192  Left")

        # level name
        title = s.get("level_title", "")
        if title:
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(QRectF(0, h - 26, w, 20), Qt.AlignCenter, title)

        # message toast (crash / clear)
        msg = s.get("message", "")
        if msg and not s.get("blocked"):
            font.setPointSize(14)
            font.setBold(True)
            p.setFont(font)
            color = QColor(255, 70, 70, 220) if "Crash" in msg else QColor(80, 255, 120, 220)
            p.setPen(color)
            p.drawText(QRectF(0, h * 0.43, w, 34), Qt.AlignCenter, msg)

        # blocked banner
        blocked = s.get("blocked", "")
        if blocked:
            font.setPointSize(12)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor(255, 200, 60, 220))
            p.drawText(QRectF(0, h * 0.43, w, 30), Qt.AlignCenter, blocked)

    # ── menu button (same style as other game widgets) ────────────────

    def _draw_menu_button(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 120), 2))
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(rect, 12, 12)
        cx, cy = rect.center().x(), rect.center().y()
        for dy in (-8, 0, 8):
            p.setPen(QPen(QColor(255, 255, 255, 200), 2.5))
            p.drawLine(QPointF(cx - 10, cy + dy), QPointF(cx + 10, cy + dy))

    # ── level-up / game-over overlay ──────────────────────────────────

    def _draw_overlay(self, p: QPainter) -> None:
        p.fillRect(self.rect(), _OVERLAY_BG)
        kind = self._state.get("overlay_kind", "")
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(80, 220, 120))
        label = "LEVEL UP" if kind == "level_up" else "FINISHED"
        p.drawText(self.rect(), Qt.AlignCenter, label)
