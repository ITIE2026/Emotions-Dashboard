"""
SpectrumChart – PSD (Power Spectral Density) frequency-domain chart.

Displays a filled-area spectrum plot (0–35 Hz) with colour-coded
frequency band regions and a legend, matching the Capsule reference app.
"""
from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient

from utils.config import (
    BG_CARD, BORDER_SUBTLE, TEXT_SECONDARY,
    COLOR_DELTA, COLOR_THETA, COLOR_ALPHA, COLOR_SMR, COLOR_BETA,
    BAND_DELTA, BAND_THETA, BAND_ALPHA, BAND_SMR, BAND_BETA,
)

_BG = "#131624"


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
        for name, colour in [
            ("Delta", COLOR_DELTA), ("Theta", COLOR_THETA),
            ("Alpha", COLOR_ALPHA), ("SMR", COLOR_SMR), ("Beta", COLOR_BETA),
        ]:
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
        self._plot.setXRange(0, 35, padding=0)
        self._plot.setYRange(0, 100, padding=0.02)
        self._plot.getPlotItem().setMenuEnabled(False)
        self._plot.getViewBox().setMouseEnabled(x=False, y=False)

        # Band shading regions
        for (lo, hi), colour in [
            (BAND_DELTA, COLOR_DELTA), (BAND_THETA, COLOR_THETA),
            (BAND_ALPHA, COLOR_ALPHA), (BAND_SMR, COLOR_SMR),
            (BAND_BETA, COLOR_BETA),
        ]:
            region = pg.LinearRegionItem(
                values=[lo, hi], orientation="vertical", movable=False,
                brush=pg.mkBrush(QColor(colour).red(), QColor(colour).green(),
                                 QColor(colour).blue(), 20),
                pen=pg.mkPen(None),
            )
            region.setZValue(-10)
            self._plot.addItem(region)

        # Main spectrum curve with fill
        self._curve = self._plot.plot(
            pen=pg.mkPen(color="#64B5F6", width=2),
        )
        self._fill = pg.FillBetweenItem(
            self._curve,
            self._plot.plot([0], [0], pen=pg.mkPen(None)),
            brush=pg.mkBrush(100, 181, 246, 40),
        )
        self._plot.addItem(self._fill)

        layout.addWidget(self._plot, stretch=1)

    def update_psd(self, freqs, powers):
        """Update the spectrum display.

        Args:
            freqs: array-like of frequency bins (Hz).
            powers: array-like of power values (µV²).
        """
        freqs = np.asarray(freqs, dtype=float)
        powers = np.asarray(powers, dtype=float)

        # Limit to 0-35 Hz for display
        mask = freqs <= 35
        freqs = freqs[mask]
        powers = powers[mask]

        if len(freqs) == 0:
            return

        self._curve.setData(freqs, powers)
        # Auto-scale Y to ~110% of max visible power
        y_max = max(float(np.max(powers)) * 1.1, 1.0)
        self._plot.setYRange(0, y_max, padding=0.02)

        # Update fill
        self._plot.removeItem(self._fill)
        zero_curve = self._plot.plot(freqs, np.zeros_like(powers), pen=pg.mkPen(None))
        self._fill = pg.FillBetweenItem(
            self._curve, zero_curve,
            brush=pg.mkBrush(100, 181, 246, 40),
        )
        self._plot.addItem(self._fill)
