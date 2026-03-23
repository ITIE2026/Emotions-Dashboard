"""
Main window orchestration for connection, calibration, dashboard, training, and sessions.
"""
from __future__ import annotations

import logging
import threading
import time
from queue import Queue

import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from calibration.calibration_manager import CalibrationManager
from classifiers.cardio_handler import CardioHandler
from classifiers.emotions_handler import EmotionsHandler
from classifiers.mems_handler import MemsHandler
from classifiers.physio_handler import PhysioHandler
from classifiers.productivity_handler import ProductivityHandler
from device.capsule_bridge import CapsuleBridge
from device.device_manager import DeviceManager
from device.device_status_monitor import DeviceStatusMonitor
from gui.calibration_screen import CalibrationScreen
from gui.connection_screen import ConnectionScreen
from gui.dashboard_screen import DashboardScreen
from gui.mems_screen import MemsScreen
from gui.phaseon_screen import PhaseonScreen
from gui.sessions_screen import SessionsScreen
from gui.training_screen import TrainingScreen
from prosthetic_arm.phaseon_runtime import PhaseonRuntime
from storage.session_recorder import SessionRecorder
from utils.config import (
    ACCENT_GREEN,
    BG_NAV,
    BORDER_SUBTLE,
    EEG_FILTER_ENABLED_DEFAULT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_TITLE,
)
from utils.helpers import compute_band_powers, compute_peak_frequencies


log = logging.getLogger(__name__)

PAGE_CONNECTION = 0
PAGE_CALIBRATION = 1
PAGE_DASHBOARD = 2
PAGE_MEMS = 3
PAGE_TRAINING = 4
PAGE_SESSIONS = 5
PAGE_PHASEON = 6


class AsyncSessionRecorder:
    def __init__(self):
        self._impl = SessionRecorder()
        self._queue: Queue = Queue()
        self._closed = False
        self._session_id = ""
        self._file_path = None
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="session-recorder",
            daemon=True,
        )
        self._thread.start()

    @property
    def session_id(self):
        return self._session_id

    @property
    def file_path(self):
        return self._file_path

    def _worker_loop(self):
        while True:
            task = self._queue.get()
            if task is None:
                return
            name, args, kwargs, event, holder = task
            try:
                result = getattr(self._impl, name)(*args, **kwargs)
                self._session_id = getattr(self._impl, "session_id", self._session_id)
                self._file_path = getattr(self._impl, "file_path", self._file_path)
                if holder is not None:
                    holder["result"] = result
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("Session recorder task failed: %s", name)
                if holder is not None:
                    holder["error"] = exc
            finally:
                if event is not None:
                    event.set()

    def _call_sync(self, name: str, *args, **kwargs):
        if self._closed:
            return None
        event = threading.Event()
        holder: dict = {}
        self._queue.put((name, args, kwargs, event, holder))
        event.wait()
        if "error" in holder:
            raise holder["error"]
        return holder.get("result")

    def _call_async(self, name: str, *args, **kwargs):
        if self._closed:
            return
        self._queue.put((name, args, kwargs, None, None))

    def start_session(self, metadata, write_options):
        return self._call_sync("start_session", metadata, write_options)

    def stop_session(self):
        return self._call_sync("stop_session")

    def update_calibration_info(self, payload):
        self._call_async("update_calibration_info", payload)

    def record_baselines(self, data):
        self._call_async("record_baselines", data)

    def record_resistances(self, data):
        self._call_async("record_resistances", data)

    def record_emotions(self, data):
        self._call_async("record_emotions", data)

    def record_productivity_metrics(self, data):
        self._call_async("record_productivity_metrics", data)

    def record_productivity_indexes(self, data):
        self._call_async("record_productivity_indexes", data)

    def record_ppg_packet(self, ppg_timed_data):
        # Eagerly extract from the DLL object while we're on the calling (main) thread.
        # Passing raw ctypes objects to the background queue causes use-after-free crashes.
        try:
            count = len(ppg_timed_data)
            snapshot = {"values": [], "timestampsMs": []}
            for idx in range(count):
                snapshot["values"].append(float(ppg_timed_data.get_value(idx)))
                snapshot["timestampsMs"].append(float(ppg_timed_data.get_timestamp(idx)))
        except Exception:
            return
        if snapshot["values"]:
            self._call_async("record_ppg_snapshot", snapshot)

    def record_cardio_metrics(self, data):
        self._call_async("record_cardio_metrics", data)

    def record_raw_eeg_packet(self, eeg_timed_data):
        # Eagerly extract from the DLL object while we're on the calling (main) thread.
        # Passing raw ctypes objects to the background queue causes use-after-free crashes.
        try:
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()
        except Exception:
            return
        if n_channels <= 0 or n_samples <= 0:
            return
        timestamps = []
        for sample_idx in range(n_samples):
            try:
                timestamps.append(float(eeg_timed_data.get_timestamp(sample_idx)))
            except Exception:
                timestamps.append(float(sample_idx))
        channels = {}
        for ch_idx in range(n_channels):
            values = []
            for sample_idx in range(n_samples):
                try:
                    values.append(float(eeg_timed_data.get_raw_value(ch_idx, sample_idx)) * 1_000_000.0)
                except Exception:
                    values.append(0.0)
            channels[ch_idx] = values
        self._call_async("record_raw_eeg_snapshot", {"timestampsMs": timestamps, "channels": channels})

    def record_raw_eeg_snapshot(self, snapshot: dict):
        if not snapshot:
            return
        timestamps = list(snapshot.get("timestampsMs", []))
        channels = {}
        for ch_idx, values in (snapshot.get("channels", {}) or {}).items():
            try:
                normalized_idx = int(ch_idx)
            except (TypeError, ValueError):
                normalized_idx = ch_idx
            channels[normalized_idx] = list(values or [])
        if not timestamps or not channels:
            return
        self._call_async(
            "record_raw_eeg_snapshot",
            {"timestampsMs": timestamps, "channels": channels},
        )

    def record_artifacts(self, artifacts):
        # Extract artifact data from the DLL object eagerly in the calling thread
        # (main GUI thread) while the ctypes pointer is still valid.  Passing the
        # raw DLL object to the background queue leads to use-after-free crashes
        # once the C library frees the underlying artifact buffer (manifests as
        # "Channel index is out of range" errors in the recorder thread).
        try:
            count = artifacts.get_channels_count()
            snapshot = {}
            for ch_idx in range(min(count, 8)):  # cap at 8 channels max
                try:
                    snapshot[ch_idx] = bool(artifacts.get_artifacts_by_channel(ch_idx))
                except Exception:
                    break
        except Exception:
            return
        if snapshot:
            self._call_async("record_artifacts_snapshot", snapshot)

    def record_mems_packet(self, mems_timed_data):
        # Eagerly extract from the DLL object while we're on the calling (main) thread.
        # Passing raw ctypes objects to the background queue causes use-after-free crashes.
        try:
            count = len(mems_timed_data)
            samples = []
            for idx in range(count):
                accel = mems_timed_data.get_accelerometer(idx)
                gyro = mems_timed_data.get_gyroscope(idx)
                samples.append({
                    "timestampMs": float(mems_timed_data.get_timestamp(idx)),
                    "accelerometer": {"x": float(accel.x), "y": float(accel.y), "z": float(accel.z)},
                    "gyroscope": {"x": float(gyro.x), "y": float(gyro.y), "z": float(gyro.z)},
                })
        except Exception:
            return
        if samples:
            self._call_async("record_mems_snapshot", {"samples": samples})

    def record_rhythms(self, band_powers):
        self._call_async("record_rhythms", band_powers)

    def record_eeg_summary(self, band_powers, peak_freqs, filter_enabled, iapf_status):
        self._call_async(
            "record_eeg_summary",
            band_powers,
            peak_freqs,
            filter_enabled,
            iapf_status,
        )

    def log_metrics_row(self, **kwargs):
        self._call_async("log_metrics_row", **kwargs)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=5.0)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.showMaximized()

        self._bridge = CapsuleBridge()
        self._dm = DeviceManager(self._bridge, parent=self)
        self._phaseon_runtime = PhaseonRuntime(self)

        self._emotions_h: EmotionsHandler | None = None
        self._prod_h: ProductivityHandler | None = None
        self._cardio_h: CardioHandler | None = None
        self._physio_h: PhysioHandler | None = None
        self._mems_h: MemsHandler | None = None
        self._cal_mgr: CalibrationManager | None = None
        self._status_mon: DeviceStatusMonitor | None = None
        self._recorder = AsyncSessionRecorder()

        self._classifiers_created = False
        self._streaming = False
        self._session_active = False
        self._calibration_return_page = PAGE_CONNECTION
        self._streaming_before_calibration = False
        self._embedded_neuroflow_calibration = False
        self._quick_background_calibration_active = False

        self._latest_emo: dict = {}
        self._latest_prod: dict = {}
        self._latest_indexes: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}
        self._latest_resistances: dict = {}
        self._latest_band_powers: dict = {}
        self._latest_peak_freqs: dict = {}
        self._latest_psd_t: float | None = None
        self._iapf_status: dict = {
            "frequency": None,
            "source": "Not set",
            "status": "Not set",
            "applied": False,
        }

        self._disconnect_timer = QTimer(self)
        self._disconnect_timer.setSingleShot(True)
        self._disconnect_timer.setInterval(5000)
        self._disconnect_timer.timeout.connect(self._confirm_disconnected)

        self._build_ui()
        self._connect_device_signals()

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(1000)
        self._log_timer.timeout.connect(self._log_tick)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_menu_bar()

        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet(
            f"background: {BG_NAV}; border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        tb_layout = QHBoxLayout(toolbar_widget)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)

        self._stop_btn = self._toolbar_btn("Stop", "#EF5350", "#2a1515")
        self._stop_btn.clicked.connect(self._on_stop_signal)
        tb_layout.addWidget(self._stop_btn)

        self._start_btn = self._toolbar_btn("Start Signal", ACCENT_GREEN, "#1E3A2F")
        self._start_btn.clicked.connect(self._on_start_signal)
        tb_layout.addWidget(self._start_btn)

        self._detect_iapf_btn = self._toolbar_btn(
            "Detect iAPF (Closed Eyes)", "#FFB74D", "#3A2E1F"
        )
        self._detect_iapf_btn.clicked.connect(self._on_detect_iapf)
        tb_layout.addWidget(self._detect_iapf_btn)

        self._quick_cal_btn = self._toolbar_btn(
            "Quick iAPF Calibration (Closed Eyes)", "#FFB74D", "#3A2E1F"
        )
        self._quick_cal_btn.clicked.connect(self._on_quick_iapf)
        tb_layout.addWidget(self._quick_cal_btn)

        status_col = QVBoxLayout()
        status_col.setContentsMargins(8, 0, 0, 0)
        status_col.setSpacing(0)
        self._iapf_value_lbl = QLabel("iAPF: Not set")
        self._iapf_detail_lbl = QLabel("Source: Not set")
        for lbl, colour in (
            (self._iapf_value_lbl, TEXT_PRIMARY),
            (self._iapf_detail_lbl, TEXT_SECONDARY),
        ):
            lbl.setStyleSheet(
                f"font-size: 11px; color: {colour}; background: transparent;"
            )
        status_col.addWidget(self._iapf_value_lbl)
        status_col.addWidget(self._iapf_detail_lbl)
        tb_layout.addSpacing(10)
        tb_layout.addLayout(status_col)
        tb_layout.addStretch()
        root.addWidget(toolbar_widget)

        self._stack = QStackedWidget()
        self._conn_screen = ConnectionScreen(self._dm)
        self._cal_screen = CalibrationScreen()
        self._dash_screen = DashboardScreen()
        self._mems_screen = MemsScreen()
        self._training_screen = TrainingScreen(runtime=self._phaseon_runtime)
        self._sessions_screen = SessionsScreen()
        self._phaseon_screen = PhaseonScreen(self._phaseon_runtime)

        self._stack.addWidget(self._conn_screen)
        self._stack.addWidget(self._cal_screen)
        self._stack.addWidget(self._dash_screen)
        self._stack.addWidget(self._mems_screen)
        self._stack.addWidget(self._training_screen)
        self._stack.addWidget(self._sessions_screen)
        self._stack.addWidget(self._phaseon_screen)
        root.addWidget(self._stack, stretch=1)
        self._stack.currentChanged.connect(self._update_live_view_activity)
        self._conn_screen.filter_signal_changed.connect(self._on_connection_filter_changed)

        self._dash_screen.set_iapf_status()
        self._dash_screen.set_eeg_filter_enabled(self._filter_act.isChecked())
        self._conn_screen.set_filter_signal_checked(self._filter_act.isChecked())
        self._training_screen.neuroflow_quick_calibration_requested.connect(
            self._on_neuroflow_quick_calibration_requested
        )
        self._update_live_view_activity(self._stack.currentIndex())

    def _build_menu_bar(self):
        mb = self.menuBar()
        mb.setStyleSheet(
            f"QMenuBar {{ background: {BG_NAV}; color: {TEXT_PRIMARY}; "
            f"font-size: 13px; border-bottom: 1px solid {BORDER_SUBTLE}; padding: 2px 4px; }}"
            f"QMenuBar::item {{ padding: 6px 12px; border-radius: 4px; }}"
            f"QMenuBar::item:selected {{ background: #2a2e48; }}"
            f"QMenu {{ background: {BG_NAV}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER_SUBTLE}; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 24px; }}"
            f"QMenu::item:selected {{ background: #2a2e48; }}"
        )

        file_menu = mb.addMenu("File")
        training_act = QAction("Training Lab", self)
        training_act.triggered.connect(lambda: self._stack.setCurrentIndex(PAGE_TRAINING))
        file_menu.addAction(training_act)
        sessions_act = QAction("Sessions Data", self)
        sessions_act.triggered.connect(lambda: self._stack.setCurrentIndex(PAGE_SESSIONS))
        file_menu.addAction(sessions_act)
        file_menu.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        eeg_menu = mb.addMenu("EEG")
        for name in [
            "Frequency Peaks",
            "Concentration Index",
            "Relaxation Index",
            "Fatigue Score",
            "Reverse Fatigue Score",
            "Accumulated Fatigue",
            "EEG Quality",
        ]:
            act = QAction(name, self)
            act.triggered.connect(lambda checked, n=name: self._show_dashboard(n))
            eeg_menu.addAction(act)

        ppg_menu = mb.addMenu("PPG")
        hr_act = QAction("Heart Rate", self)
        hr_act.triggered.connect(lambda: self._show_dashboard("Heart Rate"))
        ppg_menu.addAction(hr_act)

        mems_menu = mb.addMenu("MEMS")
        accel_act = QAction("Accelerometer Tab", self)
        accel_act.triggered.connect(lambda: self._show_mems("Accelerometer Tab"))
        mems_menu.addAction(accel_act)
        gyro_act = QAction("Gyroscope Tab", self)
        gyro_act.triggered.connect(lambda: self._show_mems("Gyroscope Tab"))
        mems_menu.addAction(gyro_act)
        rhythms_act = QAction("Rhythms Diagram", self)
        rhythms_act.triggered.connect(lambda: self._show_mems("Rhythms Diagram"))
        mems_menu.addAction(rhythms_act)

        prod_menu = mb.addMenu("Productivity")
        for name in [
            "Productivity Tab",
            "Concentration Index",
            "Fatigue Score",
            "Reverse Fatigue Score",
            "Alpha Gravity",
            "Productivity Score",
        ]:
            act = QAction(name, self)
            act.triggered.connect(lambda checked, n=name: self._show_dashboard(n))
            prod_menu.addAction(act)

        emo_menu = mb.addMenu("Emotions")
        cog_act = QAction("Cognitive States", self)
        cog_act.triggered.connect(lambda: self._show_dashboard("Emotions"))
        emo_menu.addAction(cog_act)

        phaseon_menu = mb.addMenu("Phaseon")
        phaseon_act = QAction("Phaseon Dashboard", self)
        phaseon_act.triggered.connect(self._show_phaseon)
        phaseon_menu.addAction(phaseon_act)

        training_menu = mb.addMenu("Training")
        training_lab_act = QAction("Training Lab", self)
        training_lab_act.triggered.connect(lambda: self._stack.setCurrentIndex(PAGE_TRAINING))
        training_menu.addAction(training_lab_act)

        settings_menu = mb.addMenu("Settings")
        self._filter_act = QAction("Filter Signal", self)
        self._filter_act.setCheckable(True)
        self._filter_act.setChecked(bool(EEG_FILTER_ENABLED_DEFAULT))
        self._filter_act.toggled.connect(self._on_filter_toggled)
        settings_menu.addAction(self._filter_act)

    def _toolbar_btn(self, text, colour, bg):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {colour}; border: 1px solid {colour};"
            f" border-radius: 6px; padding: 5px 14px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {colour}; color: #111; }}"
        )
        return btn

    def _show_dashboard(self, section: str = ""):
        self._stack.setCurrentIndex(PAGE_DASHBOARD)
        section_map = {
            "Rhythms Diagram": "rhythms_diagram",
        }
        section_id = section_map.get(section)
        if section_id:
            QTimer.singleShot(0, lambda sid=section_id: self._dash_screen.show_section(sid))

    def _show_mems(self, section: str = ""):
        self._stack.setCurrentIndex(PAGE_MEMS)
        section_map = {
            "Rhythms Diagram": "rhythms_diagram",
            "Accelerometer": "accelerometer",
            "Accelerometer Tab": "accelerometer",
            "Gyroscope": "gyroscope",
            "Gyroscope Tab": "gyroscope",
        }
        section_id = section_map.get(section)
        if section_id:
            QTimer.singleShot(0, lambda sid=section_id: self._mems_screen.show_section(sid))

    def _show_phaseon(self):
        self._stack.setCurrentIndex(PAGE_PHASEON)

    def _on_stop_signal(self):
        if self._streaming:
            self._streaming = False
            self._dash_screen.set_streaming_active(False)
            self._training_screen.set_streaming_active(False)
            self._update_live_view_activity(self._stack.currentIndex())
            self._dm.stop_streaming()
            self._stop_session()
            log.info("Signal stopped by user")

    def _on_start_signal(self):
        if self._session_active:
            return
        self._safe_start_streaming()
        if self._streaming:
            self._begin_session()
            log.info("Signal started by user")

    def _on_detect_iapf(self):
        self._begin_calibration_flow("detect")

    def _on_quick_iapf(self):
        self._begin_calibration_flow("quick")

    def _on_neuroflow_quick_calibration_requested(self):
        self._begin_calibration_flow("quick", embedded_neuroflow=True)

    def _begin_calibration_flow(self, mode: str, embedded_neuroflow: bool = False):
        if not self._dm.is_connected():
            QMessageBox.information(self, "Connect Device", "Connect a device before starting iAPF calibration.")
            if embedded_neuroflow:
                self._training_screen.on_neuroflow_calibration_finished(
                    False,
                    "Connect the device before starting Neuroflow calibration.",
                )
            return
        if not self._cal_mgr:
            if embedded_neuroflow:
                self._training_screen.on_neuroflow_calibration_finished(
                    False,
                    "Calibration manager is not ready.",
                )
            return

        self._embedded_neuroflow_calibration = bool(embedded_neuroflow)
        self._quick_background_calibration_active = False
        self._calibration_return_page = self._stack.currentIndex()
        self._streaming_before_calibration = self._streaming
        serial = self._dm.device_serial or ""

        self._cal_screen.set_mode(mode)
        self._cal_screen.set_result_text("")
        self._safe_start_streaming()
        if self._embedded_neuroflow_calibration:
            self._training_screen.set_streaming_active(True)
            self._training_screen.set_eeg_stream_metadata(
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
        if not self._embedded_neuroflow_calibration:
            self._stack.setCurrentIndex(PAGE_CALIBRATION)

        if mode == "detect":
            self._cal_mgr.start_detect(serial)
        else:
            self._cal_mgr.start_quick(serial)

    def _finish_calibration_flow(self):
        embedded_neuroflow = self._embedded_neuroflow_calibration
        if not self._session_active and not self._streaming_before_calibration and not embedded_neuroflow:
            self._dash_screen.set_streaming_active(False)
            self._training_screen.set_streaming_active(False)
            self._mems_screen.set_streaming_active(False)
            self._dm.stop_streaming()
            self._streaming = False
        if not embedded_neuroflow:
            self._stack.setCurrentIndex(self._calibration_return_page)
        self._embedded_neuroflow_calibration = False

    def _on_quick_calibration_ready(self, payload: dict):
        nfb = payload.get("nfb", {}) or {}
        freq = float(nfb.get("individualFrequency", 0.0) or 0.0)
        text = f"Calibration finished successfully ({freq:.2f} Hz)"
        log.info("Quick calibration visible phase finished: %s", text)
        self._cal_screen.set_result_text(text)
        self._quick_background_calibration_active = True
        if self._embedded_neuroflow_calibration:
            self._training_screen.on_neuroflow_calibration_finished(True, text)
        else:
            self._calibration_return_page = PAGE_DASHBOARD
            self._streaming_before_calibration = True
        QTimer.singleShot(0, self._finish_calibration_flow)

    def _connect_device_signals(self):
        self._dm.connection_changed.connect(self._on_device_connected)
        self._dm.battery_updated.connect(self._on_battery_updated)
        self._dm.resistance_updated.connect(self._on_resistance_updated)
        self._dm.mode_changed.connect(self._on_mode_updated)
        self._dm.error_occurred.connect(self._on_error)

    def _on_battery_updated(self, pct: int):
        self._dash_screen.set_battery(pct)
        self._mems_screen.set_battery(pct)
        self._phaseon_runtime.update_device_status(battery=pct)

    def _on_resistance_updated(self, data: dict):
        self._latest_resistances = data or {}
        self._dash_screen.on_resistance(data)
        if self._training_screen.is_neuroflow_active():
            self._training_screen.on_resistance(data or {})
        self._phaseon_runtime.ingest_resistances(data)
        if self._session_active:
            self._recorder.record_resistances(data or {})

    def _on_mode_updated(self, mode: int):
        mode_map = {
            0: "Resistance",
            1: "Signal",
            2: "Signal+Resistance",
            3: "MEMS",
            4: "Stop MEMS",
            5: "PPG",
            6: "Stop PPG",
        }
        mode_str = mode_map.get(int(mode), "Unspecified")
        self._dash_screen.set_mode(mode_str)
        self._mems_screen.set_mode(mode_str)
        self._phaseon_runtime.update_device_status(mode=mode_str)

    def _on_device_connected(self, status: int):
        try:
            status = int(status)
        except (ValueError, TypeError):
            log.warning("Invalid connection status: %r", status)
            return

        if status == 1:
            log.info("Device connected - serial %s", self._dm.device_serial)
            self._disconnect_timer.stop()
            self._dash_screen.set_session_info(
                connected=True,
                serial=self._dm.device_serial or "",
            )
            self._training_screen.on_connection_state(
                connected=True,
                serial=self._dm.device_serial or "",
            )
            self._mems_screen.set_session_info(
                connected=True,
                serial=self._dm.device_serial or "",
            )
            self._dash_screen.set_eeg_stream_metadata(
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
            self._training_screen.set_eeg_stream_metadata(
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
            self._phaseon_runtime.update_device_status(
                connected=True,
                serial=self._dm.device_serial or "",
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
            self._refresh_battery_now()

            if not self._classifiers_created:
                self._create_classifiers()

            serial = self._dm.device_serial or ""
            if self._cal_mgr and serial and self._cal_mgr.can_import(serial):
                self._cal_mgr.import_saved(serial)
            if not self._session_active:
                self._safe_start_streaming()
                if self._streaming:
                    self._begin_session()
                else:
                    QMessageBox.warning(
                        self,
                        "Start Signal Failed",
                        "The device connected, but live streaming could not be started.",
                    )
        elif status == 0:
            log.info("Device disconnected signal - starting debounce timer")
            self._phaseon_runtime.update_device_status(connected=False)
            if not self._disconnect_timer.isActive():
                self._disconnect_timer.start()

    def _confirm_disconnected(self):
        if not self._dm.is_connected():
            log.info("Device confirmed disconnected")
            self._streaming = False
            self._dash_screen.set_session_info(connected=False)
            self._training_screen.on_connection_state(
                connected=False,
                serial=self._dm.device_serial or "",
            )
            self._mems_screen.set_session_info(connected=False)
            self._phaseon_runtime.update_device_status(connected=False, session_id="")
            self._dash_screen.set_streaming_active(False)
            self._mems_screen.set_streaming_active(False)
            self._stop_session()

    def _create_classifiers(self):
        dev = self._dm.device
        lib = self._bridge.lib
        if dev is None:
            return

        try:
            self._emotions_h = EmotionsHandler(dev, lib, parent=self)
            self._prod_h = ProductivityHandler(dev, lib, parent=self)
            self._cardio_h = CardioHandler(dev, lib, parent=self)
            self._physio_h = PhysioHandler(dev, lib, parent=self)
        except Exception as exc:
            log.error("Failed to create classifiers: %s", _safe_str(exc))
            return

        try:
            self._mems_h = MemsHandler(dev, lib, parent=self)
        except Exception as exc:
            self._mems_h = None
            log.warning("MEMS handler unavailable: %s", _safe_str(exc))

        self._classifiers_created = True
        self._cal_mgr = CalibrationManager(dev, lib, self._prod_h, self._physio_h, parent=self)
        self._status_mon = DeviceStatusMonitor(self._dm, parent=self)

        self._emotions_h.states_updated.connect(self._on_emotions)
        self._prod_h.metrics_updated.connect(self._on_productivity)
        self._prod_h.indexes_updated.connect(self._on_productivity_indexes)
        self._cardio_h.cardio_updated.connect(self._on_cardio)
        self._cardio_h.ppg_updated.connect(self._on_ppg)
        self._cardio_h.calibrated.connect(lambda: self._dash_screen.set_ppg_calibrated(True))
        self._physio_h.states_updated.connect(self._on_physio_states)
        if self._mems_h:
            self._mems_h.mems_updated.connect(self._on_mems)

        self._dm.psd_received.connect(self._on_psd)
        self._dm.eeg_received.connect(self._on_eeg)
        self._dm.artifacts_received.connect(self._on_artifacts)

        self._emotions_h.error_occurred.connect(self._on_error)

        self._cal_mgr.stage_changed.connect(self._cal_screen.set_stage)
        self._cal_mgr.progress_updated.connect(self._cal_screen.set_progress)
        self._cal_mgr.quick_ready.connect(self._on_quick_calibration_ready)
        self._cal_mgr.calibration_complete.connect(self._on_calibration_done)
        self._cal_mgr.calibration_failed.connect(self._on_calibration_failed)
        self._cal_mgr.iapf_updated.connect(self._on_iapf_updated)

        self._cal_screen.cancel_button.clicked.connect(self._cancel_calibration)

        self._status_mon.battery_polled.connect(self._on_battery_updated)
        self._status_mon.disconnection_detected.connect(self._on_disconnect_detected)
        self._status_mon.reconnection_failed.connect(self._on_reconnect_failed)
        self._status_mon.reconnection_succeeded.connect(self._on_reconnect_ok)

    def _on_calibration_done(self, cal_data: dict):
        mode = cal_data.get("mode", "quick")
        nfb = cal_data.get("nfb", {})
        freq = float(nfb.get("individualFrequency", 0.0) or 0.0) if nfb else 0.0
        if mode == "detect":
            text = f"iAPF detection finished successfully ({freq:.2f} Hz)"
        else:
            if self._quick_background_calibration_active:
                text = f"Background baselines ready ({freq:.2f} Hz)"
            else:
                text = f"Calibration finished successfully ({freq:.2f} Hz)"
            if self._session_active:
                self._recorder.record_baselines(cal_data)
        log.info("Calibration finished: %s", text)
        self._cal_screen.set_result_text(text)
        if mode == "quick" and self._quick_background_calibration_active:
            self._quick_background_calibration_active = False
            return
        if self._embedded_neuroflow_calibration:
            self._training_screen.on_neuroflow_calibration_finished(True, text)
        else:
            self._calibration_return_page = PAGE_DASHBOARD
            self._streaming_before_calibration = True
        QTimer.singleShot(0, self._finish_calibration_flow)

    def _on_calibration_failed(self, reason: str):
        log.warning("Calibration failed: %s", reason)
        self._cal_screen.set_result_text(reason)
        if self._quick_background_calibration_active:
            self._quick_background_calibration_active = False
            return
        if self._embedded_neuroflow_calibration:
            self._training_screen.on_neuroflow_calibration_finished(False, reason)
        else:
            QMessageBox.warning(self, "Calibration Failed", reason)
        self._finish_calibration_flow()

    def _cancel_calibration(self):
        self._cal_screen.set_result_text("Calibration cancelled.")
        self._quick_background_calibration_active = False
        if self._embedded_neuroflow_calibration:
            self._training_screen.on_neuroflow_calibration_finished(False, "Calibration cancelled.")
        self._finish_calibration_flow()

    def _on_iapf_updated(self, payload: dict):
        self._iapf_status = {
            "frequency": payload.get("frequency"),
            "source": payload.get("source", "Not set"),
            "status": payload.get("status", "Not set"),
            "applied": bool(payload.get("applied", False)),
        }
        frequency = self._iapf_status.get("frequency")
        if frequency in (None, 0):
            self._iapf_value_lbl.setText("iAPF: Not set")
        else:
            self._iapf_value_lbl.setText(f"iAPF: {float(frequency):.2f} Hz")
        self._iapf_detail_lbl.setText(
            f"Source: {self._iapf_status['source']} | {self._iapf_status['status']}"
        )
        self._dash_screen.set_iapf_status(
            frequency=self._iapf_status.get("frequency"),
            source=self._iapf_status.get("source", "Not set"),
            status=self._iapf_status.get("status", "Not set"),
            applied=self._iapf_status.get("applied", False),
        )
        if self._training_screen.is_neuroflow_active():
            self._training_screen.on_iapf_status(self._iapf_status)
        self._recorder.update_calibration_info(self._iapf_status)

    def _begin_session(self):
        if self._session_active:
            return

        metadata = {
            "deviceInfo": {
                "deviceType": self._conn_screen.selected_device_type_value,
                "deviceTypeLabel": self._conn_screen.selected_device_type_label,
                "serial": self._dm.device_serial or "",
            },
            "calibrationInfo": dict(self._iapf_status),
        }
        self._recorder.start_session(metadata, self._conn_screen.selected_write_options)
        if self._recorder.file_path:
            self._dash_screen.set_session_file(self._recorder.file_path)
        self._dash_screen.reset_session(self._recorder.session_id)
        self._dash_screen.set_eeg_stream_metadata(
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )
        self._dash_screen.set_streaming_active(True)
        self._training_screen.set_streaming_active(True)
        self._training_screen.set_eeg_stream_metadata(
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )
        self._dash_screen.set_eeg_filter_enabled(self._filter_act.isChecked())
        self._mems_screen.reset_session(self._recorder.session_id)
        self._mems_screen.set_streaming_active(True)
        self._latest_band_powers = {}
        self._latest_peak_freqs = {}
        self._phaseon_runtime.update_device_status(
            session_id=self._recorder.session_id,
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )
        self._log_timer.start()
        self._session_active = True
        self._update_live_view_activity(self._stack.currentIndex())

        if self._status_mon:
            self._status_mon.start()

        self._stack.setCurrentIndex(PAGE_DASHBOARD)

    def _safe_start_streaming(self):
        if self._streaming:
            return
        try:
            self._streaming = bool(self._dm.start_streaming())
        except Exception as exc:
            log.error("Failed to start streaming: %s", _safe_str(exc))
            self._streaming = False

    def _stop_session(self):
        self._dash_screen.set_streaming_active(False)
        self._training_screen.set_streaming_active(False)
        self._mems_screen.set_streaming_active(False)
        self._update_live_view_activity(self._stack.currentIndex())
        self._log_timer.stop()
        if self._session_active:
            self._recorder.stop_session()
            self._sessions_screen.refresh_list()
        self._session_active = False
        self._phaseon_runtime.update_device_status(session_id="")
        self._dash_screen.stop_eeg_timer()
        if self._status_mon:
            self._status_mon.stop()

    def _on_emotions(self, data: dict):
        self._latest_emo = data or {}
        self._dash_screen.on_emotions(data)
        self._training_screen.on_emotions(data)
        if self._session_active:
            self._recorder.record_emotions(self._latest_emo)

    def _on_productivity(self, data: dict):
        self._latest_prod = data or {}
        self._dash_screen.on_productivity(data)
        self._phaseon_runtime.ingest_productivity(data)
        self._training_screen.on_productivity(data)
        if self._session_active:
            self._recorder.record_productivity_metrics(self._latest_prod)

    def _on_productivity_indexes(self, data: dict):
        self._latest_indexes = data or {}
        self._dash_screen.on_indexes(data)
        if self._session_active:
            self._recorder.record_productivity_indexes(self._latest_indexes)

    def _on_cardio(self, data: dict):
        self._latest_cardio = data or {}
        self._dash_screen.on_cardio(data)
        self._training_screen.on_cardio(data)

    def _on_ppg(self, ppg_timed_data):
        if not self._streaming:
            return
        self._dash_screen.on_ppg(ppg_timed_data)
        if self._session_active:
            self._recorder.record_ppg_packet(ppg_timed_data)

    def _on_physio_states(self, data: dict):
        self._latest_physio = data or {}
        self._dash_screen.on_physio_states(data)
        self._training_screen.on_physio_states(data)

    def _on_psd(self, psd_data):
        if not self._streaming:
            return
        psd_snapshot = self._extract_psd_snapshot(psd_data)
        if not psd_snapshot:
            return
        self._latest_psd_t = float(psd_snapshot.get("received_at", time.monotonic()))
        self._latest_band_powers = dict(psd_snapshot.get("band_powers", {}))
        self._latest_peak_freqs = dict(psd_snapshot.get("peak_frequencies", {}))
        self._training_screen.update_signal_snapshot(
            self._latest_band_powers,
            self._latest_peak_freqs,
            self._latest_psd_t,
        )
        if self._stack.currentIndex() == PAGE_DASHBOARD:
            if hasattr(self._dash_screen, "on_psd_snapshot"):
                self._dash_screen.on_psd_snapshot(psd_snapshot)
            else:
                self._dash_screen.on_psd(psd_data)
        if self._stack.currentIndex() == PAGE_MEMS:
            self._mems_screen.on_band_powers(self._latest_band_powers)

    def _on_eeg(self, eeg_timed_data):
        if not self._streaming:
            return
        dashboard_visible = self._stack.currentIndex() == PAGE_DASHBOARD
        if not dashboard_visible and not self._session_active:
            return
        eeg_snapshot = self._extract_eeg_snapshot(eeg_timed_data)
        if not eeg_snapshot:
            return
        if dashboard_visible:
            if hasattr(self._dash_screen, "on_eeg_snapshot"):
                self._dash_screen.on_eeg_snapshot(eeg_snapshot)
            else:
                self._dash_screen.on_eeg(eeg_timed_data)
        if self._session_active:
            if hasattr(self._recorder, "record_raw_eeg_snapshot"):
                self._recorder.record_raw_eeg_snapshot(eeg_snapshot)
            else:
                self._recorder.record_raw_eeg_packet(eeg_timed_data)

    def _on_artifacts(self, artifacts):
        if not self._streaming:
            return
        self._dash_screen.on_artifacts(artifacts)
        if self._session_active:
            self._recorder.record_artifacts(artifacts)

    def _on_mems(self, mems_timed_data):
        if not self._streaming:
            return
        if self._stack.currentIndex() == PAGE_MEMS:
            self._mems_screen.on_mems(mems_timed_data)
        if self._session_active:
            self._recorder.record_mems_packet(mems_timed_data)

    def _log_tick(self):
        self._recorder.log_metrics_row(
            emotions=self._latest_emo,
            productivity=self._latest_prod,
            cardio=self._latest_cardio,
            band_powers=self._latest_band_powers,
            peak_freqs=self._latest_peak_freqs,
        )
        self._recorder.record_cardio_metrics(
            {
                **self._latest_cardio,
                **self._dash_screen.ppg_metrics,
            }
        )
        self._recorder.record_rhythms(self._latest_band_powers)
        self._recorder.record_eeg_summary(
            self._latest_band_powers,
            self._latest_peak_freqs,
            self._filter_act.isChecked(),
            self._iapf_status,
        )

    def _on_filter_toggled(self, checked: bool):
        self._dash_screen.set_eeg_filter_enabled(bool(checked))
        self._conn_screen.set_filter_signal_checked(bool(checked))

    def _on_connection_filter_changed(self, checked: bool):
        if self._filter_act.isChecked() != bool(checked):
            self._filter_act.setChecked(bool(checked))

    def _on_disconnect_detected(self):
        log.warning("Device disconnected - attempting to reconnect")
        self._dash_screen.set_session_info(connected=False)
        self._training_screen.on_connection_state(
            connected=False, serial=self._dm.device_serial or ""
        )
        self._mems_screen.set_session_info(connected=False)
        self._phaseon_runtime.update_device_status(connected=False)

    def _on_reconnect_failed(self):
        log.error("Reconnection failed after max attempts")
        QMessageBox.warning(
            self,
            "Disconnected",
            "Could not reconnect to the device.\nPlease check the hardware and try again.",
        )
        self._stop_session()
        self._stack.setCurrentIndex(PAGE_CONNECTION)

    def _on_reconnect_ok(self):
        log.info("Reconnected successfully")
        self._dash_screen.set_session_info(
            connected=True, serial=self._dm.device_serial or ""
        )
        self._training_screen.on_connection_state(
            connected=True, serial=self._dm.device_serial or ""
        )
        self._training_screen.set_eeg_stream_metadata(
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )
        self._mems_screen.set_session_info(
            connected=True, serial=self._dm.device_serial or ""
        )
        self._phaseon_runtime.update_device_status(
            connected=True,
            serial=self._dm.device_serial or "",
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )

    def _on_error(self, msg):
        log.error("Error: %s", _safe_str(msg))

    def _refresh_battery_now(self):
        pct = self._dm.get_battery()
        if pct is None:
            pct = -1
        self._on_battery_updated(pct)

    def closeEvent(self, event):
        log.info("Application closing")
        self._stop_session()
        self._training_screen.shutdown()
        self._phaseon_runtime.shutdown()
        self._dm.disconnect()
        self._streaming = False
        self._recorder.shutdown()
        self._bridge.shutdown()
        super().closeEvent(event)

    def _update_live_view_activity(self, index: int):
        dashboard_active = index == PAGE_DASHBOARD
        mems_active = index == PAGE_MEMS
        training_active = index == PAGE_TRAINING
        self._dash_screen.set_view_active(dashboard_active)
        if hasattr(self._mems_screen, "set_view_active"):
            self._mems_screen.set_view_active(mems_active)
        if hasattr(self._training_screen, "set_view_active"):
            self._training_screen.set_view_active(training_active)

    @staticmethod
    def _extract_psd_summary(psd_data):
        snapshot = MainWindow._extract_psd_snapshot(psd_data)
        if not snapshot:
            return {}, {}
        return (
            dict(snapshot.get("band_powers", {})),
            dict(snapshot.get("peak_frequencies", {})),
        )

    @staticmethod
    def _extract_psd_snapshot(psd_data):
        try:
            n_freq = psd_data.get_frequencies_count()
            n_channels = psd_data.get_channels_count()
            if n_freq <= 0 or n_channels <= 0:
                return None
            freqs = np.asarray(
                [float(psd_data.get_frequency(idx)) for idx in range(n_freq)],
                dtype=float,
            )
            avg_power = np.zeros(n_freq, dtype=float)
            for ch_idx in range(n_channels):
                for f_idx in range(n_freq):
                    avg_power[f_idx] += float(psd_data.get_psd(ch_idx, f_idx))
            avg_power /= float(n_channels)
            band_powers = compute_band_powers(freqs, avg_power)
            peak_frequencies = compute_peak_frequencies(freqs, avg_power)
            return {
                "freqs": freqs.tolist(),
                "avg_power": avg_power.tolist(),
                "band_powers": dict(band_powers),
                "peak_frequencies": dict(peak_frequencies),
                "received_at": time.monotonic(),
            }
        except Exception:
            return None

    @staticmethod
    def _extract_eeg_snapshot(eeg_timed_data):
        try:
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()
        except Exception:
            return None
        if n_channels <= 0 or n_samples <= 0:
            return None

        timestamps_ms = []
        for sample_idx in range(n_samples):
            try:
                timestamps_ms.append(float(eeg_timed_data.get_timestamp(sample_idx)))
            except Exception:
                timestamps_ms.append(float(sample_idx))

        channels = {}
        processed_channels = {}
        for ch_idx in range(n_channels):
            try:
                raw = np.asarray(
                    [
                        float(eeg_timed_data.get_raw_value(ch_idx, sample_idx))
                        for sample_idx in range(n_samples)
                    ],
                    dtype=float,
                )
            except Exception:
                continue
            channels[ch_idx] = MainWindow._coerce_eeg_samples_to_microvolts(raw).tolist()

            if hasattr(eeg_timed_data, "get_processed_value"):
                try:
                    processed = np.asarray(
                        [
                            float(eeg_timed_data.get_processed_value(ch_idx, sample_idx))
                            for sample_idx in range(n_samples)
                        ],
                        dtype=float,
                    )
                    processed_channels[ch_idx] = MainWindow._coerce_eeg_samples_to_microvolts(processed).tolist()
                except Exception:
                    pass

        if not channels:
            return None
        snapshot = {
            "timestampsMs": timestamps_ms,
            "channels": channels,
        }
        if processed_channels:
            snapshot["processed_channels"] = processed_channels
        return snapshot

    @staticmethod
    def _coerce_eeg_samples_to_microvolts(samples: np.ndarray) -> np.ndarray:
        if samples.size == 0:
            return samples.astype(float)
        finite = np.abs(samples[np.isfinite(samples)])
        if finite.size == 0:
            return samples.astype(float)
        max_abs = float(np.max(finite))
        if max_abs <= 0.01:
            return samples * 1_000_000.0
        return samples.astype(float)


def _safe_str(value) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, Exception) and hasattr(value, "message"):
        return _safe_str(value.message)
    return str(value)
