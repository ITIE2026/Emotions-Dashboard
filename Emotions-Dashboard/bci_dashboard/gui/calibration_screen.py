"""
CalibrationScreen – premium progress UI for the 3-stage calibration.
Dark-themed to match Mind Tracker BCI style.

Stage 1 (NFB, 30 s): circular countdown clock with gradient arc + particle field.
Stages 2+3: shows a gradient progress bar.
"""
import math
import random
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton,
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QLinearGradient, QConicalGradient,
    QRadialGradient,
)

from utils.config import (
    TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, ACCENT_CYAN, ACCENT_RED,
)

_CLOCK_SIZE  = 220   # px diameter of the countdown ring
_RING_WIDTH  = 13    # px stroke width
_NFB_SECONDS = 30


class _ParticleField(QWidget):
    """Subtle animated floating particles for the background."""

    _N = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._particles = []
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._init_particles()

    def _init_particles(self):
        self._particles = [
            {
                "x": random.uniform(0, 1),
                "y": random.uniform(0, 1),
                "vx": random.uniform(-0.0008, 0.0008),
                "vy": random.uniform(-0.0012, -0.0004),
                "r": random.uniform(1.5, 3.5),
                "alpha": random.uniform(0.15, 0.45),
            }
            for _ in range(self._N)
        ]

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["y"] < -0.02:
                p["y"] = 1.02
                p["x"] = random.uniform(0, 1)
            if not (-0.02 < p["x"] < 1.02):
                p["x"] = random.uniform(0, 1)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        for p in self._particles:
            c = QColor(ACCENT_GREEN)
            c.setAlphaF(p["alpha"])
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.drawEllipse(QPointF(p["x"] * w, p["y"] * h), p["r"], p["r"])
        painter.end()


class _CountdownClock(QWidget):
    """
    Circular countdown widget: gradient green→cyan depleting arc + large digit.
    Owns its own 1-Hz QTimer.
    """
    def __init__(self, duration: int = _NFB_SECONDS, parent=None):
        super().__init__(parent)
        self._duration  = duration
        self._remaining = duration

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self.setFixedSize(_CLOCK_SIZE, _CLOCK_SIZE)

    def start(self):
        self._remaining = self._duration
        self.update()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._remaining = 0
        self.update()

    def _tick(self):
        if self._remaining > 0:
            self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        m    = _RING_WIDTH / 2 + 2
        rect = QRectF(m, m, self.width() - 2*m, self.height() - 2*m)
        cx, cy = self.width() / 2, self.height() / 2

        # Background ring glow (blurred outer halo)
        glow_pen = QPen(QColor(ACCENT_GREEN), _RING_WIDTH + 8)
        glow_pen.setCapStyle(Qt.RoundCap)
        glow_c = QColor(ACCENT_GREEN)
        glow_c.setAlphaF(0.08)
        glow_pen.setColor(glow_c)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Track ring
        painter.setPen(QPen(QColor("#1E2238"), _RING_WIDTH))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Depleting gradient arc (starts full, drains clockwise)
        frac = self._remaining / self._duration if self._duration > 0 else 0
        span = int(frac * 360 * 16)
        if span > 0:
            # Use conical gradient for green→cyan sweep
            cg = QConicalGradient(cx, cy, 90)
            cg.setColorAt(0.0, QColor(ACCENT_GREEN))
            cg.setColorAt(0.5, QColor(ACCENT_CYAN))
            cg.setColorAt(1.0, QColor(ACCENT_GREEN))
            arc_pen = QPen(cg, _RING_WIDTH)
            arc_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(arc_pen)
            painter.drawArc(rect, 90 * 16, -span)

        # Subtle inner fill
        r_fill = QRadialGradient(cx, cy, (self.width() / 2) - _RING_WIDTH - 6)
        r_fill.setColorAt(0.0, QColor(20, 25, 45, 60))
        r_fill.setColorAt(1.0, QColor(10, 12, 22, 120))
        painter.setBrush(r_fill)
        painter.setPen(Qt.NoPen)
        inner_r = (self.width() / 2) - _RING_WIDTH - 4
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Centre digit
        font = QFont("Segoe UI", 1, QFont.Bold)
        font.setPointSize(52)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect, Qt.AlignCenter, str(self._remaining))

        # Seconds label
        font2 = QFont("Segoe UI", 1)
        font2.setPointSize(11)
        painter.setFont(font2)
        painter.setPen(QColor(TEXT_SECONDARY))
        sub_rect = QRectF(rect.x(), rect.y() + rect.height() * 0.62,
                          rect.width(), rect.height() * 0.2)
        painter.drawText(sub_rect, Qt.AlignCenter, "seconds left")

        painter.end()


class CalibrationScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_stage = 0
        self._mode = "quick"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(0)

        # Particle background layer (behind all content)
        self._particles = _ParticleField(self)
        self._particles.setGeometry(0, 0, 1280, 720)
        self._particles.lower()

        # Title
        title = QLabel("Calibration")
        title.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {TEXT_PRIMARY}; letter-spacing: 1px;"
        )
        title.setAlignment(Qt.AlignCenter)
        self._title_label = title
        layout.addWidget(title)
        layout.addSpacing(16)

        # Instruction
        self._instruction = QLabel("Preparing\u2026")
        self._instruction.setStyleSheet(
            f"font-size: 16px; color: {TEXT_PRIMARY}; letter-spacing: 0.3px;"
        )
        self._instruction.setAlignment(Qt.AlignCenter)
        self._instruction.setWordWrap(True)
        layout.addWidget(self._instruction)
        layout.addSpacing(28)

        # ── Countdown clock (stage 1) ──────────────────────────────────
        self._clock = _CountdownClock(_NFB_SECONDS)
        self._clock_wrap = QWidget()
        cw_layout = QVBoxLayout(self._clock_wrap)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setAlignment(Qt.AlignCenter)
        cw_layout.addWidget(self._clock, alignment=Qt.AlignHCenter)
        layout.addWidget(self._clock_wrap)
        layout.addSpacing(8)

        # ── Progress bar (stages 2-3) ──────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMinimumHeight(20)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                border: none;
                border-radius: 10px;
                background: #1E2238;
                text-align: center;
                color: {TEXT_PRIMARY};
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {ACCENT_GREEN}, stop:1 {ACCENT_CYAN});
                border-radius: 10px;
            }}
            """
        )
        self._progress_label = QLabel("0%")
        self._progress_label.setStyleSheet(
            f"font-size: 14px; color: {TEXT_SECONDARY}; font-weight: bold;"
        )
        self._progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._progress)
        layout.addSpacing(6)
        layout.addWidget(self._progress_label)
        layout.addSpacing(18)

        # Stage label
        self._stage_label = QLabel("Stage 1 / 3")
        self._stage_label.setStyleSheet(
            f"font-size: 13px; color: {TEXT_SECONDARY}; letter-spacing: 0.5px;"
        )
        self._stage_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._stage_label)
        layout.addStretch()

        # Result text
        self._result_label = QLabel("")
        self._result_label.setStyleSheet(
            f"font-size: 14px; color: {ACCENT_GREEN}; font-weight: bold;"
        )
        self._result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._result_label)
        layout.addSpacing(12)

        # Cancel button
        self._cancel_btn = QPushButton("Cancel Calibration")
        self._cancel_btn.setMinimumHeight(44)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ACCENT_RED}; "
            f"border: 1px solid {ACCENT_RED}; border-radius: 10px; "
            f"padding: 10px; font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: rgba(239,83,80,0.1); }}"
        )
        layout.addWidget(self._cancel_btn)

        # Default: clock mode visible, bar hidden
        self._show_clock_mode()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._particles.setGeometry(0, 0, self.width(), self.height())

    # ── Mode helpers ──────────────────────────────────────────────────
    def _show_clock_mode(self):
        self._clock_wrap.show()
        self._progress.hide()
        self._progress_label.hide()

    def _show_bar_mode(self):
        self._clock.stop()
        self._clock_wrap.hide()
        self._progress.show()
        self._progress_label.show()

    # ── Public API ────────────────────────────────────────────────────
    def set_stage(self, stage_num: int, description: str):
        self._current_stage = stage_num
        total_stages = 1 if self._mode == "detect" else 3
        self._stage_label.setText(f"Stage {stage_num} / {total_stages}")
        if stage_num == 1:
            self._instruction.setText(description or "Close your eyes, relax, and breathe slowly")
            self._show_clock_mode()
            self._clock.start()
            self._particles.start()
        else:
            self._particles.stop()
            self._instruction.setText(description)
            self._show_bar_mode()

    def set_progress(self, fraction: float):
        if self._current_stage == 1:
            return   # clock handles stage-1 visually
        pct = int(fraction * 100)
        self._progress.setValue(pct)
        self._progress_label.setText(f"{pct}%")

    def set_result_text(self, text: str):
        self._result_label.setText(text)

    def set_mode(self, mode: str):
        self._mode = mode or "quick"
        if self._mode == "detect":
            self._title_label.setText("Detect iAPF")
            self._stage_label.setText("Stage 1 / 1")
        else:
            self._title_label.setText("Quick iAPF Calibration")
            self._stage_label.setText("Stage 1 / 3")

    @property
    def cancel_button(self):
        return self._cancel_btn
