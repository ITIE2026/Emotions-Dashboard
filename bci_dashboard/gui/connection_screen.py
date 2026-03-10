"""
ConnectionScreen – scan, select device, view resistance & battery.
Dark-themed to match Mind Tracker BCI style.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QGroupBox, QGridLayout,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from gui.widgets.electrode_diagram import ElectrodeDiagram
from utils.helpers import resist_color, resist_label
from utils.config import (
    BG_CARD, BG_INPUT, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT_GREEN, ACCENT_RED,
)

# ── Common button styles ──────────────────────────────────────────────
_BTN_PRIMARY = (
    f"QPushButton {{ background: {ACCENT_GREEN}; color: #111; font-weight: bold; "
    f"border: none; border-radius: 10px; padding: 10px; font-size: 14px; }}"
    f"QPushButton:hover {{ background: #7DFFC4; }}"
    f"QPushButton:disabled {{ background: #333; color: #666; }}"
)
_BTN_SECONDARY = (
    f"QPushButton {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; "
    f"border: 1px solid {BORDER_SUBTLE}; border-radius: 10px; padding: 10px; font-size: 13px; }}"
    f"QPushButton:hover {{ background: #252525; }}"
)
_BTN_DANGER = (
    f"QPushButton {{ background: transparent; color: {ACCENT_RED}; "
    f"border: 1px solid {ACCENT_RED}; border-radius: 10px; padding: 8px; font-size: 13px; }}"
    f"QPushButton:hover {{ background: #2a1515; }}"
)


class ConnectionScreen(QWidget):
    """
    Signals consumed from DeviceManager:
      devices_found, connection_changed, resistance_updated, battery_updated
    """

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._dm = device_manager
        self._selected_serial = None
        self._build_ui()
        self._connect_signals()

        # Connection timeout – resets the button if the SDK never fires the
        # status=1 callback (e.g. device still paired in Windows BT stack)
        self._conn_timer = QTimer(self)
        self._conn_timer.setSingleShot(True)
        self._conn_timer.setInterval(30_000)
        self._conn_timer.timeout.connect(self._on_conn_timeout)

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Title
        title = QLabel("Connect Headband")
        title.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {TEXT_PRIMARY};")
        root.addWidget(title)

        subtitle = QLabel("Search and connect to your NeuroSDK device")
        subtitle.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        root.addWidget(subtitle)

        # Scan button
        self._scan_btn = QPushButton("Scan Devices")
        self._scan_btn.setMinimumHeight(42)
        self._scan_btn.setStyleSheet(_BTN_PRIMARY)
        self._scan_btn.clicked.connect(self._on_scan)
        root.addWidget(self._scan_btn)

        # Device list
        self._device_list = QListWidget()
        self._device_list.setMinimumHeight(100)
        self._device_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 10px; color: {TEXT_PRIMARY}; font-size: 13px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 8px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: #2a2a2a; }}"
        )
        self._device_list.currentItemChanged.connect(self._on_selection)
        root.addWidget(self._device_list)

        # Connect button
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setEnabled(False)
        self._connect_btn.setMinimumHeight(42)
        self._connect_btn.setStyleSheet(_BTN_PRIMARY)
        self._connect_btn.clicked.connect(self._on_connect)
        root.addWidget(self._connect_btn)

        # ── Post-connection section (hidden initially) ────────────────
        self._post_group = QWidget()
        self._post_group.setVisible(False)
        self._post_group.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )
        post_layout = QVBoxLayout(self._post_group)
        post_layout.setContentsMargins(16, 14, 16, 14)
        post_layout.setSpacing(10)

        conn_header = QLabel("Connected")
        conn_header.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ACCENT_GREEN}; "
            f"background: transparent; border: none;"
        )
        post_layout.addWidget(conn_header)

        # Battery
        self._battery_label = QLabel("Battery: --%")
        self._battery_label.setStyleSheet(
            f"font-size: 14px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        post_layout.addWidget(self._battery_label)

        # Electrode diagram
        self._diagram = ElectrodeDiagram()
        post_layout.addWidget(self._diagram)

        # Resistance grid
        resist_container = QWidget()
        resist_container.setStyleSheet("background: transparent; border: none;")
        self._resist_grid = QGridLayout(resist_container)
        self._resist_grid.setSpacing(8)
        self._resist_labels: dict[str, QLabel] = {}
        for col, ch_name in enumerate(["T3", "O1", "O2", "T4"]):
            name_lbl = QLabel(ch_name)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet(
                f"font-weight: bold; color: {TEXT_PRIMARY}; font-size: 13px; "
                f"background: transparent; border: none;"
            )
            val_lbl = QLabel("--")
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
            self._resist_grid.addWidget(name_lbl, 0, col)
            self._resist_grid.addWidget(val_lbl, 1, col)
            self._resist_labels[ch_name] = val_lbl
        post_layout.addWidget(resist_container)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._start_cal_btn = QPushButton("Start Calibration")
        self._start_cal_btn.setMinimumHeight(42)
        self._start_cal_btn.setStyleSheet(_BTN_PRIMARY)
        self._skip_cal_btn = QPushButton("Import Previous")
        self._skip_cal_btn.setMinimumHeight(42)
        self._skip_cal_btn.setStyleSheet(_BTN_SECONDARY)
        self._skip_cal_btn.setVisible(False)
        btn_row.addWidget(self._start_cal_btn)
        btn_row.addWidget(self._skip_cal_btn)
        post_layout.addLayout(btn_row)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setMinimumHeight(36)
        self._disconnect_btn.setStyleSheet(_BTN_DANGER)
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
        self._dm.scan_error.connect(self._on_scan_error)

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
        self._conn_timer.start()
        try:
            self._dm.connect_device(self._selected_serial)
        except Exception as exc:
            self._conn_timer.stop()
            QMessageBox.critical(self, "Connection Error", str(exc))
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("Connect")

    def _on_conn_changed(self, status):
        if status == 1:  # Connected
            self._conn_timer.stop()
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
            val_label.setStyleSheet(
                f"color: {resist_color(ohms)}; font-size: 14px; background: transparent; border: none;"
            )

    def _on_battery(self, pct: int):
        self._battery_label.setText(f"Battery: {pct}%")

    def _on_disconnect(self):
        self._dm.disconnect()
    def _on_conn_timeout(self):
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect")
        QMessageBox.warning(
            self,
            "Connection Timed Out",
            "Could not connect to the headband.\n"
            "Try turning the headband off and on, then scan again.",
        )

    def _on_scan_error(self, msg: str):
        QMessageBox.warning(self, "Scan Error", msg)
    # ── External access ───────────────────────────────────────────────
    @property
    def start_cal_button(self):
        return self._start_cal_btn

    @property
    def skip_cal_button(self):
        return self._skip_cal_btn

    def show_skip_button(self, show: bool):
        self._skip_cal_btn.setVisible(show)

