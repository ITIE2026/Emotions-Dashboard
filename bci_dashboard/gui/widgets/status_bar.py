"""
StatusBar – top bar showing connection status + battery level.
Dark themed to match Mind Tracker BCI style.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from utils.config import BG_NAV, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, ACCENT_RED


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_NAV}; border-bottom: 1px solid #1E1E1E;")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        # Connection indicator (coloured dot via Unicode)
        self._conn_dot = QLabel("●")
        self._conn_dot.setStyleSheet(f"font-size: 14px; color: {ACCENT_RED}; border: none;")
        layout.addWidget(self._conn_dot)

        self._device_label = QLabel("Not connected")
        self._device_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY}; border: none;")
        layout.addWidget(self._device_label)

        layout.addStretch()

        # Battery
        self._battery_label = QLabel("🔋 --%")
        self._battery_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY}; border: none;")
        self._battery_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._battery_label)

    def set_connected(self, connected: bool, device_name: str = ""):
        if connected:
            self._conn_dot.setStyleSheet(f"font-size: 14px; color: {ACCENT_GREEN}; border: none;")
            self._device_label.setText(device_name or "Connected")
            self._device_label.setStyleSheet(f"font-size: 13px; color: {TEXT_PRIMARY}; border: none;")
        else:
            self._conn_dot.setStyleSheet(f"font-size: 14px; color: {ACCENT_RED}; border: none;")
            self._device_label.setText("Disconnected")
            self._device_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY}; border: none;")

    def set_battery(self, pct: int):
        icon = "🔋"
        if pct < 20:
            icon = "🪫"
        self._battery_label.setText(f"{icon} {pct}%")
