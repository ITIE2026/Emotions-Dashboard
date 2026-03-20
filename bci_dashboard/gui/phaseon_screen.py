"""
Native Phaseon page embedded inside the dashboard application.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.phaseon_widgets import (
    MetricMeterCard,
    ResistanceGridWidget,
    StatusSummaryCard,
)
from utils.config import ACCENT_GREEN, BG_NAV, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


class PhaseonScreen(QWidget):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self._runtime = runtime
        self._build_ui()
        self._wire_runtime()
        self._apply_state(self._runtime.snapshot_state())
        self._apply_metrics(self._runtime.snapshot_metrics())
        self._resistance_grid.set_resistances(self._runtime.snapshot_resistances())

    def _build_ui(self):
        self.setStyleSheet("background: #000000; color: #f8fafc;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")
        root.addWidget(scroll)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setMaximumWidth(1100)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(36, 24, 36, 36)
        layout.setSpacing(18)

        title = QLabel("Phaseon")
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel(
            "Live neurofeedback view using the current dashboard pipeline, with shared BrainBit and Arduino controls."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QFrame()
        controls.setStyleSheet(
            f"QFrame {{ background: {BG_NAV}; border: 1px solid {BORDER_SUBTLE}; border-radius: 24px; }}"
        )
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(18, 14, 18, 14)
        controls_layout.setSpacing(12)
        controls_layout.addWidget(self._field_label("Source"))
        self._source_combo = QComboBox()
        self._source_combo.addItem("Capsule", "capsule")
        self._source_combo.addItem("BrainBit", "brainbit")
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        self._source_combo.setStyleSheet(self._input_style())
        controls_layout.addWidget(self._source_combo)

        self._brainbit_btn = self._action_button("Connect BrainBit", accent="#7cc7ff", fill="#152336")
        self._brainbit_btn.clicked.connect(lambda _checked=False: self._runtime.toggle_brainbit_connection())
        controls_layout.addWidget(self._brainbit_btn)

        controls_layout.addWidget(self._field_label("Port"))
        self._arduino_port = QLineEdit()
        self._arduino_port.setPlaceholderText("Auto / COM3")
        self._arduino_port.setStyleSheet(self._input_style())
        self._arduino_port.setFixedWidth(140)
        controls_layout.addWidget(self._arduino_port)

        self._arduino_btn = self._action_button("Connect Arduino", accent=ACCENT_GREEN, fill="#153225")
        self._arduino_btn.clicked.connect(self._on_toggle_arduino)
        controls_layout.addWidget(self._arduino_btn)

        self._iapf_btn = self._action_button("BrainBit iAPF", accent="#ffcc66", fill="#322817")
        self._iapf_btn.clicked.connect(lambda _checked=False: self._runtime.request_brainbit_iapf())
        controls_layout.addWidget(self._iapf_btn)

        self._baseline_btn = self._action_button("BrainBit Baseline", accent="#ffcc66", fill="#322817")
        self._baseline_btn.clicked.connect(lambda _checked=False: self._runtime.request_brainbit_baseline())
        controls_layout.addWidget(self._baseline_btn)

        controls_layout.addStretch()
        layout.addWidget(controls)

        self._status_lbl = QLabel("Capsule standby.")
        self._status_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._status_lbl)

        cards = QGridLayout()
        cards.setHorizontalSpacing(14)
        cards.setVerticalSpacing(14)

        self._metric_card = MetricMeterCard()
        cards.addWidget(self._metric_card, 0, 0, 2, 1)

        self._device_card = StatusSummaryCard("Device")
        cards.addWidget(self._device_card, 0, 1)

        self._session_card = StatusSummaryCard("Session")
        cards.addWidget(self._session_card, 0, 2)

        self._arm_card = StatusSummaryCard("Arm / Control")
        cards.addWidget(self._arm_card, 1, 1)

        self._source_card = StatusSummaryCard("Source Status")
        cards.addWidget(self._source_card, 1, 2)
        layout.addLayout(cards)

        lower = QGridLayout()
        lower.setHorizontalSpacing(14)
        lower.setVerticalSpacing(14)
        self._resistance_grid = ResistanceGridWidget()
        lower.addWidget(self._resistance_grid, 0, 0)

        phaseon_note = StatusSummaryCard("Signal Ownership")
        phaseon_note.value_label.setText("Dashboard")
        phaseon_note.detail_label.setText(
            "Raw EEG and live rhythm plots stay on the main Dashboard.\n"
            "Phaseon now uses lightweight summary/control state only."
        )
        lower.addWidget(phaseon_note, 0, 1)
        layout.addLayout(lower)

        outer.addWidget(panel, alignment=Qt.AlignHCenter)
        scroll.setWidget(container)

    def _wire_runtime(self):
        self._runtime.state_changed.connect(self._apply_state)
        self._runtime.metrics_changed.connect(self._apply_metrics)
        self._runtime.resistance_changed.connect(self._resistance_grid.set_resistances)

    def _apply_state(self, state: dict):
        state = dict(state or {})
        source_mode = state.get("source_mode", "capsule")
        index = 1 if source_mode == "brainbit" else 0
        if self._source_combo.currentIndex() != index:
            self._source_combo.blockSignals(True)
            self._source_combo.setCurrentIndex(index)
            self._source_combo.blockSignals(False)

        battery = state.get("battery_pct")
        battery_text = "?" if battery in (None, "") else f"{battery}%"
        capsule_connected = bool(state.get("capsule_connected"))
        brainbit_connected = bool(state.get("brainbit_connected"))
        arduino_connected = bool(state.get("arduino_connected"))

        self._status_lbl.setText(str(state.get("source_status") or "Waiting for live data."))
        self._device_card.value_label.setText("Connected" if capsule_connected else "Standby")
        self._device_card.detail_label.setText(
            f"Battery: {battery_text}\n"
            f"Serial: {state.get('serial') or '--'}\n"
            f"Mode: {state.get('mode') or 'Idle'}"
        )

        self._session_card.value_label.setText(state.get("session_id") or "No session")
        channel_names = ", ".join(state.get("channel_names") or []) or "--"
        self._session_card.detail_label.setText(
            f"Sample rate: {float(state.get('sample_rate_hz') or 250.0):.1f} Hz\n"
            f"Channels: {channel_names}"
        )

        self._arm_card.value_label.setText(str(state.get("arm_state") or "OPEN"))
        self._arm_card.detail_label.setText(
            f"Arduino: {'Connected' if arduino_connected else 'Simulation'}\n"
            f"Dominant: {state.get('dominant_state') or 'Balanced'}"
        )

        active_connected = brainbit_connected if source_mode == "brainbit" else capsule_connected
        self._source_card.value_label.setText("Live" if active_connected else "Idle")
        self._source_card.detail_label.setText(
            f"Source: {source_mode.title()}\n"
            f"BrainBit: {'Connected' if brainbit_connected else 'Disconnected'}"
        )

        self._brainbit_btn.setText("Disconnect BrainBit" if brainbit_connected else "Connect BrainBit")
        self._arduino_btn.setText("Disconnect Arduino" if arduino_connected else "Connect Arduino")

    def _apply_metrics(self, metrics: dict):
        metrics = dict(metrics or {})
        attention = float(metrics.get("attention", 0.0) or 0.0)
        relaxation = float(metrics.get("relaxation", 0.0) or 0.0)
        dominant_state = str(metrics.get("dominant_state") or "Balanced")
        self._metric_card.set_metrics(attention, relaxation, dominant_state)

    def _on_source_changed(self, *_args):
        source_mode = self._source_combo.currentData()
        self._runtime.set_source_mode(source_mode)

    def _on_toggle_arduino(self, *_args):
        port = self._arduino_port.text().strip() or None
        self._runtime.toggle_arduino_connection(port)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        return label

    def _input_style(self) -> str:
        return (
            f"QComboBox, QLineEdit {{ background: #151a24; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; "
            "border-radius: 10px; padding: 7px 10px; font-size: 13px; }}"
        )

    def _action_button(self, text: str, *, accent: str, fill: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: {fill}; color: {accent}; border: 1px solid {accent}; border-radius: 12px; "
            "padding: 8px 14px; font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {accent}; color: #111111; }}"
        )
        return btn
