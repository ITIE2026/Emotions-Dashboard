"""
ElectrodeTable - compact per-channel EEG status table with live traces.

The table buffers raw EEG in microvolts, keeps the hot path lightweight, and
renders a stable centered view with gentler scaling.
"""
from __future__ import annotations

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

from utils.config import (
    BG_CARD,
    BORDER_SUBTLE,
    EEG_FILTER_SFREQ,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


_DEFAULT_CHANNEL_NAMES = {0: "O1-T3", 1: "O2-T4"}
_TRACE_COLOR = "#00E5FF"
_NAME_BG = "#5567A9"
_GRAPH_BG = "#131624"
_WINDOW_SEC = 6.0
_MAX_SAMPLES = 4000
_MIN_HALF_RANGE_UV = 35.0
_MAX_HALF_RANGE_UV = 250.0
_MIN_PLOT_POINTS = 600
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
    """Live EEG summary table used by the dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_start = time.time()
        self._sdk_time_origin = None
        self._filter_enabled = False
        self._display_filter = None
        self._sample_rate_hz = float(EEG_FILTER_SFREQ)
        self._channel_names = dict(_DEFAULT_CHANNEL_NAMES)
        self._raw_buffers = {index: deque(maxlen=_MAX_SAMPLES) for index in _DEFAULT_CHANNEL_NAMES}
        self._display_buffers = {index: deque(maxlen=_MAX_SAMPLES) for index in _DEFAULT_CHANNEL_NAMES}
        self._time_bufs = {index: deque(maxlen=_MAX_SAMPLES) for index in _DEFAULT_CHANNEL_NAMES}
        self._avg_uv = {name: 0.0 for name in self._channel_names.values()}
        self._has_artifacts = {}
        self._plot_half_ranges = {index: 70.0 for index in _DEFAULT_CHANNEL_NAMES}
        self._dirty = False
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
            ("Average uV", 96),
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
        ordered_indexes = list(_DEFAULT_CHANNEL_NAMES.keys())
        last_index = ordered_indexes[-1]
        for index in ordered_indexes:
            row_widget = QWidget()
            row_widget.setStyleSheet(f"background: {_ROW_BG}; border: none;")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(6, 4, 6, 4)
            row.setSpacing(4)

            name_lbl = QLabel(self._channel_names[index])
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
                "font-size: 11px; color: #69F0AE; background: transparent; border: none;"
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
            plot.setFixedHeight(82 if index == last_index else 72)
            plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            plot.getPlotItem().setMenuEnabled(False)
            plot.getViewBox().setMouseEnabled(x=False, y=False)
            plot.setDownsampling(auto=True, mode="peak")
            plot.setClipToView(True)
            plot.showGrid(x=True, y=True, alpha=0.12)
            plot.getPlotItem().getAxis("left").hide()
            plot.getPlotItem().getAxis("top").hide()
            plot.getPlotItem().getAxis("right").hide()
            bottom_axis = plot.getPlotItem().getAxis("bottom")
            bottom_axis.setPen(pg.mkPen("#444"))
            bottom_axis.setTextPen(pg.mkPen("#888"))
            if index != last_index:
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

            self._rows[index] = {
                "name_lbl": name_lbl,
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

    def set_display_filter(self, enabled: bool, filter_func=None):
        previous_enabled = self._filter_enabled
        previous_filter = self._display_filter
        self._filter_enabled = bool(enabled)
        self._display_filter = filter_func
        if hasattr(filter_func, "reset"):
            filter_func.reset()
        if previous_enabled != self._filter_enabled or previous_filter is not filter_func:
            self._rebuild_display_buffers()
        self._dirty = True

    def set_sample_rate(self, sample_rate_hz: float | None):
        try:
            value = float(sample_rate_hz)
        except (TypeError, ValueError):
            value = EEG_FILTER_SFREQ
        if not np.isfinite(value) or value <= 0.0:
            value = EEG_FILTER_SFREQ
        self._sample_rate_hz = float(np.clip(value, 50.0, 1000.0))
        self._rebuild_display_buffers()
        self._dirty = True

    def set_channel_names(self, channel_names=None):
        if not channel_names:
            channel_names = list(_DEFAULT_CHANNEL_NAMES.values())
        names = [self._normalize_channel_name(name) for name in channel_names]
        if len(names) < len(self._rows):
            for index in range(len(names), len(self._rows)):
                names.append(_DEFAULT_CHANNEL_NAMES.get(index, f"Ch {index + 1}"))

        self._channel_names = {
            index: names[index] if index < len(names) else _DEFAULT_CHANNEL_NAMES.get(index, f"Ch {index + 1}")
            for index in self._rows
        }
        self._avg_uv = {name: 0.0 for name in self._channel_names.values()}
        self._has_artifacts = {}
        for index, row in self._rows.items():
            row["name_lbl"].setText(self._channel_names[index])
        self._dirty = True

    def add_eeg_data(self, eeg_timed_data):
        """Buffer microvolt-scaled EEG samples from the SDK packet."""
        try:
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()
            if n_channels <= 0 or n_samples <= 0:
                return

            sample_times = []
            now = time.time()
            fallback_rate = max(self._sample_rate_hz, 1.0)
            for sample_idx in range(n_samples):
                try:
                    sample_times.append(float(eeg_timed_data.get_timestamp(sample_idx)) / 1000.0)
                except Exception:
                    sample_times.append(now - (n_samples - 1 - sample_idx) / fallback_rate)

            if sample_times and self._sdk_time_origin is None:
                self._sdk_time_origin = sample_times[0]
            if self._sdk_time_origin is None:
                self._sdk_time_origin = now

            mapped_times = [
                self._session_start + (sample_time - self._sdk_time_origin)
                for sample_time in sample_times
            ]

            for ch_idx in range(min(n_channels, len(self._rows))):
                raw_chunk = np.asarray(
                    [
                        float(eeg_timed_data.get_raw_value(ch_idx, sample_idx))
                        for sample_idx in range(n_samples)
                    ],
                    dtype=float,
                )
                raw_chunk_uv = self._to_microvolts(raw_chunk)
                display_source_chunk = raw_chunk_uv
                if hasattr(eeg_timed_data, "get_processed_value"):
                    try:
                        processed_chunk = np.asarray(
                            [
                                float(eeg_timed_data.get_processed_value(ch_idx, sample_idx))
                                for sample_idx in range(n_samples)
                            ],
                            dtype=float,
                        )
                        processed_chunk_uv = self._to_microvolts(processed_chunk)
                        if self._prefer_processed_signal(processed_chunk_uv):
                            display_source_chunk = processed_chunk_uv
                    except Exception:
                        pass

                filtered_chunk = display_source_chunk
                if self._filter_enabled and self._display_filter is not None:
                    try:
                        if hasattr(self._display_filter, "process_chunk"):
                            filtered_chunk = np.asarray(
                                self._display_filter.process_chunk(
                                    self._channel_names[ch_idx],
                                    display_source_chunk,
                                    self._sample_rate_hz,
                                ),
                                dtype=float,
                            )
                        else:
                            filtered_chunk = np.asarray(
                                self._display_filter(display_source_chunk, sample_rate=self._sample_rate_hz),
                                dtype=float,
                            )
                    except TypeError:
                        filtered_chunk = np.asarray(self._display_filter(display_source_chunk), dtype=float)
                    except Exception:
                        filtered_chunk = display_source_chunk

                for sample_idx, mapped_time in enumerate(mapped_times):
                    self._raw_buffers[ch_idx].append(float(raw_chunk_uv[sample_idx]))
                    self._display_buffers[ch_idx].append(float(filtered_chunk[sample_idx]))
                    self._time_bufs[ch_idx].append(mapped_time)
            self._dirty = True
        except Exception:
            pass

    def update_eeg(self, eeg_timed_data):
        """Compatibility wrapper for older callers."""
        self.add_eeg_data(eeg_timed_data)

    def has_data(self) -> bool:
        return any(bool(times) for times in self._time_bufs.values())

    def has_pending_refresh(self) -> bool:
        return self._dirty

    def refresh(self):
        """Redraw both channel traces from the rolling buffers."""
        latest_times = [times[-1] for times in self._time_bufs.values() if times]
        if not latest_times:
            for row in self._rows.values():
                row["curve"].setData([], [])
            self._dirty = False
            return

        t_end = max(latest_times)
        t_start = t_end - _WINDOW_SEC

        for ch_idx, row in self._rows.items():
            times = self._time_bufs[ch_idx]
            samples = self._display_buffers[ch_idx]
            if not times or not samples:
                row["curve"].setData([], [])
                row["plot"].setXRange(t_start, t_end, padding=0)
                row["plot"].setYRange(-_MIN_HALF_RANGE_UV, _MIN_HALF_RANGE_UV, padding=0)
                continue

            t = np.asarray(times, dtype=float)
            y = np.asarray(samples, dtype=float)
            visible_mask = t >= t_start
            if not np.any(visible_mask):
                row["curve"].setData([], [])
                continue

            visible_t = t[visible_mask]
            visible_y = y[visible_mask]
            baseline = float(np.median(visible_y))
            centered_visible = visible_y - baseline
            avg_uv = float(np.mean(np.abs(centered_visible))) if centered_visible.size else 0.0

            target_half_range = max(
                float(np.percentile(np.abs(centered_visible), 98)) * 1.35 if centered_visible.size else 0.0,
                _MIN_HALF_RANGE_UV,
            )
            previous_half_range = self._plot_half_ranges.get(ch_idx, target_half_range)
            half_range = (0.82 * previous_half_range) + (0.18 * target_half_range)
            half_range = float(np.clip(half_range, _MIN_HALF_RANGE_UV, _MAX_HALF_RANGE_UV))
            self._plot_half_ranges[ch_idx] = half_range

            centered_all = y - baseline
            plot_limit = half_range * 2.5
            centered_all = np.clip(centered_all, -plot_limit, plot_limit)
            plot_t, plot_y = self._downsample_for_plot(t, centered_all)

            row["curve"].setData(plot_t, plot_y)
            row["plot"].setXRange(t_start, t_end, padding=0)
            row["plot"].setYRange(-half_range, half_range, padding=0)
            display_name = self._channel_names[ch_idx]
            self._avg_uv[display_name] = avg_uv
            row["avg_lbl"].setText(f"{avg_uv:.3f}")

        self._dirty = False

    def clear(self):
        self._sdk_time_origin = None
        self._avg_uv = {name: 0.0 for name in self._channel_names.values()}
        self._has_artifacts.clear()
        self._plot_half_ranges = {index: 70.0 for index in self._rows}
        if hasattr(self._display_filter, "reset"):
            self._display_filter.reset()
        self._dirty = False
        for ch_idx, row in self._rows.items():
            self._raw_buffers[ch_idx].clear()
            self._display_buffers[ch_idx].clear()
            self._time_bufs[ch_idx].clear()
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
            for ch_idx in range(min(n, len(self._rows))):
                has_art = bool(artifacts.get_artifacts_by_channel(ch_idx))
                label = "Yes" if has_art else "No"
                colour = "#EF5350" if has_art else "#69F0AE"
                display_name = self._channel_names[ch_idx]
                self._has_artifacts[display_name] = has_art
                self._rows[ch_idx]["art_lbl"].setText(label)
                self._rows[ch_idx]["art_lbl"].setStyleSheet(
                    f"font-size: 11px; color: {colour}; background: transparent; border: none;"
                )
                self._dirty = True
        except Exception:
            pass

    @staticmethod
    def _normalize_channel_name(name) -> str:
        text = str(name or "").strip()
        if not text:
            return "Unknown"
        upper = text.upper().replace(" ", "")
        alias_map = {
            "O1T3": "O1-T3",
            "O1-T3": "O1-T3",
            "01-T3": "O1-T3",
            "O2T4": "O2-T4",
            "O2-T4": "O2-T4",
            "02-T4": "O2-T4",
        }
        return alias_map.get(upper, text)

    @staticmethod
    def _prefer_processed_signal(processed_chunk: np.ndarray) -> bool:
        if processed_chunk.size == 0:
            return False
        if not np.all(np.isfinite(processed_chunk)):
            return False
        return bool(np.nanmax(np.abs(processed_chunk)) > 0.01)

    @staticmethod
    def _to_microvolts(samples: np.ndarray) -> np.ndarray:
        if samples.size == 0:
            return samples.astype(float)
        finite = np.abs(samples[np.isfinite(samples)])
        if finite.size == 0:
            return samples.astype(float)
        max_abs = float(np.max(finite))
        if max_abs <= 0.01:
            return samples * 1_000_000.0
        return samples.astype(float)

    @staticmethod
    def _downsample_for_plot(times: np.ndarray, values: np.ndarray):
        if times.size <= _MIN_PLOT_POINTS:
            return times, values
        stride = max(int(np.ceil(times.size / _MIN_PLOT_POINTS)), 1)
        return times[::stride], values[::stride]

    def _rebuild_display_buffers(self):
        for samples in self._display_buffers.values():
            samples.clear()
        if hasattr(self._display_filter, "reset"):
            self._display_filter.reset()
        for ch_idx in self._rows:
            raw = np.asarray(self._raw_buffers[ch_idx], dtype=float)
            if raw.size == 0:
                continue
            filtered = raw
            if self._filter_enabled and self._display_filter is not None:
                try:
                    if hasattr(self._display_filter, "process_chunk"):
                        filtered = np.asarray(
                            self._display_filter.process_chunk(
                                self._channel_names[ch_idx],
                                raw,
                                self._sample_rate_hz,
                            ),
                            dtype=float,
                        )
                    else:
                        filtered = np.asarray(
                            self._display_filter(raw, sample_rate=self._sample_rate_hz),
                            dtype=float,
                        )
                except TypeError:
                    filtered = np.asarray(self._display_filter(raw), dtype=float)
                except Exception:
                    filtered = raw
            self._display_buffers[ch_idx].extend(float(value) for value in filtered)
        self._dirty = True
