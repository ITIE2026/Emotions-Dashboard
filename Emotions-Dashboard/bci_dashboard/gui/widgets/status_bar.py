"""
StatusBar – top bar showing connection status + battery level.
Premium dark-themed with pulsing live dot, gradient background,
color-coded battery bar, and optional EEG quality chip.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer

from utils.config import BG_NAV, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, ACCENT_RED


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 #0C0F1E, stop:0.5 #131624, stop:1 #0C0F1E);"
            " border-bottom: 1px solid #1A1F34;"
        )
        self._pulse_on = True
        self._connected = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(600)
        self._pulse_timer.timeout.connect(self._toggle_pulse)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 5, 14, 5)
        layout.setSpacing(10)

        # Pulsing connection dot
        self._conn_dot = QLabel("●")
        self._conn_dot.setStyleSheet(f"font-size: 13px; color: {ACCENT_RED}; border: none;")
        layout.addWidget(self._conn_dot)

        self._device_label = QLabel("Not connected")
        self._device_label.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY}; border: none;")
        layout.addWidget(self._device_label)

        layout.addStretch()

        # EEG quality chip (hidden by default)
        self._eeg_chip = QLabel("EEG ●")
        self._eeg_chip.setVisible(False)
        self._eeg_chip.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {ACCENT_GREEN}; border: none; "
            f"background: rgba(105,240,174,0.10); border-radius: 8px; padding: 2px 10px;"
        )
        layout.addWidget(self._eeg_chip)

        # Battery column (label above thin bar)
        batt_col = QWidget()
        batt_col.setStyleSheet("background: transparent;")
        batt_v = QHBoxLayout(batt_col)
        batt_v.setContentsMargins(0, 0, 0, 0)
        batt_v.setSpacing(6)

        self._battery_label = QLabel("🔋 --%")
        self._battery_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; border: none;"
        )
        self._battery_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        batt_v.addWidget(self._battery_label)

        self._battery_bar = QFrame()
        self._battery_bar.setFixedSize(46, 4)
        self._battery_bar.setStyleSheet(
            "background: #1A1F34; border-radius: 2px;"
        )
        self._battery_fill = QFrame(self._battery_bar)
        self._battery_fill.setFixedHeight(4)
        self._battery_fill.setFixedWidth(0)
        self._battery_fill.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #69F0AE,stop:1 #4DD0E1);"
            " border-radius: 2px;"
        )
        batt_v.addWidget(self._battery_bar)

        layout.addWidget(batt_col)

    # ── Pulse animation ────────────────────────────────────────────────

    def _toggle_pulse(self):
        self._pulse_on = not self._pulse_on
        if self._connected:
            color = ACCENT_GREEN if self._pulse_on else "rgba(105,240,174,0.35)"
        else:
            color = ACCENT_RED
        self._conn_dot.setStyleSheet(f"font-size: 13px; color: {color}; border: none;")

    # ── Public API ─────────────────────────────────────────────────────

    def set_connected(self, connected: bool, device_name: str = ""):
        self._connected = bool(connected)
        if connected:
            self._pulse_timer.start()
            self._conn_dot.setStyleSheet(
                f"font-size: 13px; color: {ACCENT_GREEN}; border: none;"
            )
            self._device_label.setText(device_name or "Connected")
            self._device_label.setStyleSheet(
                f"font-size: 12px; color: {TEXT_PRIMARY}; border: none;"
            )
        else:
            self._pulse_timer.stop()
            self._conn_dot.setStyleSheet(
                f"font-size: 13px; color: {ACCENT_RED}; border: none;"
            )
            self._device_label.setText("Disconnected")
            self._device_label.setStyleSheet(
                f"font-size: 12px; color: {TEXT_SECONDARY}; border: none;"
            )

    def set_battery(self, pct: int):
        icon = "🔋"
        if pct < 20:
            icon = "🪫"
        self._battery_label.setText(f"{icon} {pct}%")
        if pct >= 60:
            text_color = "#69F0AE"
            fill_css = "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #69F0AE,stop:1 #4DD0E1);"
        elif pct >= 20:
            text_color = "#FFD740"
            fill_css = "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FFD740,stop:1 #FFAB40);"
        else:
            text_color = "#EF5350"
            fill_css = "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #EF5350,stop:1 #FF7043);"
        self._battery_label.setStyleSheet(
            f"font-size: 12px; color: {text_color}; border: none;"
        )
        fill_w = max(0, min(46, int(46 * pct / 100)))
        self._battery_fill.setFixedWidth(fill_w)
        self._battery_fill.setStyleSheet(f"{fill_css} border-radius: 2px;")

    def set_eeg_quality(self, level: str):
        """level: 'good' | 'noise' | 'off'"""
        level = level.lower()
        if level == "good":
            self._eeg_chip.setText("EEG ● GOOD")
            self._eeg_chip.setStyleSheet(
                "font-size: 10px; font-weight: bold; color: #69F0AE; border: none; "
                "background: rgba(105,240,174,0.10); border-radius: 8px; padding: 2px 10px;"
            )
            self._eeg_chip.setVisible(True)
        elif level == "noise":
            self._eeg_chip.setText("EEG ● NOISE")
            self._eeg_chip.setStyleSheet(
                "font-size: 10px; font-weight: bold; color: #FFAB40; border: none; "
                "background: rgba(255,171,64,0.10); border-radius: 8px; padding: 2px 10px;"
            )
            self._eeg_chip.setVisible(True)
        else:
            self._eeg_chip.setVisible(False)
