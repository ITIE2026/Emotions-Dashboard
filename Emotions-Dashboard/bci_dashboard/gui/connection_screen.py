"""
Connection screen with device selection and write options.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.electrode_diagram import ElectrodeDiagram
from utils.config import (
    ACCENT_GREEN,
    ACCENT_CYAN,
    ACCENT_RED,
    BG_CARD,
    BG_INPUT,
    BIPOLAR_CHANNELS,
    BORDER_SUBTLE,
    DEVICE_TYPE_OPTIONS,
    EEG_FILTER_ENABLED_DEFAULT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WRITE_OPTION_DEFAULTS,
    WRITE_OPTION_SPECS,
)
from utils.helpers import resist_color, resist_label
from utils.ui_effects import gradient_button_style, danger_button_style


_BTN_PRIMARY = gradient_button_style(
    ACCENT_GREEN, ACCENT_CYAN, "#0A0A14", border_radius=10, padding="10px", font_size=14
)
_BTN_DANGER = danger_button_style(ACCENT_RED)


class _DeviceRowWidget(QWidget):
    """Custom row widget for each discovered device in the scan list."""

    def __init__(self, name: str, serial: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        bars = QLabel("▮▮▮")
        bars.setStyleSheet(
            f"font-size: 11px; color: {ACCENT_GREEN}; background: transparent; letter-spacing: 1px;"
        )
        lay.addWidget(bars)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        serial_lbl = QLabel(serial)
        serial_lbl.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        text_col.addWidget(name_lbl)
        text_col.addWidget(serial_lbl)
        lay.addLayout(text_col, stretch=1)

        arrow = QLabel("›")
        arrow.setStyleSheet(
            f"font-size: 18px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        lay.addWidget(arrow)


class ConnectionScreen(QWidget):
    device_type_changed = Signal(str)
    write_options_changed = Signal(dict)
    bipolar_mode_changed = Signal(bool)
    filter_signal_changed = Signal(bool)

    def __init__(self, device_manager, parent=None):
        super().__init__(parent)
        self._dm = device_manager
        self._selected_serial = None
        self._write_option_boxes: dict[str, QCheckBox] = {}
        self._bipolar_checkbox: QCheckBox | None = None
        self._filter_checkbox: QCheckBox | None = None
        self._build_ui()
        self._connect_signals()

        self._conn_timer = QTimer(self)
        self._conn_timer.setSingleShot(True)
        self._conn_timer.setInterval(30_000)
        self._conn_timer.timeout.connect(self._on_conn_timeout)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Gradient header banner ───────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 #0D1926, stop:0.5 #112234, stop:1 #0D1926);"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 14px;"
        )
        header.setMinimumHeight(70)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 20, 12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("\U0001F9E0  Device Connection")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        subtitle = QLabel("Select device type, configure recording options, then scan and connect.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;")
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col, stretch=1)
        root.addWidget(header)

        root.addWidget(self._build_write_options_panel())

        device_row = QWidget()
        device_row.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )
        device_layout = QVBoxLayout(device_row)
        device_layout.setContentsMargins(14, 12, 14, 12)
        device_layout.setSpacing(8)

        device_label = QLabel("Select Device")
        device_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        device_layout.addWidget(device_label)

        self._device_type_combo = QComboBox()
        for label, value in DEVICE_TYPE_OPTIONS:
            self._device_type_combo.addItem(label, value)
        self._device_type_combo.setStyleSheet(
            f"QComboBox {{ background: {BG_INPUT}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 8px; padding: 8px; color: {TEXT_PRIMARY}; font-size: 13px; }}"
            f"QComboBox QAbstractItemView {{ background: {BG_INPUT}; color: {TEXT_PRIMARY}; }}"
        )
        self._device_type_combo.currentTextChanged.connect(self._on_device_type_changed)
        device_layout.addWidget(self._device_type_combo)

        options_row = QHBoxLayout()
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.setSpacing(18)

        checkbox_style = (
            f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_SUBTLE}; "
            f"background: #25293d; }}"
            "QCheckBox::indicator:checked { background: #5567a9; image: none; }"
        )

        self._bipolar_checkbox = QCheckBox("Bipolar channels")
        self._bipolar_checkbox.setChecked(bool(BIPOLAR_CHANNELS))
        self._bipolar_checkbox.setStyleSheet(checkbox_style)
        self._bipolar_checkbox.toggled.connect(self.bipolar_mode_changed)
        options_row.addWidget(self._bipolar_checkbox)

        self._filter_checkbox = QCheckBox("Filter signal")
        self._filter_checkbox.setChecked(bool(EEG_FILTER_ENABLED_DEFAULT))
        self._filter_checkbox.setStyleSheet(checkbox_style)
        self._filter_checkbox.toggled.connect(self.filter_signal_changed)
        options_row.addWidget(self._filter_checkbox)
        options_row.addStretch()

        device_layout.addLayout(options_row)
        root.addWidget(device_row)

        self._scan_btn = QPushButton("Scan Devices")
        self._scan_btn.setMinimumHeight(42)
        self._scan_btn.setStyleSheet(_BTN_PRIMARY)
        self._scan_btn.clicked.connect(self._on_scan)
        root.addWidget(self._scan_btn)

        self._device_list = QListWidget()
        self._device_list.setMinimumHeight(110)
        self._device_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 10px; color: {TEXT_PRIMARY}; font-size: 13px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 8px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: #2a2e48; }}"
        )
        self._device_list.currentItemChanged.connect(self._on_selection)
        root.addWidget(self._device_list)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setEnabled(False)
        self._connect_btn.setMinimumHeight(42)
        self._connect_btn.setStyleSheet(_BTN_PRIMARY)
        self._connect_btn.clicked.connect(self._on_connect)
        root.addWidget(self._connect_btn)

        self._post_group = QWidget()
        self._post_group.setVisible(False)
        self._post_group.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )
        post_layout = QVBoxLayout(self._post_group)
        post_layout.setContentsMargins(16, 14, 16, 14)
        post_layout.setSpacing(10)

        conn_header = QLabel("✅  Connected")
        conn_header.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ACCENT_GREEN}; background: transparent;"
        )
        post_layout.addWidget(conn_header)

        batt_row = QHBoxLayout()
        batt_row.setSpacing(8)
        self._battery_label = QLabel("Battery: --%")
        self._battery_label.setStyleSheet(
            f"font-size: 13px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        batt_row.addWidget(self._battery_label)
        batt_row.addStretch()
        post_layout.addLayout(batt_row)

        self._battery_bar = QProgressBar()
        self._battery_bar.setRange(0, 100)
        self._battery_bar.setValue(0)
        self._battery_bar.setFixedHeight(4)
        self._battery_bar.setTextVisible(False)
        self._battery_bar.setStyleSheet(
            "QProgressBar { background: #1A1F34; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #69F0AE, stop:1 #4DD0E1); border-radius: 2px; }"
        )
        post_layout.addWidget(self._battery_bar)

        self._diagram = ElectrodeDiagram()
        post_layout.addWidget(self._diagram)

        resist_container = QWidget()
        resist_container.setStyleSheet("background: transparent; border: none;")
        self._resist_grid = QGridLayout(resist_container)
        self._resist_grid.setSpacing(8)
        self._resist_labels: dict[str, QLabel] = {}
        for col, ch_name in enumerate(["T3", "O1", "O2", "T4"]):
            name_lbl = QLabel(ch_name)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet(
                f"font-weight: bold; color: {TEXT_PRIMARY}; font-size: 13px; background: transparent;"
            )
            val_lbl = QLabel("--")
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
            self._resist_grid.addWidget(name_lbl, 0, col)
            self._resist_grid.addWidget(val_lbl, 1, col)
            self._resist_labels[ch_name] = val_lbl
        post_layout.addWidget(resist_container)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setMinimumHeight(36)
        self._disconnect_btn.setStyleSheet(_BTN_DANGER)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        post_layout.addWidget(self._disconnect_btn)

        root.addWidget(self._post_group)
        root.addStretch()

    def _build_write_options_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button = QToolButton()
        button.setText("Write options")
        button.setCheckable(True)
        button.setChecked(True)
        button.setArrowType(Qt.DownArrow)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setStyleSheet(
            "QToolButton { background: #5567a9; color: #f4f6ff; border: none; "
            "padding: 8px 12px; font-size: 13px; font-weight: bold; text-align: left; }"
        )
        layout.addWidget(button)

        body = QWidget()
        body.setStyleSheet("background: transparent; border: none;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(8)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for row, (key, label) in enumerate(WRITE_OPTION_SPECS):
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(WRITE_OPTION_DEFAULTS.get(key, True)))
            checkbox.setStyleSheet(
                f"QCheckBox {{ color: {TEXT_PRIMARY}; font-size: 13px; spacing: 8px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_SUBTLE}; "
                f"background: #25293d; }}"
                "QCheckBox::indicator:checked { background: #5567a9; image: none; }"
            )
            checkbox.toggled.connect(self._emit_write_options)
            self._write_option_boxes[key] = checkbox
            grid.addWidget(checkbox, row, 0)
        body_layout.addLayout(grid)
        layout.addWidget(body)

        def toggle_panel(checked: bool):
            button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
            body.setVisible(checked)

        button.toggled.connect(toggle_panel)
        return panel

    def _connect_signals(self):
        self._dm.devices_found.connect(self._on_devices_found)
        self._dm.connection_changed.connect(self._on_conn_changed)
        self._dm.resistance_updated.connect(self._on_resistance)
        self._dm.battery_updated.connect(self._on_battery)
        self._dm.scan_error.connect(self._on_scan_error)

    @property
    def selected_device_type_label(self) -> str:
        return self._device_type_combo.currentText()

    @property
    def selected_device_type_value(self) -> int:
        return int(self._device_type_combo.currentData())

    @property
    def selected_write_options(self) -> dict:
        return {
            key: bool(box.isChecked())
            for key, box in self._write_option_boxes.items()
        }

    @property
    def selected_bipolar_channels(self) -> bool:
        return bool(self._bipolar_checkbox and self._bipolar_checkbox.isChecked())

    @property
    def selected_filter_signal(self) -> bool:
        return bool(self._filter_checkbox and self._filter_checkbox.isChecked())

    def set_filter_signal_checked(self, checked: bool):
        if self._filter_checkbox is None:
            return
        checked = bool(checked)
        if self._filter_checkbox.isChecked() == checked:
            return
        blocked = self._filter_checkbox.blockSignals(True)
        try:
            self._filter_checkbox.setChecked(checked)
        finally:
            self._filter_checkbox.blockSignals(blocked)

    def _emit_write_options(self):
        self.write_options_changed.emit(self.selected_write_options)

    def _on_device_type_changed(self, text: str):
        self.device_type_changed.emit(text)
        self._refresh_connect_state()

    def _on_scan(self):
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("Scanning...")
        self._device_list.clear()
        self._diagram.start_scan()
        self._dm.scan_devices(self.selected_device_type_value)

    def _on_devices_found(self, devices: list):
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("Scan Devices")
        self._diagram.stop_scan()
        self._device_list.clear()
        self._selected_serial = None
        for name, serial, dtype in devices:
            item = QListWidgetItem()
            item.setSizeHint(QSize(280, 58))
            item.setData(Qt.UserRole, serial)
            item.setData(Qt.UserRole + 1, dtype)
            self._device_list.addItem(item)
            self._device_list.setItemWidget(item, _DeviceRowWidget(name, serial))
        if not devices:
            empty = QListWidgetItem("No devices found")
            empty.setFlags(Qt.NoItemFlags)
            self._device_list.addItem(empty)
        self._refresh_connect_state()

    def _on_selection(self, current, previous):
        del previous
        self._selected_serial = current.data(Qt.UserRole) if current else None
        self._refresh_connect_state()

    def _on_connect(self):
        if not self._selected_serial:
            return
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting...")
        self._conn_timer.start()
        try:
            self._dm.connect_device(
                self._selected_serial,
                bipolar=self.selected_bipolar_channels,
            )
        except Exception as exc:
            self._conn_timer.stop()
            QMessageBox.critical(self, "Connection Error", str(exc))
            self._connect_btn.setText("Connect")
            self._refresh_connect_state()

    def _on_conn_changed(self, status):
        if status == 1:
            self._conn_timer.stop()
            self._diagram.stop_scan()
            self._post_group.setVisible(True)
            self._post_group.setStyleSheet(
                f"background: {BG_CARD}; border: 1px solid {ACCENT_GREEN}; "
                f"border-radius: 12px; "
                f"box-shadow: 0 0 12px rgba(105,240,174,0.25);"
            )
            self._connect_btn.setText("Connected")
            self._scan_btn.setVisible(False)
            self._device_list.setVisible(False)
            self._connect_btn.setVisible(False)
        elif status == 0:
            self._diagram.stop_scan()
            self._post_group.setVisible(False)
            self._post_group.setStyleSheet(
                f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
            )
            self._scan_btn.setVisible(True)
            self._device_list.setVisible(True)
            self._connect_btn.setVisible(True)
            self._connect_btn.setText("Connect")
            self._refresh_connect_state()

    def _on_resistance(self, data: dict):
        self._diagram.set_values(data)
        for ch_name, val_label in self._resist_labels.items():
            ohms = data.get(ch_name, float("inf"))
            val_label.setText(resist_label(ohms))
            val_label.setStyleSheet(
                f"color: {resist_color(ohms)}; font-size: 14px; background: transparent;"
            )

    def _on_battery(self, pct: int):
        self._battery_label.setText(f"Battery: {pct}%")
        self._battery_bar.setValue(max(0, min(100, int(pct))))
        if pct >= 60:
            color_css = "stop:0 #69F0AE, stop:1 #4DD0E1"
        elif pct >= 20:
            color_css = "stop:0 #FFD740, stop:1 #FFAB40"
        else:
            color_css = "stop:0 #EF5350, stop:1 #FF7043"
        self._battery_bar.setStyleSheet(
            "QProgressBar { background: #1A1F34; border: none; border-radius: 2px; }"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,{color_css}); border-radius: 2px; }}"
        )

    def _on_disconnect(self):
        self._dm.disconnect()

    def _on_conn_timeout(self):
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect")
        QMessageBox.warning(
            self,
            "Connection Timed Out",
            f"Could not connect to the selected {self.selected_device_type_label.lower()}.\n"
            "Try turning the device off and on, then scan again.",
        )
        self._refresh_connect_state()

    def _on_scan_error(self, msg: str):
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("Scan Devices")
        self._diagram.stop_scan()
        self._refresh_connect_state()
        QMessageBox.warning(self, "Scan Error", msg)

    def _refresh_connect_state(self):
        self._connect_btn.setEnabled(bool(self._selected_serial))
