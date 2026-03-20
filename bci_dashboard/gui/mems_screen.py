"""
Dedicated MEMS and rhythms screen.
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.raw_metrics import aggregate_band_history
from gui.widgets.raw_data_widgets import (
    CollapsibleSection,
    RhythmsPieChartWidget,
    TriAxisChartWidget,
)
from utils.config import BG_CARD, BG_PRIMARY, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


BAND_HISTORY_POINTS = 5000
MEMS_WINDOW_SAMPLES = 2000
MEMS_WINDOW_SEC = 5.0


class MemsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._streaming_active = False
        self._session_id = str(uuid.uuid4())
        self._session_start = datetime.now()
        self._session_start_wall = time.time()
        self._mems_time_origin = None
        self._latest_band_powers = {}
        self._band_history = deque(maxlen=BAND_HISTORY_POINTS)
        self._last_nonempty_band_history = None
        self._mems_buffers = {
            "accelerometer": self._new_vector_buffer(),
            "gyroscope": self._new_vector_buffer(),
        }
        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self._refresh_live_panels)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        info_bar = QWidget()
        info_bar.setStyleSheet(
            f"background: {BG_CARD}; border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(16, 8, 16, 8)
        info_layout.setSpacing(20)

        title = QLabel("MEMS and Rhythms")
        title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._status_label = QLabel("Status: Idle")
        self._status_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._device_label = QLabel("Device: --")
        self._device_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._mode_label = QLabel("Mode: Unspecified")
        self._mode_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._battery_label = QLabel("Battery: ?")
        self._battery_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._session_label = QLabel(f"Session ID: {self._session_id}")
        self._session_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        info_layout.addWidget(title)
        info_layout.addStretch()
        for widget in (
            self._status_label,
            self._device_label,
            self._mode_label,
            self._battery_label,
            self._session_label,
        ):
            info_layout.addWidget(widget)
        outer.addWidget(info_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {BG_PRIMARY}; }}"
        )
        body = QWidget()
        body.setStyleSheet(f"background: {BG_PRIMARY};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(8)

        self._sections = {}

        accel_section = CollapsibleSection("Accelerometer", expanded=True)
        self._sections["accelerometer"] = accel_section
        self._accel_chart = TriAxisChartWidget("Accelerometer")
        self._accel_chart.set_session_start(self._session_start_wall)
        accel_section.content_layout.addWidget(self._accel_chart)
        body_layout.addWidget(accel_section)

        gyro_section = CollapsibleSection("Gyroscope", expanded=True)
        self._sections["gyroscope"] = gyro_section
        self._gyro_chart = TriAxisChartWidget("Gyroscope")
        self._gyro_chart.set_session_start(self._session_start_wall)
        gyro_section.content_layout.addWidget(self._gyro_chart)
        body_layout.addWidget(gyro_section)

        rhythms_section = CollapsibleSection("Rhythms Diagram", expanded=True)
        self._sections["rhythms_diagram"] = rhythms_section
        rhythm_controls = QHBoxLayout()
        rhythm_controls.setContentsMargins(10, 8, 10, 0)
        rhythm_controls.setSpacing(8)
        time_scale_lbl = QLabel("Time Scale")
        time_scale_lbl.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent; font-weight: bold;"
        )
        self._rhythm_scale_combo = QComboBox()
        self._rhythm_scale_combo.addItems(["1min", "5min", "15min"])
        self._rhythm_scale_combo.setCurrentText("1min")
        self._rhythm_scale_combo.currentTextChanged.connect(
            lambda _text: self._update_rhythms_diagram()
        )
        self._rhythm_scale_combo.setStyleSheet(
            f"QComboBox {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; padding: 4px 8px; }}"
        )
        rhythm_controls.addWidget(time_scale_lbl)
        rhythm_controls.addWidget(self._rhythm_scale_combo)
        rhythm_controls.addStretch()
        rhythms_section.content_layout.addLayout(rhythm_controls)
        self._rhythms_pie = RhythmsPieChartWidget()
        rhythms_section.content_layout.addWidget(self._rhythms_pie)
        body_layout.addWidget(rhythms_section)
        body_layout.addStretch()

        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, stretch=1)
        self._update_rhythms_diagram()

    def set_streaming_active(self, active: bool):
        self._streaming_active = bool(active)
        self._status_label.setText("Status: Live" if self._streaming_active else "Status: Idle")
        if self._streaming_active:
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
            return
        self._refresh_timer.stop()
        self._clear_vector_buffers()
        self._refresh_mems_charts()

    def set_session_info(self, connected: bool = False, serial: str = "--"):
        state = "Connected" if connected else "Disconnected"
        self._device_label.setText(f"Device: {state} | {serial or '--'}")

    def set_mode(self, mode_str: str):
        self._mode_label.setText(f"Mode: {mode_str}")

    def set_battery(self, pct: int):
        try:
            pct = int(pct)
        except (TypeError, ValueError):
            pct = -1
        if 0 <= pct <= 100:
            self._battery_label.setText(f"Battery: {pct}%")
            return
        self._battery_label.setText("Battery: ?")

    def reset_session(self, session_id: str | None = None):
        self._session_id = session_id or str(uuid.uuid4())
        self._session_start = datetime.now()
        self._session_start_wall = time.time()
        self._mems_time_origin = None
        self._latest_band_powers = {}
        self._band_history.clear()
        self._last_nonempty_band_history = None
        self._clear_vector_buffers()
        self._session_label.setText(f"Session ID: {self._session_id}")
        self._accel_chart.set_session_start(self._session_start_wall)
        self._gyro_chart.set_session_start(self._session_start_wall)
        self._refresh_mems_charts()
        self._update_rhythms_diagram()

    def show_section(self, section_id: str):
        section = self._sections.get(section_id)
        if section is None:
            return
        section.set_expanded(True)
        if section_id == "rhythms_diagram":
            self._update_rhythms_diagram()
        QTimer.singleShot(
            0,
            lambda: self._scroll.ensureWidgetVisible(section, 0, 24),
        )

    def on_mems(self, mems_timed_data):
        if not self._streaming_active:
            return
        try:
            for idx in range(len(mems_timed_data)):
                sample_ts = float(mems_timed_data.get_timestamp(idx)) / 1000.0
                mapped_ts = self._map_sdk_time(sample_ts)
                accel = mems_timed_data.get_accelerometer(idx)
                gyro = mems_timed_data.get_gyroscope(idx)
                self._append_vector_sample(
                    self._mems_buffers["accelerometer"],
                    mapped_ts,
                    (float(accel.x), float(accel.y), float(accel.z)),
                )
                self._append_vector_sample(
                    self._mems_buffers["gyroscope"],
                    mapped_ts,
                    (float(gyro.x), float(gyro.y), float(gyro.z)),
                )
        except Exception:
            return

    def on_band_powers(self, band_powers: dict):
        self._latest_band_powers = {
            key: float(value)
            for key, value in (band_powers or {}).items()
        }
        if any(float(value) > 0.0 for value in self._latest_band_powers.values()):
            self._band_history.append((time.monotonic(), dict(self._latest_band_powers)))
        self._update_rhythms_diagram()

    def _refresh_live_panels(self):
        if not self._streaming_active:
            return
        self._refresh_mems_charts()

    def _update_rhythms_diagram(self):
        window_lookup = {"1min": 60.0, "5min": 300.0, "15min": 900.0}
        window_seconds = window_lookup.get(self._rhythm_scale_combo.currentText(), 60.0)
        aggregated = aggregate_band_history(
            self._band_history,
            window_seconds,
            now=time.monotonic(),
        )
        if aggregated is not None:
            self._last_nonempty_band_history = dict(aggregated)
            self._rhythms_pie.set_band_powers(aggregated)
            return
        if any(float(value) > 0.0 for value in self._latest_band_powers.values()):
            self._last_nonempty_band_history = dict(self._latest_band_powers)
            self._rhythms_pie.set_band_powers(self._latest_band_powers)
            return
        if self._last_nonempty_band_history is not None:
            self._rhythms_pie.set_band_powers(self._last_nonempty_band_history)
            return
        self._rhythms_pie.set_waiting("Waiting for PSD data")

    def _refresh_mems_charts(self):
        accel = self._mems_buffers["accelerometer"]
        gyro = self._mems_buffers["gyroscope"]
        self._accel_chart.set_series(
            accel["times"],
            accel["x"],
            accel["y"],
            accel["z"],
            current_vector=accel["current"],
            span_seconds=MEMS_WINDOW_SEC,
            fixed_range=(-1.0, 1.0),
        )
        self._gyro_chart.set_series(
            gyro["times"],
            gyro["x"],
            gyro["y"],
            gyro["z"],
            current_vector=gyro["current"],
            span_seconds=MEMS_WINDOW_SEC,
            fixed_range=(-50.0, 50.0),
        )

    def _clear_vector_buffers(self):
        for buf in self._mems_buffers.values():
            buf["times"].clear()
            buf["x"].clear()
            buf["y"].clear()
            buf["z"].clear()
            buf["current"] = (0.0, 0.0, 0.0)

    @staticmethod
    def _new_vector_buffer():
        return {
            "times": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "x": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "y": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "z": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "current": (0.0, 0.0, 0.0),
        }

    @staticmethod
    def _append_vector_sample(
        buffer: dict,
        mapped_ts: float,
        vector: tuple[float, float, float],
    ):
        buffer["times"].append(mapped_ts)
        buffer["x"].append(vector[0])
        buffer["y"].append(vector[1])
        buffer["z"].append(vector[2])
        buffer["current"] = vector

    def _map_sdk_time(self, sdk_ts: float) -> float:
        if self._mems_time_origin is None:
            self._mems_time_origin = sdk_ts
        return self._session_start_wall + (float(sdk_ts) - float(self._mems_time_origin))
