"""
ElectrodeTable – compact per-channel EEG status table with live traces.

Shows electrode name, artifact state, average microvolt amplitude, and
an embedded scrolling EEG trace for the two bipolar channels.
"""
from collections import deque
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.config import BG_CARD, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


_CHANNEL_COLORS = {
    "O1-T3": "#4FC3F7",
    "O2-T4": "#81C784",
}
_TRACE_COLOR = "#00E5FF"
_NAME_BG = "#5567A9"

_CHANNEL_NAMES = {0: "O1-T3", 1: "O2-T4"}
_GRAPH_BG = "#131624"
_WINDOW_SEC = 6.0
_MAX_SAMPLES = 1500
_MIN_HALF_RANGE_UV = 15.0
_HEADER_BG = "#5E70B7"
_ROW_BG = "#2A2E48"


class _SessionAxisItem(pg.AxisItem):
    """Bottom axis showing elapsed session time."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session_start = time.time()

    def set_session_start(self, t: float):
        self._session_start = t

    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            elapsed = max(0.0, value - self._session_start)
            hours, rem = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(rem, 60)
            labels.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        return labels


class ElectrodeTable(QWidget):
    """
    Feed with:
      - ``add_eeg_data(eeg_timed_data)``  – buffers live EEG samples
      - ``refresh()``                     – redraws the mini traces
      - ``update_artifacts(artifacts)``   – sets artifact flags
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_start = time.time()
        self._sdk_time_origin = None
        self._buffers = {
            name: deque(maxlen=_MAX_SAMPLES) for name in _CHANNEL_COLORS
        }
        self._time_bufs = {
            name: deque(maxlen=_MAX_SAMPLES) for name in _CHANNEL_COLORS
        }
        self._avg_uv = {}
        self._has_artifacts = {}
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)

        trace_header = QHBoxLayout()
        trace_header.setContentsMargins(0, 0, 0, 4)
        trace_header.setSpacing(0)
        trace_spacer = QWidget()
        trace_spacer.setFixedWidth(270)
        trace_label = QLabel("Hz")
        trace_label.setAlignment(Qt.AlignCenter)
        trace_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )
        trace_header.addWidget(trace_spacer)
        trace_header.addWidget(trace_label, stretch=1)
        layout.addLayout(trace_header)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 6)
        header.setSpacing(4)
        header_widget = QWidget()
        header_widget.setStyleSheet(
            f"background: {_HEADER_BG}; border: none; border-radius: 0px;"
        )
        header_widget.setFixedHeight(28)
        header_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_inner = QHBoxLayout(header_widget)
        header_inner.setContentsMargins(6, 0, 6, 0)
        header_inner.setSpacing(4)
        for text, width in [
            ("Electrode", 90),
            ("Artifacts", 72),
            ("Average µV", 96),
            ("EEG Signal", 0),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: bold; color: {TEXT_PRIMARY}; "
                f"background: transparent; border: none; padding: 2px;"
            )
            if width:
                lbl.setFixedWidth(width)
            header_inner.addWidget(lbl, stretch=(0 if width else 1))
        layout.addWidget(header_widget)

        self._rows = {}
        channel_names = list(_CHANNEL_COLORS.keys())
        last_channel = channel_names[-1]
        for ch_name, colour in _CHANNEL_COLORS.items():
            row_widget = QWidget()
            row_widget.setStyleSheet(
                f"background: {_ROW_BG}; border: none;"
            )
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(6, 4, 6, 4)
            row.setSpacing(4)

            name_lbl = QLabel(ch_name)
            name_lbl.setFixedWidth(90)
            name_lbl.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY}; "
                f"background: {_NAME_BG}; border: none; border-radius: 4px; "
                f"padding: 4px 6px;"
            )

            art_lbl = QLabel("No")
            art_lbl.setFixedWidth(72)
            art_lbl.setAlignment(Qt.AlignCenter)
            art_lbl.setStyleSheet(
                f"font-size: 11px; color: #69F0AE; background: transparent; border: none;"
            )

            avg_lbl = QLabel("0.000")
            avg_lbl.setFixedWidth(96)
            avg_lbl.setAlignment(Qt.AlignCenter)
            avg_lbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_PRIMARY}; background: transparent; border: none;"
            )

            axis = _SessionAxisItem(orientation="bottom")
            axis.set_session_start(self._session_start)
            plot = pg.PlotWidget(axisItems={"bottom": axis})
            plot.setBackground(_GRAPH_BG)
            plot.setFixedHeight(82 if ch_name == last_channel else 72)
            plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            plot.getPlotItem().setMenuEnabled(False)
            plot.getViewBox().setMouseEnabled(x=False, y=False)
            plot.showGrid(x=True, y=True, alpha=0.12)
            plot.getPlotItem().getAxis("left").hide()
            plot.getPlotItem().getAxis("top").hide()
            plot.getPlotItem().getAxis("right").hide()
            bottom_axis = plot.getPlotItem().getAxis("bottom")
            bottom_axis.setPen(pg.mkPen("#444"))
            bottom_axis.setTextPen(pg.mkPen("#888"))
            if ch_name != last_channel:
                bottom_axis.hide()
            plot.setXRange(self._session_start - _WINDOW_SEC, self._session_start, padding=0)
            plot.setYRange(-_MIN_HALF_RANGE_UV, _MIN_HALF_RANGE_UV, padding=0)

            baseline = pg.InfiniteLine(
                pos=0,
                angle=0,
                pen=pg.mkPen(color="#334055", width=1),
            )
            plot.addItem(baseline)
            curve = plot.plot(pen=pg.mkPen(_TRACE_COLOR, width=1.4))

            row.addWidget(name_lbl)
            row.addWidget(art_lbl)
            row.addWidget(avg_lbl)
            row.addWidget(plot, stretch=1)

            self._rows[ch_name] = {
                "art_lbl": art_lbl,
                "avg_lbl": avg_lbl,
                "plot": plot,
                "curve": curve,
                "axis": axis,
            }
            layout.addWidget(row_widget)

    def set_session_start(self, t=None):
        self._session_start = float(t or time.time())
        self._sdk_time_origin = None
        for row in self._rows.values():
            row["axis"].set_session_start(self._session_start)

    def add_eeg_data(self, eeg_timed_data):
        """Buffer microvolt-scaled EEG samples from the SDK packet."""
        try:
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()
            if n_channels <= 0 or n_samples <= 0:
                return

            sample_times = []
            now = time.time()
            for sample_idx in range(n_samples):
                try:
                    sample_times.append(float(eeg_timed_data.get_timestamp(sample_idx)) / 1000.0)
                except Exception:
                    sample_times.append(now - (n_samples - 1 - sample_idx) / 250.0)

            if sample_times and self._sdk_time_origin is None:
                self._sdk_time_origin = sample_times[0]

            if self._sdk_time_origin is None:
                self._sdk_time_origin = now

            mapped_times = [
                self._session_start + (sample_time - self._sdk_time_origin)
                for sample_time in sample_times
            ]

            for ch_idx in range(n_channels):
                ch_name = _CHANNEL_NAMES.get(ch_idx)
                if ch_name not in self._rows:
                    continue

                for sample_idx in range(n_samples):
                    raw_value = float(eeg_timed_data.get_raw_value(ch_idx, sample_idx))
                    value_uv = raw_value * 1_000_000.0
                    self._buffers[ch_name].append(value_uv)
                    self._time_bufs[ch_name].append(mapped_times[sample_idx])
        except Exception:
            pass

    def update_eeg(self, eeg_timed_data):
        """Compatibility wrapper for older callers."""
        self.add_eeg_data(eeg_timed_data)

    def has_data(self) -> bool:
        return any(bool(times) for times in self._time_bufs.values())

    def refresh(self):
        """Redraw both channel traces from the rolling buffers."""
        latest_times = [
            times[-1]
            for times in self._time_bufs.values()
            if times
        ]
        if not latest_times:
            for row in self._rows.values():
                row["curve"].setData([], [])
            return

        t_end = max(latest_times)
        t_start = t_end - _WINDOW_SEC

        for ch_name, row in self._rows.items():
            times = self._time_bufs[ch_name]
            samples = self._buffers[ch_name]
            if not times or not samples:
                row["curve"].setData([], [])
                row["plot"].setXRange(t_start, t_end, padding=0)
                row["plot"].setYRange(-_MIN_HALF_RANGE_UV, _MIN_HALF_RANGE_UV, padding=0)
                continue

            t = np.asarray(times, dtype=float)
            y = np.asarray(samples, dtype=float)
            visible = y[t >= t_start]
            if visible.size == 0:
                display = y
                half_range = _MIN_HALF_RANGE_UV
                avg_uv = 0.0
            else:
                center = float(np.median(visible))
                display = y - center
                display_visible = display[t >= t_start]
                if display_visible.size == 0:
                    display_visible = display
                clip_level = max(
                    float(np.percentile(np.abs(display_visible), 99)),
                    _MIN_HALF_RANGE_UV,
                )
                display = np.clip(display, -clip_level * 1.5, clip_level * 1.5)
                display_visible = np.clip(
                    display_visible, -clip_level * 1.5, clip_level * 1.5
                )
                avg_uv = float(np.mean(np.abs(display_visible)))
                half_range = max(
                    float(np.percentile(np.abs(display_visible), 97)) * 1.25,
                    _MIN_HALF_RANGE_UV,
                )
            row["curve"].setData(t, display)
            row["plot"].setXRange(t_start, t_end, padding=0)
            self._avg_uv[ch_name] = avg_uv
            row["avg_lbl"].setText(f"{avg_uv:.3f}")
            row["plot"].setYRange(-half_range, half_range, padding=0)

    def clear(self):
        self._sdk_time_origin = None
        self._avg_uv.clear()
        self._has_artifacts.clear()
        for ch_name, row in self._rows.items():
            self._buffers[ch_name].clear()
            self._time_bufs[ch_name].clear()
            row["avg_lbl"].setText("0.000")
            row["art_lbl"].setText("No")
            row["art_lbl"].setStyleSheet(
                "font-size: 11px; color: #69F0AE; background: transparent; border: none;"
            )
            row["curve"].setData([], [])
            row["plot"].setYRange(-_MIN_HALF_RANGE_UV, _MIN_HALF_RANGE_UV, padding=0)
            row["plot"].setXRange(self._session_start - _WINDOW_SEC, self._session_start, padding=0)

    def update_artifacts(self, artifacts):
        """Update artifact flags from EEGArtifacts object."""
        try:
            n = artifacts.get_channels_count()
            for ch_idx in range(n):
                ch_name = _CHANNEL_NAMES.get(ch_idx)
                if ch_name not in self._rows:
                    continue
                has_art = bool(artifacts.get_artifacts_by_channel(ch_idx))
                self._has_artifacts[ch_name] = has_art
                label = "Yes" if has_art else "No"
                colour = "#EF5350" if has_art else "#69F0AE"
                self._rows[ch_name]["art_lbl"].setText(label)
                self._rows[ch_name]["art_lbl"].setStyleSheet(
                    f"font-size: 11px; color: {colour}; background: transparent; border: none;"
                )
        except Exception:
            pass
