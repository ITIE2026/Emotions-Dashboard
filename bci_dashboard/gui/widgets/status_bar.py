"""
StatusBar – top bar showing connection status + battery level.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Connection indicator (coloured dot via Unicode)
        self._conn_dot = QLabel("●")
        self._conn_dot.setStyleSheet("font-size: 16px; color: #F44336;")  # red = disconnected
        layout.addWidget(self._conn_dot)

        self._device_label = QLabel("Not connected")
        self._device_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._device_label)

        layout.addStretch()

        # Battery
        self._battery_label = QLabel("🔋 --%")
        self._battery_label.setStyleSheet("font-size: 13px;")
        self._battery_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._battery_label)

    def set_connected(self, connected: bool, device_name: str = ""):
        if connected:
            self._conn_dot.setStyleSheet("font-size: 16px; color: #4CAF50;")
            self._device_label.setText(device_name or "Connected")
        else:
            self._conn_dot.setStyleSheet("font-size: 16px; color: #F44336;")
            self._device_label.setText("Disconnected")

    def set_battery(self, pct: int):
        icon = "🔋"
        if pct < 20:
            icon = "🪫"
        self._battery_label.setText(f"{icon} {pct}%")
