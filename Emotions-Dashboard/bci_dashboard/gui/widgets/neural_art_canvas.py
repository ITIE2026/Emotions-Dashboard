"""
Neural Art Generator – brain-driven particle system rendered via QPainter.

Four brain metrics map to visual properties:
  attention   → particle count & orbital tightness
  relaxation  → colour hue (cool ↔ warm) & velocity
  stress      → turbulence / jitter
  cogLoad     → particle size & trail length
"""
from __future__ import annotations

import math
import os
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    BG_CARD,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# ── Tunables ──────────────────────────────────────────────────────────────────
_FPS = 30
_BASE_PARTICLE_COUNT = 120
_MAX_PARTICLES = 300
_SPAWN_RATE = 4          # new particles per frame
_TRAIL_ALPHA = 18        # lower = longer trails (semi-transparent overlay)
_MIN_SPEED = 0.3
_MAX_SPEED = 3.5


class _Particle:
    """Lightweight mutable particle state."""
    __slots__ = (
        "x", "y", "vx", "vy", "angle", "radius",
        "size", "life", "max_life", "hue", "sat", "val", "alpha",
    )

    def __init__(self, cx: float, cy: float, metrics: dict):
        attention = metrics.get("attention", 50)
        relaxation = metrics.get("relaxation", 50)
        stress = metrics.get("stress", 50)
        cog_load = metrics.get("cogLoad", 50)

        # --- spawn from centre with slight offset -------------------------
        spread = 12.0
        self.x = cx + random.uniform(-spread, spread)
        self.y = cy + random.uniform(-spread, spread)

        # --- orbital angle & radius (attention drives tightness) ----------
        self.angle = random.uniform(0, 2 * math.pi)
        self.radius = random.uniform(2.0, 6.0)

        # --- velocity: relaxation slows things down -----------------------
        speed_factor = 1.0 - (relaxation / 150.0)  # 0.33 … 1.0
        base_speed = _MIN_SPEED + (_MAX_SPEED - _MIN_SPEED) * speed_factor
        self.vx = math.cos(self.angle) * base_speed * random.uniform(0.6, 1.4)
        self.vy = math.sin(self.angle) * base_speed * random.uniform(0.6, 1.4)

        # --- size: cogLoad drives it (bigger = more load) -----------------
        min_sz, max_sz = 2.0, 10.0
        t = cog_load / 100.0
        self.size = min_sz + (max_sz - min_sz) * t + random.uniform(-0.5, 0.5)

        # --- lifetime: higher cogLoad = longer trails --------------------
        self.max_life = int(40 + 80 * (cog_load / 100.0)) + random.randint(-10, 10)
        self.life = self.max_life

        # --- colour: relaxation shifts hue (warm→cool) -------------------
        # low relaxation → hue 0-30 (red/orange)
        # high relaxation → hue 200-270 (blue/purple)
        hue_low = 0 + random.randint(-5, 30)
        hue_high = 210 + random.randint(-10, 60)
        self.hue = int(hue_low + (hue_high - hue_low) * (relaxation / 100.0))
        self.sat = random.randint(180, 255)
        self.val = random.randint(200, 255)
        self.alpha = 255


class NeuralArtCanvas(QWidget):
    """Real-time particle system driven by brain metrics.

    Public API
    ----------
    update_brain_metrics(attention, relaxation, stress, cognitive_load)
    export_image() -> str | None
    clear_data()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)

        # brain state (0-100 each)
        self._attention: float = 0.0
        self._relaxation: float = 0.0
        self._stress: float = 0.0
        self._cog_load: float = 0.0
        self._has_data = False

        # particle pool
        self._particles: list[_Particle] = []

        # off-screen buffer for trail effect
        self._buffer: QPixmap | None = None

        # animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // _FPS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ── public API ────────────────────────────────────────────────────

    def update_brain_metrics(
        self,
        attention: float,
        relaxation: float,
        stress: float,
        cognitive_load: float,
    ):
        self._attention = max(0.0, min(100.0, attention))
        self._relaxation = max(0.0, min(100.0, relaxation))
        self._stress = max(0.0, min(100.0, stress))
        self._cog_load = max(0.0, min(100.0, cognitive_load))
        self._has_data = True

    def export_image(self) -> str | None:
        if self._buffer is None:
            return None
        default_name = f"BCI_NeuralArt_{int(time.time())}.png"
        pictures = os.path.join(os.path.expanduser("~"), "Pictures")
        if not os.path.isdir(pictures):
            pictures = os.path.expanduser("~")
        default_path = os.path.join(pictures, default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Neural Art", default_path, "PNG Images (*.png)"
        )
        if path:
            self._buffer.save(path, "PNG")
            return path
        return None

    def clear_data(self):
        self._has_data = False
        self._particles.clear()
        self._buffer = None
        self.update()

    # ── context menu ──────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid #333; padding: 4px; }}"
            f"QMenu::item:selected {{ background: {ACCENT_CYAN}; color: #0A0A14; }}"
        )
        save_action = menu.addAction("\U0001F4BE  Save Art as PNG\u2026")
        action = menu.exec(self.mapToGlobal(pos))
        if action == save_action:
            self.export_image()

    # ── simulation ────────────────────────────────────────────────────

    def _metrics_dict(self) -> dict:
        return {
            "attention": self._attention,
            "relaxation": self._relaxation,
            "stress": self._stress,
            "cogLoad": self._cog_load,
        }

    def _desired_count(self) -> int:
        # attention drives density: low=60, high=300
        t = self._attention / 100.0
        return int(_BASE_PARTICLE_COUNT + (_MAX_PARTICLES - _BASE_PARTICLE_COUNT) * t)

    def _tick(self):
        if not self._has_data:
            return
        if not self.isVisible():
            return

        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return

        cx, cy = w / 2.0, h / 2.0
        metrics = self._metrics_dict()
        stress_norm = self._stress / 100.0
        attention_norm = self._attention / 100.0

        # --- spawn new particles ------------------------------------------
        desired = self._desired_count()
        for _ in range(_SPAWN_RATE):
            if len(self._particles) < desired:
                self._particles.append(_Particle(cx, cy, metrics))

        # --- update existing particles ------------------------------------
        to_remove: list[int] = []
        max_dist = math.hypot(cx, cy) * 1.15

        for i, p in enumerate(self._particles):
            # age
            p.life -= 1
            if p.life <= 0:
                to_remove.append(i)
                continue

            # turbulence from stress
            jitter = stress_norm * 2.5
            p.vx += random.uniform(-jitter, jitter)
            p.vy += random.uniform(-jitter, jitter)

            # gentle spiral bias (attention tightens orbit)
            orbit_strength = 0.02 + 0.06 * attention_norm
            dx, dy = p.x - cx, p.y - cy
            p.vx += -dy * orbit_strength * 0.01
            p.vy += dx * orbit_strength * 0.01

            # move
            p.x += p.vx
            p.y += p.vy

            # fade alpha with remaining life
            life_ratio = p.life / max(p.max_life, 1)
            p.alpha = int(255 * life_ratio)

            # remove if out of bounds
            if math.hypot(p.x - cx, p.y - cy) > max_dist:
                to_remove.append(i)

        for idx in reversed(to_remove):
            self._particles.pop(idx)

        self.update()

    # ── rendering ─────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return

        # ensure buffer matches widget size
        if self._buffer is None or self._buffer.size() != self.size():
            self._buffer = QPixmap(self.size())
            self._buffer.fill(QColor(10, 10, 20))

        if not self._has_data:
            # placeholder
            qp = QPainter(self)
            qp.fillRect(self.rect(), QColor(10, 10, 20))
            qp.setPen(QColor(TEXT_SECONDARY))
            qp.drawText(self.rect(), Qt.AlignCenter, "Waiting for brain data\u2026")
            qp.end()
            return

        # --- draw trail overlay on buffer ---------------------------------
        bp = QPainter(self._buffer)
        bp.setRenderHint(QPainter.Antialiasing, True)

        # semi-transparent dark wash → creates trail / afterglow
        trail_strength = _TRAIL_ALPHA + int(12 * (1.0 - self._cog_load / 100.0))
        bp.fillRect(self._buffer.rect(), QColor(10, 10, 20, trail_strength))

        # --- draw particles -----------------------------------------------
        for p in self._particles:
            col = QColor.fromHsv(
                max(0, min(359, p.hue)),
                max(0, min(255, p.sat)),
                max(0, min(255, p.val)),
                max(0, min(255, p.alpha)),
            )

            if p.size > 4.0:
                # glow effect via radial gradient
                grad = QRadialGradient(QPointF(p.x, p.y), p.size * 2.0)
                core = QColor(col)
                core.setAlpha(min(255, p.alpha))
                outer = QColor(col)
                outer.setAlpha(0)
                grad.setColorAt(0.0, core)
                grad.setColorAt(0.4, QColor(col.red(), col.green(), col.blue(), p.alpha // 2))
                grad.setColorAt(1.0, outer)
                bp.setPen(Qt.NoPen)
                bp.setBrush(grad)
                bp.drawEllipse(QPointF(p.x, p.y), p.size * 2.0, p.size * 2.0)
            else:
                bp.setPen(Qt.NoPen)
                bp.setBrush(col)
                bp.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

        bp.end()

        # --- blit buffer to screen ----------------------------------------
        qp = QPainter(self)
        qp.drawPixmap(0, 0, self._buffer)

        # --- HUD: metric badges in bottom-left ----------------------------
        qp.setRenderHint(QPainter.Antialiasing, True)
        hud_y = h - 28
        qp.setPen(QColor(255, 255, 255, 140))
        qp.drawText(
            QRectF(8, hud_y, w - 16, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"ATT {self._attention:.0f}  |  REL {self._relaxation:.0f}"
            f"  |  STR {self._stress:.0f}  |  COG {self._cog_load:.0f}",
        )
        # particle count (right)
        qp.drawText(
            QRectF(8, hud_y, w - 16, 20),
            Qt.AlignRight | Qt.AlignVCenter,
            f"{len(self._particles)} particles",
        )
        qp.end()


class NeuralArtChart(QWidget):
    """Wrapper with header label + NeuralArtCanvas, matching HemisphereRadarChart pattern."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(0)

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)
        header.setSpacing(0)

        title = QLabel("Neural Art Generator")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        subtitle = QLabel("Brain-Driven Particle System")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)

        self._canvas = NeuralArtCanvas(self)
        layout.addWidget(self._canvas, stretch=1)

    def update_brain_metrics(
        self, attention: float, relaxation: float, stress: float, cognitive_load: float
    ):
        self._canvas.update_brain_metrics(attention, relaxation, stress, cognitive_load)

    def clear_data(self):
        self._canvas.clear_data()
