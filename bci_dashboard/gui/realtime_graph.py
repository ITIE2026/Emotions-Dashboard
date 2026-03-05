"""
RealtimeGraph – PyQtGraph widget matching the reference UI style.

  • Dark plot background, no axis labels/ticks in 1m mode
  • Real HH:MM time ticks on X axis in 15m mode
  • Live percentage labels at the right end of each curve
  • Dot markers at curve tips
"""
from collections import deque
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from utils.config import (
    GRAPH_1MIN_POINTS,
    GRAPH_15MIN_POINTS,
    COLOR_FOCUS,
    COLOR_COGNITIVE,
    COLOR_RELAXATION,
)

_BG = "#161616"


class _TimeAxisItem(pg.AxisItem):
    """X axis that shows HH:MM from Unix timestamps."""
    def tickStrings(self, values, scale, spacing):
        import datetime
        result = []
        for v in values:
            try:
                result.append(datetime.datetime.fromtimestamp(v).strftime("%H:%M"))
            except Exception:
                result.append("")
        return result


class RealtimeGraph(QWidget):
    """Call ``add_data(focus, cognitive, relaxation)`` every second."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "1m"
        self._max_points = GRAPH_1MIN_POINTS

        self._focus_buf = deque(maxlen=self._max_points)
        self._cog_buf   = deque(maxlen=self._max_points)
        self._relax_buf = deque(maxlen=self._max_points)
        self._time_buf  = deque(maxlen=self._max_points)   # Unix timestamps

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1m / 15m toggle
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 8, 8, 4)
        self._btn_1m  = QPushButton("1m")
        self._btn_15m = QPushButton("15m")
        for btn in (self._btn_1m, self._btn_15m):
            btn.setCheckable(True)
            btn.setMinimumWidth(64)
            btn.setMinimumHeight(30)
            btn.setStyleSheet(
                "QPushButton{border-radius:14px;background:#2a2a2a;color:#aaa;"
                "font-size:13px;padding:4px 16px;border:none;}"
                "QPushButton:checked{background:#3c3c3c;color:#fff;}"
            )
        self._btn_1m.setChecked(True)
        self._btn_1m.clicked.connect(lambda: self._set_mode("1m"))
        self._btn_15m.clicked.connect(lambda: self._set_mode("15m"))
        btn_row.addStretch()
        btn_row.addWidget(self._btn_1m)
        btn_row.addWidget(self._btn_15m)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Build the plot (time axis used in 15m mode)
        self._time_axis = _TimeAxisItem(orientation="bottom")
        self._plot = pg.PlotWidget(axisItems={"bottom": self._time_axis})
        self._plot.setBackground(_BG)

        # Hide axes by default (1m mode)
        self._plot.getPlotItem().getAxis("left").hide()
        self._plot.getPlotItem().getAxis("top").hide()
        self._plot.getPlotItem().getAxis("right").hide()
        self._time_axis.hide()          # hidden in 1m mode

        self._plot.showGrid(x=False, y=False)
        self._plot.getPlotItem().setMenuEnabled(False)
        self._plot.getViewBox().setMouseEnabled(x=False, y=False)
        self._plot.setYRange(0, 100, padding=0.05)
        self._plot.getViewBox().disableAutoRange()

        # Dashed 50% reference line
        ref = pg.InfiniteLine(
            pos=50, angle=0,
            pen=pg.mkPen(color="#333333", style=Qt.PenStyle.DashLine, width=1),
        )
        self._plot.addItem(ref)

        # Curves
        self._focus_curve = self._plot.plot(pen=pg.mkPen(COLOR_FOCUS,     width=2.5))
        self._cog_curve   = self._plot.plot(pen=pg.mkPen(COLOR_COGNITIVE, width=2.5))
        self._relax_curve = self._plot.plot(pen=pg.mkPen(COLOR_RELAXATION,width=2.5))

        # Tip dots
        self._focus_dot = pg.ScatterPlotItem(size=10, brush=pg.mkBrush(COLOR_FOCUS),      pen=pg.mkPen(None))
        self._cog_dot   = pg.ScatterPlotItem(size=10, brush=pg.mkBrush(COLOR_COGNITIVE),  pen=pg.mkPen(None))
        self._relax_dot = pg.ScatterPlotItem(size=10, brush=pg.mkBrush(COLOR_RELAXATION), pen=pg.mkPen(None))
        for d in (self._focus_dot, self._cog_dot, self._relax_dot):
            self._plot.addItem(d)

        # Tip labels
        lf = QFont(); lf.setPointSize(11); lf.setBold(True)
        self._focus_lbl = pg.TextItem("", color=COLOR_FOCUS,      anchor=(0, 0.5))
        self._cog_lbl   = pg.TextItem("", color=COLOR_COGNITIVE,  anchor=(0, 0.5))
        self._relax_lbl = pg.TextItem("", color=COLOR_RELAXATION, anchor=(0, 0.5))
        for lbl in (self._focus_lbl, self._cog_lbl, self._relax_lbl):
            lbl.setFont(lf)
            self._plot.addItem(lbl)

        layout.addWidget(self._plot, stretch=1)

    # ── Public API ────────────────────────────────────────────────────
    def add_data(self, focus: float, cognitive: float, relaxation: float):
        now = time.time()
        self._focus_buf.append(float(focus))
        self._cog_buf.append(float(cognitive))
        self._relax_buf.append(float(relaxation))
        self._time_buf.append(now)
        self._refresh()

    def clear(self):
        for buf in (self._focus_buf, self._cog_buf, self._relax_buf, self._time_buf):
            buf.clear()
        self._refresh()

    # ── Mode toggle ───────────────────────────────────────────────────
    def _set_mode(self, mode: str):
        self._mode = mode
        new_max = GRAPH_1MIN_POINTS if mode == "1m" else GRAPH_15MIN_POINTS
        self._max_points = new_max
        self._btn_1m.setChecked(mode == "1m")
        self._btn_15m.setChecked(mode == "15m")

        self._focus_buf = deque(self._focus_buf, maxlen=new_max)
        self._cog_buf   = deque(self._cog_buf,   maxlen=new_max)
        self._relax_buf = deque(self._relax_buf, maxlen=new_max)
        self._time_buf  = deque(self._time_buf,  maxlen=new_max)

        # Show time axis only in 15m mode
        if mode == "15m":
            self._time_axis.show()
            self._plot.getPlotItem().getAxis("bottom").show()
        else:
            self._time_axis.hide()

        self._refresh()

    # ── Redraw ────────────────────────────────────────────────────────
    def _refresh(self):
        if not self._time_buf:
            self._focus_curve.setData([], [])
            self._cog_curve.setData([], [])
            self._relax_curve.setData([], [])
            return

        t  = np.array(self._time_buf,  dtype=float)
        fa = np.array(self._focus_buf, dtype=float)
        ca = np.array(self._cog_buf,   dtype=float)
        ra = np.array(self._relax_buf, dtype=float)

        self._focus_curve.setData(t, fa)
        self._cog_curve.setData(t,   ca)
        self._relax_curve.setData(t, ra)

        # X window: last N seconds visible
        t_end   = t[-1]
        t_start = t_end - self._max_points  # max_points == seconds

        # Extra right margin for the labels (~5 % of window width)
        margin = self._max_points * 0.05
        self._plot.setXRange(t_start, t_end + margin, padding=0)
        self._plot.setYRange(0, 100, padding=0.05)

        # Tip dots & labels
        xp = t[-1]
        self._focus_dot.setData([xp], [fa[-1]])
        self._cog_dot.setData([xp],   [ca[-1]])
        self._relax_dot.setData([xp], [ra[-1]])

        lx = xp + margin * 0.3
        self._focus_lbl.setPos(lx, fa[-1]);  self._focus_lbl.setText(f"{fa[-1]:.0f}%")
        self._cog_lbl.setPos(lx,   ca[-1]);  self._cog_lbl.setText(f"{ca[-1]:.0f}%")
        self._relax_lbl.setPos(lx, ra[-1]);  self._relax_lbl.setText(f"{ra[-1]:.0f}%")



