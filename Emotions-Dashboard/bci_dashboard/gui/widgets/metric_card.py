"""
MetricCard – premium dark card with a circular arc progress ring.
Matches the Mind Tracker BCI monitoring screen style.
"""
from __future__ import annotations
import math

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QPen, QColor, QConicalGradient, QFont, QRadialGradient

from utils.config import BG_CARD, BORDER_SUBTLE, TEXT_SECONDARY, BG_PRIMARY


_RING_OUTER_FRAC = 0.72   # ring outer radius as fraction of half-width
_RING_WIDTH = 9            # stroke width in px


class _ArcRing(QWidget):
    """Custom widget that draws a circular arc progress ring."""

    def __init__(self, colour: str = "#69F0AE", parent=None):
        super().__init__(parent)
        self._colour = colour
        self._value = 0.0          # 0–100
        self._display_text = "--"
        self.setMinimumSize(90, 90)

    # ── Public API ──────────────────────────────────────────────────
    def get_fill(self) -> float:
        return self._value

    def set_fill(self, v: float):
        self._value = max(0.0, min(100.0, v))
        self.update()

    fill = Property(float, get_fill, set_fill)

    def set_display(self, text: str):
        self._display_text = text
        self.update()

    # ── Paint ────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        side = min(w, h)
        xo = (w - side) / 2
        yo = (h - side) / 2

        ring_r = side * _RING_OUTER_FRAC / 2
        cx = w / 2
        cy = h / 2
        margin = side * (1 - _RING_OUTER_FRAC) / 2
        rect = QRectF(xo + margin, yo + margin,
                      side - 2 * margin, side - 2 * margin)

        # Background track
        track_pen = QPen(QColor("#1E2238"), _RING_WIDTH)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Foreground arc (value fraction)
        frac = self._value / 100.0
        if frac > 0:
            span_angle = int(frac * 360 * 16)
            arc_pen = QPen(QColor(self._colour), _RING_WIDTH)
            arc_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(arc_pen)
            # Start at top (90°), sweep clockwise (negative direction in Qt)
            painter.drawArc(rect, 90 * 16, -span_angle)

        # Inner glow dot at arc end
        if frac > 0.01:
            angle_rad = math.radians(90 - frac * 360)
            dot_x = cx + ring_r * math.cos(angle_rad)
            dot_y = cy - ring_r * math.sin(angle_rad)
            glow_c = QColor(self._colour)
            glow_c.setAlphaF(0.6)
            grd = QRadialGradient(dot_x, dot_y, _RING_WIDTH)
            grd.setColorAt(0, QColor(self._colour))
            grd.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(grd)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QRectF(dot_x - _RING_WIDTH, dot_y - _RING_WIDTH,
                       _RING_WIDTH * 2, _RING_WIDTH * 2)
            )

        # Centre value text
        font = QFont("Segoe UI", 1, QFont.Bold)
        font_size = max(8, int(side * 0.22))
        font.setPointSize(font_size)
        painter.setFont(font)
        painter.setPen(QColor(self._colour))
        painter.drawText(rect, Qt.AlignCenter, self._display_text)

        painter.end()


class MetricCard(QWidget):
    """
    Premium dark card with circular arc progress ring:

        ┌─────────────────────┐
        │   ╭──────────╮      │
        │  ╱   67%      ╲     │
        │ │    ◌◌◌◌◌◌◌◌  │   │
        │  ╲             ╱    │
        │   ╰──────────╯      │
        │       Focus         │
        └─────────────────────┘
    """

    def __init__(self, title: str = "", colour: str = "#69F0AE", parent=None):
        super().__init__(parent)
        self._colour = colour
        self._anim: QPropertyAnimation | None = None
        self._build_ui(title)
        self._apply_glow()

    def _build_ui(self, title: str):
        self.setStyleSheet(
            f"MetricCard {{ background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 16px; }}"
        )
        self.setMinimumSize(110, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        self._ring = _ArcRing(colour=self._colour)
        self._ring.setMinimumSize(80, 80)
        layout.addWidget(self._ring, alignment=Qt.AlignCenter)

        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent; "
            f"border: none; letter-spacing: 0.5px; text-transform: uppercase;"
        )
        layout.addWidget(self._title_label)

    def _apply_glow(self):
        shadow = QGraphicsDropShadowEffect(self)
        qc = QColor(self._colour)
        qc.setAlphaF(0.25)
        shadow.setColor(qc)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    # ── Public API (backward-compatible with old MetricCard) ─────────
    def set_value(self, value: float, suffix: str = "%"):
        """Update the displayed value (0–100 expected)."""
        if suffix == "%":
            display = f"{value:.0f}%"
        elif suffix == "bpm" or suffix == "":
            display = f"{value:.0f}"
        else:
            display = f"{value:.1f}"

        # Animate ring fill
        current = self._ring.get_fill()
        target = float(min(100, max(0, value)))
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self._ring, b"fill", self._ring)
        self._anim.setStartValue(current)
        self._anim.setEndValue(target)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

        self._ring.set_display(display)

    def set_title(self, title: str):
        self._title_label.setText(title)

