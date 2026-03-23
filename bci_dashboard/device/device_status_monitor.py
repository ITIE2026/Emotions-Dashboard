"""
DeviceStatusMonitor – polls connection / battery and handles
reconnection attempts when the headband goes out of range.

Disconnect is only declared after MISS_THRESHOLD consecutive poll
failures, so brief SDK state transitions (e.g. end-of-calibration)
do not falsely trigger reconnection logic.
"""
from PySide6.QtCore import QObject, QTimer, Signal

from utils.config import (
    STATUS_POLL_INTERVAL_MS,
    RECONNECT_INTERVAL_MS,
    MAX_RECONNECT_ATTEMPTS,
)

# How many consecutive missed polls before we declare a real disconnect
_MISS_THRESHOLD = 3
# Grace period after start() before first poll fires (ms)
_STARTUP_GRACE_MS = 6000


class DeviceStatusMonitor(QObject):
    """Heartbeat monitor with automatic reconnection logic."""

    disconnection_detected = Signal()
    reconnection_attempted = Signal(int)   # attempt number
    reconnection_succeeded = Signal()
    reconnection_failed = Signal()
    battery_polled = Signal(int)

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._dm = device_manager
        self._was_connected = False
        self._reconnecting = False
        self._attempt = 0
        self._miss_count = 0          # consecutive poll misses

        # ── Poll timer ────────────────────────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(STATUS_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

        # ── Reconnect timer ──────────────────────────────────────────
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(RECONNECT_INTERVAL_MS)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        # ── Startup grace timer (one-shot) ───────────────────────────
        self._grace_timer = QTimer(self)
        self._grace_timer.setSingleShot(True)
        self._grace_timer.setInterval(_STARTUP_GRACE_MS)
        self._grace_timer.timeout.connect(self._after_grace)

        # Listen for reconnection success from DeviceManager
        self._dm.connection_changed.connect(self._on_connection_changed)

    # ── Public ────────────────────────────────────────────────────────
    def start(self):
        """Begin monitoring – delayed by grace period to ignore
        transient SDK events right after calibration ends."""
        self._was_connected = True
        self._miss_count = 0
        self._grace_timer.start()   # poll timer starts after grace period

    def stop(self):
        self._grace_timer.stop()
        self._poll_timer.stop()
        self._reconnect_timer.stop()

    # ── Grace expiry ─────────────────────────────────────────────────
    def _after_grace(self):
        """Called once the startup grace period expires – now safe to poll."""
        if self._dm.is_connected():
            self._was_connected = True
            self._miss_count = 0
            self._poll_timer.start()
        else:
            # Device already gone – treat as immediate disconnect
            self._was_connected = False
            self._start_reconnect()

    # ── Polling ───────────────────────────────────────────────────────
    def _poll(self):
        battery = self._dm.get_battery()
        if battery >= 0:
            self.battery_polled.emit(battery)
            self._miss_count = 0    # successful comms = reset counter

        if self._dm.is_connected():
            self._miss_count = 0
        else:
            self._miss_count += 1
            if self._miss_count >= _MISS_THRESHOLD:
                self._miss_count = 0
                self._was_connected = False
                self._start_reconnect()

    def _on_connection_changed(self, status):
        """Only use this signal to confirm successful reconnections."""
        if status == 1 and self._reconnecting:
            self._reconnecting = False
            self._reconnect_timer.stop()
            self._was_connected = True
            self._miss_count = 0
            self.reconnection_succeeded.emit()

    # ── Reconnection ─────────────────────────────────────────────────
    def _start_reconnect(self):
        if self._reconnecting:
            return
        self._poll_timer.stop()
        self._reconnecting = True
        self._attempt = 0
        self.disconnection_detected.emit()
        self._reconnect_timer.start()

    def _try_reconnect(self):
        self._attempt += 1
        self.reconnection_attempted.emit(self._attempt)

        if self._attempt > MAX_RECONNECT_ATTEMPTS:
            self._reconnect_timer.stop()
            self._reconnecting = False
            self.reconnection_failed.emit()
            return

        try:
            serial = self._dm.device_serial
            if serial:
                self._dm.connect_device(serial, self._dm.active_bipolar_mode)
        except Exception:
            pass  # will retry on next timer tick

