"""
BCI Gyro Mouse Controller — system-wide cursor control via Neiry headband.

Uses gyroscope (pitch + roll) for directional movement and EEG attention
(focus dwell) for clicking.  Drives the real Windows cursor via ctypes.
"""
from __future__ import annotations

import ctypes
import logging
import time

from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QColor, QPainter, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QApplication

log = logging.getLogger(__name__)

# ── Windows user32 bindings ───────────────────────────────────────────
_user32 = ctypes.windll.user32


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _get_cursor_pos() -> tuple[int, int]:
    pt = _POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _set_cursor_pos(x: int, y: int):
    _user32.SetCursorPos(int(x), int(y))


# mouse_event flags
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


def _click():
    _user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    _user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


# ── Tuning constants ─────────────────────────────────────────────────
_DEAD_ZONE_DEG_S = 2.0        # Ignore gyro magnitude below this
_SENSITIVITY = 8.0             # Pixels per deg/s
_TICK_MS = 20                  # Cursor update interval (50 Hz)
_FOCUS_THRESHOLD = 70          # Attention level to start dwell
_DWELL_SEC = 1.5               # Seconds of sustained focus to click
_CLICK_COOLDOWN_SEC = 2.0      # Cooldown after a click


# ── Floating overlay ─────────────────────────────────────────────────

class _GyroMouseOverlay(QWidget):
    """Small always-on-top overlay showing gyro mouse state."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(160, 70)
        self._active = False
        self._focus = 0.0
        self._dwell_frac = 0.0  # 0.0 → 1.0
        self._move_to_corner()

    def _move_to_corner(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 12,
                      geo.top() + 12)

    def set_state(self, *, active: bool, focus: float = 0.0,
                  dwell_frac: float = 0.0):
        self._active = active
        self._focus = focus
        self._dwell_frac = max(0.0, min(1.0, dwell_frac))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Background
        bg = QColor(20, 24, 40, 200)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 10, 10)

        # Title
        p.setPen(QColor("#00E676") if self._active else QColor("#888"))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        status = "GYRO MOUSE ON" if self._active else "GYRO MOUSE OFF"
        p.drawText(10, 18, status)

        # Focus bar background
        bar_x, bar_y, bar_w, bar_h = 10, 28, 140, 10
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(50, 55, 75))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

        # Focus bar fill
        fill_w = int(bar_w * self._focus / 100.0)
        color = QColor("#00E676") if self._focus >= _FOCUS_THRESHOLD else QColor("#4FC3F7")
        p.setBrush(color)
        p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 4, 4)

        # Focus label
        p.setPen(QColor("#ccc"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(10, 52, f"Focus: {self._focus:.0f}")

        # Dwell ring
        if self._active and self._dwell_frac > 0:
            ring_cx, ring_cy, ring_r = 135, 52, 8
            p.setPen(QColor(80, 85, 100))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(ring_cx - ring_r, ring_cy - ring_r,
                          ring_r * 2, ring_r * 2)
            p.setPen(QColor("#00E676"))
            span = int(self._dwell_frac * 360 * 16)
            p.drawArc(ring_cx - ring_r, ring_cy - ring_r,
                      ring_r * 2, ring_r * 2,
                      90 * 16, -span)

        p.end()


# ── Main controller ──────────────────────────────────────────────────

class BciMouseController(QObject):
    """Drives the system cursor from headband gyro + EEG focus.

    Public API consumed by MainWindow / SignalDispatcher:
        toggle()          — turn on/off
        on_mems(data)     — feed raw MEMSTimedData packets
        on_emotions(data) — feed emotions dict (attention 0-100)
    """

    toggled = Signal(bool)  # emitted when active state changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False

        # Accumulated gyro deltas (thread-safe via Qt main thread)
        self._dx = 0.0  # roll  → cursor X
        self._dy = 0.0  # pitch → cursor Y

        # Focus-dwell state
        self._focus = 0.0
        self._dwell_start: float | None = None
        self._last_click_time = 0.0

        # Cursor update timer
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

        # Overlay
        self._overlay = _GyroMouseOverlay()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        return self._active

    def toggle(self):
        self._active = not self._active
        if self._active:
            self._dx = 0.0
            self._dy = 0.0
            self._dwell_start = None
            self._timer.start()
            self._overlay.show()
            log.info("Gyro mouse ENABLED")
        else:
            self._timer.stop()
            self._overlay.set_state(active=False)
            self._overlay.hide()
            log.info("Gyro mouse DISABLED")
        self.toggled.emit(self._active)

    def on_mems(self, mems_timed_data):
        """Receive raw MEMSTimedData from MemsHandler."""
        if not self._active:
            return
        n = len(mems_timed_data)
        for i in range(n):
            gyro = mems_timed_data.get_gyroscope(i)
            # Pitch (gyro.x) → cursor Y, Roll (gyro.z) → cursor X
            gx = gyro.x  # pitch: tilt forward/back
            gz = gyro.z  # roll:  tilt left/right

            if abs(gz) > _DEAD_ZONE_DEG_S:
                self._dx += gz
            if abs(gx) > _DEAD_ZONE_DEG_S:
                self._dy += gx

    def on_emotions(self, data: dict):
        """Receive emotions dict — uses 'attention' for dwell-click."""
        if not self._active or not data:
            return
        self._focus = data.get("attention", 0.0) or 0.0
        now = time.monotonic()

        if self._focus >= _FOCUS_THRESHOLD:
            if self._dwell_start is None:
                self._dwell_start = now
            else:
                elapsed = now - self._dwell_start
                if elapsed >= _DWELL_SEC:
                    # Fire click if cooldown OK
                    if (now - self._last_click_time) >= _CLICK_COOLDOWN_SEC:
                        _click()
                        log.info("Gyro mouse: CLICK (focus=%.0f, dwell=%.1fs)",
                                 self._focus, elapsed)
                        self._last_click_time = now
                    self._dwell_start = None  # reset after click attempt
        else:
            self._dwell_start = None

        # Update overlay
        dwell_frac = 0.0
        if self._dwell_start is not None:
            dwell_frac = (now - self._dwell_start) / _DWELL_SEC
        self._overlay.set_state(
            active=True, focus=self._focus, dwell_frac=dwell_frac,
        )

    # ── Internal ──────────────────────────────────────────────────────

    def _tick(self):
        """Apply accumulated gyro deltas to cursor position (50 Hz)."""
        if not self._active:
            return
        dx = self._dx * _SENSITIVITY * (_TICK_MS / 1000.0)
        dy = self._dy * _SENSITIVITY * (_TICK_MS / 1000.0)
        self._dx = 0.0
        self._dy = 0.0

        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return

        cx, cy = _get_cursor_pos()
        nx = cx + int(dx)
        ny = cy + int(dy)

        # Clamp to virtual screen bounds
        sx = _user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        sy = _user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        ox = _user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        oy = _user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        nx = max(ox, min(ox + sx - 1, nx))
        ny = max(oy, min(oy + sy - 1, ny))

        _set_cursor_pos(nx, ny)
