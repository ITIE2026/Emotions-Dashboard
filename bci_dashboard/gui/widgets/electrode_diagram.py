"""
ElectrodeDiagram – custom QWidget that draws a head outline
with 4 coloured dots representing electrode contact quality.
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush

from utils.helpers import resist_color


class ElectrodeDiagram(QWidget):
    """Shows a schematic headband on a head with 4 electrode indicators."""

    # Electrode positions expressed as fractions (x, y) of the widget size.
    # Layout:  T3 ... O1 ... O2 ... T4  (left→right across headband)
    _POSITIONS = {
        "T3": (0.22, 0.45),
        "O1": (0.40, 0.38),
        "O2": (0.60, 0.38),
        "T4": (0.78, 0.45),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 240)
        # {channel: ohms}
        self._values: dict[str, float] = {}

    def set_values(self, data: dict[str, float]):
        self._values = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        # ── Head outline (oval) ───────────────────────────────────────
        head_pen = QPen(QColor("#888888"), 2)
        p.setPen(head_pen)
        p.setBrush(Qt.NoBrush)
        cx, cy = w * 0.5, h * 0.48
        rx, ry = w * 0.28, h * 0.38
        p.drawEllipse(QPointF(cx, cy), rx, ry)

        # ── Headband arc ──────────────────────────────────────────────
        band_pen = QPen(QColor("#555555"), 4)
        p.setPen(band_pen)
        band_rect = QRectF(cx - rx * 1.08, cy - ry * 0.55, rx * 2.16, ry * 1.1)
        p.drawArc(band_rect, 30 * 16, 120 * 16)  # top arc

        # ── Ears ──────────────────────────────────────────────────────
        ear_pen = QPen(QColor("#888888"), 2)
        p.setPen(ear_pen)
        ear_w, ear_h = w * 0.04, h * 0.10
        p.drawEllipse(QPointF(cx - rx - ear_w, cy), ear_w, ear_h)
        p.drawEllipse(QPointF(cx + rx + ear_w, cy), ear_w, ear_h)

        # ── Electrode dots ────────────────────────────────────────────
        dot_r = min(w, h) * 0.04
        font = QFont()
        font.setPointSize(max(8, int(h * 0.04)))
        p.setFont(font)

        for name, (fx, fy) in self._POSITIONS.items():
            x, y = w * fx, h * fy
            ohms = self._values.get(name, float("inf"))
            colour = resist_color(ohms)

            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(colour)))
            p.drawEllipse(QPointF(x, y), dot_r, dot_r)

            # Label below dot
            p.setPen(QColor("#cccccc"))
            label = f"{name}"
            if ohms < float("inf"):
                label += f"\n{ohms / 1000:.0f}kΩ"
            text_rect = QRectF(x - 30, y + dot_r + 2, 60, 30)
            p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)

        p.end()
