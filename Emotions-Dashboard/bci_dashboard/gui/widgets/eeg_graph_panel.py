"""
Dashboard EEG graph panel with click-to-toggle spectrum and hemisphere radar views.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.spectrum_chart import SpectrumChart
from utils.config import (
    BG_CARD,
    BORDER_SUBTLE,
    COLOR_ALPHA,
    COLOR_BETA,
    COLOR_DELTA,
    COLOR_SMR,
    COLOR_THETA,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_BAND_ORDER = ("delta", "theta", "alpha", "smr", "beta")
_BAND_LABELS = {
    "delta": "Delta",
    "theta": "Theta",
    "alpha": "Alpha",
    "smr": "SMR",
    "beta": "Beta",
}
_BAND_COLOURS = {
    "delta": COLOR_DELTA,
    "theta": COLOR_THETA,
    "alpha": COLOR_ALPHA,
    "smr": COLOR_SMR,
    "beta": COLOR_BETA,
}


class _DualHemisphereRadarCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._left_band_powers: dict[str, float] = {}
        self._right_band_powers: dict[str, float] = {}
        self.setMinimumHeight(220)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_band_powers(self, left_band_powers: dict | None, right_band_powers: dict | None):
        self._left_band_powers = dict(left_band_powers or {})
        self._right_band_powers = dict(right_band_powers or {})
        self.update()

    def clear_data(self):
        self._left_band_powers = {}
        self._right_band_powers = {}
        self.update()

    @staticmethod
    def _normalized_arrays(left_band_powers: dict, right_band_powers: dict):
        left_values = [max(0.0, float(left_band_powers.get(name, 0.0))) for name in _BAND_ORDER]
        right_values = [max(0.0, float(right_band_powers.get(name, 0.0))) for name in _BAND_ORDER]
        transformed = [math.log1p(value) for value in left_values + right_values]
        scale = max(transformed, default=0.0)
        if scale <= 0.0:
            return [0.0] * len(_BAND_ORDER), [0.0] * len(_BAND_ORDER)
        left = [value / scale for value in transformed[: len(_BAND_ORDER)]]
        right = [value / scale for value in transformed[len(_BAND_ORDER):]]
        return left, right

    def _draw_single_radar(
        self,
        painter: QPainter,
        rect: QRectF,
        title: str,
        values: list[float],
        *,
        fill_colour: QColor,
        outline_colour: QColor,
    ):
        center = QPointF(rect.center().x(), rect.center().y() + 6.0)
        radius = min(rect.width(), rect.height()) * 0.30
        if radius <= 0:
            return

        painter.save()
        grid_pen = QPen(QColor(120, 128, 158, 120))
        grid_pen.setStyle(Qt.DashLine)
        painter.setPen(grid_pen)

        for ring in range(1, 6):
            scale = ring / 5.0
            ring_points = []
            for index, band_name in enumerate(_BAND_ORDER):
                angle = -math.pi / 2.0 + (2.0 * math.pi * index / len(_BAND_ORDER))
                ring_radius = radius * scale
                ring_points.append(
                    QPointF(
                        center.x() + math.cos(angle) * ring_radius,
                        center.y() + math.sin(angle) * ring_radius,
                    )
                )
            painter.drawPolygon(QPolygonF(ring_points))

        for index, band_name in enumerate(_BAND_ORDER):
            angle = -math.pi / 2.0 + (2.0 * math.pi * index / len(_BAND_ORDER))
            end_point = QPointF(
                center.x() + math.cos(angle) * radius,
                center.y() + math.sin(angle) * radius,
            )
            painter.drawLine(center, end_point)

            label_point = QPointF(
                center.x() + math.cos(angle) * (radius + 24.0),
                center.y() + math.sin(angle) * (radius + 24.0),
            )
            label_rect = QRectF(label_point.x() - 32.0, label_point.y() - 10.0, 64.0, 20.0)
            painter.setPen(QColor(_BAND_COLOURS[band_name]))
            painter.drawText(label_rect, Qt.AlignCenter, _BAND_LABELS[band_name])
            painter.setPen(grid_pen)

        polygon_points = []
        for index, value in enumerate(values):
            clamped_value = max(0.0, min(1.0, float(value)))
            angle = -math.pi / 2.0 + (2.0 * math.pi * index / len(_BAND_ORDER))
            polygon_points.append(
                QPointF(
                    center.x() + math.cos(angle) * (radius * clamped_value),
                    center.y() + math.sin(angle) * (radius * clamped_value),
                )
            )

        painter.setPen(QPen(outline_colour, 2.0))
        painter.setBrush(fill_colour)
        painter.drawPolygon(QPolygonF(polygon_points))

        painter.setPen(QColor(TEXT_PRIMARY))
        title_rect = QRectF(rect.left(), rect.bottom() - 24.0, rect.width(), 20.0)
        painter.drawText(title_rect, Qt.AlignCenter, title)
        painter.restore()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        inner = self.rect().adjusted(12, 6, -12, -8)
        if inner.width() <= 0 or inner.height() <= 0:
            return

        left_values, right_values = self._normalized_arrays(self._left_band_powers, self._right_band_powers)
        if max(left_values + right_values, default=0.0) <= 0.0:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(inner, Qt.AlignCenter, "Waiting for hemisphere PSD data")
            return

        left_rect = QRectF(inner.left(), inner.top(), inner.width() / 2.0, inner.height())
        right_rect = QRectF(inner.center().x(), inner.top(), inner.width() / 2.0, inner.height())
        self._draw_single_radar(
            painter,
            left_rect,
            "Left Hemisphere",
            left_values,
            fill_colour=QColor(255, 213, 79, 78),
            outline_colour=QColor(255, 213, 79, 235),
        )
        self._draw_single_radar(
            painter,
            right_rect,
            "Right Hemisphere",
            right_values,
            fill_colour=QColor(77, 208, 225, 78),
            outline_colour=QColor(77, 208, 225, 235),
        )


class HemisphereRadarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(0)

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)
        header.setSpacing(0)

        title = QLabel("Brain Activity")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        subtitle = QLabel("Electroencephalogram (EEG)")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)

        self._canvas = _DualHemisphereRadarCanvas(self)
        layout.addWidget(self._canvas, stretch=1)

    def update_hemisphere_band_powers(self, left_band_powers: dict | None, right_band_powers: dict | None):
        self._canvas.set_band_powers(left_band_powers, right_band_powers)

    def clear_data(self):
        self._canvas.clear_data()

    def hemisphere_band_powers(self):
        return dict(self._canvas._left_band_powers), dict(self._canvas._right_band_powers)


class ToggleableEegGraphPanel(QWidget):
    VIEW_SPECTRUM = "spectrum"
    VIEW_HEMISPHERE_RADAR = "hemisphere_radar"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view_mode = self.VIEW_SPECTRUM
        self.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack_host = QWidget(self)
        self._stack = QStackedLayout(self._stack_host)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._spectrum_view = SpectrumChart(self._stack_host)
        self._hemisphere_view = HemisphereRadarChart(self._stack_host)
        self._stack.addWidget(self._spectrum_view)
        self._stack.addWidget(self._hemisphere_view)
        self._stack.setCurrentWidget(self._spectrum_view)
        layout.addWidget(self._stack_host, stretch=1)

        self._click_surface = QPushButton("", self)
        self._click_surface.setCursor(Qt.PointingHandCursor)
        self._click_surface.setToolTip("Click to switch EEG graph view")
        self._click_surface.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.01); }"
        )
        self._click_surface.clicked.connect(self.toggle_view_mode)
        self._click_surface.raise_()

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._click_surface.setGeometry(self.rect())
        self._click_surface.raise_()

    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str):
        if mode == self.VIEW_HEMISPHERE_RADAR:
            self._view_mode = self.VIEW_HEMISPHERE_RADAR
            self._stack.setCurrentWidget(self._hemisphere_view)
        else:
            self._view_mode = self.VIEW_SPECTRUM
            self._stack.setCurrentWidget(self._spectrum_view)

    def toggle_view_mode(self):
        if self._view_mode == self.VIEW_SPECTRUM:
            self.set_view_mode(self.VIEW_HEMISPHERE_RADAR)
        else:
            self.set_view_mode(self.VIEW_SPECTRUM)

    def reset_view(self):
        self.set_view_mode(self.VIEW_SPECTRUM)

    def update_psd(self, freqs, powers):
        self._spectrum_view.update_psd(freqs, powers)

    def update_hemisphere_band_powers(self, left_band_powers: dict | None, right_band_powers: dict | None):
        self._hemisphere_view.update_hemisphere_band_powers(left_band_powers, right_band_powers)

    def hemisphere_band_powers(self):
        return self._hemisphere_view.hemisphere_band_powers()

    def clear_data(self):
        self._spectrum_view.update_psd([], [])
        self._hemisphere_view.clear_data()
