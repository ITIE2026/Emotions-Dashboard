"""
Widgets for the raw-data dashboard panels.
"""
from __future__ import annotations

import math
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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


_SERIES_COLORS = {
    "x": "#6FA0FF",
    "y": "#F39A5A",
    "z": "#64C96A",
}

_PIE_COLORS = {
    "delta": COLOR_DELTA,
    "theta": COLOR_THETA,
    "alpha": COLOR_ALPHA,
    "smr": COLOR_SMR,
    "beta": COLOR_BETA,
}


class _SessionAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session_start = time.time()

    def set_session_start(self, t: float):
        self._session_start = float(t)

    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            elapsed = max(0.0, float(value) - self._session_start)
            hours, rem = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(rem, 60)
            labels.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        return labels


class CollapsibleSection(QWidget):
    expanded_changed = Signal(bool)

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._button = QToolButton()
        self._button.setText(title)
        self._button.setCheckable(True)
        self._button.setChecked(expanded)
        self._button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._button.clicked.connect(self._toggle)
        self._button.setStyleSheet(
            f"QToolButton {{ color: {TEXT_PRIMARY}; background: #5567a9; border: none; "
            f"padding: 6px 10px; font-size: 12px; font-weight: bold; text-align: left; }}"
        )

        self._body = QWidget()
        self._body.setVisible(expanded)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._button)
        layout.addWidget(self._body)

    @property
    def content_layout(self):
        return self._body_layout

    def is_expanded(self) -> bool:
        return bool(self._button.isChecked())

    def set_expanded(self, expanded: bool):
        expanded = bool(expanded)
        if self._button.isChecked() == expanded:
            self._button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
            self._body.setVisible(expanded)
            return
        self._button.setChecked(expanded)
        self._toggle(expanded)

    def toggle(self):
        self.set_expanded(not self.is_expanded())

    def _toggle(self, checked: bool):
        self._button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self._body.setVisible(checked)
        self.expanded_changed.emit(bool(checked))


class TriAxisChartWidget(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._base_title = title
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)

        self._span_label = QLabel("Span: 5 sec")
        self._span_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_PRIMARY}; background: transparent; font-weight: bold;"
        )
        self._value_label = QLabel(f"{self._base_title}: (0.00, 0.00, 0.00)")
        self._value_label.setAlignment(Qt.AlignCenter)
        self._value_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_PRIMARY}; background: transparent; font-weight: bold;"
        )
        meta_row.addWidget(self._span_label)
        meta_row.addStretch()
        meta_row.addWidget(self._value_label, stretch=1)
        meta_row.addStretch()
        layout.addLayout(meta_row)

        axis = _SessionAxisItem(orientation="bottom")
        self._plot = pg.PlotWidget(axisItems={"bottom": axis})
        self._axis = axis
        self._plot.setBackground("#131624")
        self._plot.showGrid(x=True, y=True, alpha=0.12)
        self._plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#555"))
        self._plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen("#888"))
        self._plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#555"))
        self._plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen("#888"))
        self._plot.getViewBox().setMouseEnabled(x=False, y=False)
        self._plot.getPlotItem().setMenuEnabled(False)
        baseline = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color="#435069", width=1))
        self._plot.addItem(baseline)

        legend = self._plot.addLegend(offset=(12, 12))
        legend.setBrush(pg.mkBrush(0, 0, 0, 0))
        legend.setPen(pg.mkPen(None))
        self._curves = {}
        for key in ("x", "y", "z"):
            curve = self._plot.plot(
                pen=pg.mkPen(_SERIES_COLORS[key], width=1.3),
                name=key.upper(),
            )
            self._curves[key] = curve

        layout.addWidget(self._plot, stretch=1)

    def set_session_start(self, t: float):
        self._axis.set_session_start(t)

    def set_series(
        self,
        times,
        x_values,
        y_values,
        z_values,
        current_vector=None,
        span_seconds: float = 5.0,
        fixed_range=None,
    ):
        t = np.asarray(times, dtype=float)
        x_arr = np.asarray(x_values, dtype=float)
        y_arr = np.asarray(y_values, dtype=float)
        z_arr = np.asarray(z_values, dtype=float)

        if current_vector is None:
            current_vector = (
                float(x_arr[-1]) if x_arr.size else 0.0,
                float(y_arr[-1]) if y_arr.size else 0.0,
                float(z_arr[-1]) if z_arr.size else 0.0,
            )
        self._value_label.setText(
            f"{self._base_title}: ({current_vector[0]:.2f}, {current_vector[1]:.2f}, {current_vector[2]:.2f})"
        )
        self._span_label.setText(f"Span: {int(round(span_seconds))} sec")

        if t.size == 0:
            for curve in self._curves.values():
                curve.setData([], [])
            return

        self._curves["x"].setData(t, x_arr)
        self._curves["y"].setData(t, y_arr)
        self._curves["z"].setData(t, z_arr)

        t_end = float(t[-1])
        t_start = t_end - float(span_seconds)
        self._plot.setXRange(t_start, t_end, padding=0)

        if fixed_range is not None:
            self._plot.setYRange(float(fixed_range[0]), float(fixed_range[1]), padding=0)
            return

        visible_mask = t >= t_start
        visible_values = np.concatenate([
            x_arr[visible_mask],
            y_arr[visible_mask],
            z_arr[visible_mask],
        ])
        if visible_values.size == 0:
            self._plot.setYRange(-1.0, 1.0, padding=0)
            return

        ymin = float(np.min(visible_values))
        ymax = float(np.max(visible_values))
        pad = max((ymax - ymin) * 0.12, 0.1)
        self._plot.setYRange(ymin - pad, ymax + pad, padding=0)


class RhythmsPieChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._band_powers = {key: 0.0 for key in _PIE_COLORS}
        self._waiting_text = "Waiting for PSD data"
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_band_powers(self, band_powers: dict):
        self._band_powers = {key: float(band_powers.get(key, 0.0)) for key in _PIE_COLORS}
        self._waiting_text = ""
        self.update()

    def set_waiting(self, message: str = "Waiting for PSD data"):
        self._waiting_text = message
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#131624"))

        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.drawText(self.rect().adjusted(0, 10, 0, 0), Qt.AlignTop | Qt.AlignHCenter, "Rhythms Diagram")

        legend_x = 18
        legend_y = 54
        legend_step = 22
        painter.setFont(QFont("Segoe UI", 10))
        for idx, (band, colour) in enumerate(_PIE_COLORS.items()):
            y = legend_y + (idx * legend_step)
            painter.fillRect(legend_x, y, 14, 14, QColor(colour))
            painter.drawText(legend_x + 18, y + 12, band.capitalize())

        total = sum(max(value, 0.0) for value in self._band_powers.values())
        chart_rect = self.rect().adjusted(140, 38, -24, -24)
        side = min(chart_rect.width(), chart_rect.height())
        pie_rect = chart_rect.adjusted(
            (chart_rect.width() - side) // 2,
            0,
            -(chart_rect.width() - side) // 2,
            -(chart_rect.height() - side),
        )
        if total <= np.finfo(float).eps:
            painter.setPen(QPen(QColor(TEXT_SECONDARY), 1))
            painter.drawEllipse(pie_rect)
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                pie_rect.adjusted(-20, 0, 20, 0),
                Qt.AlignCenter | Qt.TextWordWrap,
                self._waiting_text or "Waiting for rhythm data",
            )
            return

        start_angle = 90 * 16
        for band, value in self._band_powers.items():
            fraction = max(0.0, value) / total
            span_angle = int(round(-fraction * 360 * 16))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_PIE_COLORS[band]))
            painter.drawPie(pie_rect, start_angle, span_angle)

            mid_angle = math.radians((-start_angle - (span_angle / 2)) / 16)
            text_radius = pie_rect.width() * 0.28
            cx = pie_rect.center().x() + (text_radius * math.cos(mid_angle))
            cy = pie_rect.center().y() + (text_radius * math.sin(mid_angle))
            painter.setPen(QColor("#0B1020") if band == "beta" else QColor("#F5F7FF"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(
                int(cx - 24),
                int(cy - 10),
                48,
                20,
                Qt.AlignCenter,
                f"{fraction:.3f}",
            )
            start_angle += span_angle
