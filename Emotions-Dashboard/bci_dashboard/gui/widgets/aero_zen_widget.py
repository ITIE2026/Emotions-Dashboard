"""Aero Zen – minimalist Japanese ink-wash (sumi-e) crane flyer widget."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from gui.widgets.training_game_widgets import _ImmersiveGameWidget

# ── colour palette (monochrome → colour with serenity) ────────────────
_INK_DARK = QColor(30, 28, 26)
_INK_MID = QColor(80, 76, 72)
_INK_LIGHT = QColor(180, 175, 168)
_PAPER = QColor(240, 235, 225)
_PAPER_DARK = QColor(60, 55, 50)
_CRANE_CLR = QColor(220, 210, 200)
_STORM_CLR = QColor(80, 70, 90, 180)
_ZEN_GATE = QColor(220, 50, 50)
_BLOSSOM_PINK = QColor(255, 180, 200, 180)
_HUD = QColor(60, 55, 50, 200)
_ZEN_GOLD = QColor(230, 200, 120)
_SKY_CLEAR = QColor(190, 215, 240)
_SKY_STORM = QColor(50, 45, 55)
_MT_NEAR = QColor(100, 95, 88)
_MT_FAR = QColor(160, 155, 148)


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class AeroZenWidget(_ImmersiveGameWidget):
    """Sumi-e ink-wash parallax flyer that gains colour as serenity rises."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(560)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(640, 600)

    # ── main paint ────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = self._state
        serenity = float(s.get("sky_serenity", 0.5))
        sat = float(s.get("color_saturation", 0.1))

        # -- sky gradient (storm → clear) ----------------------------
        sky_clr = _lerp_color(_SKY_STORM, _SKY_CLEAR, serenity)
        sky = QLinearGradient(0, 0, 0, h * 0.65)
        sky.setColorAt(0.0, sky_clr)
        sky.setColorAt(1.0, _lerp_color(_PAPER_DARK, _PAPER, serenity))
        painter.fillRect(self.rect(), sky)

        # -- far mountains (parallax layer 1) -------------------------
        scroll = float(s.get("scroll_x", 0))
        self._draw_mountains(painter, w, h, s.get("mountains", []), scroll * 0.3, 0.7, _MT_FAR, sat)

        # -- near mountains (parallax layer 2) ------------------------
        self._draw_mountains(painter, w, h, s.get("mountains", []), scroll * 0.6, 0.85, _MT_NEAR, sat)

        # -- blossoms -------------------------------------------------
        for b in s.get("blossoms", []):
            bx = b["x"] * w
            by = b["y"] * h
            life = max(1, int(b.get("life", 1)))
            alpha = min(255, int(life * 6 * sat))
            painter.setPen(Qt.NoPen)
            clr = QColor(_BLOSSOM_PINK.red(), _BLOSSOM_PINK.green(), _BLOSSOM_PINK.blue(), alpha)
            painter.setBrush(clr)
            r = 3.5 + math.sin(life * 0.3) * 1.5
            painter.drawEllipse(QPointF(bx, by), r, r)

        # -- zen gates (torii) ----------------------------------------
        for g in s.get("zen_gates", []):
            gx = g["x"] * w
            gy = g["y"] * h
            collected = g.get("collected", False)
            self._draw_torii(painter, gx, gy, collected)

        # -- storm clouds ---------------------------------------------
        for obs in s.get("obstacles", []):
            ox = obs["x"] * w
            oy = obs["y"] * h
            ow = obs.get("width", 0.12) * w
            oh = obs.get("height", 0.08) * h
            painter.setPen(Qt.NoPen)
            painter.setBrush(_STORM_CLR)
            painter.drawEllipse(QPointF(ox, oy), ow / 2, oh / 2)
            painter.setBrush(QColor(60, 50, 70, 120))
            painter.drawEllipse(QPointF(ox - ow * 0.2, oy + oh * 0.15), ow * 0.35, oh * 0.3)

        # -- crane (player) -------------------------------------------
        crane_y = s.get("crane_y", 0.5) * h
        self._draw_crane(painter, w * 0.15, crane_y, s)

        # -- HUD -------------------------------------------------------
        menu_rect = QRectF(16, 16, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(painter, menu_rect)

        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(_HUD)
        painter.drawText(QRectF(80, 22, 180, 28), Qt.AlignLeft | Qt.AlignVCenter,
                         f"Score {int(s.get('score', 0))}")

        # Zen score (gold)
        zen = float(s.get("zen_score", 0))
        if zen > 0:
            painter.setPen(_ZEN_GOLD)
            painter.drawText(QRectF(w - 160, 22, 140, 28), Qt.AlignRight | Qt.AlignVCenter,
                             f"Zen {zen:.0f}")

        # Hull pips
        hull = int(s.get("hull", 3))
        for i in range(3):
            cx = w - 30 - i * 20
            clr = QColor(220, 50, 50) if i < hull else QColor(80, 60, 60)
            painter.setPen(Qt.NoPen)
            painter.setBrush(clr)
            painter.drawEllipse(QPointF(cx, 58), 6, 6)

        # -- serenity bar ---------------------------------------------
        bar_x, bar_y, bar_w, bar_h = 80.0, 56.0, w - 180.0, 7.0
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1))
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)
        fill_clr = _lerp_color(QColor(120, 100, 140), QColor(100, 200, 255), serenity)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill_clr)
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w * serenity, bar_h), 3, 3)

        font.setPointSize(7)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 130))
        painter.drawText(QRectF(bar_x, bar_y - 12, bar_w, 11), Qt.AlignCenter, "SERENITY")

        # -- level title -----------------------------------------------
        title = s.get("level_title", "")
        if title:
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(80, 75, 70, 180))
            painter.drawText(QRectF(0, h - 28, w, 20), Qt.AlignCenter, title)

        # -- message toast --------------------------------------------
        msg = s.get("message", "")
        if msg:
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(200, 60, 60, 220))
            painter.drawText(QRectF(0, h * 0.40, w, 28), Qt.AlignCenter, msg)

        self._draw_balance_panel(painter, top=74.0, width_ratio=0.50)
        if s.get("overlay_kind"):
            self._draw_overlay(painter)

    # ── mountains (ink-wash silhouettes) ──────────────────────────────
    def _draw_mountains(self, p: QPainter, w: float, h: float,
                        mts: list[dict], offset: float, y_frac: float,
                        base_clr: QColor, sat: float) -> None:
        if not mts:
            return
        path = QPainterPath()
        ground_y = h * y_frac
        path.moveTo(0, h)
        for mt in mts:
            mx = ((mt["x"] - offset) % 1.8) * w
            mh = mt.get("height", 0.25) * h
            mw = mt.get("width", 0.12) * w
            peak_y = ground_y - mh
            path.lineTo(mx - mw, ground_y)
            path.lineTo(mx, peak_y)
            path.lineTo(mx + mw, ground_y)
        path.lineTo(w, ground_y)
        path.lineTo(w, h)
        path.closeSubpath()

        # Desaturate based on colour saturation
        clr = _lerp_color(QColor(base_clr.red(), base_clr.red(), base_clr.red()), base_clr, sat)
        p.setPen(Qt.NoPen)
        p.setBrush(clr)
        p.drawPath(path)

    # ── crane (origami bird) ──────────────────────────────────────────
    def _draw_crane(self, p: QPainter, x: float, y: float, s: dict) -> None:
        vy = float(s.get("crane_vy", 0))
        tick = int(s.get("tick", 0))
        wing_angle = math.sin(tick * 0.25) * 15 + vy * 100

        # Body
        body = QPainterPath()
        body.moveTo(x + 20, y)
        body.lineTo(x - 12, y - 5)
        body.lineTo(x - 18, y)
        body.lineTo(x - 12, y + 5)
        body.closeSubpath()
        p.setPen(QPen(_INK_DARK, 1.5))
        p.setBrush(_CRANE_CLR)
        p.drawPath(body)

        # Upper wing
        wy_up = y - 5 - abs(wing_angle) * 0.3
        p.drawLine(QPointF(x - 2, y - 3), QPointF(x - 10, wy_up))
        p.drawLine(QPointF(x - 10, wy_up), QPointF(x - 16, wy_up - 3))

        # Lower wing
        wy_dn = y + 5 + abs(wing_angle) * 0.25
        p.drawLine(QPointF(x - 2, y + 3), QPointF(x - 10, wy_dn))
        p.drawLine(QPointF(x - 10, wy_dn), QPointF(x - 16, wy_dn + 2))

    # ── torii gate ────────────────────────────────────────────────────
    def _draw_torii(self, p: QPainter, x: float, y: float, collected: bool) -> None:
        clr = QColor(180, 180, 180, 80) if collected else _ZEN_GATE
        p.setPen(QPen(clr, 2.5))
        p.setBrush(Qt.NoBrush)
        # Two pillars
        p.drawLine(QPointF(x - 12, y - 16), QPointF(x - 12, y + 16))
        p.drawLine(QPointF(x + 12, y - 16), QPointF(x + 12, y + 16))
        # Top beam
        p.drawLine(QPointF(x - 16, y - 14), QPointF(x + 16, y - 14))
        p.drawLine(QPointF(x - 14, y - 10), QPointF(x + 14, y - 10))

    # ── menu button ───────────────────────────────────────────────────
    def _draw_menu_button(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(QColor(80, 75, 70, 150), 2))
        p.setBrush(QColor(240, 235, 225, 80))
        p.drawRoundedRect(rect, 12, 12)
        cx, cy = rect.center().x(), rect.center().y()
        for dy in (-8, 0, 8):
            p.setPen(QPen(QColor(80, 75, 70, 180), 2.5))
            p.drawLine(QPointF(cx - 10, cy + dy), QPointF(cx + 10, cy + dy))

    # ── overlay ───────────────────────────────────────────────────────
    def _draw_overlay(self, p: QPainter) -> None:
        p.fillRect(self.rect(), QColor(240, 235, 225, 180))
        kind = self._state.get("overlay_kind", "")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        p.setFont(font)
        p.setPen(_INK_DARK)
        label = "ASCEND" if kind == "level_up" else "PEACE"
        p.drawText(self.rect(), Qt.AlignCenter, label)
