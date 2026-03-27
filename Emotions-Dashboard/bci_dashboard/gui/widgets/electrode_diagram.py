"""
ElectrodeDiagram – premium custom QWidget that draws a photorealistic
head silhouette with glowing animated electrode contact indicators.

Public API:
  set_values(data)  – update resistance readings
  start_scan()      – activate pulsing scan rings on each electrode
  stop_scan()       – stop the scan animation
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush,
    QLinearGradient, QRadialGradient,
)

from utils.helpers import resist_color
from utils.config import ACCENT_CYAN


class ElectrodeDiagram(QWidget):
    """Shows a schematic headband on a head with 4 electrode indicators."""

    _POSITIONS = {
        "T3": (0.22, 0.45),
        "O1": (0.40, 0.38),
        "O2": (0.60, 0.38),
        "T4": (0.78, 0.45),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 240)
        self._values: dict[str, float] = {}
        self._pulse_phase: float = 0.0
        self._scanning: bool = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._tick_pulse)

    # ── Public API ─────────────────────────────────────────────────────

    def set_values(self, data: dict[str, float]):
        self._values = data
        self.update()

    def start_scan(self):
        """Activate the pulsing scan-ring animation on each electrode."""
        self._scanning = True
        self._pulse_phase = 0.0
        self._pulse_timer.start()

    def stop_scan(self):
        """Stop the scan animation."""
        self._scanning = False
        self._pulse_timer.stop()
        self.update()

    # ── Internal ───────────────────────────────────────────────────────

    def _tick_pulse(self):
        self._pulse_phase = (self._pulse_phase + 0.025) % 1.0
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w * 0.5, h * 0.47
        rx, ry = w * 0.28, h * 0.37

        # ── 3D head silhouette ─────────────────────────────────────────
        head_grad = QRadialGradient(cx - rx * 0.18, cy - ry * 0.22, max(rx, ry) * 1.05)
        head_grad.setColorAt(0.00, QColor("#1E2A3A"))
        head_grad.setColorAt(0.45, QColor("#111827"))
        head_grad.setColorAt(0.80, QColor("#0D1322"))
        head_grad.setColorAt(1.00, QColor("#070A12"))
        p.setPen(QPen(QColor("#2A3850"), 1.5))
        p.setBrush(QBrush(head_grad))
        p.drawEllipse(QPointF(cx, cy), rx, ry)

        # Surface sheen highlight
        sheen = QRadialGradient(cx - rx * 0.28, cy - ry * 0.34, min(rx, ry) * 0.55)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 20))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sheen))
        p.drawEllipse(QPointF(cx - rx * 0.08, cy - ry * 0.08), rx * 0.82, ry * 0.82)

        # ── Ears ───────────────────────────────────────────────────────
        ear_w, ear_h = w * 0.038, h * 0.088
        for ear_x in (cx - rx - ear_w * 0.4, cx + rx + ear_w * 0.4):
            ear_grad = QRadialGradient(ear_x, cy, ear_w * 1.5)
            ear_grad.setColorAt(0.0, QColor("#1A2535"))
            ear_grad.setColorAt(1.0, QColor("#090C14"))
            p.setPen(QPen(QColor("#222D3C"), 1.5))
            p.setBrush(QBrush(ear_grad))
            p.drawEllipse(QPointF(ear_x, cy), ear_w, ear_h)

        # ── Glowing headband ───────────────────────────────────────────
        band_rect = QRectF(cx - rx * 1.08, cy - ry * 0.56, rx * 2.16, ry * 1.14)

        # Soft glow halo
        glow_pen = QPen(QColor(105, 240, 174, 22), 16)
        glow_pen.setCapStyle(Qt.RoundCap)
        p.setPen(glow_pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(band_rect, 30 * 16, 120 * 16)

        # Main band gradient (fades at both ends)
        band_grad = QLinearGradient(cx - rx * 1.1, cy, cx + rx * 1.1, cy)
        band_grad.setColorAt(0.00, QColor(105, 240, 174, 30))
        band_grad.setColorAt(0.25, QColor(105, 240, 174, 190))
        band_grad.setColorAt(0.50, QColor(77, 208, 225, 255))
        band_grad.setColorAt(0.75, QColor(105, 240, 174, 190))
        band_grad.setColorAt(1.00, QColor(105, 240, 174, 30))
        band_pen = QPen(QBrush(band_grad), 5)
        band_pen.setCapStyle(Qt.RoundCap)
        p.setPen(band_pen)
        p.drawArc(band_rect, 30 * 16, 120 * 16)

        # ── Electrode indicators ───────────────────────────────────────
        dot_r = min(w, h) * 0.040

        for name, (fx, fy) in self._POSITIONS.items():
            x, y = w * fx, h * fy
            ohms = self._values.get(name, float("inf"))
            colour_str = resist_color(ohms)
            colour = QColor(colour_str)
            cr, cg, cb = colour.red(), colour.green(), colour.blue()

            # Scan pulse rings (two staggered concentric expanding rings)
            if self._scanning:
                for ring_offset, ring_col in ((0.0, colour), (0.42, QColor(ACCENT_CYAN))):
                    phase = (self._pulse_phase + fx * 0.3 + ring_offset) % 1.0
                    ring_r = dot_r * (1.5 + phase * 3.2)
                    alpha = int(155 * (1.0 - phase))
                    rc = QColor(ring_col)
                    rc.setAlpha(alpha)
                    p.setPen(QPen(rc, 1.2))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(x, y), ring_r, ring_r)

            # Radial glow halo
            halo = QRadialGradient(x, y, dot_r * 2.4)
            halo.setColorAt(0.0, QColor(cr, cg, cb, 80))
            halo.setColorAt(1.0, QColor(cr, cg, cb, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(x, y), dot_r * 2.4, dot_r * 2.4)

            # Outer coloured ring
            p.setPen(QPen(colour, 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x, y), dot_r, dot_r)

            # Dark inner fill
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(cr, cg, cb, 55)))
            p.drawEllipse(QPointF(x, y), dot_r * 0.62, dot_r * 0.62)

            # Specular highlight dot
            p.setBrush(QBrush(QColor(255, 255, 255, 165)))
            p.drawEllipse(QPointF(x - dot_r * 0.22, y - dot_r * 0.22), dot_r * 0.18, dot_r * 0.18)

            # ── Badge pill ────────────────────────────────────────────
            badge_w, badge_h = 60.0, 17.0
            badge_rect = QRectF(x - badge_w / 2, y + dot_r + 5, badge_w, badge_h)
            p.setBrush(QBrush(QColor(8, 12, 22, 210)))
            p.drawRoundedRect(badge_rect, 6, 6)
            p.setPen(QColor(colour_str))
            p.setFont(QFont("Segoe UI", max(6, int(h * 0.028))))
            badge_text = (
                f"{name}  {ohms / 1000:.1f}kΩ" if ohms < float("inf") else name
            )
            p.drawText(badge_rect, Qt.AlignCenter, badge_text)

        p.end()

