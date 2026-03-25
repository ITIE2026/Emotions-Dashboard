"""
SpectrumChart – PSD (Power Spectral Density) frequency-domain chart.

Displays a filled-area spectrum plot (0–35 Hz) with colour-coded
frequency band regions and band-coloured spectrum segments, matching the
Capsule reference app more closely.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from utils.config import (
    TEXT_SECONDARY,
    COLOR_DELTA, COLOR_THETA, COLOR_ALPHA, COLOR_SMR, COLOR_BETA,
    BAND_DELTA, BAND_THETA, BAND_ALPHA, BAND_SMR, BAND_BETA,
)

_BG = "#131624"
_MAX_FREQ_HZ = 35.0
_DEFAULT_Y_MAX = 100.0
_BAND_SPECS = (
    ("delta", "Delta", BAND_DELTA, COLOR_DELTA),
    ("theta", "Theta", BAND_THETA, COLOR_THETA),
    ("alpha", "Alpha", BAND_ALPHA, COLOR_ALPHA),
    ("smr", "SMR", BAND_SMR, COLOR_SMR),
    ("beta", "Beta", BAND_BETA, COLOR_BETA),
)


class SpectrumChart(QWidget):
    """Feed with ``update_psd(freqs, powers)``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title
        title = QLabel("Spectrum")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_SECONDARY}; "
            f"background: transparent; padding: 4px;"
        )
        layout.addWidget(title)

        # Legend row
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(8, 0, 8, 0)
        legend_row.addStretch()
        for _band_key, name, _band_range, colour in _BAND_SPECS:
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {colour}; font-size: 10px; background: transparent;")
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
            legend_row.addWidget(dot)
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # Plot widget
        self._plot = pg.PlotWidget()
        self._plot.setBackground(_BG)
        self._plot.setLabel("bottom", "Hz")
        self._plot.setLabel("left", "µV²")
        self._plot.getPlotItem().getAxis("left").setStyle(showValues=True)
        self._plot.getPlotItem().getAxis("bottom").setStyle(showValues=True)
        self._plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#555"))
        self._plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#555"))
        self._plot.getPlotItem().getAxis("left").setTextPen(pg.mkPen("#888"))
        self._plot.getPlotItem().getAxis("bottom").setTextPen(pg.mkPen("#888"))
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.setXRange(0, _MAX_FREQ_HZ, padding=0)
        self._plot.setYRange(0, _DEFAULT_Y_MAX, padding=0.02)
        self._plot.getPlotItem().setMenuEnabled(False)
        self._plot.getViewBox().setMouseEnabled(x=False, y=False)

        # Band shading regions
        for _band_key, _name, (lo, hi), colour in _BAND_SPECS:
            region = pg.LinearRegionItem(
                values=[lo, hi], orientation="vertical", movable=False,
                brush=pg.mkBrush(QColor(colour).red(), QColor(colour).green(),
                                 QColor(colour).blue(), 8),
                pen=pg.mkPen(None),
            )
            region.setZValue(-20)
            self._plot.addItem(region)

        base_curve_colour = QColor("#7fd9ff")
        self._main_curve = self._plot.plot(
            pen=pg.mkPen(
                color=(base_curve_colour.red(), base_curve_colour.green(), base_curve_colour.blue(), 170),
                width=1.6,
            ),
        )
        self._main_curve.setZValue(0)
        self._main_zero_curve = self._plot.plot([], [], pen=pg.mkPen(None))
        self._main_fill = pg.FillBetweenItem(
            self._main_curve,
            self._main_zero_curve,
            brush=pg.mkBrush(
                base_curve_colour.red(),
                base_curve_colour.green(),
                base_curve_colour.blue(),
                28,
            ),
        )
        self._main_fill.setZValue(-5)
        self._plot.addItem(self._main_fill)

        self._band_items = {}
        for band_key, _name, _band_range, colour in _BAND_SPECS:
            curve = self._plot.plot(
                pen=pg.mkPen(color=colour, width=2),
            )
            curve.setZValue(3)
            self._band_items[band_key] = {
                "range": _band_range,
                "curve": curve,
            }

        layout.addWidget(self._plot, stretch=1)

    @staticmethod
    def _slice_band_segment(freqs, powers, lo: float, hi: float, include_hi: bool):
        if freqs.size == 0:
            return np.array([], dtype=float), np.array([], dtype=float)

        if include_hi:
            mask = (freqs >= lo) & (freqs <= hi)
        else:
            mask = (freqs >= lo) & (freqs < hi)

        seg_freqs = freqs[mask]
        seg_powers = powers[mask]

        if freqs[0] < lo < freqs[-1]:
            lo_power = float(np.interp(lo, freqs, powers))
            if seg_freqs.size == 0 or seg_freqs[0] > lo:
                seg_freqs = np.insert(seg_freqs, 0, lo)
                seg_powers = np.insert(seg_powers, 0, lo_power)

        if freqs[0] < hi < freqs[-1]:
            hi_power = float(np.interp(hi, freqs, powers))
            if seg_freqs.size == 0 or seg_freqs[-1] < hi:
                seg_freqs = np.append(seg_freqs, hi)
                seg_powers = np.append(seg_powers, hi_power)

        return seg_freqs, seg_powers

    def _clear_segments(self):
        empty = np.array([], dtype=float)
        self._main_curve.setData(empty, empty)
        self._main_zero_curve.setData(empty, empty)
        for item in self._band_items.values():
            item["curve"].setData(empty, empty)
        self._plot.setYRange(0, _DEFAULT_Y_MAX, padding=0.02)

    def update_psd(self, freqs, powers):
        """Update the spectrum display.

        Args:
            freqs: array-like of frequency bins (Hz).
            powers: array-like of power values (µV²).
        """
        freqs = np.asarray(freqs, dtype=float)
        powers = np.asarray(powers, dtype=float)

        # Limit to 0-35 Hz for display
        mask = freqs <= _MAX_FREQ_HZ
        freqs = freqs[mask]
        powers = powers[mask]

        if len(freqs) == 0:
            self._clear_segments()
            return

        self._main_curve.setData(freqs, powers)
        self._main_zero_curve.setData(freqs, np.zeros_like(powers))

        for index, (band_key, _name, (lo, hi), _colour) in enumerate(_BAND_SPECS):
            seg_freqs, seg_powers = self._slice_band_segment(
                freqs,
                powers,
                lo,
                hi,
                include_hi=(index == len(_BAND_SPECS) - 1),
            )
            self._band_items[band_key]["curve"].setData(seg_freqs, seg_powers)

        # Auto-scale Y
        y_max = float(np.max(powers)) * 1.15
        if y_max > 0:
            self._plot.setYRange(0, y_max, padding=0.02)
        else:
            self._plot.setYRange(0, _DEFAULT_Y_MAX, padding=0.02)
