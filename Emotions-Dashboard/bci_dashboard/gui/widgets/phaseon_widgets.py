"""
Widgets used by the in-app Phaseon page.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from utils.config import ACCENT_GREEN, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


def _format_resistance(value) -> str:
    if value in (None, "", False):
        return "--"
    try:
        kohm = float(value) / 1000.0
    except (TypeError, ValueError):
        return "--"
    return f"{kohm:.0f} kΩ"


def _contact_state(value) -> tuple[str, str]:
    if value in (None, "", False):
        return "Unknown", "#6b7280"
    try:
        kohm = float(value) / 1000.0
    except (TypeError, ValueError):
        return "Unknown", "#6b7280"
    if kohm <= 800:
        return "Good", "#3fd68a"
    if kohm <= 1800:
        return "Fair", "#f6c15e"
    return "Poor", "#ef5350"


class PhaseonCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: #11141a; border: 1px solid {BORDER_SUBTLE}; border-radius: 26px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT_SECONDARY};")
        layout.addWidget(self._title_lbl)


class MetricMeterCard(PhaseonCard):
    def __init__(self, parent=None):
        super().__init__("Attention / Relaxation", parent)
        layout = self.layout()
        self._dominant_lbl = QLabel("Balanced")
        self._dominant_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(self._dominant_lbl)

        self._attention_value = QLabel("Attention 0.0")
        self._attention_value.setStyleSheet("font-size: 14px; color: #9dd8ff;")
        layout.addWidget(self._attention_value)
        self._attention_bar = QProgressBar()
        self._attention_bar.setRange(0, 100)
        self._attention_bar.setTextVisible(False)
        self._attention_bar.setStyleSheet(
            "QProgressBar { background: #1c2230; border: none; border-radius: 8px; min-height: 12px; }"
            "QProgressBar::chunk { background: #37c9ff; border-radius: 8px; }"
        )
        layout.addWidget(self._attention_bar)

        self._relax_value = QLabel("Relaxation 0.0")
        self._relax_value.setStyleSheet(f"font-size: 14px; color: {ACCENT_GREEN};")
        layout.addWidget(self._relax_value)
        self._relax_bar = QProgressBar()
        self._relax_bar.setRange(0, 100)
        self._relax_bar.setTextVisible(False)
        self._relax_bar.setStyleSheet(
            "QProgressBar { background: #1c2230; border: none; border-radius: 8px; min-height: 12px; }"
            f"QProgressBar::chunk {{ background: {ACCENT_GREEN}; border-radius: 8px; }}"
        )
        layout.addWidget(self._relax_bar)
        layout.addStretch()

    def set_metrics(self, attention: float, relaxation: float, dominant_state: str):
        self._dominant_lbl.setText(str(dominant_state or "Balanced"))
        self._attention_value.setText(f"Attention {attention:.1f}")
        self._relax_value.setText(f"Relaxation {relaxation:.1f}")
        self._attention_bar.setValue(int(round(max(0.0, min(100.0, attention)))))
        self._relax_bar.setValue(int(round(max(0.0, min(100.0, relaxation)))))


class StatusSummaryCard(PhaseonCard):
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        layout = self.layout()
        self.value_label = QLabel("--")
        self.value_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)
        layout.addStretch()


class ResistanceGridWidget(PhaseonCard):
    CHANNELS = ("O1", "T3", "T4", "O2")

    def __init__(self, parent=None):
        super().__init__("Contact / Resistance", parent)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.layout().addLayout(grid)
        self._cells = {}
        for index, channel in enumerate(self.CHANNELS):
            cell = QFrame()
            cell.setStyleSheet(
                f"QFrame {{ background: #171c24; border: 1px solid {BORDER_SUBTLE}; border-radius: 18px; }}"
            )
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(12, 12, 12, 12)
            cell_layout.setSpacing(4)
            name_lbl = QLabel(channel)
            name_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
            state_lbl = QLabel("Unknown")
            state_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
            value_lbl = QLabel("--")
            value_lbl.setStyleSheet("font-size: 15px; color: #c9d4e4;")
            cell_layout.addWidget(name_lbl)
            cell_layout.addWidget(state_lbl)
            cell_layout.addWidget(value_lbl)
            grid.addWidget(cell, index // 2, index % 2)
            self._cells[channel] = {"frame": cell, "state": state_lbl, "value": value_lbl}
        self.layout().addStretch()

    def set_resistances(self, values: Mapping | None):
        values = dict(values or {})
        for channel, widgets in self._cells.items():
            state_text, colour = _contact_state(values.get(channel))
            widgets["state"].setText(state_text)
            widgets["state"].setStyleSheet(f"font-size: 13px; color: {colour};")
            widgets["value"].setText(_format_resistance(values.get(channel)))


class LineTrendWidget(PhaseonCard):
    def __init__(self, title: str, lines: Sequence[tuple[str, str]], max_points: int = 120, parent=None):
        super().__init__(title, parent)
        self._max_points = max_points
        self._lines = [(name, QColor(color)) for name, color in lines]
        self._buffers = {name: deque(maxlen=max_points) for name, _ in lines}
        legend = QHBoxLayout()
        legend.setContentsMargins(0, 0, 0, 0)
        legend.setSpacing(12)
        for name, color in self._lines:
            lbl = QLabel(name)
            lbl.setStyleSheet(f"font-size: 12px; color: {color.name()};")
            legend.addWidget(lbl)
        legend.addStretch()
        self.layout().addLayout(legend)
        self._plot = _TrendCanvas(self._buffers, self._lines)
        self._plot.setMinimumHeight(180)
        self.layout().addWidget(self._plot)

    def append_points(self, values: Mapping[str, float]):
        for name, _color in self._lines:
            self._buffers[name].append(float(values.get(name, 0.0)))
        self._plot.update()


class _TrendCanvas(QWidget):
    def __init__(self, buffers, lines, parent=None):
        super().__init__(parent)
        self._buffers = buffers
        self._lines = lines
        self.setMinimumHeight(160)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1016"))

        bounds = self.rect().adjusted(10, 10, -10, -10)
        painter.setPen(QPen(QColor("#2b3342"), 1))
        for ratio in (0.25, 0.5, 0.75):
            y = bounds.top() + bounds.height() * ratio
            painter.drawLine(bounds.left(), int(y), bounds.right(), int(y))

        all_values = []
        for name, _color in self._lines:
            all_values.extend(self._buffers[name])
        if not all_values:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(bounds, Qt.AlignCenter, "Waiting for live values")
            return

        values = np.asarray(all_values, dtype=float)
        span = max(1.0, float(np.max(values) - np.min(values)))
        lower = float(np.min(values)) - span * 0.1
        upper = float(np.max(values)) + span * 0.1
        height = max(1.0, upper - lower)

        for name, color in self._lines:
            series = list(self._buffers[name])
            if len(series) < 2:
                continue
            painter.setPen(QPen(color, 2))
            path = QPainterPath()
            step_x = bounds.width() / max(1, len(series) - 1)
            for index, value in enumerate(series):
                x = bounds.left() + step_x * index
                y_ratio = (float(value) - lower) / height
                y = bounds.bottom() - (bounds.height() * y_ratio)
                point = QPointF(x, y)
                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            painter.drawPath(path)


class RawSignalWidget(PhaseonCard):
    def __init__(self, parent=None):
        super().__init__("Raw EEG", parent)
        self._buffers: dict[str, deque] = {}
        self._max_points = 900
        self._plot = _RawSignalCanvas(self._buffers)
        self._plot.setMinimumHeight(260)
        self.layout().addWidget(self._plot)

    def ingest_payload(self, payload):
        channels = {}
        if isinstance(payload, Mapping):
            nested = payload.get("channels")
            if isinstance(nested, Mapping):
                channels = nested
            else:
                channels = {
                    key: value
                    for key, value in payload.items()
                    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
                }
        if not isinstance(channels, Mapping) or not channels:
            return

        seen = []
        for name, samples in channels.items():
            if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes, bytearray)):
                continue
            series = self._buffers.setdefault(str(name), deque(maxlen=self._max_points))
            try:
                for value in samples:
                    series.append(float(value))
            except (TypeError, ValueError):
                continue
            seen.append(str(name))

        stale = [name for name in self._buffers if name not in seen]
        for name in stale:
            del self._buffers[name]
        self._plot.update()


class _RawSignalCanvas(QWidget):
    def __init__(self, buffers, parent=None):
        super().__init__(parent)
        self._buffers = buffers
        self._palette = ["#2fe0ff", "#8cf4b1", "#ffca62", "#ff8aa0", "#9fb6ff"]

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1016"))
        bounds = self.rect().adjusted(16, 18, -16, -18)

        if not self._buffers:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(bounds, Qt.AlignCenter, "Waiting for EEG stream")
            return

        channel_names = list(self._buffers.keys())
        track_gap = bounds.height() / max(1, len(channel_names))
        for index, name in enumerate(channel_names):
            mid_y = bounds.top() + track_gap * (index + 0.5)
            painter.setPen(QPen(QColor("#253145"), 1))
            painter.drawLine(bounds.left(), int(mid_y), bounds.right(), int(mid_y))
            painter.setPen(QColor(TEXT_PRIMARY))
            painter.drawText(QRectF(bounds.left(), mid_y - 16, 70, 20), Qt.AlignLeft, name)

            series = np.asarray(list(self._buffers[name]), dtype=float)
            if series.size < 2:
                continue
            centered = series - float(np.mean(series))
            scale = max(20.0, float(np.percentile(np.abs(centered), 95)))
            scale = min(scale, 250.0)
            usable_width = max(1.0, bounds.width() - 84.0)
            start_x = bounds.left() + 84.0
            step_x = usable_width / max(1, centered.size - 1)
            amplitude = max(12.0, track_gap * 0.32)
            painter.setPen(QPen(QColor(self._palette[index % len(self._palette)]), 1.5))
            path = QPainterPath()
            for sample_index, value in enumerate(centered):
                x = start_x + (step_x * sample_index)
                y = mid_y - (float(value) / scale) * amplitude
                point = QPointF(x, y)
                if sample_index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            painter.drawPath(path)
