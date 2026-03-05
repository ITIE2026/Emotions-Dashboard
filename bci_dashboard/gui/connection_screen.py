"""
ConnectionScreen – scan, select device, view resistance & battery.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QGroupBox, QGridLayout,
    QMessageBox,
)
from PySide6.QtCore import Qt

from gui.widgets.electrode_diagram import ElectrodeDiagram
from utils.helpers import resist_color, resist_label


class ConnectionScreen(QWidget):
    """
    Signals consumed from DeviceManager:
      devices_found, connection_changed, resistance_updated, battery_updated
    Signals emitted to MainWindow:
      (none – actions are method calls that MainWindow orchestrates)
    """

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._dm = device_manager
        self._selected_serial = None
        self._build_ui()
        self._connect_signals()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)

        # Title
        title = QLabel("Connect Headband")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        # Scan button
        self._scan_btn = QPushButton("Scan Devices")
        self._scan_btn.setMinimumHeight(36)
        self._scan_btn.clicked.connect(self._on_scan)
        root.addWidget(self._scan_btn)

        # Device list
        self._device_list = QListWidget()
        self._device_list.setMinimumHeight(100)
        self._device_list.currentItemChanged.connect(self._on_selection)
        root.addWidget(self._device_list)

        # Connect button
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setEnabled(False)
        self._connect_btn.setMinimumHeight(36)
        self._connect_btn.clicked.connect(self._on_connect)
        root.addWidget(self._connect_btn)

        # ── Post-connection section (hidden initially) ────────────────
        self._post_group = QGroupBox("Connection Details")
        self._post_group.setVisible(False)
        post_layout = QVBoxLayout(self._post_group)

        # Battery
        self._battery_label = QLabel("Battery: --%")
        self._battery_label.setStyleSheet("font-size: 14px;")
        post_layout.addWidget(self._battery_label)

        # Electrode diagram
        self._diagram = ElectrodeDiagram()
        post_layout.addWidget(self._diagram)

        # Resistance grid
        resist_group = QGroupBox("Electrode Resistance")
        self._resist_grid = QGridLayout(resist_group)
        self._resist_labels: dict[str, QLabel] = {}
        for col, ch_name in enumerate(["T3", "O1", "O2", "T4"]):
            name_lbl = QLabel(ch_name)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet("font-weight: bold;")
            val_lbl = QLabel("--")
            val_lbl.setAlignment(Qt.AlignCenter)
            self._resist_grid.addWidget(name_lbl, 0, col)
            self._resist_grid.addWidget(val_lbl, 1, col)
            self._resist_labels[ch_name] = val_lbl
        post_layout.addWidget(resist_group)

        # Action buttons
        btn_row = QHBoxLayout()
        self._start_cal_btn = QPushButton("Start Calibration")
        self._start_cal_btn.setMinimumHeight(36)
        self._skip_cal_btn = QPushButton("Import Previous Calibration")
        self._skip_cal_btn.setMinimumHeight(36)
        self._skip_cal_btn.setVisible(False)
        btn_row.addWidget(self._start_cal_btn)
        btn_row.addWidget(self._skip_cal_btn)
        post_layout.addLayout(btn_row)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setMinimumHeight(32)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        post_layout.addWidget(self._disconnect_btn)

        root.addWidget(self._post_group)
        root.addStretch()

    # ── Signals ───────────────────────────────────────────────────────
    def _connect_signals(self):
        self._dm.devices_found.connect(self._on_devices_found)
        self._dm.connection_changed.connect(self._on_conn_changed)
        self._dm.resistance_updated.connect(self._on_resistance)
        self._dm.battery_updated.connect(self._on_battery)

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_scan(self):
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("Scanning…")
        self._device_list.clear()
        self._dm.scan_devices()

    def _on_devices_found(self, devices: list):
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("Scan Devices")
        self._device_list.clear()
        for name, serial, dtype in devices:
            item = QListWidgetItem(f"{name}  [{serial}]")
            item.setData(Qt.UserRole, serial)
            self._device_list.addItem(item)
        if not devices:
            self._device_list.addItem("No devices found")

    def _on_selection(self, current, previous):
        if current:
            self._selected_serial = current.data(Qt.UserRole)
            self._connect_btn.setEnabled(self._selected_serial is not None)

    def _on_connect(self):
        if not self._selected_serial:
            return
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting…")
        try:
            self._dm.connect_device(self._selected_serial)
        except Exception as exc:
            QMessageBox.critical(self, "Connection Error", str(exc))
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("Connect")

    def _on_conn_changed(self, status):
        if status == 1:  # Connected
            self._post_group.setVisible(True)
            self._connect_btn.setText("Connected ✓")
            self._scan_btn.setVisible(False)
            self._device_list.setVisible(False)
            self._connect_btn.setVisible(False)
        elif status == 0:  # Disconnected
            self._post_group.setVisible(False)
            self._scan_btn.setVisible(True)
            self._device_list.setVisible(True)
            self._connect_btn.setVisible(True)
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("Connect")

    def _on_resistance(self, data: dict):
        self._diagram.set_values(data)
        for ch_name, val_label in self._resist_labels.items():
            ohms = data.get(ch_name, float("inf"))
            val_label.setText(resist_label(ohms))
            val_label.setStyleSheet(f"color: {resist_color(ohms)}; font-size: 14px;")

    def _on_battery(self, pct: int):
        self._battery_label.setText(f"Battery: {pct}%")

    def _on_disconnect(self):
        self._dm.disconnect()

    # ── External access ───────────────────────────────────────────────
    @property
    def start_cal_button(self):
        return self._start_cal_btn

    @property
    def skip_cal_button(self):
        return self._skip_cal_btn

    def show_skip_button(self, show: bool):
        self._skip_cal_btn.setVisible(show)
