"""
Main window orchestration for connection, calibration, dashboard, training, and sessions.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
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

from device.capsule_bridge import CapsuleBridge
from device.device_manager import DeviceManager
from gui.calibration_screen import CalibrationScreen
from gui.connection_screen import ConnectionScreen
from gui.dashboard_screen import DashboardScreen
from gui.graph_window_manager import GraphWindowManagerMixin
from gui.mems_screen import MemsScreen
from gui.phaseon_screen import PhaseonScreen
from gui.screen_router import (
    PAGE_CALIBRATION,
    PAGE_CONNECTION,
    PAGE_DASHBOARD,
    PAGE_MEMS,
    PAGE_PHASEON,
    PAGE_SESSIONS,
    PAGE_TRAINING,
    PAGE_YOUTUBE,
    ScreenRouterMixin,
)
from gui.sessions_screen import SessionsScreen
from gui.signal_dispatcher import SignalDispatcherMixin
from gui.training_screen import TrainingScreen
from gui.youtube_screen import YouTubeScreen
from gui.widgets.nav_bar import NavBar
from prosthetic_arm.phaseon_runtime import PhaseonRuntime
from storage.session_recorder import SessionRecorder
from utils.psd_worker import PsdWorker
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
from utils.helpers import (
    compute_band_powers,
    compute_hemisphere_band_powers,
    compute_peak_frequencies,
)


log = logging.getLogger(__name__)

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


class MainWindow(GraphWindowManagerMixin, ScreenRouterMixin, SignalDispatcherMixin, QMainWindow):
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

        self._latest_emo: dict = {}
        self._latest_prod: dict = {}
        self._latest_indexes: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}
        self._latest_resistances: dict = {}
        self._latest_band_powers: dict = {}
        self._latest_peak_freqs: dict = {}
        self._latest_psd_t: float | None = None
        self._graph_windows: dict[str, QWidget] = {}
        self._active_graphs: set[str] = set()
        self._graph_histories: dict[str, dict[str, deque]] = {}
        self._graph_references: dict[str, float | None] = {}
        self._graph_session_starts: dict[str, float] = {}
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

        self._psd_worker = PsdWorker(parent=self)
        self._psd_worker.result_ready.connect(self._on_psd_computed)

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
        self._youtube_screen = YouTubeScreen()

        self._stack.addWidget(self._conn_screen)
        self._stack.addWidget(self._cal_screen)
        self._stack.addWidget(self._dash_screen)
        self._stack.addWidget(self._mems_screen)
        self._stack.addWidget(self._training_screen)
        self._stack.addWidget(self._sessions_screen)
        self._stack.addWidget(self._phaseon_screen)
        self._stack.addWidget(self._youtube_screen)
        root.addWidget(self._stack, stretch=1)

        # ── Bottom NavBar: Home / Monitoring / Training / Sessions ────
        self._nav_bar = NavBar()
        root.addWidget(self._nav_bar)
        self._nav_bar.tab_selected.connect(self._on_nav_tab_selected)
        self._stack.currentChanged.connect(self._sync_nav_bar)
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

        home_act = QAction("Home", self)
        home_act.triggered.connect(self._go_home)
        mb.addAction(home_act)

        eeg_menu = mb.addMenu("EEG")
        eeg_graph_map = {
            "Frequency Peaks": "frequency_peaks",
            "Concentration Index": "concentration_index",
            "Relaxation Index": "relaxation_index",
            "Fatigue Score": "fatigue_score",
            "Reverse Fatigue Score": "reverse_fatigue_score",
            "Accumulated Fatigue": "accumulated_fatigue",
            "EEG Quality": "eeg_quality",
        }
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
            act.triggered.connect(lambda checked=False, gid=eeg_graph_map[name]: self._show_metric_graph(gid))
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
        productivity_graph_map = {
            "Concentration Index": "concentration_index",
            "Fatigue Score": "fatigue_score",
            "Reverse Fatigue Score": "reverse_fatigue_score",
            "Alpha Gravity": "alpha_gravity",
            "Productivity Score": "productivity_score",
        }
        for name in [
            "Productivity Tab",
            "Concentration Index",
            "Fatigue Score",
            "Reverse Fatigue Score",
            "Alpha Gravity",
            "Productivity Score",
        ]:
            act = QAction(name, self)
            if name == "Productivity Tab":
                act.triggered.connect(lambda checked=False, n=name: self._show_dashboard(n))
            else:
                act.triggered.connect(lambda checked=False, gid=productivity_graph_map[name]: self._show_metric_graph(gid))
            prod_menu.addAction(act)

        emo_menu = mb.addMenu("Emotions")
        cog_act = QAction("Cognitive States", self)
        cog_act.triggered.connect(lambda: self._show_metric_graph("cognitive_states"))
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
            f" border-radius: 8px; padding: 5px 16px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {colour}; color: #0A0A14; }}"
            f"QPushButton:disabled {{ background: #1A1E2E; color: #444; border-color: #333; }}"
        )
        return btn

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

    def _on_calibration_done(self, cal_data: dict):
        mode = cal_data.get("mode", "quick")
        nfb = cal_data.get("nfb", {})
        freq = float(nfb.get("individualFrequency", 0.0) or 0.0) if nfb else 0.0
        self._update_graph_references_from_prod_baselines(cal_data.get("prod_baselines", {}))
        if mode == "detect":
            text = f"iAPF detection finished successfully ({freq:.2f} Hz)"
        else:
            text = f"Calibration finished successfully ({freq:.2f} Hz)"
            if self._session_active:
                self._recorder.record_baselines(cal_data)
        log.info("Calibration finished: %s", text)
        self._cal_screen.set_result_text(text)
        if self._embedded_neuroflow_calibration:
            self._training_screen.on_neuroflow_calibration_finished(True, text)
        QTimer.singleShot(1200, self._finish_calibration_flow)
    def _on_calibration_failed(self, reason: str):
        log.warning("Calibration failed: %s", reason)
        self._cal_screen.set_result_text(reason)
        if self._embedded_neuroflow_calibration:
            self._training_screen.on_neuroflow_calibration_finished(False, reason)
        else:
            QMessageBox.warning(self, "Calibration Failed", reason)
        self._finish_calibration_flow()

    def _cancel_calibration(self):
        self._cal_screen.set_result_text("Calibration cancelled.")
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

        self._reset_metric_graph_history()
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

    def _refresh_battery_now(self):
        pct = self._dm.get_battery()
        if pct is None:
            pct = -1
        self._on_battery_updated(pct)

    def closeEvent(self, event):
        log.info("Application closing")
        self._stop_session()
        for window in self._graph_windows.values():
            try:
                window.close()
            except Exception:
                pass
        self._training_screen.shutdown()
        self._phaseon_runtime.shutdown()
        self._dm.disconnect()
        self._streaming = False
        self._recorder.shutdown()
        self._psd_worker.shutdown()
        self._bridge.shutdown()
        super().closeEvent(event)

    @staticmethod
    def _extract_psd_raw(psd_data):
        """Read raw frequency/power arrays from the DLL object (main-thread only)."""
        try:
            n_freq = psd_data.get_frequencies_count()
            n_channels = psd_data.get_channels_count()
            if n_freq <= 0 or n_channels <= 0:
                return None
            freqs = np.asarray(
                [float(psd_data.get_frequency(idx)) for idx in range(n_freq)],
                dtype=float,
            )
            channel_powers = np.zeros((n_channels, n_freq), dtype=float)
            for ch_idx in range(n_channels):
                for f_idx in range(n_freq):
                    channel_powers[ch_idx, f_idx] = float(psd_data.get_psd(ch_idx, f_idx))
            return freqs, channel_powers
        except Exception:
            return None

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
            channel_powers = np.zeros((n_channels, n_freq), dtype=float)
            for ch_idx in range(n_channels):
                for f_idx in range(n_freq):
                    channel_powers[ch_idx, f_idx] = float(psd_data.get_psd(ch_idx, f_idx))
            avg_power = np.mean(channel_powers, axis=0)
            band_powers = compute_band_powers(freqs, avg_power)
            left_band_powers, right_band_powers = compute_hemisphere_band_powers(freqs, channel_powers)
            peak_frequencies = compute_peak_frequencies(freqs, avg_power)
            return {
                "freqs": freqs.tolist(),
                "avg_power": avg_power.tolist(),
                "band_powers": dict(band_powers),
                "left_band_powers": dict(left_band_powers),
                "right_band_powers": dict(right_band_powers),
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
