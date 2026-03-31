"""
BCI Aim Trainer — Head-aim (gyro) + Focus-fire (EEG attention dwell).

Standalone pop-up game window. Targets appear at random positions.
Aim the crosshair by tilting your head, fire by sustaining focus ≥ 70
for 0.8 s.  Tracks accuracy, reaction time, streak, and session history.

Arcade / retro visual style with scanline overlay and neon colors.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QRadialGradient,
    QLinearGradient, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QApplication,
)

log = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────
_DEAD_ZONE = 2.0           # deg/s — ignore gyro noise below this
_SENSITIVITY = 6.0          # pixels per deg/s (slightly less than mouse)
_TICK_MS = 16               # ~60 FPS repaint
_FOCUS_THRESHOLD = 70       # attention level to start dwell
_DWELL_SEC = 0.8            # seconds to hold focus → fire
_FIRE_COOLDOWN = 1.0        # seconds between shots
_ROUND_DURATION = 60        # seconds per round
_TARGET_RADIUS = 32         # pixels
_TARGET_MARGIN = 60         # min margin from edges
_TARGET_TIMEOUT = 5.0       # seconds before target auto-expires (miss)

# Scoring
_SCORE_HIT = 100
_SCORE_FAST_BONUS = 50      # if reaction < 1.5 s

# Colors (arcade/retro)
_BG = QColor(10, 10, 20)
_GRID = QColor(25, 30, 55)
_SCANLINE = QColor(0, 0, 0, 30)
_TARGET_COLORS = [
    QColor("#00E5FF"),   # cyan
    QColor("#FF4081"),   # magenta
    QColor("#FFEA00"),   # yellow
    QColor("#76FF03"),   # lime
    QColor("#E040FB"),   # purple
]
_CROSSHAIR = QColor("#00E676")
_CROSSHAIR_FIRE = QColor("#FF6D00")
_TEXT_COLOR = QColor("#E0E0E0")
_HIT_COLOR = QColor("#00E676")
_MISS_COLOR = QColor("#FF1744")

# Session history file
_HISTORY_DIR = Path(__file__).resolve().parent.parent / "sessions"
_HISTORY_FILE = _HISTORY_DIR / "aim_trainer_history.json"


# ── Data structures ───────────────────────────────────────────────────

class _Target:
    __slots__ = ("x", "y", "radius", "color", "spawn_time", "alive")

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.radius = _TARGET_RADIUS
        self.color: QColor = random.choice(_TARGET_COLORS)
        self.spawn_time = time.monotonic()
        self.alive = True


class _HitEffect:
    __slots__ = ("x", "y", "color", "birth", "score_text")

    def __init__(self, x: float, y: float, color: QColor, score_text: str):
        self.x = x
        self.y = y
        self.color = color
        self.birth = time.monotonic()
        self.score_text = score_text


# ══════════════════════════════════════════════════════════════════════
#  Game Canvas — custom painted widget
# ══════════════════════════════════════════════════════════════════════

class _GameCanvas(QWidget):
    """Full game rendering surface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(800, 600)

        # Crosshair position (center-relative accumulator)
        self._cx = 0.0
        self._cy = 0.0
        self._dx = 0.0  # accumulated gyro delta
        self._dy = 0.0

        # Game state
        self._state = "idle"  # idle | countdown | playing | results
        self._countdown_val = 3
        self._round_start = 0.0
        self._time_left = _ROUND_DURATION

        # Target
        self._target: _Target | None = None
        self._effects: list[_HitEffect] = []

        # Dwell state
        self._focus = 0.0
        self._dwell_start: float | None = None
        self._last_fire_time = 0.0

        # Round stats
        self._score = 0
        self._hits = 0
        self._misses = 0
        self._total_targets = 0
        self._reaction_times: list[float] = []
        self._streak = 0
        self._best_streak = 0
        self._focus_samples: list[float] = []

        # History
        self._history: list[dict] = []
        self._load_history()

        # Timers
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(_TICK_MS)
        self._tick_timer.timeout.connect(self._tick)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._countdown_tick)

    # ── Public API ────────────────────────────────────────────────────

    def start_game(self):
        self._state = "countdown"
        self._countdown_val = 3
        self._score = 0
        self._hits = 0
        self._misses = 0
        self._total_targets = 0
        self._reaction_times.clear()
        self._streak = 0
        self._best_streak = 0
        self._focus_samples.clear()
        self._target = None
        self._effects.clear()
        self._cx = self.width() / 2
        self._cy = self.height() / 2
        self._countdown_timer.start()
        self._tick_timer.start()
        self.update()

    def feed_gyro(self, gx: float, gz: float):
        """Accumulate gyro deltas. gx=pitch (Y-axis), gz=roll (X-axis)."""
        if abs(gz) > _DEAD_ZONE:
            self._dx += gz
        if abs(gx) > _DEAD_ZONE:
            self._dy += gx

    def feed_focus(self, attention: float):
        """Receive current attention level (0-100)."""
        self._focus = attention
        if self._state == "playing":
            self._focus_samples.append(attention)

    @property
    def game_active(self) -> bool:
        return self._state in ("countdown", "playing")

    # ── Timers ────────────────────────────────────────────────────────

    def _countdown_tick(self):
        self._countdown_val -= 1
        if self._countdown_val <= 0:
            self._countdown_timer.stop()
            self._state = "playing"
            self._round_start = time.monotonic()
            self._spawn_target()
        self.update()

    def _tick(self):
        now = time.monotonic()

        # Apply gyro → crosshair
        dx = self._dx * _SENSITIVITY * (_TICK_MS / 1000.0)
        dy = self._dy * _SENSITIVITY * (_TICK_MS / 1000.0)
        self._dx = 0.0
        self._dy = 0.0
        self._cx = max(0, min(self.width(), self._cx + dx))
        self._cy = max(0, min(self.height(), self._cy + dy))

        if self._state == "playing":
            self._time_left = max(0, _ROUND_DURATION - (now - self._round_start))

            # Check target timeout
            if self._target and self._target.alive:
                if now - self._target.spawn_time >= _TARGET_TIMEOUT:
                    self._on_miss()

            # Dwell-fire logic
            self._check_fire(now)

            # Round over?
            if self._time_left <= 0:
                self._end_round()

        # Expire old hit effects
        self._effects = [e for e in self._effects if now - e.birth < 1.0]

        self.update()

    def _check_fire(self, now: float):
        if not self._target or not self._target.alive:
            return
        # Is crosshair on target?
        dist = math.hypot(self._cx - self._target.x, self._cy - self._target.y)
        on_target = dist <= self._target.radius + 12  # small grace margin

        if on_target and self._focus >= _FOCUS_THRESHOLD:
            if self._dwell_start is None:
                self._dwell_start = now
            elif now - self._dwell_start >= _DWELL_SEC:
                if now - self._last_fire_time >= _FIRE_COOLDOWN:
                    self._on_hit(now)
                    self._last_fire_time = now
                self._dwell_start = None
        else:
            self._dwell_start = None

    @property
    def _dwell_frac(self) -> float:
        if self._dwell_start is None:
            return 0.0
        return min(1.0, (time.monotonic() - self._dwell_start) / _DWELL_SEC)

    # ── Game logic ────────────────────────────────────────────────────

    def _spawn_target(self):
        margin = _TARGET_MARGIN
        x = random.randint(margin, max(margin + 1, self.width() - margin))
        y = random.randint(margin, max(margin + 1, self.height() - margin))
        self._target = _Target(x, y)
        self._total_targets += 1

    def _on_hit(self, now: float):
        t = self._target
        rt = now - t.spawn_time
        self._reaction_times.append(rt)
        bonus = _SCORE_FAST_BONUS if rt < 1.5 else 0
        points = _SCORE_HIT + bonus
        self._score += points
        self._hits += 1
        self._streak += 1
        self._best_streak = max(self._best_streak, self._streak)

        score_text = f"+{points}"
        self._effects.append(_HitEffect(t.x, t.y, _HIT_COLOR, score_text))
        t.alive = False
        log.info("Aim Trainer: HIT! rt=%.2fs score=%d streak=%d", rt, self._score, self._streak)

        # Spawn next target after short delay
        QTimer.singleShot(400, self._spawn_target)

    def _on_miss(self):
        t = self._target
        self._misses += 1
        self._streak = 0
        self._effects.append(_HitEffect(t.x, t.y, _MISS_COLOR, "MISS"))
        t.alive = False
        log.info("Aim Trainer: MISS (timeout)")
        QTimer.singleShot(400, self._spawn_target)

    def _end_round(self):
        self._state = "results"
        self._tick_timer.stop()
        self._target = None

        # Save session
        session = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "score": self._score,
            "hits": self._hits,
            "misses": self._misses,
            "total": self._total_targets,
            "accuracy": round(self._hits / max(1, self._total_targets) * 100, 1),
            "avg_reaction": round(sum(self._reaction_times) / max(1, len(self._reaction_times)), 2),
            "best_streak": self._best_streak,
            "avg_focus": round(sum(self._focus_samples) / max(1, len(self._focus_samples)), 1),
        }
        self._history.append(session)
        if len(self._history) > 50:
            self._history = self._history[-50:]
        self._save_history()
        log.info("Aim Trainer: Round over — %s", session)
        self.update()

    # ── History persistence ───────────────────────────────────────────

    def _load_history(self):
        try:
            if _HISTORY_FILE.exists():
                with open(_HISTORY_FILE, "r") as f:
                    self._history = json.load(f)
        except Exception:
            self._history = []

    def _save_history(self):
        try:
            _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            with open(_HISTORY_FILE, "w") as f:
                json.dump(self._history, f, indent=2)
        except Exception as e:
            log.warning("Failed to save aim trainer history: %s", e)

    # ══════════════════════════════════════════════════════════════════
    #  PAINTING
    # ══════════════════════════════════════════════════════════════════

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(self.rect(), _BG)

        # Grid
        p.setPen(QPen(_GRID, 1))
        for x in range(0, w, 40):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 40):
            p.drawLine(0, y, w, y)

        # Scanlines
        p.setPen(Qt.NoPen)
        p.setBrush(_SCANLINE)
        for y in range(0, h, 4):
            p.drawRect(0, y, w, 2)

        if self._state == "idle":
            self._paint_idle(p, w, h)
        elif self._state == "countdown":
            self._paint_countdown(p, w, h)
        elif self._state == "playing":
            self._paint_game(p, w, h)
        elif self._state == "results":
            self._paint_results(p, w, h)

        p.end()

    def _paint_idle(self, p: QPainter, w: int, h: int):
        # Title
        p.setPen(_TEXT_COLOR)
        p.setFont(QFont("Consolas", 36, QFont.Bold))
        p.drawText(QRectF(0, h * 0.2, w, 60), Qt.AlignCenter, "🎯 AIM TRAINER")

        p.setFont(QFont("Consolas", 14))
        p.drawText(QRectF(0, h * 0.38, w, 30), Qt.AlignCenter,
                    "Aim with HEAD movement  •  Fire with FOCUS dwell")
        p.drawText(QRectF(0, h * 0.44, w, 30), Qt.AlignCenter,
                    f"Hold Attention ≥ {_FOCUS_THRESHOLD} for {_DWELL_SEC}s on target to shoot")

        p.setPen(QColor("#00E676"))
        p.setFont(QFont("Consolas", 20, QFont.Bold))
        p.drawText(QRectF(0, h * 0.58, w, 40), Qt.AlignCenter, "[ Press START or SPACE ]")

        # Recent history
        if self._history:
            p.setPen(QColor("#888"))
            p.setFont(QFont("Consolas", 11))
            p.drawText(QRectF(0, h * 0.72, w, 20), Qt.AlignCenter, "— Recent Sessions —")
            last = self._history[-min(5, len(self._history)):]
            for i, s in enumerate(reversed(last)):
                y = h * 0.77 + i * 20
                txt = (f"{s['timestamp']}  Score: {s['score']}  "
                       f"Acc: {s['accuracy']}%  RT: {s['avg_reaction']}s  "
                       f"Streak: {s['best_streak']}")
                p.drawText(QRectF(20, y, w - 40, 20), Qt.AlignCenter, txt)

    def _paint_countdown(self, p: QPainter, w: int, h: int):
        p.setPen(QColor("#FFEA00"))
        p.setFont(QFont("Consolas", 120, QFont.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, str(self._countdown_val))

    def _paint_game(self, p: QPainter, w: int, h: int):
        now = time.monotonic()

        # Target
        if self._target and self._target.alive:
            t = self._target
            age = now - t.spawn_time
            pulse = 1.0 + 0.15 * math.sin(age * 6)
            r = t.radius * pulse

            # Glow
            glow = QRadialGradient(t.x, t.y, r * 2.5)
            gc = QColor(t.color)
            gc.setAlpha(60)
            glow.setColorAt(0.0, gc)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(t.x, t.y), r * 2.5, r * 2.5)

            # Target body
            p.setPen(QPen(t.color, 3))
            p.setBrush(QColor(t.color.red(), t.color.green(), t.color.blue(), 80))
            p.drawEllipse(QPointF(t.x, t.y), r, r)

            # Inner ring
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(t.color, 2))
            p.drawEllipse(QPointF(t.x, t.y), r * 0.5, r * 0.5)

            # Timeout bar
            timeout_frac = min(1.0, age / _TARGET_TIMEOUT)
            bar_w = r * 2
            bar_h = 4
            bx = t.x - r
            by = t.y + r + 10
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(60, 60, 80))
            p.drawRect(int(bx), int(by), int(bar_w), bar_h)
            bar_color = QColor("#FF1744") if timeout_frac > 0.7 else t.color
            p.setBrush(bar_color)
            p.drawRect(int(bx), int(by), int(bar_w * (1 - timeout_frac)), bar_h)

        # Hit/miss effects
        for eff in self._effects:
            age = now - eff.birth
            alpha = max(0, int(255 * (1 - age)))
            radius = 20 + age * 120
            c = QColor(eff.color)
            c.setAlpha(alpha)
            p.setPen(QPen(c, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(eff.x, eff.y), radius, radius)
            # Score text floats up
            p.setFont(QFont("Consolas", 16, QFont.Bold))
            p.drawText(int(eff.x - 30), int(eff.y - 20 - age * 60), eff.score_text)

        # Crosshair
        self._paint_crosshair(p)

        # HUD
        self._paint_hud(p, w, h)

    def _paint_crosshair(self, p: QPainter):
        cx, cy = self._cx, self._cy
        dwell = self._dwell_frac
        color = _CROSSHAIR_FIRE if dwell > 0 else _CROSSHAIR
        size = 18

        # Main lines
        p.setPen(QPen(color, 2))
        p.drawLine(int(cx - size), int(cy), int(cx - 6), int(cy))
        p.drawLine(int(cx + 6), int(cy), int(cx + size), int(cy))
        p.drawLine(int(cx), int(cy - size), int(cx), int(cy - 6))
        p.drawLine(int(cx), int(cy + 6), int(cx), int(cy + size))

        # Center dot
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 3, 3)

        # Dwell ring
        if dwell > 0:
            ring_r = 22
            p.setPen(QPen(QColor(60, 60, 80), 3))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

            p.setPen(QPen(_CROSSHAIR_FIRE, 3))
            span = int(dwell * 360 * 16)
            p.drawArc(int(cx - ring_r), int(cy - ring_r),
                      ring_r * 2, ring_r * 2, 90 * 16, -span)

    def _paint_hud(self, p: QPainter, w: int, h: int):
        # Top bar
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawRect(0, 0, w, 40)

        p.setFont(QFont("Consolas", 14, QFont.Bold))
        p.setPen(_TEXT_COLOR)

        # Score
        p.drawText(15, 28, f"SCORE: {self._score}")

        # Time
        time_str = f"TIME: {int(self._time_left)}s"
        time_color = QColor("#FF1744") if self._time_left < 10 else _TEXT_COLOR
        p.setPen(time_color)
        p.drawText(w // 2 - 50, 28, time_str)

        # Stats
        p.setPen(_TEXT_COLOR)
        acc = self._hits / max(1, self._total_targets) * 100
        p.drawText(w - 300, 28, f"ACC: {acc:.0f}%")
        p.drawText(w - 180, 28, f"STREAK: {self._streak}")

        # Focus bar (bottom-left)
        bar_x, bar_y, bar_w, bar_h = 15, h - 30, 120, 12
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 40, 60))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)
        fill_w = int(bar_w * self._focus / 100.0)
        fc = QColor("#00E676") if self._focus >= _FOCUS_THRESHOLD else QColor("#4FC3F7")
        p.setBrush(fc)
        p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 4, 4)
        p.setPen(QColor("#aaa"))
        p.setFont(QFont("Consolas", 9))
        p.drawText(bar_x + bar_w + 8, bar_y + 10, f"Focus: {self._focus:.0f}")

    def _paint_results(self, p: QPainter, w: int, h: int):
        # Semi-transparent overlay
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 10, 20, 220))
        p.drawRect(self.rect())

        # Title
        p.setPen(QColor("#FFEA00"))
        p.setFont(QFont("Consolas", 36, QFont.Bold))
        p.drawText(QRectF(0, h * 0.08, w, 50), Qt.AlignCenter, "ROUND COMPLETE")

        # Stats
        total = max(1, self._total_targets)
        acc = self._hits / total * 100
        avg_rt = (sum(self._reaction_times) / max(1, len(self._reaction_times)))
        avg_focus = (sum(self._focus_samples) / max(1, len(self._focus_samples)))

        stats = [
            ("SCORE", str(self._score), "#00E676"),
            ("HITS / TOTAL", f"{self._hits} / {self._total_targets}", "#4FC3F7"),
            ("ACCURACY", f"{acc:.1f}%", "#00E5FF"),
            ("AVG REACTION", f"{avg_rt:.2f}s", "#FFEA00"),
            ("BEST STREAK", str(self._best_streak), "#E040FB"),
            ("AVG FOCUS", f"{avg_focus:.0f}", "#76FF03"),
        ]

        p.setFont(QFont("Consolas", 18))
        for i, (label, value, color) in enumerate(stats):
            y = h * 0.25 + i * 45
            p.setPen(QColor("#888"))
            p.drawText(QRectF(w * 0.2, y, w * 0.35, 35), Qt.AlignRight | Qt.AlignVCenter, label)
            p.setPen(QColor(color))
            p.drawText(QRectF(w * 0.58, y, w * 0.3, 35), Qt.AlignLeft | Qt.AlignVCenter, value)

        # History mini-chart (last 10 sessions - bar chart of scores)
        recent = self._history[-min(10, len(self._history)):]
        if recent:
            chart_x = w * 0.15
            chart_y = h * 0.68
            chart_w = w * 0.7
            chart_h = h * 0.18
            max_score = max(s["score"] for s in recent) or 1

            p.setPen(QColor("#444"))
            p.drawLine(int(chart_x), int(chart_y + chart_h),
                       int(chart_x + chart_w), int(chart_y + chart_h))

            bar_gap = 6
            bar_w = max(8, (chart_w - bar_gap * len(recent)) / len(recent))
            for i, s in enumerate(recent):
                bx = chart_x + i * (bar_w + bar_gap)
                bh = (s["score"] / max_score) * chart_h * 0.9
                by = chart_y + chart_h - bh

                # Bar color: latest = bright, others dimmer
                is_latest = (i == len(recent) - 1)
                bc = QColor("#00E676") if is_latest else QColor("#2E7D32")
                p.setPen(Qt.NoPen)
                p.setBrush(bc)
                p.drawRoundedRect(int(bx), int(by), int(bar_w), int(bh), 3, 3)

                # Score label
                p.setPen(QColor("#aaa"))
                p.setFont(QFont("Consolas", 8))
                p.drawText(int(bx), int(chart_y + chart_h + 14), str(s["score"]))

            p.setPen(QColor("#666"))
            p.setFont(QFont("Consolas", 10))
            p.drawText(QRectF(chart_x, chart_y - 20, chart_w, 18),
                       Qt.AlignCenter, "Session History (Last 10)")

        # Play again prompt
        p.setPen(QColor("#00E676"))
        p.setFont(QFont("Consolas", 16, QFont.Bold))
        p.drawText(QRectF(0, h * 0.92, w, 30), Qt.AlignCenter,
                    "[ SPACE or START to play again ]")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            if self._state in ("idle", "results"):
                self.start_game()
        super().keyPressEvent(event)


# ══════════════════════════════════════════════════════════════════════
#  Aim Trainer Window
# ══════════════════════════════════════════════════════════════════════

class AimTrainerWindow(QMainWindow):
    """Standalone pop-up window for the BCI Aim Trainer game."""

    def __init__(self):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("🎯  BCI Aim Trainer — Head Aim + Focus Fire")
        self.setMinimumSize(900, 650)
        self.resize(1200, 800)
        self.setStyleSheet("QMainWindow { background: #0A0A14; }")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top control bar
        ctrl_bar = QWidget()
        ctrl_bar.setFixedHeight(48)
        ctrl_bar.setStyleSheet("background: #12132a; border-bottom: 1px solid #222;")
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(12, 0, 12, 0)

        title_lbl = QLabel("🎯 AIM TRAINER")
        title_lbl.setStyleSheet("color: #00E676; font: bold 14px 'Consolas';")
        ctrl_layout.addWidget(title_lbl)
        ctrl_layout.addStretch()

        self._start_btn = QPushButton("▶  START")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setStyleSheet(
            "QPushButton { background: #00E676; color: #000; font: bold 13px 'Consolas'; "
            "padding: 6px 20px; border-radius: 4px; }"
            "QPushButton:hover { background: #69F0AE; }"
        )
        self._start_btn.clicked.connect(self._on_start)
        ctrl_layout.addWidget(self._start_btn)

        layout.addWidget(ctrl_bar)

        # Game canvas
        self._canvas = _GameCanvas()
        layout.addWidget(self._canvas, stretch=1)

    def _on_start(self):
        self._canvas.start_game()
        self._canvas.setFocus()

    # ── Public API (called by signal dispatcher) ─────────────────────

    def on_mems(self, mems_timed_data):
        """Receive raw MEMSTimedData — extract gyro for crosshair."""
        if not self.isVisible() or not self._canvas.game_active:
            return
        n = len(mems_timed_data)
        for i in range(n):
            gyro = mems_timed_data.get_gyroscope(i)
            self._canvas.feed_gyro(gyro.x, gyro.z)

    def on_emotions(self, data: dict):
        """Receive emotions dict — extract attention for fire trigger."""
        if not self.isVisible() or not data:
            return
        attention = data.get("attention", 0.0) or 0.0
        self._canvas.feed_focus(attention)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def shutdown(self):
        self._canvas._tick_timer.stop()
        self._canvas._countdown_timer.stop()
        self.destroy()
