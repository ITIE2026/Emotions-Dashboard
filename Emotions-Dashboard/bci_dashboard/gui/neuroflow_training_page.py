"""
Embedded Neuroflow launcher page for the Training Lab.
"""
from __future__ import annotations

from collections import deque
import math
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.neuroflow_runtime import (
    APPS,
    CI_FOCUS_DROPOUT,
    CI_FOCUS_THRESHOLD,
    FOCUS_DWELL_SECONDS,
    SIM_START_DELAY_S,
    STAGES,
    NeuroflowSimulationEngine,
    NeuroflowStateMachine,
    threaded_launch,
)
from gui.widgets.spectrum_chart import SpectrumChart
from utils.config import BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY
from utils.helpers import compute_band_powers, compute_peak_frequencies


class FocusProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.setMinimumHeight(8)

    def set_progress(self, value: float):
        self._value = max(0.0, min(1.0, float(value)))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 1, 0, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#172036"))
        painter.drawRoundedRect(rect, 4, 4)
        if self._value <= 0.0:
            return
        width = int(rect.width() * self._value)
        fill_rect = rect.adjusted(0, 0, -(rect.width() - width), 0)
        painter.setBrush(QColor("#10B981"))
        painter.drawRoundedRect(fill_rect, 4, 4)


class GaugeDial(QWidget):
    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._color = QColor(color)
        self._value = 0.0
        self._max_value = 1.0
        self.setMinimumSize(120, 120)

    def set_value(self, value: float, max_value: float = 1.0):
        self._value = max(0.0, float(value))
        self._max_value = max(float(max_value), 1e-6)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#0F172A"))
        painter.drawEllipse(rect)

        pen_bg = QPen(QColor("#24304A"), 10)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        fraction = max(0.0, min(1.0, self._value / self._max_value))
        pen_fg = QPen(self._color, 10)
        pen_fg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_fg)
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * fraction))

        painter.setPen(QColor(TEXT_SECONDARY))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(self.rect().adjusted(0, 12, 0, 0), Qt.AlignTop | Qt.AlignHCenter, self._title)

        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Segoe UI", 14, QFont.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, f"{self._value:.2f}")


class StagePipeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._labels = []
        for label, stage_id in STAGES:
            pill = QLabel(label)
            pill.setAlignment(Qt.AlignCenter)
            pill.setMinimumWidth(90)
            pill.setStyleSheet(
                "QLabel { background: #121A2B; color: #64748B; border: 1px solid #24304A; "
                "border-radius: 16px; padding: 8px 10px; font-size: 11px; font-weight: bold; }"
            )
            layout.addWidget(pill)
            self._labels.append((stage_id, pill))
        layout.addStretch()

    def set_stage(self, stage: int):
        for step, label in self._labels:
            if step < stage:
                label.setStyleSheet(
                    "QLabel { background: #0E3B2B; color: #D1FAE5; border: 1px solid #10B981; "
                    "border-radius: 16px; padding: 8px 10px; font-size: 11px; font-weight: bold; }"
                )
            elif step == stage:
                label.setStyleSheet(
                    "QLabel { background: #1D2B53; color: #E0E7FF; border: 1px solid #60A5FA; "
                    "border-radius: 16px; padding: 8px 10px; font-size: 11px; font-weight: bold; }"
                )
            else:
                label.setStyleSheet(
                    "QLabel { background: #121A2B; color: #64748B; border: 1px solid #24304A; "
                    "border-radius: 16px; padding: 8px 10px; font-size: 11px; font-weight: bold; }"
                )


class ResistanceBadge(QWidget):
    CHANNELS = ("T3", "T4", "O1", "O2")

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._labels = {}
        for channel in self.CHANNELS:
            label = QLabel(f"{channel}: --")
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(92)
            label.setStyleSheet(
                "QLabel { background: #1A2338; color: #FCA5A5; border: 1px solid #24304A; "
                "border-radius: 14px; padding: 8px 10px; font-size: 11px; font-weight: bold; }"
            )
            layout.addWidget(label)
            self._labels[channel] = label
        layout.addStretch()

    def set_resistances(self, resistances: dict[str, float]):
        for channel, label in self._labels.items():
            value = resistances.get(channel)
            if value is None:
                text = f"{channel}: --"
                color = "#FCA5A5"
            elif value >= 1_000_000.0:
                text = f"{channel}: {value / 1_000_000.0:.1f} MΩ"
                color = "#FCA5A5"
            else:
                text = f"{channel}: {value / 1000.0:.0f} kΩ"
                color = "#69F0AE" if value <= 500_000.0 else "#FBBF24"
            label.setText(text)
            label.setStyleSheet(
                f"QLabel {{ background: #1A2338; color: {color}; border: 1px solid #24304A; "
                "border-radius: 14px; padding: 8px 10px; font-size: 11px; font-weight: bold; }"
            )


class CalibrationOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = False
        self._text = "Quick calibration running"
        self.hide()

    def start(self, text: str):
        self._visible = True
        self._text = text
        self.show()
        self.raise_()
        self.update()

    def stop(self):
        self._visible = False
        self.hide()

    def paintEvent(self, event):  # noqa: N802
        if not self._visible:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(2, 6, 23, 214))
        painter.setPen(QColor("#E2E8F0"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Bold))
        painter.drawText(self.rect().adjusted(0, -12, 0, 0), Qt.AlignCenter, self._text)
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(
            self.rect().adjusted(0, 42, 0, 0),
            Qt.AlignCenter,
            "Relax, keep still, and wait for the embedded calibration to finish.",
        )


class NeuroflowTrainingPage(QWidget):
    back_requested = Signal()
    quick_calibration_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._runtime = NeuroflowStateMachine()
        self._sim = NeuroflowSimulationEngine()
        self._streaming_active = False
        self._live_connected = False
        self._serial = "--"
        self._sample_rate_hz = 250.0
        self._channel_names = ["O1-T3", "O2-T4"]
        self._simulation_delay_started = 0.0
        self._simulation_enabled = False
        self._sim_psd_accumulator = 0.0
        self._last_freqs = np.asarray([], dtype=float)
        self._last_powers = np.asarray([], dtype=float)
        self._log_lines = deque(maxlen=180)

        self._app_cycle_timer = QTimer(self)
        self._app_cycle_timer.setInterval(5000)
        self._app_cycle_timer.timeout.connect(self._cycle_next_app)

        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(50)
        self._sim_timer.timeout.connect(self._tick_simulation)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._refresh_runtime_ui)

        self._build_ui()
        self._refresh_runtime_ui()

    def _build_ui(self):
        self.setStyleSheet("background: #05070B; color: #F8FAFC;")
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        back_btn = QPushButton("Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(
            f"QPushButton {{ background: #151922; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; "
            "border-radius: 18px; padding: 8px 16px; font-size: 13px; font-weight: bold; }}"
        )
        back_btn.clicked.connect(self.back_requested.emit)
        top_row.addWidget(back_btn)

        self._status_lbl = QLabel("Neuroflow idle")
        self._status_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #E2E8F0;")
        top_row.addWidget(self._status_lbl, stretch=1)

        self._simulation_lbl = QLabel("")
        self._simulation_lbl.setStyleSheet(
            "font-size: 12px; color: #F59E0B; background: #2F2110; border: 1px solid #7C4A0A; "
            "border-radius: 14px; padding: 6px 10px;"
        )
        self._simulation_lbl.hide()
        top_row.addWidget(self._simulation_lbl)

        self._calibrate_btn = QPushButton("Quick Calibrate")
        self._calibrate_btn.setCursor(Qt.PointingHandCursor)
        self._calibrate_btn.clicked.connect(self._request_quick_calibration)
        self._calibrate_btn.setStyleSheet(
            "QPushButton { background: #1F3A2B; color: #D1FAE5; border: 1px solid #10B981; "
            "border-radius: 18px; padding: 8px 16px; font-size: 13px; font-weight: bold; }"
            "QPushButton:disabled { background: #20252E; color: #6B7280; border-color: #374151; }"
        )
        top_row.addWidget(self._calibrate_btn)

        self._manual_launch_btn = QPushButton("Launch Manually")
        self._manual_launch_btn.setCursor(Qt.PointingHandCursor)
        self._manual_launch_btn.clicked.connect(self._launch_current_app)
        self._manual_launch_btn.setStyleSheet(
            "QPushButton { background: #142034; color: #DBEAFE; border: 1px solid #60A5FA; "
            "border-radius: 18px; padding: 8px 16px; font-size: 13px; font-weight: bold; }"
            "QPushButton:disabled { background: #20252E; color: #6B7280; border-color: #374151; }"
        )
        top_row.addWidget(self._manual_launch_btn)
        root.addLayout(top_row)

        self._pipeline = StagePipeline()
        root.addWidget(self._pipeline)

        self._resistance_badges = ResistanceBadge()
        root.addWidget(self._resistance_badges)

        body = QHBoxLayout()
        body.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(10)
        signal_frame = QFrame()
        signal_frame.setStyleSheet(
            f"QFrame {{ background: #11161F; border: 1px solid {BORDER_SUBTLE}; border-radius: 22px; }}"
        )
        signal_layout = QVBoxLayout(signal_frame)
        signal_layout.setContentsMargins(14, 14, 14, 14)
        signal_layout.setSpacing(10)
        signal_title = QLabel("Live Signal Source")
        signal_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #E2E8F0;")
        signal_layout.addWidget(signal_title)
        self._signal_source_lbl = QLabel(
            "Raw EEG rendering stays on the main Dashboard. Neuroflow listens to live spectral summaries for focus triggering."
        )
        self._signal_source_lbl.setWordWrap(True)
        self._signal_source_lbl.setStyleSheet("font-size: 12px; color: #CBD5E1;")
        signal_layout.addWidget(self._signal_source_lbl)
        self._band_summary_lbl = QLabel("Band powers: waiting for dashboard PSD")
        self._band_summary_lbl.setWordWrap(True)
        self._band_summary_lbl.setStyleSheet("font-size: 12px; color: #93C5FD;")
        signal_layout.addWidget(self._band_summary_lbl)
        self._peaks_lbl = QLabel("Peaks: --")
        self._peaks_lbl.setWordWrap(True)
        self._peaks_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        signal_layout.addWidget(self._peaks_lbl)
        signal_layout.addStretch()
        left.addWidget(signal_frame, stretch=1)
        body.addLayout(left, stretch=4)

        middle = QVBoxLayout()
        middle.setSpacing(10)
        focus_frame = QFrame()
        focus_frame.setStyleSheet(
            f"QFrame {{ background: #11161F; border: 1px solid {BORDER_SUBTLE}; border-radius: 22px; }}"
        )
        focus_layout = QVBoxLayout(focus_frame)
        focus_layout.setContentsMargins(14, 14, 14, 14)
        focus_layout.setSpacing(10)
        title = QLabel("Concentration Index")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #E2E8F0;")
        focus_layout.addWidget(title)
        self._ci_gauge = GaugeDial("CI", "#38BDF8")
        focus_layout.addWidget(self._ci_gauge, alignment=Qt.AlignCenter)
        self._ci_meta_lbl = QLabel("")
        self._ci_meta_lbl.setAlignment(Qt.AlignCenter)
        self._ci_meta_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        focus_layout.addWidget(self._ci_meta_lbl)
        self._dwell_bar = FocusProgressBar()
        focus_layout.addWidget(self._dwell_bar)
        self._focus_hint_lbl = QLabel(
            f"Start focus above {CI_FOCUS_THRESHOLD:.2f}, reset below {CI_FOCUS_DROPOUT:.2f}, hold for {FOCUS_DWELL_SECONDS:.1f}s."
        )
        self._focus_hint_lbl.setWordWrap(True)
        self._focus_hint_lbl.setStyleSheet("font-size: 12px; color: #CBD5E1;")
        focus_layout.addWidget(self._focus_hint_lbl)
        middle.addWidget(focus_frame)

        app_frame = QFrame()
        app_frame.setStyleSheet(
            f"QFrame {{ background: #11161F; border: 1px solid {BORDER_SUBTLE}; border-radius: 22px; }}"
        )
        app_layout = QVBoxLayout(app_frame)
        app_layout.setContentsMargins(14, 14, 14, 14)
        app_layout.setSpacing(10)
        app_title = QLabel("App Selector")
        app_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #E2E8F0;")
        app_layout.addWidget(app_title)
        self._app_list = QListWidget()
        self._app_list.setFixedHeight(240)
        self._app_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; color: #E2E8F0; }"
            "QListWidget::item { background: #131B2C; border: 1px solid #24304A; border-radius: 16px; padding: 10px; margin: 4px 0; }"
            "QListWidget::item:selected { background: #0E3B2B; border: 1px solid #10B981; }"
        )
        for app in APPS:
            item = QListWidgetItem(f"{app['icon']}  {app['name']}")
            self._app_list.addItem(item)
        self._app_list.setCurrentRow(0)
        self._app_list.currentRowChanged.connect(self._on_app_selected)
        app_layout.addWidget(self._app_list)
        self._launch_hint_lbl = QLabel("")
        self._launch_hint_lbl.setWordWrap(True)
        self._launch_hint_lbl.setStyleSheet("font-size: 12px; color: #38BDF8;")
        app_layout.addWidget(self._launch_hint_lbl)
        middle.addWidget(app_frame, stretch=1)
        body.addLayout(middle, stretch=3)

        right = QVBoxLayout()
        right.setSpacing(10)
        spectrum_frame = QFrame()
        spectrum_frame.setStyleSheet(
            f"QFrame {{ background: #11161F; border: 1px solid {BORDER_SUBTLE}; border-radius: 22px; }}"
        )
        spectrum_layout = QVBoxLayout(spectrum_frame)
        spectrum_layout.setContentsMargins(12, 12, 12, 12)
        spectrum_layout.setSpacing(10)
        spectrum_title = QLabel("Spectral Status")
        spectrum_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #E2E8F0;")
        spectrum_layout.addWidget(spectrum_title)
        gauges = QGridLayout()
        gauges.setContentsMargins(0, 0, 0, 0)
        gauges.setHorizontalSpacing(8)
        gauges.setVerticalSpacing(8)
        self._delta_gauge = GaugeDial("Delta", "#0EA5E9")
        self._theta_gauge = GaugeDial("Theta", "#22D3EE")
        self._alpha_gauge = GaugeDial("Alpha", "#4ADE80")
        self._beta_gauge = GaugeDial("Beta", "#F59E0B")
        gauges.addWidget(self._delta_gauge, 0, 0)
        gauges.addWidget(self._theta_gauge, 0, 1)
        gauges.addWidget(self._alpha_gauge, 1, 0)
        gauges.addWidget(self._beta_gauge, 1, 1)
        spectrum_layout.addLayout(gauges)
        right.addWidget(spectrum_frame, stretch=1)

        log_frame = QFrame()
        log_frame.setStyleSheet(
            f"QFrame {{ background: #11161F; border: 1px solid {BORDER_SUBTLE}; border-radius: 22px; }}"
        )
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(14, 14, 14, 14)
        log_layout.setSpacing(8)
        log_title = QLabel("System Log")
        log_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #E2E8F0;")
        log_layout.addWidget(log_title)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(180)
        self._log.setStyleSheet(
            "QTextEdit { background: #0A0F1A; border: 1px solid #24304A; border-radius: 12px; color: #CBD5E1; font-size: 12px; }"
        )
        log_layout.addWidget(self._log)
        right.addWidget(log_frame, stretch=1)
        body.addLayout(right, stretch=4)

        root.addLayout(body, stretch=1)

        self._overlay = CalibrationOverlay(self)
        self._overlay.setGeometry(self.rect())
        self._on_app_selected(0)
        self._log_message("Neuroflow embedded page ready.")

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def activate(self):
        if not self._ui_timer.isActive():
            self._ui_timer.start()
        if self._streaming_active and self._live_connected:
            self._stop_simulation()
        else:
            self._schedule_simulation_fallback()
        self._refresh_runtime_ui()

    def deactivate(self):
        self._ui_timer.stop()
        self._stop_simulation()
        self._app_cycle_timer.stop()
        self._overlay.stop()

    def shutdown(self):
        self.deactivate()

    def set_streaming_active(self, active: bool):
        self._streaming_active = bool(active)
        if self._streaming_active and self._live_connected:
            self._stop_simulation()
        elif not self._streaming_active and not self._simulation_enabled:
            self._schedule_simulation_fallback()
        self._refresh_runtime_ui()

    def set_connection_state(self, connected: bool, serial: str = "--"):
        self._live_connected = bool(connected)
        self._serial = serial or "--"
        if self._live_connected:
            self._runtime.set_connected(True, simulation=False)
            self._stop_simulation()
            self._log_message(f"Live device detected: {self._serial}")
        else:
            self._runtime.set_connected(False, simulation=False)
            self._schedule_simulation_fallback()
            self._log_message("Live device not connected. Neuroflow will fall back to simulation.")
        self._refresh_runtime_ui()

    def set_eeg_stream_metadata(self, sample_rate_hz: float | None = None, channel_names: list[str] | None = None):
        if channel_names:
            self._channel_names = [str(name).strip() for name in channel_names if str(name).strip()]
        if sample_rate_hz:
            try:
                self._sample_rate_hz = float(sample_rate_hz)
            except (TypeError, ValueError):
                self._sample_rate_hz = 250.0

    def on_resistance(self, data: dict):
        self._resistance_badges.set_resistances(data or {})
        passed = self._runtime.set_resistances(data or {})
        if passed:
            self._log_message("Resistance check passed. Quick calibration is ready.")
        self._refresh_runtime_ui()

    def on_eeg(self, eeg_timed_data):
        return

    def on_psd(self, psd_data):
        if self._simulation_enabled or not self._streaming_active:
            return
        try:
            n_freq = psd_data.get_frequencies_count()
            n_channels = psd_data.get_channels_count()
            freqs = np.asarray([float(psd_data.get_frequency(idx)) for idx in range(n_freq)], dtype=float)
            avg_power = np.zeros(n_freq, dtype=float)
            for ch_idx in range(n_channels):
                for f_idx in range(n_freq):
                    avg_power[f_idx] += float(psd_data.get_psd(ch_idx, f_idx))
            if n_channels > 0:
                avg_power /= max(1, n_channels)
            band_powers = compute_band_powers(freqs, avg_power)
            peaks = compute_peak_frequencies(freqs, avg_power)
            self.update_signal_snapshot(band_powers, peaks)
        except Exception:
            pass

    def update_signal_snapshot(
        self,
        band_powers: dict[str, float],
        peak_freqs: dict[str, float] | None = None,
        psd_timestamp: float | None = None,
    ):
        del psd_timestamp
        band_powers = dict(band_powers or {})
        peak_freqs = dict(peak_freqs or {})
        if not band_powers:
            return
        max_value = max(0.4, max(band_powers.values()) * 1.1)
        self._delta_gauge.set_value(band_powers.get("delta", 0.0), max_value=max_value)
        self._theta_gauge.set_value(band_powers.get("theta", 0.0), max_value=max_value)
        self._alpha_gauge.set_value(band_powers.get("alpha", 0.0), max_value=max_value)
        self._beta_gauge.set_value(band_powers.get("beta", 0.0), max_value=max_value)
        self._band_summary_lbl.setText(
            "Band powers: "
            f"Delta {band_powers.get('delta', 0.0):.3f} • "
            f"Theta {band_powers.get('theta', 0.0):.3f} • "
            f"Alpha {band_powers.get('alpha', 0.0):.3f} • "
            f"Beta {band_powers.get('beta', 0.0):.3f}"
        )
        self._peaks_lbl.setText(
            "Peaks: "
            f"Alpha {peak_freqs.get('alpha_peak', 0.0):.1f} Hz • "
            f"Beta {peak_freqs.get('beta_peak', 0.0):.1f} Hz • "
            f"Theta {peak_freqs.get('theta_peak', 0.0):.1f} Hz"
        )
        triggered = self._runtime.ingest_band_powers(band_powers)
        self._ci_gauge.set_value(self._runtime.ci_smooth, max_value=max(0.6, CI_FOCUS_THRESHOLD * 1.8))
        self._ci_meta_lbl.setText(
            f"CI raw {self._runtime.ci_raw:.3f} • smooth {self._runtime.ci_smooth:.3f} • Alpha peak {peak_freqs.get('alpha_peak', 0.0):.1f} Hz"
        )
        if triggered:
            app = self._runtime.current_app()
            self._log_message(f"Focus confirmed. Launching {app['name']}.")
            threaded_launch(app)
        self._refresh_runtime_ui()

    def on_iapf_status(self, payload: dict):
        if not payload:
            return
        frequency = payload.get("frequency")
        source = str(payload.get("source", "Calibration"))
        if frequency not in (None, 0):
            self._ci_meta_lbl.setText(f"{source} iAPF {float(frequency):.2f} Hz")

    def on_calibration_started(self):
        self._runtime.start_calibration()
        self._overlay.start("Quick calibration running")
        self._log_message("Quick calibration started from Neuroflow.")
        self._refresh_runtime_ui()

    def on_calibration_finished(self, success: bool, message: str = ""):
        self._runtime.finish_calibration(success, message)
        self._overlay.stop()
        if success:
            self._log_message(message or "Quick calibration completed.")
            if not self._app_cycle_timer.isActive():
                self._app_cycle_timer.start()
        else:
            self._log_message(message or "Quick calibration failed.")
        self._refresh_runtime_ui()

    def _request_quick_calibration(self):
        self.on_calibration_started()
        self.quick_calibration_requested.emit()

    def _apply_psd(self, freqs: np.ndarray, powers: np.ndarray):
        if freqs.size == 0 or powers.size == 0:
            return
        self._last_freqs = np.asarray(freqs, dtype=float)
        self._last_powers = np.asarray(powers, dtype=float)
        band_powers = compute_band_powers(freqs, powers)
        peaks = compute_peak_frequencies(freqs, powers)
        self.update_signal_snapshot(band_powers, peaks)

    def _schedule_simulation_fallback(self):
        if self._simulation_enabled:
            return
        self._simulation_delay_started = time.monotonic()
        self._simulation_lbl.setText(f"Simulation fallback in {int(SIM_START_DELAY_S)}s if no live stream appears.")
        self._simulation_lbl.show()

    def _start_simulation(self):
        if self._simulation_enabled:
            return
        self._simulation_enabled = True
        self._simulation_delay_started = 0.0
        self._simulation_lbl.setText("Simulation mode active")
        self._simulation_lbl.show()
        self._sim.reset()
        self._runtime.set_connected(True, simulation=True)
        self._runtime.set_resistances(self._sim.generate_resistances())
        self._sim_psd_accumulator = 0.0
        self._sim_timer.start()
        self._log_message("Simulation mode started.")
        self._refresh_runtime_ui()

    def _stop_simulation(self):
        if self._simulation_enabled:
            self._simulation_enabled = False
            self._sim_timer.stop()
            self._simulation_lbl.hide()
            self._runtime.set_connected(self._live_connected, simulation=False)
            if self._live_connected:
                self._log_message("Returning to live Neuroflow data.")
        else:
            self._simulation_lbl.hide()
        self._refresh_runtime_ui()

    def _tick_simulation(self):
        if not self._simulation_enabled:
            return
        self._sim_psd_accumulator += 0.05
        if self._sim_psd_accumulator >= 0.5:
            self._sim_psd_accumulator = 0.0
            band_powers = self._sim.generate_band_powers()
            freqs, powers = self._synthetic_psd_curve(band_powers)
            self._apply_psd(freqs, powers)

    def _synthetic_psd_curve(self, band_powers: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
        freqs = np.linspace(0.5, 35.0, 180)
        powers = np.zeros_like(freqs)
        peaks = [
            (2.5, band_powers.get("delta", 0.0)),
            (6.0, band_powers.get("theta", 0.0)),
            (10.0, band_powers.get("alpha", 0.0)),
            (14.0, band_powers.get("smr", 0.0)),
            (20.0, band_powers.get("beta", 0.0)),
        ]
        for center, amplitude in peaks:
            powers += amplitude * np.exp(-0.5 * ((freqs - center) / 1.35) ** 2)
        powers += 0.005 * np.exp(-freqs / 15.0)
        return freqs, powers

    def _cycle_next_app(self):
        if not self._runtime.calibrated:
            return
        next_index = self._runtime.cycle_next_app()
        self._app_list.blockSignals(True)
        self._app_list.setCurrentRow(next_index)
        self._app_list.blockSignals(False)
        self._on_app_selected(next_index)

    def _on_app_selected(self, row: int):
        if row < 0:
            return
        self._runtime.set_current_app(row)
        app = APPS[row]
        self._launch_hint_lbl.setText(f"Maintain focus to launch: {app['icon']} {app['name']}")
        self._refresh_runtime_ui()

    def _launch_current_app(self):
        if not self._runtime.calibrated:
            self._log_message("Manual launch is blocked until quick calibration completes.")
            return
        app = self._runtime.current_app()
        self._log_message(f"Manual launch: {app['name']}")
        threaded_launch(app)

    def _refresh_runtime_ui(self):
        if not self._simulation_enabled and not self._live_connected and self._simulation_delay_started > 0.0:
            elapsed = time.monotonic() - self._simulation_delay_started
            remaining = max(0, int(math.ceil(SIM_START_DELAY_S - elapsed)))
            if elapsed >= SIM_START_DELAY_S:
                self._start_simulation()
            else:
                self._simulation_lbl.setText(f"Simulation fallback in {remaining}s if no live stream appears.")
                self._simulation_lbl.show()

        snapshot = self._runtime.snapshot()
        self._pipeline.set_stage(snapshot.stage)
        mode_text = "Simulation" if snapshot.simulation_active else ("Live Capsule" if snapshot.connected else "Disconnected")
        self._status_lbl.setText(f"Neuroflow • {mode_text} • Serial {self._serial} • Stage {STAGES[snapshot.stage][0]}")
        self._calibrate_btn.setEnabled(snapshot.connected and snapshot.ready_to_calibrate and not snapshot.calibration_active)
        self._manual_launch_btn.setEnabled(snapshot.calibrated)
        self._ci_gauge.set_value(snapshot.ci_smooth, max_value=max(0.6, CI_FOCUS_THRESHOLD * 1.8))
        cooldown_text = f"Cooldown {snapshot.cooldown_remaining:.1f}s" if snapshot.cooldown_remaining > 0.0 else "Ready to launch"
        if not self._last_freqs.size:
            self._ci_meta_lbl.setText(f"CI raw {snapshot.ci_raw:.3f} • smooth {snapshot.ci_smooth:.3f} • {cooldown_text}")
        self._dwell_bar.set_progress(snapshot.dwell_progress)
        self._focus_hint_lbl.setText(snapshot.last_message)
        if snapshot.calibration_active:
            self._overlay.start("Quick calibration running")
        elif not self._overlay.isHidden():
            self._overlay.stop()

    def _log_message(self, text: str):
        if not text:
            return
        stamp = time.strftime("%H:%M:%S")
        self._log_lines.append(f"[{stamp}] {text}")
        self._log.setPlainText("\n".join(self._log_lines))
        self._log.moveCursor(QTextCursor.End)
