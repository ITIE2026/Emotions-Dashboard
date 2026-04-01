"""Chrono Shift – neon cyber time-manipulation runner widget."""
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
_BG_TOP = QColor(8, 4, 22)
_BG_MID = QColor(12, 8, 40)
_BG_BOT = QColor(6, 2, 16)

# Time-mode palettes
_FAST_AMBER = QColor(255, 160, 40)
_FAST_RED = QColor(255, 60, 30)
_FAST_TINT = QColor(180, 80, 0, 35)
_SLOW_CYAN = QColor(0, 220, 255)
_SLOW_BLUE = QColor(40, 100, 255)
_SLOW_TINT = QColor(0, 60, 140, 35)
_NORMAL_WHITE = QColor(200, 210, 230)

# Orb
_ORB_CORE = QColor(220, 240, 255)
_ORB_GLOW_NORMAL = QColor(180, 200, 255, 80)
_ORB_GLOW_FAST = QColor(255, 140, 30, 100)
_ORB_GLOW_SLOW = QColor(0, 180, 255, 100)

# Grid
_GRID_CLR = QColor(60, 80, 160, 24)

# Gates
_GATE_WHITE = QColor(180, 190, 210, 180)
_GATE_BLUE = QColor(0, 180, 255, 200)
_GATE_BLUE_EDGE = QColor(120, 220, 255, 160)
_GATE_RED = QColor(255, 60, 40, 200)
_GATE_RED_EDGE = QColor(255, 160, 60, 160)
_GAP_LINE = QColor(0, 255, 200, 120)

# HUD
_HUD_CLR = QColor(220, 240, 255, 220)
_HULL_FULL = QColor(0, 255, 180)
_HULL_EMPTY = QColor(60, 30, 40)

# Particles
_PARTICLE_CLR = QColor(255, 180, 80)


class ChronoShiftWidget(_ImmersiveGameWidget):
    """Neon cyber runner with time-distortion visuals and chrono-gated obstacles."""

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
        time_mode = s.get("time_mode", "normal")
        tick = int(s.get("tick", 0))

        # -- background gradient --------------------------------------
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, _BG_TOP)
        bg.setColorAt(0.5, _BG_MID)
        bg.setColorAt(1.0, _BG_BOT)
        painter.fillRect(self.rect(), bg)

        # -- scrolling grid -------------------------------------------
        self._draw_grid(painter, w, h, tick, time_mode)

        # -- time distortion overlay ----------------------------------
        if time_mode == "fast":
            painter.fillRect(self.rect(), _FAST_TINT)
            self._draw_speed_lines(painter, w, h, tick)
        elif time_mode == "slow":
            painter.fillRect(self.rect(), _SLOW_TINT)
            self._draw_ripple_rings(painter, w, h, tick)

        # -- obstacles / chrono gates ---------------------------------
        for obs in s.get("obstacles", []):
            self._draw_obstacle(painter, w, h, obs)

        # -- particles ------------------------------------------------
        for p in s.get("particles", []):
            px = p.get("x", 0.5) * w
            py = p.get("y", 0.5) * h
            life = max(1, int(p.get("life", 1)))
            painter.setPen(Qt.NoPen)
            if time_mode == "fast":
                clr = QColor(255, 140 + life * 6, 40, min(255, life * 20))
            elif time_mode == "slow":
                clr = QColor(60, 180 + life * 4, 255, min(255, life * 20))
            else:
                clr = QColor(200, 200 + life * 3, 255, min(255, life * 20))
            painter.setBrush(clr)
            painter.drawEllipse(QPointF(px, py), 2.5, 2.5)

        # -- trail (afterimages) --------------------------------------
        trail = s.get("trail", [])
        for i, t in enumerate(trail):
            tx = t.get("x", 0.5) * w
            ty = t.get("y", 0.5) * h
            alpha = int(20 + (i / max(1, len(trail))) * 50)
            if time_mode == "fast":
                tc = QColor(255, 160, 40, alpha)
            elif time_mode == "slow":
                tc = QColor(0, 180, 255, alpha)
            else:
                tc = QColor(180, 200, 255, alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(tc)
            radius = 3.0 + (i / max(1, len(trail))) * 4.0
            painter.drawEllipse(QPointF(tx, ty), radius, radius)

        # -- orb (player) --------------------------------------------
        orb_x = s.get("orb_x", 0.5) * w
        orb_y = s.get("orb_y", 0.5) * h
        self._draw_orb(painter, orb_x, orb_y, time_mode, tick)

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

        # -- time mode badge ------------------------------------------
        self._draw_time_badge(painter, w, time_mode)

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
        base_speed = max(1.0, float(s.get("speed", 2.0)))
        painter.setPen(QPen(_SLOW_CYAN.darker(140), 2))
        bar_w = w - 180
        painter.drawRoundedRect(QRectF(90, 56, bar_w, 8), 3, 3)
        fill_frac = min(1.0, dist / max(1.0, 200.0))
        painter.setPen(Qt.NoPen)
        if time_mode == "fast":
            painter.setBrush(_FAST_AMBER)
        elif time_mode == "slow":
            painter.setBrush(_SLOW_CYAN)
        else:
            painter.setBrush(_NORMAL_WHITE)
        painter.drawRoundedRect(QRectF(90, 56, bar_w * fill_frac, 8), 3, 3)

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

    # ── scrolling perspective grid ────────────────────────────────────
    def _draw_grid(self, p: QPainter, w: float, h: float,
                   tick: int, mode: str) -> None:
        speed_mult = 4 if mode == "fast" else (1 if mode == "slow" else 2)
        if mode == "fast":
            grid_clr = QColor(160, 100, 40, 20)
        elif mode == "slow":
            grid_clr = QColor(40, 100, 200, 20)
        else:
            grid_clr = _GRID_CLR
        p.setPen(QPen(grid_clr, 1))
        for i in range(20):
            y = ((i * h / 20) + tick * speed_mult) % h
            p.drawLine(QPointF(0, y), QPointF(w, y))
        vx, vy = w / 2, -h * 0.2
        for i in range(12):
            bx = (i / 12) * w
            p.drawLine(QPointF(vx, vy), QPointF(bx, h))

    # ── speed lines (fast-forward effect) ─────────────────────────────
    def _draw_speed_lines(self, p: QPainter, w: float, h: float,
                          tick: int) -> None:
        p.setPen(QPen(QColor(255, 180, 60, 40), 2))
        for i in range(14):
            x = (hash(i * 31) % int(w)) if w > 0 else 0
            y_start = ((i * 47 + tick * 8) % int(h)) if h > 0 else 0
            length = 30 + (i % 5) * 12
            p.drawLine(QPointF(x, y_start), QPointF(x, y_start + length))

    # ── ripple rings (slow-motion effect) ─────────────────────────────
    def _draw_ripple_rings(self, p: QPainter, w: float, h: float,
                           tick: int) -> None:
        cx, cy = w / 2, h / 2
        for i in range(4):
            radius = 40 + i * 60 + (tick * 0.8) % 60
            alpha = max(0, 60 - i * 14)
            p.setPen(QPen(QColor(0, 180, 255, alpha), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

    # ── obstacle (chrono gate bar) ────────────────────────────────────
    def _draw_obstacle(self, p: QPainter, w: float, h: float,
                       obs: dict) -> None:
        y = obs.get("y", 0) * h
        gc = obs.get("gap_center", 0.5) * w
        base_gw = obs.get("gap_width", 0.3) * w
        openness = float(obs.get("openness", 1.0))
        gw = base_gw * openness
        gate_type = obs.get("gate_type", "white")
        bar_h = 6.0

        if gate_type == "blue":
            wall_clr = _GATE_BLUE
            edge_clr = _GATE_BLUE_EDGE
        elif gate_type == "red":
            wall_clr = _GATE_RED
            edge_clr = _GATE_RED_EDGE
        else:
            wall_clr = _GATE_WHITE
            edge_clr = _GAP_LINE

        # Left wall
        p.setPen(Qt.NoPen)
        p.setBrush(wall_clr)
        left_end = gc - gw / 2
        if left_end > 0:
            p.drawRect(QRectF(0, y - bar_h / 2, left_end, bar_h))
        # Right wall
        right_start = gc + gw / 2
        if right_start < w:
            p.drawRect(QRectF(right_start, y - bar_h / 2, w - right_start, bar_h))

        # Gate edge glow
        p.setPen(QPen(edge_clr, 2))
        if left_end > 0:
            p.drawLine(QPointF(left_end, y - bar_h), QPointF(left_end, y + bar_h))
        if right_start < w:
            p.drawLine(QPointF(right_start, y - bar_h), QPointF(right_start, y + bar_h))

        # Closing indicator for locked gates
        if openness < 0.5 and gate_type != "white":
            p.setPen(QPen(wall_clr.lighter(130), 1, Qt.DashLine))
            p.drawLine(QPointF(left_end, y), QPointF(right_start, y))

    # ── orb with time aura ────────────────────────────────────────────
    def _draw_orb(self, p: QPainter, x: float, y: float,
                  mode: str, tick: int) -> None:
        # Outer aura (pulsing)
        pulse = 0.85 + 0.15 * math.sin(tick * 0.25)
        if mode == "fast":
            glow_clr = _ORB_GLOW_FAST
            aura_radius = 32 * pulse
        elif mode == "slow":
            glow_clr = _ORB_GLOW_SLOW
            aura_radius = 36 * pulse
        else:
            glow_clr = _ORB_GLOW_NORMAL
            aura_radius = 26 * pulse

        glow = QRadialGradient(QPointF(x, y), aura_radius)
        glow.setColorAt(0.0, glow_clr)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(x, y), aura_radius, aura_radius)

        # Aura ring
        if mode == "fast":
            ring_clr = QColor(255, 160, 40, 120)
        elif mode == "slow":
            ring_clr = QColor(0, 200, 255, 120)
        else:
            ring_clr = QColor(180, 200, 255, 80)
        p.setPen(QPen(ring_clr, 2.5))
        p.setBrush(Qt.NoBrush)
        ring_r = 16 * pulse
        p.drawEllipse(QPointF(x, y), ring_r, ring_r)

        # Core
        p.setPen(Qt.NoPen)
        p.setBrush(_ORB_CORE)
        p.drawEllipse(QPointF(x, y), 7, 7)

    # ── time mode badge ───────────────────────────────────────────────
    def _draw_time_badge(self, p: QPainter, w: float, mode: str) -> None:
        if mode == "fast":
            label = "▶▶ FAST"
            bg_clr = QColor(180, 80, 0, 160)
            txt_clr = _FAST_AMBER
        elif mode == "slow":
            label = "◉ SLOW-MO"
            bg_clr = QColor(0, 60, 140, 160)
            txt_clr = _SLOW_CYAN
        else:
            label = "▶ NORMAL"
            bg_clr = QColor(40, 40, 60, 120)
            txt_clr = _NORMAL_WHITE

        badge_w, badge_h = 110, 26
        bx = (w - badge_w) / 2
        by = 22
        p.setPen(Qt.NoPen)
        p.setBrush(bg_clr)
        p.drawRoundedRect(QRectF(bx, by, badge_w, badge_h), 8, 8)

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(txt_clr)
        p.drawText(QRectF(bx, by, badge_w, badge_h), Qt.AlignCenter, label)

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
        if kind == "level_up":
            p.setPen(_SLOW_CYAN)
            label = "LEVEL UP"
        else:
            p.setPen(_FAST_AMBER)
            label = "GAME OVER"
        p.drawText(self.rect(), Qt.AlignCenter, label)
