"""
DeviceStatusMonitor – polls connection / battery and handles
reconnection attempts when the headband goes out of range.
"""
from PySide6.QtCore import QObject, QTimer, Signal

from utils.config import (
    STATUS_POLL_INTERVAL_MS,
    RECONNECT_INTERVAL_MS,
    MAX_RECONNECT_ATTEMPTS,
    BIPOLAR_CHANNELS,
)


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

        # ── Poll timer ────────────────────────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(STATUS_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

        # ── Reconnect timer ──────────────────────────────────────────
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(RECONNECT_INTERVAL_MS)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        # Listen for connection signal from DeviceManager
        self._dm.connection_changed.connect(self._on_connection_changed)

    # ── Public ────────────────────────────────────────────────────────
    def start(self):
        self._was_connected = True
        self._poll_timer.start()

    def stop(self):
        self._poll_timer.stop()
        self._reconnect_timer.stop()

    # ── Polling ───────────────────────────────────────────────────────
    def _poll(self):
        battery = self._dm.get_battery()
        if battery >= 0:
            self.battery_polled.emit(battery)

        if self._was_connected and not self._dm.is_connected():
            self._was_connected = False
            self._start_reconnect()

    def _on_connection_changed(self, status):
        if status == 0 and self._was_connected:  # Disconnected
            self._was_connected = False
            self._start_reconnect()
        elif status == 1:  # Connected
            if self._reconnecting:
                self._reconnecting = False
                self._reconnect_timer.stop()
                self.reconnection_succeeded.emit()
            self._was_connected = True

    # ── Reconnection ─────────────────────────────────────────────────
    def _start_reconnect(self):
        if self._reconnecting:
            return
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
                self._dm.connect_device(serial, BIPOLAR_CHANNELS)
        except Exception:
            pass  # will retry on next timer tick
