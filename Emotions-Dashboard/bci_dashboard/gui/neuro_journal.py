"""
Neuro Journal — Emotion Timeline & Diary.

Standalone pop-up window.  Continuously records brain-state metrics
(attention, relaxation, stress, cognitive-control, self-control) while
open and visualises them as a scrolling colour-coded heatmap timeline.

Features:
  • Live scrolling heatmap — every second of brain data colour-mapped
  • Activity tags — label what you're doing (work, meditate, game, …)
  • Moment annotations — add text notes at any point on the timeline
  • Session persistence — auto-saves to JSON, loads previous sessions
  • Export — save the full timeline as a PNG report
"""
from __future__ import annotations

import colorsys
import datetime
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QLinearGradient,
    QGuiApplication,
)
from PySide6.QtWidgets import (
    QWidget,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QScrollArea,
    QFileDialog,
    QInputDialog,
)

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JOURNAL_DIR = os.path.join(_APP_DIR, "sessions", "neuro_journal")
_HISTORY_FILE = os.path.join(_JOURNAL_DIR, "journal_sessions.json")

# ── Tuning ────────────────────────────────────────────────────────────
_TICK_MS = 200            # UI refresh rate (5 Hz)
_SAMPLE_INTERVAL = 1.0    # record one data point per second
_MAX_SAMPLES = 7200       # 2 hours max per session
_CELL_W = 6               # heatmap cell width (px)
_CELL_H = 28              # heatmap row height (px)
_TIMELINE_PAD = 60         # left padding for labels

# ── Metric definitions ────────────────────────────────────────────────
_METRICS = [
    ("attention",        "Focus",     "#00E676"),
    ("relaxation",       "Relax",     "#7C4DFF"),
    ("cognitiveLoad",    "Stress",    "#FF5252"),
    ("cognitiveControl", "Control",   "#4FC3F7"),
    ("selfControl",      "Self-Ctrl", "#FFD740"),
]
_METRIC_KEYS = [m[0] for m in _METRICS]

# ── Activity tags ─────────────────────────────────────────────────────
_ACTIVITY_PRESETS = [
    ("💻", "Working"),
    ("🧘", "Meditating"),
    ("🎮", "Gaming"),
    ("📖", "Reading"),
    ("🎵", "Listening"),
    ("💬", "Talking"),
    ("🏃", "Exercise"),
    ("😴", "Resting"),
]

# ── Colors ────────────────────────────────────────────────────────────
_BG = QColor(10, 10, 20)
_PANEL_BG = QColor(16, 18, 32)
_CARD_BG = QColor(20, 24, 45)
_BORDER = QColor(40, 50, 80)
_TEXT_DIM = QColor(120, 120, 140)
_TEXT_MED = QColor(180, 180, 200)
_TEXT_BRIGHT = QColor(230, 230, 245)
_MARKER_LINE = QColor(255, 255, 255, 60)


# ── Data structures ───────────────────────────────────────────────────
@dataclass
class TimelinePoint:
    t: float                 # monotonic timestamp (seconds since session start)
    wall: str                # wall-clock ISO string for display
    attention: float = 0.0
    relaxation: float = 0.0
    cognitiveLoad: float = 0.0
    cognitiveControl: float = 0.0
    selfControl: float = 0.0
    tag: str = ""            # current activity tag


@dataclass
class Annotation:
    t: float                 # time offset in session (seconds)
    wall: str
    text: str = ""


@dataclass
class JournalSession:
    session_id: str = ""
    start_wall: str = ""
    end_wall: str = ""
    duration_sec: float = 0.0
    points: list[TimelinePoint] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _value_to_color(value: float, base_hue_hex: str) -> QColor:
    """Map a 0-100 value to a color ranging from dark to bright."""
    base = QColor(base_hue_hex)
    h = base.hsvHueF()
    s = base.hsvSaturationF()
    # Lightness ramps from 0.08 (value=0) to 0.65 (value=100)
    v = 0.08 + (value / 100.0) * 0.57
    c = QColor.fromHsvF(h, s * 0.8 + (value / 100.0) * 0.2, v)
    return c


# ══════════════════════════════════════════════════════════════════════
#  Timeline Heatmap Widget
# ══════════════════════════════════════════════════════════════════════

class _TimelineCanvas(QWidget):
    """Custom-painted heatmap timeline of brain metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(len(_METRICS) * _CELL_H + 100)

        self._points: list[TimelinePoint] = []
        self._annotations: list[Annotation] = []
        self._hover_idx: int | None = None

        # Scroll offset (controlled by parent scroll area)
        self._scroll_x = 0

    def set_data(self, points: list[TimelinePoint], annotations: list[Annotation]):
        self._points = points
        self._annotations = annotations
        # Resize to fit content
        needed_w = _TIMELINE_PAD + len(points) * _CELL_W + 80
        self.setMinimumWidth(max(needed_w, 600))
        self.update()

    def paintEvent(self, _event):
        if not self._points:
            self._paint_empty()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), _BG)

        n = len(self._points)
        top_y = 40  # space for time axis
        row_h = _CELL_H

        # ── Row labels (left side) ────────────────────────────────────
        p.setFont(QFont("Consolas", 9, QFont.Bold))
        for ri, (key, label, color_hex) in enumerate(_METRICS):
            y = top_y + ri * row_h
            p.setPen(QColor(color_hex))
            p.drawText(QRectF(4, y, _TIMELINE_PAD - 8, row_h),
                       Qt.AlignVCenter | Qt.AlignRight, label)

        # ── Heatmap cells ─────────────────────────────────────────────
        for ci, pt in enumerate(self._points):
            x = _TIMELINE_PAD + ci * _CELL_W
            for ri, (key, label, color_hex) in enumerate(_METRICS):
                y = top_y + ri * row_h
                val = getattr(pt, key, 0.0)
                color = _value_to_color(val, color_hex)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRect(QRectF(x, y + 1, _CELL_W, row_h - 2))

        # ── Time axis (top) ───────────────────────────────────────────
        p.setFont(QFont("Consolas", 7))
        p.setPen(_TEXT_DIM)
        # Show a tick every 60 samples (1 minute)
        for ci in range(0, n, 60):
            x = _TIMELINE_PAD + ci * _CELL_W
            minutes = ci // 60
            label = f"{minutes}m"
            p.drawText(QRectF(x - 10, 2, 30, 16), Qt.AlignCenter, label)
            # Tick line
            p.setPen(QPen(QColor(60, 60, 80), 1))
            p.drawLine(int(x), 18, int(x), top_y + len(_METRICS) * row_h)
            p.setPen(_TEXT_DIM)

        # ── Activity tag bands ────────────────────────────────────────
        tag_y = top_y + len(_METRICS) * row_h + 4
        p.setFont(QFont("Consolas", 8))
        last_tag = ""
        tag_start_x = _TIMELINE_PAD
        for ci, pt in enumerate(self._points):
            x = _TIMELINE_PAD + ci * _CELL_W
            if pt.tag != last_tag or ci == n - 1:
                # Draw previous tag block
                if last_tag and ci > 0:
                    block_w = x - tag_start_x
                    p.setPen(Qt.NoPen)
                    tag_color = QColor(40, 50, 70)
                    p.setBrush(tag_color)
                    p.drawRoundedRect(QRectF(tag_start_x, tag_y, block_w, 20), 3, 3)
                    if block_w > 24:
                        p.setPen(_TEXT_MED)
                        p.drawText(QRectF(tag_start_x + 4, tag_y, block_w - 8, 20),
                                   Qt.AlignVCenter | Qt.AlignLeft, last_tag)
                tag_start_x = x
                last_tag = pt.tag

        # ── Annotations ───────────────────────────────────────────────
        ann_y = tag_y + 28
        p.setFont(QFont("Consolas", 8))
        for ann in self._annotations:
            # Find closest point index
            ci = min(int(ann.t), n - 1)
            x = _TIMELINE_PAD + ci * _CELL_W
            # Marker line
            p.setPen(QPen(_MARKER_LINE, 1, Qt.DashLine))
            p.drawLine(int(x), top_y, int(x), ann_y - 2)
            # Marker dot
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFD740"))
            p.drawEllipse(QPointF(x, ann_y + 6), 4, 4)
            # Text bubble
            p.setPen(_TEXT_BRIGHT)
            text_rect = QRectF(x + 6, ann_y - 2, 140, 16)
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, ann.text[:30])

        # ── Current position indicator ────────────────────────────────
        if n > 0:
            cx = _TIMELINE_PAD + (n - 1) * _CELL_W
            p.setPen(QPen(QColor("#00E676"), 2))
            p.drawLine(int(cx), top_y - 4, int(cx), top_y + len(_METRICS) * row_h + 4)

        # ── Legend at bottom ──────────────────────────────────────────
        legend_y = ann_y + 24
        p.setFont(QFont("Consolas", 8))
        legend_x = _TIMELINE_PAD
        for key, label, color_hex in _METRICS:
            # Color swatch
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color_hex))
            p.drawRoundedRect(QRectF(legend_x, legend_y, 10, 10), 2, 2)
            p.setPen(_TEXT_DIM)
            p.drawText(QRectF(legend_x + 14, legend_y - 1, 60, 14),
                       Qt.AlignVCenter | Qt.AlignLeft, label)
            legend_x += 80

        p.end()

    def _paint_empty(self):
        p = QPainter(self)
        p.fillRect(self.rect(), _BG)
        p.setPen(_TEXT_DIM)
        p.setFont(QFont("Consolas", 14))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "No data yet — connect headband and start recording")
        p.end()


# ══════════════════════════════════════════════════════════════════════
#  Summary Panel
# ══════════════════════════════════════════════════════════════════════

class _SummaryPanel(QWidget):
    """Shows session summary stats + mini bar charts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(140)
        self._stats: dict = {}

    def set_stats(self, stats: dict):
        self._stats = stats
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), _CARD_BG)

        if not self._stats:
            p.setPen(_TEXT_DIM)
            p.setFont(QFont("Consolas", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "Session summary will appear here")
            p.end()
            return

        # ── Duration + samples ────────────────────────────────────────
        p.setPen(_TEXT_BRIGHT)
        p.setFont(QFont("Consolas", 11, QFont.Bold))
        dur = self._stats.get("duration_min", 0)
        p.drawText(QRectF(16, 8, 200, 20), Qt.AlignLeft | Qt.AlignVCenter,
                    f"Duration: {dur:.1f} min")

        samples = self._stats.get("samples", 0)
        p.setFont(QFont("Consolas", 9))
        p.setPen(_TEXT_DIM)
        p.drawText(QRectF(220, 8, 200, 20), Qt.AlignLeft | Qt.AlignVCenter,
                    f"({samples} samples)")

        # ── Metric average bars ───────────────────────────────────────
        bar_y = 36
        bar_h = 16
        bar_max_w = max(80, (w - _TIMELINE_PAD - 100) / len(_METRICS))

        for i, (key, label, color_hex) in enumerate(_METRICS):
            x = 16 + i * (bar_max_w + 12)
            avg = self._stats.get(f"avg_{key}", 0)
            peak = self._stats.get(f"peak_{key}", 0)

            # Label
            p.setPen(QColor(color_hex))
            p.setFont(QFont("Consolas", 8, QFont.Bold))
            p.drawText(QRectF(x, bar_y, bar_max_w, 14),
                       Qt.AlignLeft | Qt.AlignVCenter, label)

            # Bar background
            by = bar_y + 16
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(30, 34, 55))
            p.drawRoundedRect(QRectF(x, by, bar_max_w, bar_h), 3, 3)

            # Bar fill
            fill_w = bar_max_w * avg / 100.0
            p.setBrush(QColor(color_hex))
            p.drawRoundedRect(QRectF(x, by, fill_w, bar_h), 3, 3)

            # Value text
            p.setPen(_TEXT_BRIGHT)
            p.setFont(QFont("Consolas", 8))
            p.drawText(QRectF(x, by, bar_max_w, bar_h),
                       Qt.AlignCenter, f"avg {avg:.0f}  peak {peak:.0f}")

        # ── Dominant state ────────────────────────────────────────────
        dom = self._stats.get("dominant", "—")
        p.setPen(_TEXT_MED)
        p.setFont(QFont("Consolas", 9))
        p.drawText(QRectF(16, bar_y + 50, w - 32, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"Dominant state: {dom}")

        # ── Tag breakdown ─────────────────────────────────────────────
        tags = self._stats.get("tags", {})
        if tags:
            tag_str = "  •  ".join(f"{t}: {c}s" for t, c in tags.items())
            p.drawText(QRectF(16, bar_y + 68, w - 32, 20),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"Activities: {tag_str}")

        p.end()


# ══════════════════════════════════════════════════════════════════════
#  History Panel (past sessions)
# ══════════════════════════════════════════════════════════════════════

class _HistoryPanel(QWidget):
    """Vertical list of past session summaries."""

    def __init__(self, on_load_session, parent=None):
        super().__init__(parent)
        self._sessions: list[dict] = []
        self._on_load = on_load_session
        self.setMinimumHeight(100)

    def set_sessions(self, sessions: list[dict]):
        self._sessions = sessions
        self.setMinimumHeight(max(100, len(sessions) * 46 + 20))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), _BG)

        if not self._sessions:
            p.setPen(_TEXT_DIM)
            p.setFont(QFont("Consolas", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "No past sessions")
            p.end()
            return

        p.setFont(QFont("Consolas", 9))
        y = 8
        for i, sess in enumerate(reversed(self._sessions[-20:])):
            rect = QRectF(8, y, self.width() - 16, 40)

            # Card background
            p.setPen(Qt.NoPen)
            p.setBrush(_CARD_BG)
            p.drawRoundedRect(rect, 6, 6)

            # Date + duration
            p.setPen(_TEXT_BRIGHT)
            p.setFont(QFont("Consolas", 9, QFont.Bold))
            date_str = sess.get("start_wall", "")[:16]
            dur = sess.get("duration_sec", 0) / 60.0
            p.drawText(QRectF(16, y + 4, 200, 16),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{date_str}  ({dur:.0f} min)")

            # Averages summary
            p.setPen(_TEXT_DIM)
            p.setFont(QFont("Consolas", 8))
            summary = sess.get("summary", {})
            avg_focus = summary.get("avg_attention", 0)
            avg_relax = summary.get("avg_relaxation", 0)
            avg_stress = summary.get("avg_cognitiveLoad", 0)
            p.drawText(QRectF(16, y + 20, 300, 14),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"Focus: {avg_focus:.0f}  Relax: {avg_relax:.0f}  Stress: {avg_stress:.0f}")

            y += 46

        p.end()

    def mousePressEvent(self, event):
        # Simple click-to-load: determine which session was clicked
        idx_from_top = int((event.position().y() - 8) / 46)
        reversed_sessions = list(reversed(self._sessions[-20:]))
        if 0 <= idx_from_top < len(reversed_sessions):
            self._on_load(reversed_sessions[idx_from_top])


# ══════════════════════════════════════════════════════════════════════
#  Main Neuro Journal Window
# ══════════════════════════════════════════════════════════════════════

class NeuroJournalWindow(QMainWindow):
    """Standalone pop-up window for BCI Neuro Journal / Emotion Timeline."""

    def __init__(self):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("📓  Neuro Journal — Emotion Timeline & Diary")
        self.setMinimumSize(1000, 700)
        self.resize(1300, 850)
        self.setStyleSheet("QMainWindow { background: #0A0A14; }")

        # Recording state
        self._recording = False
        self._session_start: float = 0.0
        self._last_sample_time: float = 0.0
        self._points: list[TimelinePoint] = []
        self._annotations: list[Annotation] = []
        self._current_tag: str = ""
        self._past_sessions: list[dict] = []

        # Latest raw metrics (updated by on_emotions)
        self._latest: dict = {}

        self._build_ui()
        self._load_history()

        # Refresh timer
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(52)
        top_bar.setStyleSheet("background: #12132a; border-bottom: 1px solid #222;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("📓 NEURO JOURNAL")
        title.setStyleSheet("color: #4FC3F7; font: bold 16px 'Consolas';")
        top_layout.addWidget(title)
        top_layout.addStretch()

        # Record button
        self._rec_btn = QPushButton("⏺  Start Recording")
        self._rec_btn.setCursor(Qt.PointingHandCursor)
        self._rec_btn.setStyleSheet(
            "QPushButton { background: #0D3320; color: #00E676; font: bold 12px 'Consolas'; "
            "padding: 8px 18px; border-radius: 6px; border: 1px solid #225533; }"
            "QPushButton:hover { background: #1A4430; }"
        )
        self._rec_btn.clicked.connect(self._toggle_recording)
        top_layout.addWidget(self._rec_btn)

        # Duration label
        self._dur_lbl = QLabel("00:00")
        self._dur_lbl.setStyleSheet("color: #888; font: bold 14px 'Consolas'; margin-left: 10px;")
        top_layout.addWidget(self._dur_lbl)

        main_layout.addWidget(top_bar)

        # ── Activity tag bar ─────────────────────────────────────────
        tag_bar = QWidget()
        tag_bar.setFixedHeight(42)
        tag_bar.setStyleSheet("background: #0E1020; border-bottom: 1px solid #1a1a2e;")
        tag_layout = QHBoxLayout(tag_bar)
        tag_layout.setContentsMargins(12, 4, 12, 4)

        tag_label = QLabel("Activity:")
        tag_label.setStyleSheet("color: #666; font: 10px 'Consolas';")
        tag_layout.addWidget(tag_label)

        self._tag_btns: list[QPushButton] = []
        for icon, name in _ACTIVITY_PRESETS:
            btn = QPushButton(f"{icon} {name}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { background: #1E2238; color: #aaa; font: 10px 'Consolas'; "
                "padding: 4px 10px; border-radius: 4px; border: 1px solid #333; }"
                "QPushButton:hover { background: #2A2E48; color: #ddd; }"
                "QPushButton:checked { background: #1A3A2A; color: #00E676; border-color: #00E676; }"
            )
            btn.clicked.connect(lambda checked, n=name: self._set_tag(n))
            self._tag_btns.append(btn)
            tag_layout.addWidget(btn)

        tag_layout.addStretch()

        # Annotate button
        ann_btn = QPushButton("📝 Add Note")
        ann_btn.setCursor(Qt.PointingHandCursor)
        ann_btn.setStyleSheet(
            "QPushButton { background: #2A2040; color: #FFD740; font: bold 10px 'Consolas'; "
            "padding: 4px 12px; border-radius: 4px; border: 1px solid #554420; }"
            "QPushButton:hover { background: #3A3050; }"
        )
        ann_btn.clicked.connect(self._add_annotation)
        tag_layout.addWidget(ann_btn)

        main_layout.addWidget(tag_bar)

        # ── Live metrics strip ────────────────────────────────────────
        self._metrics_strip = QWidget()
        self._metrics_strip.setFixedHeight(36)
        self._metrics_strip.setStyleSheet("background: #0A0C18;")
        metrics_layout = QHBoxLayout(self._metrics_strip)
        metrics_layout.setContentsMargins(12, 0, 12, 0)

        self._metric_labels: dict[str, QLabel] = {}
        for key, label, color in _METRICS:
            lbl = QLabel(f"{label}: --")
            lbl.setStyleSheet(f"color: {color}; font: bold 11px 'Consolas';")
            self._metric_labels[key] = lbl
            metrics_layout.addWidget(lbl)

        metrics_layout.addStretch()
        self._samples_lbl = QLabel("0 samples")
        self._samples_lbl.setStyleSheet("color: #555; font: 9px 'Consolas';")
        metrics_layout.addWidget(self._samples_lbl)

        main_layout.addWidget(self._metrics_strip)

        # ── Timeline heatmap (scrollable) ─────────────────────────────
        self._timeline = _TimelineCanvas()
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._timeline)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: #0A0A14; border: none; }"
        )
        main_layout.addWidget(self._scroll, stretch=1)

        # ── Summary panel ─────────────────────────────────────────────
        self._summary = _SummaryPanel()
        main_layout.addWidget(self._summary)

        # ── Bottom bar (history + export) ─────────────────────────────
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(44)
        bottom_bar.setStyleSheet("background: #12132a; border-top: 1px solid #222;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 0, 12, 0)

        btn_style = (
            "QPushButton { background: #1E2238; color: #ccc; font: bold 11px 'Consolas'; "
            "padding: 6px 14px; border-radius: 5px; border: 1px solid #333; }"
            "QPushButton:hover { background: #2A2E48; border-color: #555; }"
        )

        self._history_btn = QPushButton("📋 History")
        self._history_btn.setCursor(Qt.PointingHandCursor)
        self._history_btn.setStyleSheet(btn_style)
        self._history_btn.setCheckable(True)
        self._history_btn.clicked.connect(self._toggle_history)
        bottom_layout.addWidget(self._history_btn)

        bottom_layout.addStretch()

        export_btn = QPushButton("💾 Export PNG")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setStyleSheet(
            "QPushButton { background: #0D3320; color: #00E676; font: bold 11px 'Consolas'; "
            "padding: 6px 14px; border-radius: 5px; border: 1px solid #225533; }"
            "QPushButton:hover { background: #1A4430; }"
        )
        export_btn.clicked.connect(self._export_png)
        bottom_layout.addWidget(export_btn)

        copy_btn = QPushButton("📋 Copy")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(self._copy_to_clipboard)
        bottom_layout.addWidget(copy_btn)

        main_layout.addWidget(bottom_bar)

        # ── History panel (hidden by default) ─────────────────────────
        self._history_scroll = QScrollArea()
        self._history_panel = _HistoryPanel(on_load_session=self._load_past_session)
        self._history_scroll.setWidget(self._history_panel)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFixedHeight(220)
        self._history_scroll.setStyleSheet(
            "QScrollArea { background: #0A0A14; border: none; border-top: 1px solid #222; }"
        )
        self._history_scroll.setVisible(False)
        main_layout.addWidget(self._history_scroll)

    # ── Recording controls ────────────────────────────────────────────

    def _toggle_recording(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self._session_start = time.monotonic()
        self._last_sample_time = 0.0
        self._points.clear()
        self._annotations.clear()
        self._current_tag = ""
        self._rec_btn.setText("⏹  Stop Recording")
        self._rec_btn.setStyleSheet(
            "QPushButton { background: #3A1520; color: #FF5252; font: bold 12px 'Consolas'; "
            "padding: 8px 18px; border-radius: 6px; border: 1px solid #552233; }"
            "QPushButton:hover { background: #4A2030; }"
        )
        # Reset tag buttons
        for btn in self._tag_btns:
            btn.setChecked(False)
        self._timeline.set_data([], [])
        self._summary.set_stats({})
        log.info("Neuro Journal: recording started")

    def _stop_recording(self):
        self._recording = False
        self._rec_btn.setText("⏺  Start Recording")
        self._rec_btn.setStyleSheet(
            "QPushButton { background: #0D3320; color: #00E676; font: bold 12px 'Consolas'; "
            "padding: 8px 18px; border-radius: 6px; border: 1px solid #225533; }"
            "QPushButton:hover { background: #1A4430; }"
        )
        # Save session
        if self._points:
            self._save_session()
            self._compute_summary()
        log.info("Neuro Journal: recording stopped, %d samples", len(self._points))

    def _set_tag(self, name: str):
        if self._current_tag == name:
            self._current_tag = ""
            for btn in self._tag_btns:
                btn.setChecked(False)
        else:
            self._current_tag = name
            for btn in self._tag_btns:
                btn.setChecked(btn.text().endswith(name))

    def _add_annotation(self):
        if not self._recording or not self._points:
            return
        text, ok = QInputDialog.getText(
            self, "Add Note",
            "What's on your mind?",
        )
        if ok and text.strip():
            t = time.monotonic() - self._session_start
            ann = Annotation(
                t=t,
                wall=datetime.datetime.now().isoformat(timespec="seconds"),
                text=text.strip(),
            )
            self._annotations.append(ann)
            self._timeline.set_data(self._points, self._annotations)
            log.info("Neuro Journal: annotation added at t=%.1f: %s", t, text.strip()[:50])

    # ── Timer tick ────────────────────────────────────────────────────

    def _tick(self):
        now = time.monotonic()

        if self._recording and self._latest:
            elapsed = now - self._session_start

            # Sample once per second
            if elapsed - self._last_sample_time >= _SAMPLE_INTERVAL:
                self._last_sample_time = elapsed
                if len(self._points) < _MAX_SAMPLES:
                    pt = TimelinePoint(
                        t=elapsed,
                        wall=datetime.datetime.now().isoformat(timespec="seconds"),
                        attention=self._latest.get("attention", 0.0) or 0.0,
                        relaxation=self._latest.get("relaxation", 0.0) or 0.0,
                        cognitiveLoad=self._latest.get("cognitiveLoad", 0.0) or 0.0,
                        cognitiveControl=self._latest.get("cognitiveControl", 0.0) or 0.0,
                        selfControl=self._latest.get("selfControl", 0.0) or 0.0,
                        tag=self._current_tag,
                    )
                    self._points.append(pt)
                    self._timeline.set_data(self._points, self._annotations)

                    # Auto-scroll to latest
                    sb = self._scroll.horizontalScrollBar()
                    sb.setValue(sb.maximum())

            # Update duration label
            mins = int(elapsed) // 60
            secs = int(elapsed) % 60
            self._dur_lbl.setText(f"{mins:02d}:{secs:02d}")
            self._dur_lbl.setStyleSheet("color: #FF5252; font: bold 14px 'Consolas';")
        else:
            self._dur_lbl.setStyleSheet("color: #888; font: bold 14px 'Consolas';")

        # Update live metrics display
        if self._latest:
            for key, label, color in _METRICS:
                val = self._latest.get(key, 0.0) or 0.0
                self._metric_labels[key].setText(f"{label}: {val:.0f}")

        self._samples_lbl.setText(f"{len(self._points)} samples")

        # Live summary during recording
        if self._recording and len(self._points) > 5:
            self._compute_summary()

    # ── Summary computation ───────────────────────────────────────────

    def _compute_summary(self):
        if not self._points:
            return

        stats = {
            "duration_min": self._points[-1].t / 60.0 if self._points else 0,
            "samples": len(self._points),
        }

        # Per-metric stats
        max_avg = 0
        dominant = "—"
        for key, label, _ in _METRICS:
            vals = [getattr(pt, key, 0.0) for pt in self._points]
            avg = sum(vals) / len(vals) if vals else 0
            peak = max(vals) if vals else 0
            stats[f"avg_{key}"] = avg
            stats[f"peak_{key}"] = peak
            if avg > max_avg:
                max_avg = avg
                dominant = label

        stats["dominant"] = dominant

        # Tag breakdown (seconds per tag)
        tag_counts: dict[str, int] = {}
        for pt in self._points:
            if pt.tag:
                tag_counts[pt.tag] = tag_counts.get(pt.tag, 0) + 1
        stats["tags"] = tag_counts

        self._summary.set_stats(stats)
        return stats

    # ── Persistence ───────────────────────────────────────────────────

    def _save_session(self):
        os.makedirs(_JOURNAL_DIR, exist_ok=True)

        summary = self._compute_summary() or {}

        session_data = {
            "session_id": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_wall": self._points[0].wall if self._points else "",
            "end_wall": self._points[-1].wall if self._points else "",
            "duration_sec": self._points[-1].t if self._points else 0,
            "num_samples": len(self._points),
            "summary": summary,
            "points": [
                {
                    "t": pt.t,
                    "wall": pt.wall,
                    "attention": round(pt.attention, 1),
                    "relaxation": round(pt.relaxation, 1),
                    "cognitiveLoad": round(pt.cognitiveLoad, 1),
                    "cognitiveControl": round(pt.cognitiveControl, 1),
                    "selfControl": round(pt.selfControl, 1),
                    "tag": pt.tag,
                }
                for pt in self._points
            ],
            "annotations": [
                {"t": a.t, "wall": a.wall, "text": a.text}
                for a in self._annotations
            ],
        }

        # Save individual session file
        session_file = os.path.join(
            _JOURNAL_DIR, f"journal_{session_data['session_id']}.json"
        )
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)

        # Update history index
        history_entry = {
            "session_id": session_data["session_id"],
            "start_wall": session_data["start_wall"],
            "end_wall": session_data["end_wall"],
            "duration_sec": session_data["duration_sec"],
            "num_samples": session_data["num_samples"],
            "summary": summary,
            "file": os.path.basename(session_file),
        }
        self._past_sessions.append(history_entry)
        # Keep last 100 sessions in index
        self._past_sessions = self._past_sessions[-100:]

        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._past_sessions, f, indent=2, ensure_ascii=False)

        self._history_panel.set_sessions(self._past_sessions)
        log.info("Neuro Journal: session saved to %s", session_file)

    def _load_history(self):
        if os.path.isfile(_HISTORY_FILE):
            try:
                with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                    self._past_sessions = json.load(f)
                self._history_panel.set_sessions(self._past_sessions)
            except (json.JSONDecodeError, OSError):
                self._past_sessions = []

    def _load_past_session(self, session_meta: dict):
        """Load a past session from disk and display its timeline."""
        fname = session_meta.get("file", "")
        fpath = os.path.join(_JOURNAL_DIR, fname)
        if not os.path.isfile(fpath):
            return

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        # Stop recording if active
        if self._recording:
            self._stop_recording()

        # Restore points
        self._points = [
            TimelinePoint(**pt) for pt in data.get("points", [])
        ]
        self._annotations = [
            Annotation(**a) for a in data.get("annotations", [])
        ]

        self._timeline.set_data(self._points, self._annotations)

        # Restore summary
        summary = data.get("summary", {})
        self._summary.set_stats(summary)

        # Update duration display
        dur = data.get("duration_sec", 0)
        mins = int(dur) // 60
        secs = int(dur) % 60
        self._dur_lbl.setText(f"{mins:02d}:{secs:02d}")

        log.info("Neuro Journal: loaded session %s (%d points)",
                 data.get("session_id", "?"), len(self._points))

    # ── History toggle ────────────────────────────────────────────────

    def _toggle_history(self):
        visible = not self._history_scroll.isVisible()
        self._history_scroll.setVisible(visible)
        self._history_btn.setChecked(visible)

    # ── Export ────────────────────────────────────────────────────────

    def _render_export_image(self) -> QImage | None:
        if not self._points:
            return None

        # Render a larger image for export
        n = len(self._points)
        img_w = max(800, _TIMELINE_PAD + n * _CELL_W + 80)
        img_h = 500

        img = QImage(img_w, img_h, QImage.Format_ARGB32)
        img.fill(QColor(10, 10, 20))

        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)

        top_y = 50
        row_h = _CELL_H

        # Title
        p.setPen(_TEXT_BRIGHT)
        p.setFont(QFont("Consolas", 14, QFont.Bold))
        p.drawText(QRectF(16, 8, 400, 30), Qt.AlignLeft | Qt.AlignVCenter,
                   "📓 Neuro Journal — Emotion Timeline")

        # Date range
        p.setPen(_TEXT_DIM)
        p.setFont(QFont("Consolas", 9))
        start = self._points[0].wall[:16] if self._points else ""
        end = self._points[-1].wall[:16] if self._points else ""
        dur = self._points[-1].t / 60.0 if self._points else 0
        p.drawText(QRectF(16, 30, 500, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{start} → {end}  ({dur:.1f} min, {n} samples)")

        # Row labels
        p.setFont(QFont("Consolas", 9, QFont.Bold))
        for ri, (key, label, color_hex) in enumerate(_METRICS):
            y = top_y + ri * row_h
            p.setPen(QColor(color_hex))
            p.drawText(QRectF(4, y, _TIMELINE_PAD - 8, row_h),
                       Qt.AlignVCenter | Qt.AlignRight, label)

        # Heatmap cells
        for ci, pt in enumerate(self._points):
            x = _TIMELINE_PAD + ci * _CELL_W
            for ri, (key, label, color_hex) in enumerate(_METRICS):
                y = top_y + ri * row_h
                val = getattr(pt, key, 0.0)
                color = _value_to_color(val, color_hex)
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRect(QRectF(x, y + 1, _CELL_W, row_h - 2))

        # Time axis
        p.setFont(QFont("Consolas", 7))
        p.setPen(_TEXT_DIM)
        for ci in range(0, n, 60):
            x = _TIMELINE_PAD + ci * _CELL_W
            minutes = ci // 60
            p.drawText(QRectF(x - 10, top_y - 18, 30, 14), Qt.AlignCenter, f"{minutes}m")
            p.setPen(QPen(QColor(60, 60, 80), 1))
            p.drawLine(int(x), top_y - 4, int(x), top_y + len(_METRICS) * row_h)
            p.setPen(_TEXT_DIM)

        # Activity tags
        tag_y = top_y + len(_METRICS) * row_h + 8
        p.setFont(QFont("Consolas", 8))
        last_tag = ""
        tag_start_x = _TIMELINE_PAD
        for ci, pt in enumerate(self._points):
            x = _TIMELINE_PAD + ci * _CELL_W
            if pt.tag != last_tag or ci == n - 1:
                if last_tag:
                    block_w = x - tag_start_x
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(40, 50, 70))
                    p.drawRoundedRect(QRectF(tag_start_x, tag_y, block_w, 18), 3, 3)
                    if block_w > 20:
                        p.setPen(_TEXT_MED)
                        p.drawText(QRectF(tag_start_x + 4, tag_y, block_w - 8, 18),
                                   Qt.AlignVCenter | Qt.AlignLeft, last_tag)
                tag_start_x = x
                last_tag = pt.tag

        # Annotations
        ann_y = tag_y + 26
        p.setFont(QFont("Consolas", 8))
        for ann in self._annotations:
            ci = min(int(ann.t), n - 1)
            x = _TIMELINE_PAD + ci * _CELL_W
            p.setPen(QPen(_MARKER_LINE, 1, Qt.DashLine))
            p.drawLine(int(x), top_y, int(x), ann_y - 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFD740"))
            p.drawEllipse(QPointF(x, ann_y + 4), 3, 3)
            p.setPen(_TEXT_BRIGHT)
            p.drawText(QRectF(x + 6, ann_y - 2, 140, 14),
                       Qt.AlignVCenter | Qt.AlignLeft, ann.text[:30])

        # Summary bar at bottom
        summary_y = max(ann_y + 26, img_h - 60)
        p.setPen(_TEXT_MED)
        p.setFont(QFont("Consolas", 9))
        stats = self._compute_summary() or {}
        parts = []
        for key, label, _ in _METRICS:
            avg = stats.get(f"avg_{key}", 0)
            parts.append(f"{label}: {avg:.0f}")
        p.drawText(QRectF(16, summary_y, img_w - 32, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "Averages — " + "  •  ".join(parts))

        dom = stats.get("dominant", "—")
        p.drawText(QRectF(16, summary_y + 18, img_w - 32, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"Dominant state: {dom}")

        p.end()
        return img

    def _export_png(self):
        img = self._render_export_image()
        if img is None:
            return

        data_dir = os.path.join(_APP_DIR, "data", "journal")
        os.makedirs(data_dir, exist_ok=True)
        default_name = f"neuro_journal_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        default_path = os.path.join(data_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Journal", default_path, "PNG Image (*.png)"
        )
        if path:
            img.save(path, "PNG")
            log.info("Neuro Journal: exported to %s", path)

    def _copy_to_clipboard(self):
        img = self._render_export_image()
        if img is None:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setImage(img)
            log.info("Neuro Journal: copied to clipboard")

    # ── Public API (called by signal dispatcher) ─────────────────────

    def on_emotions(self, data: dict):
        if not self.isVisible() or not data:
            return
        self._latest = data

    def closeEvent(self, event):
        if self._recording:
            self._stop_recording()
        self.hide()
        event.ignore()

    def shutdown(self):
        if self._recording:
            self._stop_recording()
        self._timer.stop()
        self.close()
