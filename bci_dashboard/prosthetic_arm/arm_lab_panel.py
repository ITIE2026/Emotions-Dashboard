from __future__ import annotations

from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prosthetic_arm.arm_state import state_label
from utils.config import ACCENT_GREEN, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


class ArmLabPanel(QWidget):
    source_changed = Signal(str)
    brainbit_toggle_requested = Signal()
    arduino_toggle_requested = Signal()
    iapf_requested = Signal()
    baseline_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wave_alpha = deque(maxlen=160)
        self._wave_beta = deque(maxlen=160)
        self._raw_buffers = [deque(maxlen=220) for _ in range(4)]
        self._source_mode = "capsule"
        self._build_ui()
        self.setStyleSheet("background: #000000; color: #f8fafc;")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 28, 44, 36)
        root.setSpacing(18)

        eyebrow = QLabel("Arm Lab")
        eyebrow.setStyleSheet(f"font-size: 13px; color: {ACCENT_GREEN};")
        title = QLabel("Advanced Prosthetic Control")
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel(
            "Switch between Capsule and BrainBit sources, watch the live metrics, and drive the prosthetic arm in "
            "simulation or through Arduino hardware."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(subtitle)

        source_row = QHBoxLayout()
        source_row.setSpacing(12)
        self._capsule_btn = self._toggle_button("Capsule")
        self._brainbit_btn = self._toggle_button("BrainBit")
        self._capsule_btn.clicked.connect(lambda: self.source_changed.emit("capsule"))
        self._brainbit_btn.clicked.connect(lambda: self.source_changed.emit("brainbit"))
        source_row.addWidget(self._capsule_btn)
        source_row.addWidget(self._brainbit_btn)
        source_row.addStretch()
        root.addLayout(source_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.brainbit_button = self._pill_button("Connect BrainBit", filled=False)
        self.brainbit_button.clicked.connect(self.brainbit_toggle_requested)
        self.iapf_button = self._pill_button("Start IAPF", filled=False)
        self.iapf_button.clicked.connect(self.iapf_requested)
        self.baseline_button = self._pill_button("Start Baseline", filled=False)
        self.baseline_button.clicked.connect(self.baseline_requested)
        self.arduino_button = self._pill_button("Connect Arduino", filled=True)
        self.arduino_button.clicked.connect(self.arduino_toggle_requested)
        self.manual_port_edit = QLineEdit()
        self.manual_port_edit.setPlaceholderText("Manual COM port, e.g. COM3")
        self.manual_port_edit.setStyleSheet(
            f"QLineEdit {{ background: #121419; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; "
            "border-radius: 18px; padding: 10px 14px; font-size: 13px; }}"
        )
        self.back_button = self._pill_button("Back", filled=False)
        controls.addWidget(self.brainbit_button)
        controls.addWidget(self.iapf_button)
        controls.addWidget(self.baseline_button)
        controls.addWidget(self.arduino_button)
        controls.addWidget(self.manual_port_edit, stretch=1)
        controls.addWidget(self.back_button)
        root.addLayout(controls)

        badges = QHBoxLayout()
        badges.setSpacing(12)
        self._source_badge = self._badge("Source", "Capsule")
        self._brainbit_badge = self._badge("BrainBit", "Idle")
        self._arm_badge = self._badge("Arduino", "Simulation")
        self._calibration_badge = self._badge("Calibration", "Waiting")
        badges.addWidget(self._source_badge)
        badges.addWidget(self._brainbit_badge)
        badges.addWidget(self._arm_badge)
        badges.addWidget(self._calibration_badge)
        root.addLayout(badges)

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        self._attention_card = self._metric_card("Attention", "0.0")
        self._relax_card = self._metric_card("Relaxation", "0.0")
        self._dominant_card = self._metric_card("Dominant", "Balanced")
        self._arm_state_card = self._metric_card("Arm State", "Open")
        cards.addWidget(self._attention_card, 0, 0)
        cards.addWidget(self._relax_card, 0, 1)
        cards.addWidget(self._dominant_card, 0, 2)
        cards.addWidget(self._arm_state_card, 0, 3)
        root.addLayout(cards)

        resist_card = QFrame()
        resist_card.setStyleSheet(
            f"QFrame {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 28px; }}"
        )
        resist_layout = QGridLayout(resist_card)
        resist_layout.setContentsMargins(18, 18, 18, 18)
        resist_layout.setHorizontalSpacing(12)
        resist_layout.setVerticalSpacing(8)
        resist_title = QLabel("Contact / Resistance")
        resist_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        resist_layout.addWidget(resist_title, 0, 0, 1, 4)
        self._resist_labels: dict[str, QLabel] = {}
        for column, channel in enumerate(("O1", "O2", "T3", "T4")):
            channel_lbl = QLabel(channel)
            channel_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
            value_lbl = QLabel("--")
            value_lbl.setAlignment(Qt.AlignCenter)
            value_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
            resist_layout.addWidget(channel_lbl, 1, column)
            resist_layout.addWidget(value_lbl, 2, column)
            self._resist_labels[channel] = value_lbl
        root.addWidget(resist_card)

        plots = QHBoxLayout()
        plots.setSpacing(14)
        self._wave_frame, self._alpha_curve, self._beta_curve = self._plot_card("Alpha / Beta Waves")
        self._raw_frame, *self._raw_curves = self._raw_plot_card("Raw EEG")
        plots.addWidget(self._wave_frame, stretch=1)
        plots.addWidget(self._raw_frame, stretch=1)
        root.addLayout(plots, stretch=1)

        self._history_lbl = QLabel("History: OPEN")
        self._history_lbl.setWordWrap(True)
        self._history_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        self._status_lbl = QLabel("Using live Capsule productivity metrics.")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("font-size: 14px; color: #f8fafc;")
        root.addWidget(self._history_lbl)
        root.addWidget(self._status_lbl)

        self.set_source_mode("capsule")

    def _toggle_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(42)
        button.setStyleSheet(
            f"QPushButton {{ background: #121419; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; "
            "border-radius: 20px; padding: 8px 18px; font-size: 13px; font-weight: bold; }}"
            "QPushButton:checked { background: #f5f3f0; color: #111111; border-color: #f5f3f0; }"
        )
        return button

    def _pill_button(self, text: str, *, filled: bool) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(46)
        if filled:
            button.setStyleSheet(
                "QPushButton { background: #f5f3f0; color: #111111; border: none; border-radius: 22px; "
                "padding: 10px 18px; font-size: 13px; font-weight: bold; }"
            )
        else:
            button.setStyleSheet(
                f"QPushButton {{ background: #121419; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; "
                "border-radius: 22px; padding: 10px 18px; font-size: 13px; font-weight: bold; }}"
            )
        return button

    def _badge(self, title: str, value: str) -> QLabel:
        label = QLabel(f"{title}: {value}")
        label.setStyleSheet(
            f"QLabel {{ background: #121419; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; "
            "border-radius: 18px; padding: 10px 14px; font-size: 12px; }}"
        )
        return label

    def _metric_card(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 28px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        value_lbl = QLabel(value)
        value_lbl.setObjectName("value")
        value_lbl.setStyleSheet("font-size: 26px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        layout.addStretch()
        return frame

    def _plot_card(self, title: str):
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 28px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title_lbl)
        plot = pg.PlotWidget()
        plot.setBackground("#121419")
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.getAxis("left").setTextPen("#94a3b8")
        plot.getAxis("bottom").setTextPen("#94a3b8")
        plot.setMouseEnabled(x=False, y=False)
        layout.addWidget(plot, stretch=1)
        alpha_curve = plot.plot(pen=pg.mkPen("#10B981", width=2))
        beta_curve = plot.plot(pen=pg.mkPen("#EF4444", width=2))
        return card, alpha_curve, beta_curve

    def _raw_plot_card(self, title: str):
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 28px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title_lbl)
        plot = pg.PlotWidget()
        plot.setBackground("#121419")
        plot.showGrid(x=True, y=True, alpha=0.12)
        plot.getAxis("left").setTextPen("#94a3b8")
        plot.getAxis("bottom").setTextPen("#94a3b8")
        plot.setMouseEnabled(x=False, y=False)
        plot.setYRange(-220, 860)
        layout.addWidget(plot, stretch=1)
        curves = [
            plot.plot(pen=pg.mkPen("#f8fafc", width=1.5)),
            plot.plot(pen=pg.mkPen("#22c55e", width=1.5)),
            plot.plot(pen=pg.mkPen("#60a5fa", width=1.5)),
            plot.plot(pen=pg.mkPen("#f59e0b", width=1.5)),
        ]
        return card, *curves

    def _card_value_label(self, frame: QFrame) -> QLabel:
        return frame.findChild(QLabel, "value")

    def set_source_mode(self, mode: str) -> None:
        self._source_mode = mode
        self._capsule_btn.setChecked(mode == "capsule")
        self._brainbit_btn.setChecked(mode == "brainbit")
        self._source_badge.setText(f"Source: {mode.title()}")
        if mode == "capsule":
            self._status_lbl.setText("Using live Capsule productivity metrics.")
        else:
            self._status_lbl.setText("BrainBit mode selected. Connect a device to begin streaming.")

    def set_backend_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    def set_metrics(self, attention: float, relaxation: float, dominant_state: str) -> None:
        self._card_value_label(self._attention_card).setText(f"{attention:.1f}")
        self._card_value_label(self._relax_card).setText(f"{relaxation:.1f}")
        self._card_value_label(self._dominant_card).setText(dominant_state)

    def set_arm_state(self, state: str, connected: bool, backend_mode: str) -> None:
        self._card_value_label(self._arm_state_card).setText(state_label(state))
        suffix = "Hardware" if connected else "Simulation"
        self._arm_badge.setText(f"Arduino: {suffix}")
        self._source_badge.setText(f"Source: {backend_mode.title()}")

    def set_brainbit_connection(self, connected: bool, status: str | None = None) -> None:
        self.brainbit_button.setText("Disconnect BrainBit" if connected else "Connect BrainBit")
        self._brainbit_badge.setText(f"BrainBit: {'Connected' if connected else 'Idle'}")
        if status:
            self._status_lbl.setText(status)

    def set_arduino_connection(self, connected: bool, status: str | None = None) -> None:
        self.arduino_button.setText("Disconnect Arduino" if connected else "Connect Arduino")
        self._arm_badge.setText(f"Arduino: {'Hardware' if connected else 'Simulation'}")
        if status:
            self._status_lbl.setText(status)

    def set_calibration(self, mode: str, progress: int) -> None:
        label = mode if progress <= 0 else f"{mode} {progress}%"
        self._calibration_badge.setText(f"Calibration: {label}")

    def update_resistance(self, data: dict) -> None:
        for channel, label in self._resist_labels.items():
            value = data.get(channel)
            if value is None:
                label.setText("--")
            elif value >= 1_000_000:
                label.setText(f"{value/1_000_000:.1f}MΩ")
            else:
                label.setText(f"{value/1_000:.0f}kΩ")

    def append_waves(self, alpha: float, beta: float) -> None:
        self._wave_alpha.append(float(alpha))
        self._wave_beta.append(float(beta))
        x_axis = np.arange(len(self._wave_alpha))
        self._alpha_curve.setData(x_axis, list(self._wave_alpha))
        self._beta_curve.setData(x_axis, list(self._wave_beta))

    def append_raw_uv(self, samples: list[tuple[float, float, float, float]]) -> None:
        for sample in samples:
            for index, value in enumerate(sample[:4]):
                offset = index * 220.0
                self._raw_buffers[index].append(float(value) + offset)
        x_axis = np.arange(max((len(buffer) for buffer in self._raw_buffers), default=0))
        for index, curve in enumerate(self._raw_curves):
            curve.setData(x_axis[: len(self._raw_buffers[index])], list(self._raw_buffers[index]))

    def clear_raw(self) -> None:
        for buffer in self._raw_buffers:
            buffer.clear()
        for curve in self._raw_curves:
            curve.setData([], [])

    def clear_waves(self) -> None:
        self._wave_alpha.clear()
        self._wave_beta.clear()
        self._alpha_curve.setData([], [])
        self._beta_curve.setData([], [])

    def set_history(self, history: list[str]) -> None:
        if not history:
            self._history_lbl.setText("History: waiting for stable arm states.")
            return
        self._history_lbl.setText("History: " + " -> ".join(state_label(item) for item in history[-8:]))
