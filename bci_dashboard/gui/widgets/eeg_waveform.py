"""
EEGWaveform – live scrolling EEG signal traces per bipolar channel.

Shows O1-T3 and O2-T4 waveforms in a stacked plot with time axis.
"""
from collections import deque
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from utils.config import TEXT_SECONDARY

_BG = "#131624"
_WINDOW_SEC = 6        # visible time window
_MAX_SAMPLES = 1500    # ~6 s at 250 Hz


class _TimeAxisItem(pg.AxisItem):
    """X axis showing elapsed session time HH:MM:SS."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session_start = time.time()

    def set_session_start(self, t):
        self._session_start = t

    def tickStrings(self, values, scale, spacing):
        result = []
        for v in values:
            elapsed = v - self._session_start
            if elapsed < 0:
                elapsed = 0
            m, s = divmod(int(elapsed), 60)
            h, m = divmod(m, 60)
            result.append(f"{h:02d}:{m:02d}:{s:02d}")
        return result


class EEGWaveform(QWidget):
    """Feed with ``add_eeg_data(eeg_timed_data)``."""

    CHANNEL_COLORS = {
        "O1-T3": "#4FC3F7",   # light blue
        "O2-T4": "#81C784",   # green
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_start = time.time()
        self._buffers = {}
        self._time_bufs = {}
        for ch in self.CHANNEL_COLORS:
            self._buffers[ch] = deque(maxlen=_MAX_SAMPLES)
            self._time_bufs[ch] = deque(maxlen=_MAX_SAMPLES)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._plots = {}
        self._curves = {}

        for i, (ch_name, colour) in enumerate(self.CHANNEL_COLORS.items()):
            time_axis = _TimeAxisItem(orientation="bottom")
            time_axis.set_session_start(self._session_start)

            pw = pg.PlotWidget(axisItems={"bottom": time_axis})
            pw.setBackground(_BG)
            pw.setFixedHeight(80)
            pw.getPlotItem().setMenuEnabled(False)
            pw.getViewBox().setMouseEnabled(x=False, y=False)
            pw.showGrid(x=False, y=False)

            # Channel label
            label = pg.TextItem(ch_name, color=colour, anchor=(0, 0))
            label.setPos(0, 0)
            pw.addItem(label)

            # Left axis styling
            pw.getPlotItem().getAxis("left").setPen(pg.mkPen("#444"))
            pw.getPlotItem().getAxis("left").setTextPen(pg.mkPen("#666"))
            pw.getPlotItem().getAxis("left").setWidth(40)
            pw.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#444"))
            pw.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen("#888"))

            curve = pw.plot(pen=pg.mkPen(colour, width=1.5))
            self._plots[ch_name] = pw
            self._curves[ch_name] = curve
            self._plots[ch_name]._time_axis = time_axis
            self._plots[ch_name]._ch_label = label

            layout.addWidget(pw)

    def set_session_start(self, t=None):
        self._session_start = t or time.time()
        for pw in self._plots.values():
            pw._time_axis.set_session_start(self._session_start)

    def add_eeg_data(self, eeg_timed_data):
        """Process EEGTimedData from the SDK.

        The SDK provides processed samples per channel.  For bipolar mode
        the channel names are like 'O1-T3', 'O2-T4'.
        """
        try:
            now = time.time()
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()

            for ch_idx in range(n_channels):
                ch_name = eeg_timed_data.get_channel_name(ch_idx)
                if ch_name not in self._buffers:
                    continue
                for s_idx in range(n_samples):
                    val = eeg_timed_data.get_processed_sample(ch_idx, s_idx)
                    self._buffers[ch_name].append(float(val))
                    # Approximate timestamp from sample position
                    t = now - (n_samples - 1 - s_idx) / 250.0
                    self._time_bufs[ch_name].append(t)
        except Exception:
            pass

    def refresh(self):
        """Redraw all channels. Call from a timer (e.g., 10 Hz)."""
        for ch_name, curve in self._curves.items():
            buf = self._buffers[ch_name]
            tbuf = self._time_bufs[ch_name]
            if not buf:
                continue
            t = np.array(tbuf, dtype=float)
            y = np.array(buf, dtype=float)
            curve.setData(t, y)

            # Set visible window
            t_end = t[-1]
            t_start = t_end - _WINDOW_SEC
            self._plots[ch_name].setXRange(t_start, t_end, padding=0)

            # Auto-range Y
            visible = y[t >= t_start]
            if len(visible) > 0:
                ymin, ymax = float(np.min(visible)), float(np.max(visible))
                margin = max((ymax - ymin) * 0.1, 5)
                self._plots[ch_name].setYRange(ymin - margin, ymax + margin, padding=0)

    def clear(self):
        for ch in self._buffers:
            self._buffers[ch].clear()
            self._time_bufs[ch].clear()
