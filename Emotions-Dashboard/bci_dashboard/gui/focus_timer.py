"""
BCI Focus Productivity Timer — Pomodoro with brain-state validation.

25 min focus / 5 min break cycles.  EEG attention drives a live focus
meter that fills/drains and shifts green→red.  Tracks deep-focus time,
distraction count, average focus %, and saves session history to JSON.

Modern productivity-app aesthetic (clean, soft gradients).
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QLinearGradient, QRadialGradient, QConicalGradient, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy,
)

log = logging.getLogger(__name__)

# ── Tuning ────────────────────────────────────────────────────────────
_FOCUS_MIN   = 25           # minutes per focus block
_BREAK_MIN   = 5            # minutes per break
_TICK_MS     = 200          # UI refresh interval (5 Hz)
_FOCUS_THR   = 60           # attention ≥ this = focused
_DEEP_THR    = 80           # attention ≥ this = deep focus
_DISTRACT_CD = 5.0          # seconds before counting a new distraction

# ── Session history ───────────────────────────────────────────────────
_HISTORY_DIR = Path(__file__).resolve().parent.parent / "sessions"
_HISTORY_FILE = _HISTORY_DIR / "focus_timer_history.json"

# ── Colours ───────────────────────────────────────────────────────────
_BG        = QColor(18, 18, 30)
_CARD      = QColor(28, 28, 48)
_TXT       = QColor(240, 240, 255)
_TXT_DIM   = QColor(160, 160, 190)
_GREEN     = QColor(0, 230, 118)
_YELLOW    = QColor(255, 214, 0)
_RED       = QColor(255, 23, 68)
_CYAN      = QColor(0, 229, 255)
_PURPLE    = QColor(170, 0, 255)
_RING_BG   = QColor(50, 50, 70)
_BREAK_CLR = QColor(100, 181, 246)


def _focus_color(pct: float) -> QColor:
    """Return green→yellow→red based on focus percent (0–100)."""
    if pct >= 70:
        t = (pct - 70) / 30
        return QColor(
            int(_YELLOW.red() + t * (_GREEN.red() - _YELLOW.red())),
            int(_YELLOW.green() + t * (_GREEN.green() - _YELLOW.green())),
            int(_YELLOW.blue() + t * (_GREEN.blue() - _YELLOW.blue())),
        )
    elif pct >= 35:
        t = (pct - 35) / 35
        return QColor(
            int(_RED.red() + t * (_YELLOW.red() - _RED.red())),
            int(_RED.green() + t * (_YELLOW.green() - _RED.green())),
            int(_RED.blue() + t * (_YELLOW.blue() - _RED.blue())),
        )
    else:
        return _RED


# =====================================================================
#  Ring Canvas — draws the countdown ring + focus arc
# =====================================================================

class _RingCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.time_frac: float = 1.0       # 1.0 = full, 0.0 = done
        self.focus_pct: float = 0.0       # 0–100 smoothed attention
        self.is_break: bool = False
        self.paused: bool = False
        self.label_top: str = "FOCUS"
        self.label_time: str = "25:00"
        self.label_sub: str = "Ready"

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 20
        ring_w = 12

        # background
        p.fillRect(0, 0, w, h, _BG)

        # outer ring track
        pen_bg = QPen(_RING_BG, ring_w, cap=Qt.RoundCap)
        p.setPen(pen_bg)
        ring_rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.drawArc(ring_rect, 0, 360 * 16)

        # time progress arc (countdown)
        if self.is_break:
            arc_clr = _BREAK_CLR
        else:
            arc_clr = _focus_color(self.focus_pct)
        pen_arc = QPen(arc_clr, ring_w, cap=Qt.RoundCap)
        p.setPen(pen_arc)
        span = int(self.time_frac * 360 * 16)
        p.drawArc(ring_rect, 90 * 16, -span)

        # inner glow circle
        inner_r = r - ring_w - 8
        glow = QRadialGradient(cx, cy, inner_r)
        glow_clr = QColor(arc_clr)
        glow_clr.setAlphaF(0.07)
        glow.setColorAt(0.8, glow_clr)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))

        # centre text
        p.setPen(_TXT_DIM)
        p.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        p.drawText(QRectF(cx - 80, cy - 55, 160, 24), Qt.AlignCenter, self.label_top)

        p.setPen(_TXT)
        p.setFont(QFont("Segoe UI", 36, QFont.Bold))
        p.drawText(QRectF(cx - 90, cy - 30, 180, 50), Qt.AlignCenter, self.label_time)

        p.setPen(_TXT_DIM)
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(QRectF(cx - 80, cy + 22, 160, 22), Qt.AlignCenter, self.label_sub)

        # focus bar (horizontal bar under the ring)
        bar_w = r * 1.3
        bar_h = 8
        bar_x = cx - bar_w / 2
        bar_y = cy + r + 16
        # background
        p.setPen(Qt.NoPen)
        p.setBrush(_RING_BG)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 4, 4)
        # fill
        fill_w = bar_w * (self.focus_pct / 100)
        if fill_w > 0:
            p.setBrush(arc_clr)
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 4, 4)

        # focus % label
        p.setPen(arc_clr)
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(
            QRectF(bar_x, bar_y + bar_h + 2, bar_w, 18),
            Qt.AlignCenter,
            f"Focus: {int(self.focus_pct)}%" if not self.is_break else "Break",
        )

        p.end()


# =====================================================================
#  Stats Card Widget
# =====================================================================

class _StatsCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {_CARD.name()}; border-radius: 12px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(24)

        self._items: dict[str, QLabel] = {}
        for key, icon, label in [
            ("deep",    "🔥", "Deep Focus"),
            ("distr",   "⚡", "Distractions"),
            ("avg",     "📊", "Avg Focus"),
            ("rounds",  "🔄", "Rounds"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            val_lbl = QLabel("—")
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet(
                f"color: {_TXT.name()}; font-size: 18px; font-weight: 700;"
                " background: transparent;"
            )
            desc_lbl = QLabel(f"{icon} {label}")
            desc_lbl.setAlignment(Qt.AlignCenter)
            desc_lbl.setStyleSheet(
                f"color: {_TXT_DIM.name()}; font-size: 10px;"
                " background: transparent;"
            )
            col.addWidget(val_lbl)
            col.addWidget(desc_lbl)
            layout.addLayout(col)
            self._items[key] = val_lbl

    def update_stats(self, deep_sec: float, distractions: int,
                     avg_focus: float, rounds: int):
        dm, ds = divmod(int(deep_sec), 60)
        self._items["deep"].setText(f"{dm}:{ds:02d}")
        self._items["distr"].setText(str(distractions))
        self._items["avg"].setText(f"{int(avg_focus)}%")
        self._items["rounds"].setText(str(rounds))


# =====================================================================
#  Main Window
# =====================================================================

class FocusTimerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("BCI Focus Timer")
        self.resize(420, 600)
        self.setMinimumSize(340, 500)
        self.setStyleSheet(f"background: {_BG.name()};")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # title
        title = QLabel("FOCUS TIMER")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {_TXT.name()}; font-size: 16px; font-weight: 700;"
            " letter-spacing: 3px; background: transparent;"
        )
        root.addWidget(title)

        # ring
        self._ring = _RingCanvas()
        root.addWidget(self._ring, stretch=1)

        # stats card
        self._stats = _StatsCard()
        self._stats.setFixedHeight(80)
        root.addWidget(self._stats)

        # control buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(12)

        self._start_btn = self._make_btn("▶  START", _GREEN)
        self._start_btn.clicked.connect(self._on_start)
        btn_bar.addWidget(self._start_btn)

        self._pause_btn = self._make_btn("⏸  PAUSE", _YELLOW)
        self._pause_btn.clicked.connect(self._on_pause)
        self._pause_btn.setEnabled(False)
        btn_bar.addWidget(self._pause_btn)

        self._stop_btn = self._make_btn("⏹  STOP", _RED)
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        btn_bar.addWidget(self._stop_btn)

        root.addLayout(btn_bar)

        # ── state ─────────────────────────────────────────────────────
        self._running = False
        self._paused = False
        self._in_break = False
        self._round = 0
        self._phase_remaining = 0.0       # seconds left in current phase
        self._phase_duration = 0.0        # total seconds for current phase

        # focus tracking
        self._attention = 0.0
        self._focus_samples: list[float] = []
        self._deep_focus_sec = 0.0
        self._distractions = 0
        self._last_distracted = 0.0
        self._was_focused = True

        # history
        self._session_start: str = ""

        # tick
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_btn(text: str, color: QColor) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        cs = color.name()
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {cs};"
            f" border: 1.5px solid {cs}; border-radius: 10px;"
            f" padding: 8px 16px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {cs}; color: #12121e; }}"
            f"QPushButton:disabled {{ border-color: #333; color: #555; }}"
        )
        return b

    # ── controls ──────────────────────────────────────────────────────

    def _on_start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._in_break = False
        self._round = 1
        self._phase_duration = _FOCUS_MIN * 60
        self._phase_remaining = self._phase_duration
        self._deep_focus_sec = 0.0
        self._distractions = 0
        self._focus_samples.clear()
        self._was_focused = True
        self._last_distracted = 0.0
        self._session_start = datetime.now().isoformat(timespec="seconds")
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)
        self._timer.start()
        log.info("Focus Timer: started")

    def _on_pause(self):
        if not self._running:
            return
        self._paused = not self._paused
        self._pause_btn.setText("▶  RESUME" if self._paused else "⏸  PAUSE")
        log.info("Focus Timer: %s", "paused" if self._paused else "resumed")

    def _on_stop(self):
        self._timer.stop()
        self._running = False
        self._paused = False
        self._save_session()
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("⏸  PAUSE")
        self._stop_btn.setEnabled(False)
        self._ring.label_top = "FOCUS"
        self._ring.label_time = "25:00"
        self._ring.label_sub = "Stopped"
        self._ring.time_frac = 1.0
        self._ring.is_break = False
        self._ring.update()
        log.info("Focus Timer: stopped after %d rounds", self._round)

    # ── tick ──────────────────────────────────────────────────────────

    def _tick(self):
        if not self._running or self._paused:
            return
        dt = _TICK_MS / 1000.0
        now = time.monotonic()

        # countdown
        self._phase_remaining -= dt
        if self._phase_remaining <= 0:
            self._advance_phase()
            return

        frac = self._phase_remaining / self._phase_duration if self._phase_duration else 0
        mins = int(self._phase_remaining) // 60
        secs = int(self._phase_remaining) % 60

        # focus tracking (only during focus phase)
        if not self._in_break:
            self._focus_samples.append(self._attention)
            is_focused = self._attention >= _FOCUS_THR
            if self._attention >= _DEEP_THR:
                self._deep_focus_sec += dt
            if not is_focused and self._was_focused:
                if (now - self._last_distracted) > _DISTRACT_CD:
                    self._distractions += 1
                    self._last_distracted = now
            self._was_focused = is_focused

        # update ring
        self._ring.time_frac = frac
        self._ring.focus_pct = self._attention
        self._ring.is_break = self._in_break
        self._ring.label_top = "BREAK" if self._in_break else f"FOCUS — Round {self._round}"
        self._ring.label_time = f"{mins}:{secs:02d}"
        if self._in_break:
            self._ring.label_sub = "Relax your mind"
        elif self._attention >= _DEEP_THR:
            self._ring.label_sub = "🔥 Deep Focus"
        elif self._attention >= _FOCUS_THR:
            self._ring.label_sub = "Focused"
        else:
            self._ring.label_sub = "Refocus…"
        self._ring.update()

        # update stats
        avg = sum(self._focus_samples) / len(self._focus_samples) if self._focus_samples else 0
        self._stats.update_stats(self._deep_focus_sec, self._distractions, avg, self._round)

    def _advance_phase(self):
        if self._in_break:
            # break ended → start new focus round
            self._in_break = False
            self._round += 1
            self._phase_duration = _FOCUS_MIN * 60
            self._phase_remaining = self._phase_duration
            log.info("Focus Timer: round %d started", self._round)
        else:
            # focus ended → start break
            self._in_break = True
            self._phase_duration = _BREAK_MIN * 60
            self._phase_remaining = self._phase_duration
            log.info("Focus Timer: break started after round %d", self._round)

    # ── session history ───────────────────────────────────────────────

    def _save_session(self):
        if not self._focus_samples:
            return
        avg = sum(self._focus_samples) / len(self._focus_samples)
        entry = {
            "started": self._session_start,
            "rounds_completed": self._round,
            "avg_focus_pct": round(avg, 1),
            "deep_focus_sec": round(self._deep_focus_sec, 1),
            "distractions": self._distractions,
            "total_samples": len(self._focus_samples),
        }
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        history: list = []
        if _HISTORY_FILE.exists():
            try:
                history = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                history = []
        history.append(entry)
        _HISTORY_FILE.write_text(
            json.dumps(history, indent=2), encoding="utf-8"
        )
        log.info("Focus Timer: session saved — avg %.0f%%, %d distractions",
                 avg, self._distractions)

    # ── public API ────────────────────────────────────────────────────

    def on_emotions(self, data):
        if not self.isVisible():
            return
        try:
            self._attention = data.get("attention", 0.0)
        except Exception:
            pass

    def shutdown(self):
        self._timer.stop()
        if self._running:
            self._save_session()
        self.close()
