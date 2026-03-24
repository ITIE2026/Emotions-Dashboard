"""
Popup graph windows for live EEG/Productivity/Emotion metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.config import BG_CARD, BG_PRIMARY, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


_HEADER_BG = "#5E70B7"
_PLOT_BG = "#35394B"
_LEGEND_BG = "#2F3345"
_SUMMARY_GOLD = "#E4BE4D"
_SUMMARY_LIGHT = "#E0E0E0"
_THRESHOLD_COLOR = "#D7585C"
_BASELINE_COLOR = "#D0BE68"
_TIME_SCALE_OPTIONS = {
    "1 min": 60.0,
    "5 min": 300.0,
    "15 min": 900.0,
}


@dataclass(frozen=True)
class GraphSeriesSpec:
    key: str
    label: str
    color: str


@dataclass(frozen=True)
class TimeSeriesGraphSpec:
    graph_id: str
    title: str
    series: tuple[GraphSeriesSpec, ...]
    primary_key: str | None = None
    baseline_key: str | None = None
    show_threshold_band: bool = False
    min_y_max: float = 2.0
    fixed_y_range: tuple[float, float] | None = None


GRAPH_SPECS: dict[str, TimeSeriesGraphSpec] = {
    "frequency_peaks": TimeSeriesGraphSpec(
        graph_id="frequency_peaks",
        title="Frequency Peaks",
        series=(
            GraphSeriesSpec("alpha_peak", "Alpha peak", "#5B83D7"),
            GraphSeriesSpec("beta_peak", "Beta peak", "#E38A4A"),
            GraphSeriesSpec("theta_peak", "Theta peak", "#60C06D"),
        ),
        min_y_max=30.0,
    ),
    "concentration_index": TimeSeriesGraphSpec(
        graph_id="concentration_index",
        title="Concentration",
        series=(GraphSeriesSpec("concentrationScore", "Concentration", "#5B83D7"),),
        primary_key="concentrationScore",
        baseline_key="concentrationBaseline",
        show_threshold_band=True,
        min_y_max=2.0,
    ),
    "relaxation_index": TimeSeriesGraphSpec(
        graph_id="relaxation_index",
        title="Relaxation",
        series=(GraphSeriesSpec("relaxationScore", "Relaxation", "#5B83D7"),),
        primary_key="relaxationScore",
        baseline_key="relaxationBaseline",
        show_threshold_band=True,
        min_y_max=2.0,
    ),
    "alpha_gravity": TimeSeriesGraphSpec(
        graph_id="alpha_gravity",
        title="Gravity",
        series=(GraphSeriesSpec("gravityScore", "Gravity", "#5B83D7"),),
        primary_key="gravityScore",
        baseline_key="gravityBaseline",
        show_threshold_band=True,
        min_y_max=2.0,
    ),
    "productivity_score": TimeSeriesGraphSpec(
        graph_id="productivity_score",
        title="Productivity",
        series=(GraphSeriesSpec("currentValue", "Productivity", "#5B83D7"),),
        primary_key="currentValue",
        min_y_max=2.0,
    ),
    "fatigue_score": TimeSeriesGraphSpec(
        graph_id="fatigue_score",
        title="Fatigue",
        series=(GraphSeriesSpec("fatigueScore", "Fatigue", "#5B83D7"),),
        primary_key="fatigueScore",
        baseline_key="fatigueBaseline",
        show_threshold_band=True,
        min_y_max=2.0,
    ),
    "reverse_fatigue_score": TimeSeriesGraphSpec(
        graph_id="reverse_fatigue_score",
        title="Reverse Fatigue",
        series=(GraphSeriesSpec("reverseFatigueScore", "Reverse Fatigue", "#5B83D7"),),
        primary_key="reverseFatigueScore",
        baseline_key="reverseFatigueBaseline",
        show_threshold_band=True,
        min_y_max=2.0,
    ),
    "accumulated_fatigue": TimeSeriesGraphSpec(
        graph_id="accumulated_fatigue",
        title="Accumulated Fatigue",
        series=(GraphSeriesSpec("accumulatedFatigue", "Accumulated Fatigue", "#5B83D7"),),
        primary_key="accumulatedFatigue",
        min_y_max=2.0,
    ),
    "eeg_quality": TimeSeriesGraphSpec(
        graph_id="eeg_quality",
        title="EEG Quality",
        series=(GraphSeriesSpec("eegQuality", "EEG Quality", "#5B83D7"),),
        primary_key="eegQuality",
        fixed_y_range=(0.0, 100.0),
        min_y_max=100.0,
    ),
}


class _ElapsedAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session_start = time.monotonic()

    def set_session_start(self, t: float):
        self._session_start = float(t)

    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            elapsed = max(0.0, float(value) - self._session_start)
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            labels.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        return labels


class _MetricBarCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = {
            "Attention": 0.0,
            "Relaxation": 0.0,
            "Cognitive Load": 0.0,
            "Cognitive Control": 0.0,
        }
        self._bar_colors = {
            "Attention": "#5B83D7",
            "Relaxation": "#E08B52",
            "Cognitive Load": "#CB555C",
            "Cognitive Control": "#5CAD6A",
        }
        self.setMinimumHeight(360)

    def set_values(self, values: dict[str, float]):
        for key in list(self._values):
            value = values.get(key, self._values[key])
            self._values[key] = float(np.clip(value, 0.0, 100.0))
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(_PLOT_BG))

        bounds = self.rect().adjusted(18, 18, -18, -18)
        plot_rect = QRectF(bounds.left() + 120, bounds.top() + 18, bounds.width() - 140, bounds.height() - 36)

        painter.setPen(QPen(QColor("#4A5065"), 1))
        for tick in range(0, 101, 10):
            ratio = tick / 100.0
            x = plot_rect.left() + (plot_rect.width() * ratio)
            painter.drawLine(int(x), int(plot_rect.top()), int(x), int(plot_rect.bottom()))
            painter.drawText(QRectF(x - 12, plot_rect.bottom() + 4, 24, 18), Qt.AlignCenter, str(tick))

        row_names = list(self._values.keys())
        row_height = plot_rect.height() / max(1, len(row_names))
        for index, name in enumerate(row_names):
            top = plot_rect.top() + (row_height * index)
            center_y = top + (row_height * 0.5)
            painter.setPen(QColor(TEXT_PRIMARY))
            painter.drawText(
                QRectF(bounds.left(), center_y - 14, 110, 28),
                Qt.AlignRight | Qt.AlignVCenter,
                name,
            )
            bar_width = plot_rect.width() * (self._values[name] / 100.0)
            bar_rect = QRectF(plot_rect.left(), top + 6, max(0.0, bar_width), row_height - 12)
            painter.fillRect(bar_rect, QColor(self._bar_colors[name]))


class CognitiveStatesWindow(QWidget):
    window_closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Cognitive States")
        self.resize(900, 540)
        self.setStyleSheet(f"background: {BG_PRIMARY};")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(f"background: {_HEADER_BG};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        title = QLabel("Cognitive States")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY};")
        close_btn = QPushButton("×")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(28, 24)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_PRIMARY}; border: none; font-size: 18px; }}"
            f"QPushButton:hover {{ color: #FFFFFF; }}"
        )
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        root.addWidget(header)

        body = QFrame()
        body.setStyleSheet(f"background: {_PLOT_BG}; border: 1px solid {BORDER_SUBTLE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(10)
        title_lbl = QLabel("Cognitive States")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY};")
        body_layout.addWidget(title_lbl)
        self._canvas = _MetricBarCanvas()
        body_layout.addWidget(self._canvas, stretch=1)
        root.addWidget(body, stretch=1)

    def set_bar_values(self, values: dict[str, float]):
        self._canvas.set_values(values)

    def closeEvent(self, event):  # noqa: N802 - Qt API
        self.window_closed.emit()
        super().closeEvent(event)


class TimeSeriesGraphWindow(QWidget):
    window_closed = Signal()

    def __init__(self, spec: TimeSeriesGraphSpec, parent=None):
        super().__init__(parent, Qt.Window)
        self._spec = spec
        self._session_start = time.monotonic()
        self._history: dict[str, list[tuple[float, float]]] = {}
        self._references: dict[str, float | None] = {}
        self.setWindowTitle(spec.title)
        self.resize(900, 620)
        self.setStyleSheet(f"background: {BG_PRIMARY};")
        self._build_ui()
        self.set_time_scale("1 min")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(f"background: {_HEADER_BG};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        self._header_title = QLabel(self._spec.title)
        self._header_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY};")
        close_btn = QPushButton("×")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(28, 24)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_PRIMARY}; border: none; font-size: 18px; }}"
            f"QPushButton:hover {{ color: #FFFFFF; }}"
        )
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(self._header_title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        root.addWidget(header)

        body = QFrame()
        body.setStyleSheet(f"background: {_PLOT_BG}; border: 1px solid {BORDER_SUBTLE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(6)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(8)
        self._scale_badge = QLabel("1 min")
        self._scale_badge.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY};")
        self._span_label = QLabel("Span: 60 sec")
        self._span_label.setAlignment(Qt.AlignCenter)
        self._span_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY};")
        time_label = QLabel("Time Scale")
        time_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY};")
        self._scale_combo = QComboBox()
        self._scale_combo.addItems(list(_TIME_SCALE_OPTIONS.keys()))
        self._scale_combo.setStyleSheet(
            f"QComboBox {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; padding: 4px 8px; }}"
        )
        self._scale_combo.currentTextChanged.connect(self.set_time_scale)
        controls_row.addWidget(self._scale_badge)
        controls_row.addStretch()
        controls_row.addWidget(self._span_label)
        controls_row.addStretch()
        controls_row.addWidget(time_label)
        controls_row.addWidget(self._scale_combo)
        body_layout.addLayout(controls_row)

        self._summary_label = QLabel("Waiting for live values")
        self._summary_label.setAlignment(Qt.AlignCenter)
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {_SUMMARY_GOLD};")
        body_layout.addWidget(self._summary_label)

        axis = _ElapsedAxisItem(orientation="bottom")
        axis.set_session_start(self._session_start)
        self._plot = pg.PlotWidget(axisItems={"bottom": axis})
        self._time_axis = axis
        self._plot.setBackground(_PLOT_BG)
        self._plot.showGrid(x=True, y=True, alpha=0.12)
        self._plot.getPlotItem().setMenuEnabled(False)
        self._plot.getViewBox().setMouseEnabled(x=False, y=False)
        self._plot.getPlotItem().getAxis("top").hide()
        self._plot.getPlotItem().getAxis("right").hide()
        self._plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#727991"))
        self._plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen(TEXT_PRIMARY))
        self._plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#727991"))
        self._plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen(TEXT_PRIMARY))
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._legend = self._plot.addLegend(offset=(10, 12))
        if self._legend is not None:
            self._legend.setBrush(pg.mkBrush(QColor(_LEGEND_BG)))
            self._legend.setPen(pg.mkPen(BORDER_SUBTLE))
        body_layout.addWidget(self._plot, stretch=1)
        root.addWidget(body, stretch=1)

        self._curves: dict[str, pg.PlotDataItem] = {}
        for series in self._spec.series:
            pen = pg.mkPen(series.color, width=1.6)
            brush = QColor(series.color)
            brush.setAlpha(55)
            curve = self._plot.plot(
                pen=pen,
                name=series.label,
                fillLevel=0,
                brush=pg.mkBrush(brush),
            )
            self._curves[series.key] = curve

        self._baseline_line = pg.InfiniteLine(
            angle=0,
            pen=pg.mkPen(_BASELINE_COLOR, width=1.2),
        )
        self._lower_threshold_line = pg.InfiniteLine(
            angle=0,
            pen=pg.mkPen(_THRESHOLD_COLOR, width=1.2),
        )
        self._upper_threshold_line = pg.InfiniteLine(
            angle=0,
            pen=pg.mkPen(_THRESHOLD_COLOR, width=1.2),
        )
        self._plot.addItem(self._baseline_line)
        self._plot.addItem(self._lower_threshold_line)
        self._plot.addItem(self._upper_threshold_line)
        self._baseline_line.hide()
        self._lower_threshold_line.hide()
        self._upper_threshold_line.hide()

        if self._spec.baseline_key:
            self._legend.addItem(pg.PlotDataItem(pen=pg.mkPen(_BASELINE_COLOR, width=1.2)), f"{self._spec.title} Baseline")
        if self._spec.show_threshold_band:
            self._legend.addItem(pg.PlotDataItem(pen=pg.mkPen(_THRESHOLD_COLOR, width=1.2)), "-20%")
            self._legend.addItem(pg.PlotDataItem(pen=pg.mkPen(_THRESHOLD_COLOR, width=1.2)), "+20%")

    def set_session_start(self, start_monotonic: float):
        self._session_start = float(start_monotonic)
        self._time_axis.set_session_start(self._session_start)
        self._refresh_plot()

    def set_time_scale(self, label: str):
        if label not in _TIME_SCALE_OPTIONS:
            label = "1 min"
        blocker = self._scale_combo.blockSignals(True)
        self._scale_combo.setCurrentText(label)
        self._scale_combo.blockSignals(blocker)
        span_seconds = int(_TIME_SCALE_OPTIONS[label])
        self._scale_badge.setText(label)
        self._span_label.setText(f"Span: {span_seconds} sec")
        self._refresh_plot()

    def set_history_data(self, history: dict[str, list[tuple[float, float]]], references: dict[str, float | None] | None = None):
        self._history = {
            key: list(values or [])
            for key, values in (history or {}).items()
        }
        self._references = dict(references or {})
        self._refresh_plot()

    def closeEvent(self, event):  # noqa: N802 - Qt API
        self.window_closed.emit()
        super().closeEvent(event)

    def _refresh_plot(self):
        span_seconds = _TIME_SCALE_OPTIONS.get(self._scale_combo.currentText(), 60.0)
        latest_points = [
            points[-1][0]
            for points in self._history.values()
            if points
        ]
        now = max(latest_points) if latest_points else time.monotonic()
        start = max(self._session_start, now - span_seconds)
        end = max(start + span_seconds, now)

        y_values: list[float] = []
        latest_values: dict[str, float] = {}
        has_visible_data = False
        for series in self._spec.series:
            points = self._history.get(series.key, [])
            visible = [(ts, value) for ts, value in points if ts >= start]
            if visible:
                has_visible_data = True
                x = np.asarray([ts for ts, _ in visible], dtype=float)
                y = np.asarray([value for _, value in visible], dtype=float)
                self._curves[series.key].setData(x, y)
                y_values.extend(float(v) for v in y)
                latest_values[series.key] = float(y[-1])
            else:
                self._curves[series.key].setData([], [])

        baseline = None
        if self._spec.baseline_key:
            raw_baseline = self._references.get(self._spec.baseline_key)
            if raw_baseline is not None:
                try:
                    baseline = float(raw_baseline)
                except (TypeError, ValueError):
                    baseline = None

        if baseline is not None and np.isfinite(baseline):
            self._baseline_line.setPos(baseline)
            self._baseline_line.show()
            y_values.append(baseline)
            if self._spec.show_threshold_band:
                lower = baseline * 0.8
                upper = baseline * 1.2
                self._lower_threshold_line.setPos(lower)
                self._upper_threshold_line.setPos(upper)
                self._lower_threshold_line.show()
                self._upper_threshold_line.show()
                y_values.extend([lower, upper])
            else:
                self._lower_threshold_line.hide()
                self._upper_threshold_line.hide()
        else:
            self._baseline_line.hide()
            self._lower_threshold_line.hide()
            self._upper_threshold_line.hide()

        self._plot.setXRange(start, end, padding=0)
        if self._spec.fixed_y_range is not None:
            self._plot.setYRange(self._spec.fixed_y_range[0], self._spec.fixed_y_range[1], padding=0)
        else:
            max_y = max(y_values) if y_values else 0.0
            target_y = max(float(self._spec.min_y_max), max_y * 1.15 if max_y > 0 else self._spec.min_y_max)
            self._plot.setYRange(0.0, target_y, padding=0)

        self._summary_label.setText(self._summary_text(latest_values, baseline, has_visible_data))
        self._summary_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: "
            f"{_SUMMARY_GOLD if self._spec.baseline_key or self._spec.graph_id == 'frequency_peaks' else _SUMMARY_LIGHT};"
        )

    def _summary_text(self, latest_values: dict[str, float], baseline: float | None, has_visible_data: bool) -> str:
        if self._spec.graph_id == "frequency_peaks":
            alpha = latest_values.get("alpha_peak", 0.0)
            beta = latest_values.get("beta_peak", 0.0)
            theta = latest_values.get("theta_peak", 0.0)
            return f"Alpha peak: {alpha:.1f} Hz Beta peak: {beta:.1f} Hz Theta peak: {theta:.1f} Hz"

        primary_key = self._spec.primary_key or (self._spec.series[0].key if self._spec.series else "")
        primary_value = latest_values.get(primary_key)
        if primary_value is None:
            if has_visible_data:
                return "Waiting for live values"
            if baseline is not None and np.isfinite(baseline):
                return f"{self._spec.title} Baseline: {baseline:.3f}\nWaiting for live values"
            return "Baseline not ready" if self._spec.baseline_key else "Waiting for live values"

        if baseline is not None and np.isfinite(baseline):
            return f"{self._spec.title}: {primary_value:.3f}\n{self._spec.title} Baseline: {baseline:.3f}"
        if self._spec.baseline_key:
            return f"{self._spec.title}: {primary_value:.3f}\nBaseline not ready"
        if has_visible_data:
            return f"{self._spec.title}: {primary_value:.3f}"
        return "Waiting for live values"


def graph_spec(graph_id: str) -> TimeSeriesGraphSpec | None:
    return GRAPH_SPECS.get(graph_id)
