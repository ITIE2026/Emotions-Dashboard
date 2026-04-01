"""
Neuro Art Canvas — paint with your mind.

Standalone pop-up window.  Head tilt controls the brush cursor via gyro
pitch/roll.  Focus (attention ≥ 55) activates the pen; releasing focus
lifts it.  Real-time emotional state maps to visual output:

  • Attention → warm hues (reds/golds) + thicker strokes
  • Relaxation → cool hues (blues/purples) + thinner strokes
  • Stress    → splatter particle effects around the brush

Four brush modes: Flow, Glow, Splatter, Ribbon.
Export finished artwork as PNG.
"""
from __future__ import annotations

import colorsys
import datetime
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QLinearGradient,
    QGuiApplication,
)
from PySide6.QtWidgets import (
    QWidget,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
)

log = logging.getLogger(__name__)

# ── Tuning ────────────────────────────────────────────────────────────
_DEAD_ZONE = 2.0           # deg/s – ignore jitter below this
_SENSITIVITY = 4.0          # px per degree per second
_TICK_MS = 16               # ~60 FPS
_PEN_ON_THRESHOLD = 55      # attention to start drawing
_PEN_OFF_THRESHOLD = 45     # attention below this lifts pen (hysteresis)
_EMA_ALPHA = 0.15           # smoothing for color transitions
_CANVAS_W = 1000            # internal canvas width
_CANVAS_H = 700             # internal canvas height
_MAX_UNDO = 50              # stroke undo history limit
_SPLATTER_STRESS = 60       # stress above this triggers splatter
_DRIP_STRESS = 80           # stress above this triggers drip trails

# ── Brush mode enum ───────────────────────────────────────────────────
MODE_FLOW = 0
MODE_GLOW = 1
MODE_SPLATTER = 2
MODE_RIBBON = 3
_MODE_NAMES = ["Flow", "Glow", "Splatter", "Ribbon"]
_MODE_ICONS = ["〰", "✦", "💥", "🎗"]

# ── Colors ────────────────────────────────────────────────────────────
_BG = QColor(10, 10, 20)
_PANEL_BG = QColor(16, 18, 32)
_PANEL_BORDER = QColor(40, 50, 80)
_TEXT_DIM = QColor(140, 140, 160)
_TEXT_BRIGHT = QColor(220, 220, 240)
_CURSOR_RING = QColor(255, 255, 255, 120)
_PEN_ACTIVE_COLOR = QColor(0, 230, 118)
_PEN_INACTIVE_COLOR = QColor(100, 100, 120)
_FOCUS_BAR_BG = QColor(40, 40, 60)
_FOCUS_BAR_LO = QColor("#4FC3F7")
_FOCUS_BAR_HI = QColor("#00E676")
_RELAX_BAR = QColor("#7C4DFF")
_STRESS_BAR_LO = QColor("#FFA726")
_STRESS_BAR_HI = QColor("#FF5252")


# ── Stroke data ───────────────────────────────────────────────────────
@dataclass
class StrokePoint:
    x: float
    y: float
    color: QColor
    width: float
    speed: float  # head movement speed at this point


@dataclass
class StrokeData:
    points: list[StrokePoint] = field(default_factory=list)
    mode: int = MODE_FLOW


# ══════════════════════════════════════════════════════════════════════
#  Art Canvas Widget (custom-painted surface)
# ══════════════════════════════════════════════════════════════════════

class _ArtCanvas(QWidget):
    """Custom-painted art canvas with gyro cursor and brain-driven brush."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)

        # Persistent painted canvas (QImage)
        self._canvas = QImage(_CANVAS_W, _CANVAS_H, QImage.Format_ARGB32)
        self._canvas.fill(Qt.transparent)

        # Stroke history for undo
        self._strokes: list[StrokeData] = []
        self._cur_stroke: StrokeData | None = None

        # Cursor (pixel coordinates on internal canvas)
        self._cx = _CANVAS_W / 2.0
        self._cy = _CANVAS_H / 2.0
        self._prev_cx = self._cx
        self._prev_cy = self._cy

        # Gyro accumulator
        self._dx = 0.0
        self._dy = 0.0

        # Brain metrics (EMA-smoothed)
        self._attention = 0.0
        self._relaxation = 0.0
        self._stress = 0.0
        self._raw_attention = 0.0
        self._raw_relaxation = 0.0
        self._raw_stress = 0.0

        # Pen state
        self._pen_down = False

        # Brush mode
        self._mode = MODE_FLOW

        # Smoothed brush color (HSL)
        self._smooth_h = 0.5
        self._smooth_s = 0.8
        self._smooth_l = 0.55

        # Splatter particles buffer (temporary visual-only)
        self._particles: list[tuple[float, float, QColor, float, float]] = []
        # (x, y, color, radius, birth_time)

        # Timer
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._last_tick = time.monotonic()

    # ── Public API ────────────────────────────────────────────────────

    def feed_gyro(self, gx: float, gz: float):
        if abs(gz) > _DEAD_ZONE:
            self._dx += gz
        if abs(gx) > _DEAD_ZONE:
            self._dy += gx

    def feed_emotions(self, attention: float, relaxation: float, stress: float):
        self._raw_attention = attention
        self._raw_relaxation = relaxation
        self._raw_stress = stress

    def set_mode(self, mode: int):
        self._mode = mode

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def stroke_count(self) -> int:
        return len(self._strokes)

    @property
    def pen_active(self) -> bool:
        return self._pen_down

    @property
    def attention(self) -> float:
        return self._attention

    @property
    def relaxation(self) -> float:
        return self._relaxation

    @property
    def stress(self) -> float:
        return self._stress

    def clear_canvas(self):
        self._canvas.fill(Qt.transparent)
        self._strokes.clear()
        self._cur_stroke = None
        self._pen_down = False
        self._particles.clear()
        self.update()

    def undo(self):
        if not self._strokes:
            return
        self._strokes.pop()
        self._rebuild_canvas()
        self.update()

    def get_export_image(self) -> QImage:
        """Return the canvas composited on a dark background for export."""
        img = QImage(_CANVAS_W, _CANVAS_H, QImage.Format_ARGB32)
        img.fill(QColor(10, 10, 20))
        p = QPainter(img)
        p.drawImage(0, 0, self._canvas)
        p.end()
        return img

    # ── Internal ──────────────────────────────────────────────────────

    def _rebuild_canvas(self):
        """Re-render all strokes onto a fresh canvas (for undo)."""
        self._canvas.fill(Qt.transparent)
        for stroke in self._strokes:
            self._paint_stroke_to_canvas(stroke)

    def _brain_to_color(self) -> tuple[float, float, float]:
        """Map attention/relaxation balance to HSL hue."""
        attn = self._attention / 100.0
        relax = self._relaxation / 100.0

        # Hue: attention→warm (0-60°), relaxation→cool (180-280°)
        # Balance drives interpolation
        total = attn + relax
        if total < 0.01:
            h = 0.33  # default green
        else:
            warm_weight = attn / total
            # warm: H=0.0-0.16 (0-60°), cool: H=0.5-0.78 (180-280°)
            warm_hue = 0.05 + attn * 0.08       # 0.05 → 0.13 (18° → 47°)
            cool_hue = 0.50 + relax * 0.22       # 0.50 → 0.72 (180° → 259°)
            h = warm_hue * warm_weight + cool_hue * (1.0 - warm_weight)

        s = 0.70 + max(attn, relax) * 0.30   # 70-100% saturation
        l = 0.45 + attn * 0.15                # 45-60% lightness

        return h, s, l

    def _tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        if dt <= 0 or dt > 0.2:
            dt = _TICK_MS / 1000.0

        # EMA smooth brain metrics
        a = _EMA_ALPHA
        self._attention += a * (self._raw_attention - self._attention)
        self._relaxation += a * (self._raw_relaxation - self._relaxation)
        self._stress += a * (self._raw_stress - self._stress)

        # Smooth color
        target_h, target_s, target_l = self._brain_to_color()
        self._smooth_h += a * (target_h - self._smooth_h)
        self._smooth_s += a * (target_s - self._smooth_s)
        self._smooth_l += a * (target_l - self._smooth_l)

        # Apply gyro → cursor movement
        move_x = self._dx * _SENSITIVITY * dt
        move_y = self._dy * _SENSITIVITY * dt
        self._dx = 0.0
        self._dy = 0.0

        self._prev_cx = self._cx
        self._prev_cy = self._cy
        self._cx = max(0, min(_CANVAS_W - 1, self._cx + move_x))
        self._cy = max(0, min(_CANVAS_H - 1, self._cy + move_y))

        # Head movement speed
        speed = math.hypot(self._cx - self._prev_cx, self._cy - self._prev_cy) / dt

        # Pen down/up with hysteresis
        if not self._pen_down and self._attention >= _PEN_ON_THRESHOLD:
            self._pen_down = True
            self._cur_stroke = StrokeData(mode=self._mode)
        elif self._pen_down and self._attention < _PEN_OFF_THRESHOLD:
            self._pen_down = False
            if self._cur_stroke and len(self._cur_stroke.points) > 1:
                self._paint_stroke_to_canvas(self._cur_stroke)
                self._strokes.append(self._cur_stroke)
                if len(self._strokes) > _MAX_UNDO:
                    # Remove oldest, rebuild canvas
                    self._strokes = self._strokes[-_MAX_UNDO:]
                    self._rebuild_canvas()
            self._cur_stroke = None

        # If pen down, record point
        if self._pen_down and self._cur_stroke is not None:
            # Compute current color
            r_f, g_f, b_f = colorsys.hls_to_rgb(
                self._smooth_h, self._smooth_l, self._smooth_s
            )
            color = QColor(int(r_f * 255), int(g_f * 255), int(b_f * 255))

            # Width from attention (3-15px), thinner at high speed (calligraphic)
            base_w = 3.0 + self._attention * 0.12
            speed_factor = max(0.3, 1.0 - speed * 0.001)
            width = base_w * speed_factor

            # Opacity jitter from stress
            if self._stress > 50:
                jitter = (random.random() - 0.5) * 0.4 * (self._stress / 100.0)
                alpha = max(80, min(255, int(255 * (0.85 + jitter))))
                color.setAlpha(alpha)

            pt = StrokePoint(self._cx, self._cy, color, width, speed)
            self._cur_stroke.points.append(pt)

            # Stress splatter
            if self._stress > _SPLATTER_STRESS:
                n_particles = int(2 + (self._stress - _SPLATTER_STRESS) * 0.15)
                for _ in range(min(n_particles, 8)):
                    angle = random.random() * math.tau
                    dist = random.uniform(5, 30) * (self._stress / 100.0)
                    px = self._cx + math.cos(angle) * dist
                    py = self._cy + math.sin(angle) * dist
                    pc = QColor(color)
                    pc.setAlpha(random.randint(100, 220))
                    pr = random.uniform(1.5, 4.0)
                    self._particles.append((px, py, pc, pr, now))
                    # Paint splatter particles directly to canvas
                    cp = QPainter(self._canvas)
                    cp.setRenderHint(QPainter.Antialiasing)
                    cp.setPen(Qt.NoPen)
                    cp.setBrush(pc)
                    cp.drawEllipse(QPointF(px, py), pr, pr)
                    cp.end()

            # Stress drip trails
            if self._stress > _DRIP_STRESS:
                drip_color = QColor(color)
                drip_color.setAlpha(120)
                drip_len = random.uniform(8, 25)
                cp = QPainter(self._canvas)
                cp.setRenderHint(QPainter.Antialiasing)
                cp.setPen(QPen(drip_color, random.uniform(1, 2.5)))
                drip_path = QPainterPath()
                drip_path.moveTo(self._cx, self._cy)
                drip_path.cubicTo(
                    self._cx + random.uniform(-5, 5), self._cy + drip_len * 0.4,
                    self._cx + random.uniform(-3, 3), self._cy + drip_len * 0.7,
                    self._cx + random.uniform(-2, 2), self._cy + drip_len,
                )
                cp.drawPath(drip_path)
                cp.end()

            # Paint live point to canvas (immediate feedback for flow/glow/ribbon)
            if len(self._cur_stroke.points) >= 2:
                self._paint_last_segment(self._cur_stroke)

        # Expire old particles (visual overlay only, canvas already painted)
        self._particles = [
            p for p in self._particles if now - p[4] < 0.5
        ]

        self.update()

    def _paint_last_segment(self, stroke: StrokeData):
        """Paint the last segment of the current stroke onto the canvas."""
        pts = stroke.points
        if len(pts) < 2:
            return

        cp = QPainter(self._canvas)
        cp.setRenderHint(QPainter.Antialiasing)

        p1 = pts[-2]
        p2 = pts[-1]

        if stroke.mode == MODE_FLOW:
            pen = QPen(p2.color, p2.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            cp.setPen(pen)
            cp.drawLine(QPointF(p1.x, p1.y), QPointF(p2.x, p2.y))

        elif stroke.mode == MODE_GLOW:
            # Radial gradient dot
            r = p2.width * 1.5
            grad = QRadialGradient(QPointF(p2.x, p2.y), r)
            gc = QColor(p2.color)
            gc.setAlpha(180)
            grad.setColorAt(0.0, gc)
            gc2 = QColor(p2.color)
            gc2.setAlpha(0)
            grad.setColorAt(1.0, gc2)
            cp.setPen(Qt.NoPen)
            cp.setBrush(grad)
            cp.drawEllipse(QPointF(p2.x, p2.y), r, r)

        elif stroke.mode == MODE_SPLATTER:
            # Scattered particles (no continuous line)
            n = max(2, int(p2.width * 0.8))
            for _ in range(n):
                angle = random.random() * math.tau
                dist = random.uniform(2, p2.width * 2)
                sx = p2.x + math.cos(angle) * dist
                sy = p2.y + math.sin(angle) * dist
                sc = QColor(p2.color)
                sc.setAlpha(random.randint(120, 255))
                sr = random.uniform(1, p2.width * 0.4)
                cp.setPen(Qt.NoPen)
                cp.setBrush(sc)
                cp.drawEllipse(QPointF(sx, sy), sr, sr)

        elif stroke.mode == MODE_RIBBON:
            # Calligraphic — width varies with speed
            # Perpendicular offset based on speed
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            length = math.hypot(dx, dy)
            if length > 0.1:
                nx = -dy / length
                ny = dx / length
                half_w = p2.width * 0.5
                path = QPainterPath()
                path.moveTo(p1.x + nx * p1.width * 0.5, p1.y + ny * p1.width * 0.5)
                path.lineTo(p2.x + nx * half_w, p2.y + ny * half_w)
                path.lineTo(p2.x - nx * half_w, p2.y - ny * half_w)
                path.lineTo(p1.x - nx * p1.width * 0.5, p1.y - ny * p1.width * 0.5)
                path.closeSubpath()
                cp.setPen(Qt.NoPen)
                cp.setBrush(p2.color)
                cp.drawPath(path)

        cp.end()

    def _paint_stroke_to_canvas(self, stroke: StrokeData):
        """Paint an entire stroke to the canvas (used for undo rebuild)."""
        if len(stroke.points) < 2:
            return

        cp = QPainter(self._canvas)
        cp.setRenderHint(QPainter.Antialiasing)

        for i in range(1, len(stroke.points)):
            p1 = stroke.points[i - 1]
            p2 = stroke.points[i]

            if stroke.mode == MODE_FLOW:
                pen = QPen(p2.color, p2.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                cp.setPen(pen)
                cp.drawLine(QPointF(p1.x, p1.y), QPointF(p2.x, p2.y))

            elif stroke.mode == MODE_GLOW:
                r = p2.width * 1.5
                grad = QRadialGradient(QPointF(p2.x, p2.y), r)
                gc = QColor(p2.color)
                gc.setAlpha(180)
                grad.setColorAt(0.0, gc)
                gc2 = QColor(p2.color)
                gc2.setAlpha(0)
                grad.setColorAt(1.0, gc2)
                cp.setPen(Qt.NoPen)
                cp.setBrush(grad)
                cp.drawEllipse(QPointF(p2.x, p2.y), r, r)

            elif stroke.mode == MODE_SPLATTER:
                # Reproducible scatter using point index as seed
                rng = random.Random(hash((p2.x, p2.y, i)))
                n = max(2, int(p2.width * 0.8))
                for _ in range(n):
                    angle = rng.random() * math.tau
                    dist = rng.uniform(2, p2.width * 2)
                    sx = p2.x + math.cos(angle) * dist
                    sy = p2.y + math.sin(angle) * dist
                    sc = QColor(p2.color)
                    sc.setAlpha(rng.randint(120, 255))
                    sr = rng.uniform(1, p2.width * 0.4)
                    cp.setPen(Qt.NoPen)
                    cp.setBrush(sc)
                    cp.drawEllipse(QPointF(sx, sy), sr, sr)

            elif stroke.mode == MODE_RIBBON:
                dx = p2.x - p1.x
                dy = p2.y - p1.y
                length = math.hypot(dx, dy)
                if length > 0.1:
                    nx = -dy / length
                    ny = dx / length
                    half_w = p2.width * 0.5
                    path = QPainterPath()
                    path.moveTo(p1.x + nx * p1.width * 0.5, p1.y + ny * p1.width * 0.5)
                    path.lineTo(p2.x + nx * half_w, p2.y + ny * half_w)
                    path.lineTo(p2.x - nx * half_w, p2.y - ny * half_w)
                    path.lineTo(p1.x - nx * p1.width * 0.5, p1.y - ny * p1.width * 0.5)
                    path.closeSubpath()
                    cp.setPen(Qt.NoPen)
                    cp.setBrush(p2.color)
                    cp.drawPath(path)

        cp.end()

    # ── Painting (overlay) ────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Dark background
        p.fillRect(self.rect(), _BG)

        # Scale internal canvas to widget size
        sx = w / _CANVAS_W
        sy = h / _CANVAS_H
        s = min(sx, sy)
        ox = (w - _CANVAS_W * s) / 2
        oy = (h - _CANVAS_H * s) / 2

        p.save()
        p.translate(ox, oy)
        p.scale(s, s)

        # Draw persistent canvas
        p.drawImage(0, 0, self._canvas)

        # Draw live stroke (not yet committed)
        if self._cur_stroke and len(self._cur_stroke.points) >= 2:
            # The stroke is already painted incrementally to the canvas,
            # so nothing extra needed here
            pass

        # Draw cursor
        self._draw_cursor(p)

        p.restore()
        p.end()

    def _draw_cursor(self, p: QPainter):
        """Draw the crosshair cursor with brain-state glow."""
        cx, cy = self._cx, self._cy

        # Outer ring
        ring_color = _PEN_ACTIVE_COLOR if self._pen_down else _CURSOR_RING
        p.setPen(QPen(ring_color, 2))
        p.setBrush(Qt.NoBrush)
        radius = 16 if not self._pen_down else 12
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Crosshair lines
        p.setPen(QPen(ring_color, 1))
        gap = 5
        arm = 12
        p.drawLine(QPointF(cx - arm, cy), QPointF(cx - gap, cy))
        p.drawLine(QPointF(cx + gap, cy), QPointF(cx + arm, cy))
        p.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy - gap))
        p.drawLine(QPointF(cx, cy + gap), QPointF(cx, cy + arm))

        # Color preview dot at center
        r_f, g_f, b_f = colorsys.hls_to_rgb(
            self._smooth_h, self._smooth_l, self._smooth_s
        )
        preview_color = QColor(int(r_f * 255), int(g_f * 255), int(b_f * 255))
        p.setPen(Qt.NoPen)
        p.setBrush(preview_color)
        p.drawEllipse(QPointF(cx, cy), 4, 4)

        # If pen is down, draw a glow
        if self._pen_down:
            glow = QRadialGradient(QPointF(cx, cy), 30)
            gc = QColor(preview_color)
            gc.setAlpha(50)
            glow.setColorAt(0.0, gc)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx, cy), 30, 30)

        # "PEN" indicator text
        p.setPen(ring_color)
        p.setFont(QFont("Consolas", 8))
        label = "PEN ●" if self._pen_down else "PEN ○"
        p.drawText(QPointF(cx + 18, cy - 8), label)


# ══════════════════════════════════════════════════════════════════════
#  Toolbar Panel
# ══════════════════════════════════════════════════════════════════════

class _ToolPanel(QWidget):
    """Right-side toolbar with brush modes, metrics, and actions."""

    def __init__(self, canvas: _ArtCanvas, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self._canvas = canvas

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── Title ─────────────────────────────────────────────────────
        title = QLabel("🎨 NEURO ART")
        title.setStyleSheet("color: #4FC3F7; font: bold 14px 'Consolas';")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ── Color preview ─────────────────────────────────────────────
        self._color_label = QLabel("Brush Color")
        self._color_label.setStyleSheet("color: #888; font: 10px 'Consolas';")
        self._color_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._color_label)

        self._color_preview = QWidget()
        self._color_preview.setFixedSize(50, 50)
        self._color_preview.setStyleSheet(
            "background: #555; border-radius: 25px; border: 2px solid #444;"
        )
        # Center it
        color_row = QHBoxLayout()
        color_row.addStretch()
        color_row.addWidget(self._color_preview)
        color_row.addStretch()
        layout.addLayout(color_row)

        # ── Brush mode buttons ────────────────────────────────────────
        mode_label = QLabel("BRUSH MODE")
        mode_label.setStyleSheet("color: #888; font: bold 10px 'Consolas'; letter-spacing: 1px;")
        mode_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(mode_label)

        self._mode_btns: list[QPushButton] = []
        for i, (icon, name) in enumerate(zip(_MODE_ICONS, _MODE_NAMES)):
            btn = QPushButton(f" {icon}  {name}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda checked, idx=i: self._set_mode(idx))
            self._mode_btns.append(btn)
            layout.addWidget(btn)

        self._update_mode_styles()

        # ── Metrics section ───────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2A2E48;")
        layout.addWidget(sep)

        metrics_label = QLabel("BRAIN STATE")
        metrics_label.setStyleSheet("color: #888; font: bold 10px 'Consolas'; letter-spacing: 1px;")
        metrics_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(metrics_label)

        # Focus bar
        self._focus_lbl = QLabel("Focus: 0")
        self._focus_lbl.setStyleSheet("color: #8a8; font: 10px 'Consolas';")
        layout.addWidget(self._focus_lbl)

        # Relax bar
        self._relax_lbl = QLabel("Relax: 0")
        self._relax_lbl.setStyleSheet("color: #88a; font: 10px 'Consolas';")
        layout.addWidget(self._relax_lbl)

        # Stress bar
        self._stress_lbl = QLabel("Stress: 0")
        self._stress_lbl.setStyleSheet("color: #a88; font: 10px 'Consolas';")
        layout.addWidget(self._stress_lbl)

        # Pen state indicator
        self._pen_lbl = QLabel("PEN: OFF")
        self._pen_lbl.setStyleSheet("color: #666; font: bold 11px 'Consolas';")
        self._pen_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._pen_lbl)

        layout.addStretch()

        # ── Stroke counter ────────────────────────────────────────────
        self._stroke_lbl = QLabel("Strokes: 0")
        self._stroke_lbl.setStyleSheet("color: #666; font: 10px 'Consolas';")
        self._stroke_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._stroke_lbl)

        # ── Action buttons ────────────────────────────────────────────
        btn_style = (
            "QPushButton { background: #1E2238; color: #ccc; font: bold 11px 'Consolas'; "
            "padding: 8px; border-radius: 6px; border: 1px solid #333; }"
            "QPushButton:hover { background: #2A2E48; border-color: #555; }"
        )

        undo_btn = QPushButton("⟲  Undo")
        undo_btn.setCursor(Qt.PointingHandCursor)
        undo_btn.setStyleSheet(btn_style)
        undo_btn.clicked.connect(self._canvas.undo)
        layout.addWidget(undo_btn)

        clear_btn = QPushButton("✕  Clear All")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { background: #3A1520; color: #FF5252; font: bold 11px 'Consolas'; "
            "padding: 8px; border-radius: 6px; border: 1px solid #552233; }"
            "QPushButton:hover { background: #4A2030; border-color: #773344; }"
        )
        clear_btn.clicked.connect(self._canvas.clear_canvas)
        layout.addWidget(clear_btn)

        save_btn = QPushButton("💾  Save PNG")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton { background: #0D3320; color: #00E676; font: bold 11px 'Consolas'; "
            "padding: 8px; border-radius: 6px; border: 1px solid #225533; }"
            "QPushButton:hover { background: #1A4430; border-color: #337744; }"
        )
        save_btn.clicked.connect(lambda: self.parent().parent()._save_artwork())
        layout.addWidget(save_btn)

        copy_btn = QPushButton("📋  Copy to Clipboard")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(lambda: self.parent().parent()._copy_to_clipboard())
        layout.addWidget(copy_btn)

        # ── Refresh timer ─────────────────────────────────────────────
        self._refresh = QTimer(self)
        self._refresh.setInterval(100)
        self._refresh.timeout.connect(self._refresh_ui)
        self._refresh.start()

    def _set_mode(self, idx: int):
        self._canvas.set_mode(idx)
        for i, btn in enumerate(self._mode_btns):
            btn.setChecked(i == idx)
        self._update_mode_styles()

    def _update_mode_styles(self):
        for i, btn in enumerate(self._mode_btns):
            if btn.isChecked():
                btn.setStyleSheet(
                    "QPushButton { background: #1A3A2A; color: #00E676; font: bold 11px 'Consolas'; "
                    "padding: 7px 10px; border-radius: 6px; border: 1px solid #00E676; text-align: left; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #1E2238; color: #aaa; font: 11px 'Consolas'; "
                    "padding: 7px 10px; border-radius: 6px; border: 1px solid #333; text-align: left; }"
                    "QPushButton:hover { background: #2A2E48; color: #ddd; }"
                )

    def _refresh_ui(self):
        c = self._canvas

        # Color preview
        r_f, g_f, b_f = colorsys.hls_to_rgb(c._smooth_h, c._smooth_l, c._smooth_s)
        hex_c = QColor(int(r_f * 255), int(g_f * 255), int(b_f * 255)).name()
        self._color_preview.setStyleSheet(
            f"background: {hex_c}; border-radius: 25px; border: 2px solid #555;"
        )

        # Metrics
        self._focus_lbl.setText(f"Focus:  {c.attention:.0f}")
        fc = "#00E676" if c.attention >= _PEN_ON_THRESHOLD else "#4FC3F7"
        self._focus_lbl.setStyleSheet(f"color: {fc}; font: 10px 'Consolas';")

        self._relax_lbl.setText(f"Relax:  {c.relaxation:.0f}")
        self._stress_lbl.setText(f"Stress: {c.stress:.0f}")
        sc = "#FF5252" if c.stress > _SPLATTER_STRESS else "#FFA726" if c.stress > 40 else "#888"
        self._stress_lbl.setStyleSheet(f"color: {sc}; font: 10px 'Consolas';")

        # Pen state
        if c.pen_active:
            self._pen_lbl.setText("PEN: DRAWING ●")
            self._pen_lbl.setStyleSheet("color: #00E676; font: bold 11px 'Consolas';")
        else:
            self._pen_lbl.setText("PEN: OFF ○")
            self._pen_lbl.setStyleSheet("color: #666; font: bold 11px 'Consolas';")

        # Stroke counter
        self._stroke_lbl.setText(f"Strokes: {c.stroke_count}")


# ══════════════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════════════

class NeuroArtCanvasWindow(QMainWindow):
    """Standalone pop-up window for BCI Neuro Art Canvas."""

    def __init__(self):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("🎨  Neuro Art Canvas — Paint with Your Mind")
        self.setMinimumSize(900, 650)
        self.resize(1200, 800)
        self.setStyleSheet("QMainWindow { background: #0A0A14; }")
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Left: Canvas ──────────────────────────────────────────────
        canvas_container = QVBoxLayout()
        canvas_container.setContentsMargins(0, 0, 0, 0)
        canvas_container.setSpacing(0)

        # Top bar
        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("background: #12132a; border-bottom: 1px solid #222;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("🎨 NEURO ART CANVAS")
        title.setStyleSheet("color: #4FC3F7; font: bold 14px 'Consolas';")
        top_layout.addWidget(title)
        top_layout.addStretch()

        hint = QLabel("Head tilt → move brush  •  Focus → draw  •  Relax → cool colors  •  Stress → splatter")
        hint.setStyleSheet("color: #555; font: 10px 'Consolas';")
        top_layout.addWidget(hint)

        canvas_container.addWidget(top_bar)

        # Art canvas
        self._canvas = _ArtCanvas()
        canvas_container.addWidget(self._canvas, stretch=1)

        # Bottom info bar
        info_bar = QWidget()
        info_bar.setFixedHeight(28)
        info_bar.setStyleSheet("background: #12132a; border-top: 1px solid #222;")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 0, 12, 0)
        self._info_lbl = QLabel(f"Canvas: {_CANVAS_W}×{_CANVAS_H}")
        self._info_lbl.setStyleSheet("color: #555; font: 10px 'Consolas';")
        info_layout.addWidget(self._info_lbl)
        info_layout.addStretch()

        canvas_container.addWidget(info_bar)

        canvas_widget = QWidget()
        canvas_widget.setLayout(canvas_container)
        layout.addWidget(canvas_widget, stretch=1)

        # ── Right: Tool panel ─────────────────────────────────────────
        panel_wrapper = QWidget()
        panel_wrapper.setStyleSheet(
            f"background: {_PANEL_BG.name()}; border-left: 1px solid {_PANEL_BORDER.name()};"
        )
        panel_layout = QVBoxLayout(panel_wrapper)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self._panel = _ToolPanel(self._canvas, parent=panel_wrapper)
        panel_layout.addWidget(self._panel)
        layout.addWidget(panel_wrapper)

    # ── Save / Copy ───────────────────────────────────────────────────

    def _save_artwork(self):
        data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "data", "artwork"
        )
        os.makedirs(data_dir, exist_ok=True)
        default_name = f"neuro_art_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        default_path = os.path.join(data_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Artwork", default_path, "PNG Image (*.png)"
        )
        if path:
            img = self._canvas.get_export_image()
            img.save(path, "PNG")
            log.info("Neuro Art: saved artwork to %s", path)

    def _copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            img = self._canvas.get_export_image()
            clipboard.setImage(img)
            log.info("Neuro Art: copied artwork to clipboard")

    # ── Public API (called by signal dispatcher) ─────────────────────

    def on_mems(self, mems_timed_data):
        if not self.isVisible():
            return
        n = len(mems_timed_data)
        for i in range(n):
            gyro = mems_timed_data.get_gyroscope(i)
            self._canvas.feed_gyro(gyro.x, gyro.z)

    def on_emotions(self, data: dict):
        if not self.isVisible() or not data:
            return
        attention = data.get("attention", 0.0) or 0.0
        relaxation = data.get("relaxation", 0.0) or 0.0
        stress = data.get("cognitiveLoad", 0.0) or 0.0
        self._canvas.feed_emotions(attention, relaxation, stress)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def shutdown(self):
        self._canvas._timer.stop()
        self._panel._refresh.stop()
        self.close()
