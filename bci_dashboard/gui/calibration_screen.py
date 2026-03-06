"""
CalibrationScreen – progress UI for the 3-stage calibration.
Dark-themed to match Mind Tracker BCI style.

Stage 1 (NFB, 30 s): shows a circular countdown clock.
Stages 2+3: shows a progress bar.
"""
import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton,
)
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont

from utils.config import (
    TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, ACCENT_RED,
)

_CLOCK_SIZE  = 200   # px diameter of the countdown ring
_RING_WIDTH  = 12    # px stroke width
_NFB_SECONDS = 30


class _CountdownClock(QWidget):
    """
    Circular countdown widget: a depleting green arc + large digit in centre.
    Owns its own 1-Hz QTimer so it is fully self-contained.
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

        # Background ring
        painter.setPen(QPen(QColor("#2A2A2A"), _RING_WIDTH))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Depleting arc (starts full, drains clockwise)
        frac = self._remaining / self._duration if self._duration > 0 else 0
        span = int(frac * 360 * 16)
        if span > 0:
            pen = QPen(QColor(ACCENT_GREEN), _RING_WIDTH)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -span)   # negative = clockwise

        # Centre digit
        font = QFont()
        font.setPointSize(48)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect, Qt.AlignCenter, str(self._remaining))

        painter.end()


class CalibrationScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_stage = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(0)

        # Title
        title = QLabel("Calibration")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(16)

        # Instruction
        self._instruction = QLabel("Preparing…")
        self._instruction.setStyleSheet(f"font-size: 16px; color: {TEXT_PRIMARY};")
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
        self._progress.setMinimumHeight(18)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                border: none;
                border-radius: 9px;
                background: #222;
                text-align: center;
                color: {TEXT_PRIMARY};
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT_GREEN};
                border-radius: 9px;
            }}
            """
        )
        self._progress_label = QLabel("0%")
        self._progress_label.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        self._progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._progress)
        layout.addSpacing(6)
        layout.addWidget(self._progress_label)
        layout.addSpacing(18)

        # Stage label
        self._stage_label = QLabel("Stage 1 / 3")
        self._stage_label.setStyleSheet("font-size: 13px; color: #666;")
        self._stage_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._stage_label)
        layout.addStretch()

        # Result text
        self._result_label = QLabel("")
        self._result_label.setStyleSheet(f"font-size: 14px; color: {ACCENT_GREEN};")
        self._result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._result_label)
        layout.addSpacing(12)

        # Cancel button
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMinimumHeight(42)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ACCENT_RED}; "
            f"border: 1px solid {ACCENT_RED}; border-radius: 10px; "
            f"padding: 10px; font-size: 14px; }}"
            f"QPushButton:hover {{ background: #2a1515; }}"
        )
        layout.addWidget(self._cancel_btn)

        # Default: clock mode visible, bar hidden
        self._show_clock_mode()

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
        self._stage_label.setText(f"Stage {stage_num} / 3")
        if stage_num == 1:
            self._instruction.setText("Close your eyes and relax")
            self._show_clock_mode()
            self._clock.start()
        else:
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

    @property
    def cancel_button(self):
        return self._cancel_btn
