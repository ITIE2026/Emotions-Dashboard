"""Synapse Serpent – retro pixel-grid snake with neon circuit-board overlay."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from gui.widgets.training_game_widgets import _ImmersiveGameWidget

# ── colour palette ────────────────────────────────────────────────────
_BG_DARK = QColor(4, 6, 16)
_GRID_LINE = QColor(20, 60, 90, 50)
_CIRCUIT = QColor(0, 180, 220, 40)
_SNAKE_HEAD = QColor(0, 255, 200)
_SNAKE_BODY = QColor(0, 200, 160)
_SNAKE_PHASE = QColor(160, 80, 255, 120)
_FOOD_CLR = QColor(255, 80, 120)
_FOOD_GLOW = QColor(255, 80, 120, 60)
_SYNAPSE_FLASH = QColor(255, 255, 180, 200)
_HUD = QColor(220, 240, 255, 220)
_DEAD_TINT = QColor(200, 40, 40, 50)


class SynapseSerpentWidget(_ImmersiveGameWidget):
    """Retro snake on a circuit-board grid. Phase-shift turns snake translucent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(560)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(640, 640)

    # ── main paint ────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        s = self._state
        grid = max(2, int(s.get("grid", 20)))

        # -- dark background ------------------------------------------
        painter.fillRect(self.rect(), _BG_DARK)

        # -- compute board rect (square, centred) ---------------------
        margin_top = 80
        margin_bot = 80
        avail = min(w - 24, h - margin_top - margin_bot)
        cell = avail / grid
        bx = (w - avail) / 2
        by = margin_top

        # -- circuit trace background ---------------------------------
        self._draw_circuit_traces(painter, bx, by, avail, grid, cell, s)

        # -- grid lines -----------------------------------------------
        painter.setPen(QPen(_GRID_LINE, 0.5))
        for i in range(grid + 1):
            painter.drawLine(QPointF(bx + i * cell, by), QPointF(bx + i * cell, by + avail))
            painter.drawLine(QPointF(bx, by + i * cell), QPointF(bx + avail, by + i * cell))

        # -- synapse flashes ------------------------------------------
        for syn in s.get("synapses", []):
            sx_ = bx + (syn["x"] + 0.5) * cell
            sy_ = by + (syn["y"] + 0.5) * cell
            life = max(1, int(syn.get("life", 1)))
            radius = cell * 0.8 + (15 - life) * 2
            glow = QRadialGradient(QPointF(sx_, sy_), radius)
            alpha = min(255, life * 18)
            glow.setColorAt(0.0, QColor(255, 255, 180, alpha))
            glow.setColorAt(1.0, QColor(255, 255, 180, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(sx_, sy_), radius, radius)

        # -- food -----------------------------------------------------
        food = s.get("food", (5, 5))
        fx = bx + (food[0] + 0.5) * cell
        fy = by + (food[1] + 0.5) * cell
        # Glow ring
        fg = QRadialGradient(QPointF(fx, fy), cell)
        fg.setColorAt(0.0, _FOOD_GLOW)
        fg.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fg)
        painter.drawEllipse(QPointF(fx, fy), cell, cell)
        painter.setBrush(_FOOD_CLR)
        painter.drawEllipse(QPointF(fx, fy), cell * 0.3, cell * 0.3)

        # -- snake body -----------------------------------------------
        phase_shift = bool(s.get("phase_shift", False))
        snake = s.get("snake", [])
        for i, seg in enumerate(reversed(snake)):
            sx_ = bx + (seg[0] + 0.5) * cell
            sy_ = by + (seg[1] + 0.5) * cell
            if phase_shift:
                clr = _SNAKE_PHASE
            elif i == len(snake) - 1:
                clr = _SNAKE_HEAD
            else:
                frac = i / max(1, len(snake) - 1)
                clr = QColor(
                    int(_SNAKE_BODY.red() + (_SNAKE_HEAD.red() - _SNAKE_BODY.red()) * frac),
                    int(_SNAKE_BODY.green() + (_SNAKE_HEAD.green() - _SNAKE_BODY.green()) * frac),
                    int(_SNAKE_BODY.blue() + (_SNAKE_HEAD.blue() - _SNAKE_BODY.blue()) * frac),
                )
            painter.setPen(Qt.NoPen)
            painter.setBrush(clr)
            r = cell * 0.42 if i == len(snake) - 1 else cell * 0.36
            painter.drawRoundedRect(QRectF(sx_ - r, sy_ - r, r * 2, r * 2), 4, 4)

        # -- dead tint -------------------------------------------------
        if not s.get("alive", True):
            painter.fillRect(self.rect(), _DEAD_TINT)

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
        combo = int(s.get("combo", 0))
        if combo > 1:
            painter.setPen(QColor(255, 220, 80))
            painter.drawText(QRectF(w - 150, 22, 130, 28), Qt.AlignRight | Qt.AlignVCenter,
                             f"x{combo} Combo")

        # -- phase-shift indicator ------------------------------------
        if phase_shift:
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QColor(180, 120, 255, 220))
            painter.drawText(QRectF(0, h - 54, w, 22), Qt.AlignCenter,
                             f"PHASE SHIFT  {int(s.get('phase_ticks', 0))}")

        # -- level title -----------------------------------------------
        title = s.get("level_title", "")
        if title:
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 130))
            painter.drawText(QRectF(0, h - 30, w, 22), Qt.AlignCenter, title)

        # -- message ---------------------------------------------------
        msg = s.get("message", "")
        if msg:
            font.setPointSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 100, 100, 220))
            painter.drawText(QRectF(0, h * 0.38, w, 28), Qt.AlignCenter, msg)

        self._draw_balance_panel(painter, top=74.0, width_ratio=0.50)
        if s.get("overlay_kind"):
            self._draw_overlay(painter)

    # ── circuit traces (background decoration) ────────────────────────
    def _draw_circuit_traces(self, p: QPainter, bx: float, by: float,
                             size: float, grid: int, cell: float, s: dict) -> None:
        p.setPen(QPen(_CIRCUIT, 1.2))
        tick = int(s.get("tick", 0))
        # Draw ~5 random-looking traces
        for i in range(5):
            sx = bx + ((i * 7 + tick // 8) % grid) * cell + cell / 2
            sy = by + ((i * 11) % grid) * cell + cell / 2
            ex = sx + ((i % 3) - 1) * cell * 3
            ey = sy + cell * 2
            p.drawLine(QPointF(sx, sy), QPointF(ex, sy))
            p.drawLine(QPointF(ex, sy), QPointF(ex, ey))

    # ── menu button ───────────────────────────────────────────────────
    def _draw_menu_button(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 120), 2))
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(rect, 12, 12)
        cx, cy = rect.center().x(), rect.center().y()
        for dy in (-8, 0, 8):
            p.setPen(QPen(QColor(255, 255, 255, 200), 2.5))
            p.drawLine(QPointF(cx - 10, cy + dy), QPointF(cx + 10, cy + dy))

    # ── overlay ───────────────────────────────────────────────────────
    def _draw_overlay(self, p: QPainter) -> None:
        p.fillRect(self.rect(), QColor(0, 0, 0, 160))
        kind = self._state.get("overlay_kind", "")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        p.setFont(font)
        alive = self._state.get("alive", True)
        if not alive:
            p.setPen(QColor(255, 100, 100))
            p.drawText(self.rect(), Qt.AlignCenter, "GAME OVER")
        else:
            p.setPen(_SNAKE_HEAD)
            label = "LEVEL UP" if kind == "level_up" else "COMPLETE"
            p.drawText(self.rect(), Qt.AlignCenter, label)
