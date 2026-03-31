"""Gravity Drift – neon cyberpunk tunnel widget (cyan/magenta/purple glow)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from gui.widgets.training_game_widgets import _ImmersiveGameWidget, _draw_widget_balance_panel

# ── colour palette ────────────────────────────────────────────────────
_CYAN = QColor(0, 255, 230)
_MAGENTA = QColor(255, 0, 180)
_PURPLE = QColor(140, 40, 255)
_DARK_BG = QColor(6, 2, 18)
_GRID_CLR = QColor(0, 200, 255, 28)
_ORB_CORE = QColor(180, 245, 255)
_ORB_GLOW = QColor(0, 220, 255, 90)
_SHIELD_CLR = QColor(0, 255, 200, 80)
_BT_TINT = QColor(120, 0, 200, 45)  # bullet-time
_HUD_CLR = QColor(220, 240, 255, 220)
_HULL_FULL = QColor(0, 255, 180)
_HULL_EMPTY = QColor(60, 30, 40)
_OBSTACLE_LINE = QColor(255, 0, 140, 190)
_GAP_LINE = QColor(0, 255, 200, 120)
_PARTICLE_CLR = QColor(255, 180, 80)


class GravityDriftWidget(_ImmersiveGameWidget):
    """Neon tunnel with scrolling obstacles, orb pilot, shield/bullet-time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(560)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(600, 680)

    # ── painting ──────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = self._state

        # -- background gradient + grid lines -------------------------
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, _DARK_BG)
        bg.setColorAt(0.5, QColor(12, 4, 32))
        bg.setColorAt(1.0, _DARK_BG)
        painter.fillRect(self.rect(), bg)
        self._draw_tunnel_grid(painter, w, h, s)

        # -- bullet-time overlay tint ---------------------------------
        if s.get("bullet_time"):
            painter.fillRect(self.rect(), _BT_TINT)

        # -- obstacles ------------------------------------------------
        for obs in s.get("obstacles", []):
            self._draw_obstacle(painter, w, h, obs)

        # -- particles ------------------------------------------------
        for p in s.get("particles", []):
            px = p.get("x", 0.5) * w
            py = p.get("y", 0.5) * h
            life = max(1, int(p.get("life", 1)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 180 + life * 4, 60, min(255, life * 22)))
            painter.drawEllipse(QPointF(px, py), 2.5, 2.5)

        # -- orb (player) --------------------------------------------
        orb_x = s.get("orb_x", 0.5) * w
        orb_y = s.get("orb_y", 0.5) * h
        self._draw_orb(painter, orb_x, orb_y, s.get("shield", False))

        # -- HUD top bar ---------------------------------------------
        menu_rect = QRectF(16, 16, 54, 54)
        self._menu_button_rect = menu_rect
        self._draw_menu_button(painter, menu_rect)

        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(_HUD_CLR)
        painter.drawText(QRectF(80, 22, 200, 28), Qt.AlignLeft | Qt.AlignVCenter,
                         f"Score {int(s.get('score', 0))}")

        # -- hull pips ------------------------------------------------
        hull = int(s.get("hull", 4))
        for i in range(4):
            cx = w - 30 - i * 22
            clr = _HULL_FULL if i < hull else _HULL_EMPTY
            painter.setPen(Qt.NoPen)
            painter.setBrush(clr)
            painter.drawRoundedRect(QRectF(cx, 24, 16, 16), 4, 4)

        # -- distance bar ---------------------------------------------
        dist = float(s.get("distance", 0))
        painter.setPen(QPen(_CYAN.darker(140), 2))
        bar_w = w - 180
        painter.drawRoundedRect(QRectF(90, 56, bar_w, 8), 3, 3)
        fill_frac = min(1.0, dist / max(1.0, 200.0))  # rough
        painter.setPen(Qt.NoPen)
        painter.setBrush(_CYAN)
        painter.drawRoundedRect(QRectF(90, 56, bar_w * fill_frac, 8), 3, 3)

        # -- speed / state labels -------------------------------------
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(_HUD_CLR)
        label = "SHIELD" if s.get("shield") else ("SLOW-MO" if s.get("bullet_time") else "CRUISE")
        painter.drawText(QRectF(0, h - 54, w, 22), Qt.AlignCenter, label)

        # -- level title ----------------------------------------------
        title = s.get("level_title", "")
        if title:
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 140))
            painter.drawText(QRectF(0, h - 30, w, 22), Qt.AlignCenter, title)

        # -- message toast --------------------------------------------
        msg = s.get("message", "")
        if msg:
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 220, 80, 220))
            painter.drawText(QRectF(0, h * 0.38, w, 28), Qt.AlignCenter, msg)

        # -- balance panel + overlay -----------------------------------
        self._draw_balance_panel(painter, top=74.0, width_ratio=0.55)
        if s.get("overlay_kind"):
            self._draw_overlay(painter)

    # ── tunnel perspective grid ───────────────────────────────────────
    def _draw_tunnel_grid(self, p: QPainter, w: float, h: float, s: dict) -> None:
        tick = int(s.get("tick", 0))
        p.setPen(QPen(_GRID_CLR, 1))
        # Horizontal scanlines (scroll down)
        for i in range(20):
            y = ((i * h / 20) + tick * 4) % h
            p.drawLine(QPointF(0, y), QPointF(w, y))
        # Vertical converging lines (vanishing at centre top)
        vx, vy = w / 2, -h * 0.2
        for i in range(12):
            bx = (i / 12) * w
            p.drawLine(QPointF(vx, vy), QPointF(bx, h))

    # ── obstacle (gap bar) ────────────────────────────────────────────
    def _draw_obstacle(self, p: QPainter, w: float, h: float, obs: dict) -> None:
        y = obs.get("y", 0) * h
        gc = obs.get("gap_center", 0.5) * w
        gw = obs.get("gap_width", 0.3) * w
        bar_h = 6.0
        # Left wall
        p.setPen(Qt.NoPen)
        p.setBrush(_OBSTACLE_LINE)
        p.drawRect(QRectF(0, y - bar_h / 2, gc - gw / 2, bar_h))
        # Right wall
        p.drawRect(QRectF(gc + gw / 2, y - bar_h / 2, w - gc - gw / 2, bar_h))
        # Gap glow
        p.setPen(QPen(_GAP_LINE, 2))
        p.drawLine(QPointF(gc - gw / 2, y), QPointF(gc - gw / 2 + 8, y))
        p.drawLine(QPointF(gc + gw / 2 - 8, y), QPointF(gc + gw / 2, y))

    # ── orb with optional shield ring ─────────────────────────────────
    def _draw_orb(self, p: QPainter, x: float, y: float, shield: bool) -> None:
        # Outer glow
        glow = QRadialGradient(QPointF(x, y), 28)
        glow.setColorAt(0.0, _ORB_GLOW)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(x, y), 28, 28)
        # Core
        p.setBrush(_ORB_CORE)
        p.drawEllipse(QPointF(x, y), 8, 8)
        if shield:
            p.setPen(QPen(_SHIELD_CLR, 3))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x, y), 18, 18)

    # ── menu button ───────────────────────────────────────────────────
    def _draw_menu_button(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 120), 2))
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(rect, 12, 12)
        cx, cy = rect.center().x(), rect.center().y()
        for dy in (-8, 0, 8):
            p.setPen(QPen(QColor(255, 255, 255, 200), 2.5))
            p.drawLine(QPointF(cx - 10, cy + dy), QPointF(cx + 10, cy + dy))

    # ── overlay (level up / game over) ────────────────────────────────
    def _draw_overlay(self, p: QPainter) -> None:
        p.fillRect(self.rect(), QColor(0, 0, 0, 160))
        kind = self._state.get("overlay_kind", "")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        p.setFont(font)
        p.setPen(_CYAN)
        label = "LEVEL UP" if kind == "level_up" else "GAME OVER"
        p.drawText(self.rect(), Qt.AlignCenter, label)
