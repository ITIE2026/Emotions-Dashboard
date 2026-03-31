"""
BCI Brain-to-Text Speller — type with head movement + focus dwell.

Standalone pop-up window.  A 6×7 grid of characters (A-Z, 0-9, Space,
Backspace, period, comma, question-mark, exclamation).
Navigate the highlight cursor with head tilt (gyro pitch/roll).
Dwell focus ≥ 70 for 0.6 s on a cell to select it.

Arcade/retro style matching the Aim Trainer.
"""
from __future__ import annotations

import logging
import math
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QRadialGradient,
    QLinearGradient, QGuiApplication,
)
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QApplication,
)

log = logging.getLogger(__name__)

# ── Tuning ────────────────────────────────────────────────────────────
_DEAD_ZONE = 2.0          # deg/s
_SENSITIVITY = 3.5         # cells per second per deg/s (lower = finer)
_TICK_MS = 16              # ~60 FPS
_FOCUS_THRESHOLD = 70      # attention to start dwell
_DWELL_SEC = 0.6           # seconds to dwell → select
_SELECT_COOLDOWN = 0.8     # seconds between selections
_MOVE_THRESHOLD = 0.35     # accumulated fractional cell movement before snap

# ── Grid definition (6 columns × 7 rows) ─────────────────────────────
_GRID = [
    ["A", "B", "C", "D", "E", "F"],
    ["G", "H", "I", "J", "K", "L"],
    ["M", "N", "O", "P", "Q", "R"],
    ["S", "T", "U", "V", "W", "X"],
    ["Y", "Z", "0", "1", "2", "3"],
    ["4", "5", "6", "7", "8", "9"],
    ["␣", "⌫", ".", ",", "?", "!"],
]
_ROWS = len(_GRID)
_COLS = len(_GRID[0])

# Action mapping for special cells
_ACTIONS = {
    "␣": "SPACE",
    "⌫": "BACKSPACE",
}

# ── Colors ────────────────────────────────────────────────────────────
_BG = QColor(10, 10, 20)
_CELL_BG = QColor(20, 24, 45)
_CELL_BORDER = QColor(40, 50, 80)
_CELL_HIGHLIGHT = QColor(0, 230, 118, 60)   # green glow on selected cell
_CELL_HOVER = QColor(0, 180, 255, 40)       # blue highlight on cursor cell
_CELL_TEXT = QColor(220, 220, 230)
_CELL_TEXT_HOVER = QColor(255, 255, 255)
_DWELL_COLOR = QColor("#00E676")
_FLASH_COLOR = QColor("#FFEA00")
_TEXT_OUTPUT_BG = QColor(15, 18, 30)
_FOCUS_BAR_BG = QColor(40, 40, 60)
_FOCUS_BAR_LO = QColor("#4FC3F7")
_FOCUS_BAR_HI = QColor("#00E676")


# ══════════════════════════════════════════════════════════════════════
#  Speller Grid Canvas
# ══════════════════════════════════════════════════════════════════════

class _SpellerCanvas(QWidget):
    """Custom-painted character grid with gyro cursor and focus selection."""

    def __init__(self, on_char_selected, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 450)
        self._on_char_selected = on_char_selected

        # Cursor position (fractional cell coordinates)
        self._cur_row = 0.0
        self._cur_col = 0.0
        self._snap_row = 0  # integer cell the cursor is on
        self._snap_col = 0

        # Gyro accumulator
        self._dx = 0.0
        self._dy = 0.0

        # Focus / dwell
        self._focus = 0.0
        self._dwell_start: float | None = None
        self._last_select_time = 0.0

        # Flash effect on selected cell
        self._flash_cell: tuple[int, int] | None = None
        self._flash_time = 0.0

        # Timer
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── Public API ────────────────────────────────────────────────────

    def feed_gyro(self, gx: float, gz: float):
        if abs(gz) > _DEAD_ZONE:
            self._dx += gz
        if abs(gx) > _DEAD_ZONE:
            self._dy += gx

    def feed_focus(self, attention: float):
        self._focus = attention

    # ── Timer tick ────────────────────────────────────────────────────

    def _tick(self):
        now = time.monotonic()
        dt = _TICK_MS / 1000.0

        # Apply gyro → cursor movement (fractional cells)
        move_x = self._dx * _SENSITIVITY * dt
        move_y = self._dy * _SENSITIVITY * dt
        self._dx = 0.0
        self._dy = 0.0

        self._cur_col = max(0, min(_COLS - 1, self._cur_col + move_x))
        self._cur_row = max(0, min(_ROWS - 1, self._cur_row + move_y))

        # Snap to nearest cell
        new_snap_row = int(round(self._cur_row))
        new_snap_col = int(round(self._cur_col))
        new_snap_row = max(0, min(_ROWS - 1, new_snap_row))
        new_snap_col = max(0, min(_COLS - 1, new_snap_col))

        if new_snap_row != self._snap_row or new_snap_col != self._snap_col:
            self._snap_row = new_snap_row
            self._snap_col = new_snap_col
            self._dwell_start = None  # reset dwell on cell change

        # Dwell logic
        if self._focus >= _FOCUS_THRESHOLD:
            if self._dwell_start is None:
                self._dwell_start = now
            elif (now - self._dwell_start >= _DWELL_SEC and
                  now - self._last_select_time >= _SELECT_COOLDOWN):
                self._select_current()
                self._last_select_time = now
                self._dwell_start = None
        else:
            self._dwell_start = None

        self.update()

    def _select_current(self):
        char = _GRID[self._snap_row][self._snap_col]
        self._flash_cell = (self._snap_row, self._snap_col)
        self._flash_time = time.monotonic()
        self._on_char_selected(char)

    @property
    def _dwell_frac(self) -> float:
        if self._dwell_start is None:
            return 0.0
        return min(1.0, (time.monotonic() - self._dwell_start) / _DWELL_SEC)

    # ── Painting ──────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        now = time.monotonic()

        # Background
        p.fillRect(self.rect(), _BG)

        # Cell dimensions
        pad = 12
        cell_w = (w - pad * 2) / _COLS
        cell_h = (h - pad * 2) / _ROWS
        corner = min(cell_w, cell_h) * 0.15

        for r in range(_ROWS):
            for c in range(_COLS):
                x = pad + c * cell_w
                y = pad + r * cell_h
                rect = QRectF(x + 2, y + 2, cell_w - 4, cell_h - 4)
                is_cursor = (r == self._snap_row and c == self._snap_col)
                is_flash = (self._flash_cell == (r, c) and
                            now - self._flash_time < 0.4)

                # Cell background
                if is_flash:
                    bg = _FLASH_COLOR
                elif is_cursor:
                    bg = _CELL_HOVER
                else:
                    bg = _CELL_BG

                p.setPen(QPen(_CELL_BORDER, 1))
                p.setBrush(bg)
                p.drawRoundedRect(rect, corner, corner)

                # Cursor glow
                if is_cursor and not is_flash:
                    glow = QRadialGradient(rect.center(), max(cell_w, cell_h) * 0.7)
                    gc = QColor(_DWELL_COLOR)
                    gc.setAlpha(35)
                    glow.setColorAt(0.0, gc)
                    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
                    p.setPen(Qt.NoPen)
                    p.setBrush(glow)
                    p.drawRoundedRect(rect, corner, corner)

                    # Highlight border
                    p.setPen(QPen(_DWELL_COLOR, 2))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(rect, corner, corner)

                # Character label
                char = _GRID[r][c]
                text_color = _CELL_TEXT_HOVER if is_cursor else _CELL_TEXT
                if is_flash:
                    text_color = QColor("#000")
                p.setPen(text_color)
                font_size = max(10, int(min(cell_w, cell_h) * 0.38))
                p.setFont(QFont("Consolas", font_size, QFont.Bold))
                p.drawText(rect, Qt.AlignCenter, char)

        # Dwell ring on cursor cell
        dwell = self._dwell_frac
        if dwell > 0:
            cx = pad + self._snap_col * cell_w + cell_w / 2
            cy = pad + self._snap_row * cell_h + cell_h / 2
            ring_r = min(cell_w, cell_h) * 0.42

            # Background ring
            p.setPen(QPen(QColor(60, 60, 80), 3))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

            # Progress arc
            p.setPen(QPen(_DWELL_COLOR, 3))
            span = int(dwell * 360 * 16)
            arc_rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            p.drawArc(arc_rect, 90 * 16, -span)

        # Focus bar at bottom
        bar_x, bar_y = pad, h - 20
        bar_w, bar_h = w - pad * 2, 10
        p.setPen(Qt.NoPen)
        p.setBrush(_FOCUS_BAR_BG)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)
        fill_w = int(bar_w * self._focus / 100.0)
        fc = _FOCUS_BAR_HI if self._focus >= _FOCUS_THRESHOLD else _FOCUS_BAR_LO
        p.setBrush(fc)
        p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 4, 4)

        # Focus label
        p.setPen(QColor("#aaa"))
        p.setFont(QFont("Consolas", 9))
        p.drawText(bar_x + bar_w + 6, bar_y + 9, f"{self._focus:.0f}")

        p.end()


# ══════════════════════════════════════════════════════════════════════
#  Speller Window
# ══════════════════════════════════════════════════════════════════════

class BrainSpellerWindow(QMainWindow):
    """Standalone pop-up window for BCI Brain-to-Text Speller."""

    def __init__(self):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("🖊️  BCI Brain Speller — Head Navigate + Focus Select")
        self.setMinimumSize(750, 650)
        self.resize(900, 750)
        self.setStyleSheet("QMainWindow { background: #0A0A14; }")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("background: #12132a; border-bottom: 1px solid #222;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("🖊️ BRAIN SPELLER")
        title.setStyleSheet("color: #4FC3F7; font: bold 14px 'Consolas';")
        top_layout.addWidget(title)
        top_layout.addStretch()

        clear_btn = QPushButton("CLEAR")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { background: #333; color: #ccc; font: bold 11px 'Consolas'; "
            "padding: 5px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #555; }"
        )
        clear_btn.clicked.connect(self._clear_text)
        top_layout.addWidget(clear_btn)

        copy_btn = QPushButton("📋 COPY")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(
            "QPushButton { background: #00897B; color: #fff; font: bold 11px 'Consolas'; "
            "padding: 5px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #00BFA5; }"
        )
        copy_btn.clicked.connect(self._copy_text)
        top_layout.addWidget(copy_btn)

        layout.addWidget(top_bar)

        # ── Text output field ────────────────────────────────────────
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFixedHeight(80)
        self._text_edit.setStyleSheet(
            f"QTextEdit {{ background: {_TEXT_OUTPUT_BG.name()}; color: #E0E0E0; "
            f"font: 20px 'Consolas'; border: none; padding: 12px; "
            f"border-bottom: 1px solid #222; }}"
        )
        self._text_edit.setPlaceholderText("Your text will appear here...")
        layout.addWidget(self._text_edit)

        # ── Speller grid canvas ──────────────────────────────────────
        self._canvas = _SpellerCanvas(on_char_selected=self._on_char)
        layout.addWidget(self._canvas, stretch=1)

        # ── Bottom info bar ──────────────────────────────────────────
        info_bar = QWidget()
        info_bar.setFixedHeight(28)
        info_bar.setStyleSheet("background: #12132a; border-top: 1px solid #222;")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 0, 12, 0)
        info_lbl = QLabel("Head tilt → navigate  •  Focus dwell → select  •  ␣ = Space  •  ⌫ = Backspace")
        info_lbl.setStyleSheet("color: #666; font: 10px 'Consolas';")
        info_layout.addWidget(info_lbl)
        info_layout.addStretch()
        self._char_count_lbl = QLabel("0 chars")
        self._char_count_lbl.setStyleSheet("color: #666; font: 10px 'Consolas';")
        info_layout.addWidget(self._char_count_lbl)
        layout.addWidget(info_bar)

        self._typed_text = ""

    # ── Character selection callback ─────────────────────────────────

    def _on_char(self, char: str):
        action = _ACTIONS.get(char)
        if action == "SPACE":
            self._typed_text += " "
        elif action == "BACKSPACE":
            self._typed_text = self._typed_text[:-1]
        else:
            self._typed_text += char

        self._text_edit.setPlainText(self._typed_text)
        # Scroll to end
        cursor = self._text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._text_edit.setTextCursor(cursor)
        self._char_count_lbl.setText(f"{len(self._typed_text)} chars")
        log.info("Brain Speller: selected '%s' → text length=%d", char, len(self._typed_text))

    def _clear_text(self):
        self._typed_text = ""
        self._text_edit.clear()
        self._char_count_lbl.setText("0 chars")

    def _copy_text(self):
        clipboard = QGuiApplication.clipboard()
        if clipboard and self._typed_text:
            clipboard.setText(self._typed_text)
            log.info("Brain Speller: copied %d chars to clipboard", len(self._typed_text))

    # ── Public API (called by signal dispatcher) ─────────────────────

    def on_mems(self, mems_timed_data):
        if not self.isVisible():
            return
        n = len(mems_timed_data)
        for i in range(n):
            gyro = mems_timed_data.get_gyroscope(i)
            self._canvas.feed_gyro(gyro.x, gyro.z)

    def on_emotions(self, data: dict):
        if not self.isVisible() or not data:
            return
        attention = data.get("attention", 0.0) or 0.0
        self._canvas.feed_focus(attention)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def shutdown(self):
        self._canvas._timer.stop()
        self.destroy()
