"""
MainWindow - central orchestrator.

Owns every backend object, wires signals, and manages screen navigation.
Uses a top QMenuBar (matching Capsule reference app) instead of a bottom NavBar.

Screen indices:
  0 = ConnectionScreen
  1 = CalibrationScreen
  2 = DashboardScreen
  3 = TrainingScreen
  4 = SessionsScreen
"""
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QMessageBox, QMenuBar, QPushButton, QToolBar,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction

from utils.config import (
    WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    BG_NAV, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, BORDER_SUBTLE,
)

# ── Backend ───────────────────────────────────────────────────────────
from device.capsule_bridge import CapsuleBridge
from device.device_manager import DeviceManager
from device.device_status_monitor import DeviceStatusMonitor

from classifiers.emotions_handler import EmotionsHandler
from classifiers.productivity_handler import ProductivityHandler
from classifiers.cardio_handler import CardioHandler
from classifiers.physio_handler import PhysioHandler
from classifiers.mems_handler import MemsHandler

from calibration.calibration_manager import CalibrationManager
from storage.csv_logger import CSVLogger

# ── GUI ───────────────────────────────────────────────────────────────
from gui.connection_screen import ConnectionScreen
from gui.calibration_screen import CalibrationScreen
from gui.dashboard_screen import DashboardScreen
from gui.training_screen import TrainingScreen
from gui.sessions_screen import SessionsScreen

log = logging.getLogger(__name__)

PAGE_CONNECTION = 0
PAGE_CALIBRATION = 1
PAGE_DASHBOARD = 2
PAGE_TRAINING = 3
PAGE_SESSIONS = 4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.showMaximized()

        # ── Backend objects (order matters) ───────────────────────────
        self._bridge = CapsuleBridge()
        self._dm = DeviceManager(self._bridge, parent=self)

        # Classifier & calibration objects — created lazily after
        # device connection so Device instance is available.
        self._emotions_h: EmotionsHandler | None = None
        self._prod_h: ProductivityHandler | None = None
        self._cardio_h: CardioHandler | None = None
        self._physio_h: PhysioHandler | None = None
        self._mems_h: MemsHandler | None = None
        self._cal_mgr: CalibrationManager | None = None
        self._status_mon: DeviceStatusMonitor | None = None
        self._csv = CSVLogger()

        # Guards
        self._classifiers_created = False
        self._streaming = False

        # Debounce for transient disconnect events from SDK
        self._disconnect_timer = QTimer(self)
        self._disconnect_timer.setSingleShot(True)
        self._disconnect_timer.setInterval(5000)
        self._disconnect_timer.timeout.connect(self._confirm_disconnected)

        self._build_ui()
        self._connect_device_signals()

        # 1-Hz timer for CSV logging
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(1000)
        self._log_timer.timeout.connect(self._log_tick)

        # Latest data caches for CSV
        self._latest_emo: dict = {}
        self._latest_prod: dict = {}
        self._latest_cardio: dict = {}

    # ==================================================================
    #  UI construction
    # ==================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Menu bar ─────────────────────────────────────────────────
        self._build_menu_bar()

        # ── Toolbar buttons ──────────────────────────────────────────
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

        self._detect_iapf_btn = self._toolbar_btn("Detect iAPF (Closed Eyes)", "#FFB74D", "#3A2E1F")
        self._detect_iapf_btn.clicked.connect(self._start_calibration)
        tb_layout.addWidget(self._detect_iapf_btn)

        self._quick_cal_btn = self._toolbar_btn("Quick iAPF Calibration (Closed Eyes)", "#FFB74D", "#3A2E1F")
        self._quick_cal_btn.clicked.connect(self._start_calibration)
        tb_layout.addWidget(self._quick_cal_btn)

        tb_layout.addStretch()
        root.addWidget(toolbar_widget)

        # ── Stacked pages ────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._conn_screen = ConnectionScreen(self._dm)
        self._cal_screen = CalibrationScreen()
        self._dash_screen = DashboardScreen()
        self._training_screen = TrainingScreen()
        self._sessions_screen = SessionsScreen()

        self._stack.addWidget(self._conn_screen)      # 0
        self._stack.addWidget(self._cal_screen)       # 1
        self._stack.addWidget(self._dash_screen)      # 2
        self._stack.addWidget(self._training_screen)  # 3
        self._stack.addWidget(self._sessions_screen)  # 4
        root.addWidget(self._stack, stretch=1)

        # Wire connection-screen buttons
        self._conn_screen.start_cal_button.clicked.connect(self._start_calibration)
        self._conn_screen.skip_cal_button.clicked.connect(self._import_calibration)

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

        # ── File ─────────────────────────────────────────────────────
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

        # ── EEG ──────────────────────────────────────────────────────
        eeg_menu = mb.addMenu("EEG")
        for name in ["Frequency Peaks", "Rhythms Diagram", "Concentration Index",
                      "Relaxation Index", "Fatigue Score", "Reverse Fatigue Score",
                      "Accumulated Fatigue", "EEG Quality"]:
            act = QAction(name, self)
            act.triggered.connect(lambda checked, n=name: self._show_dashboard(n))
            eeg_menu.addAction(act)

        # ── PPG ──────────────────────────────────────────────────────
        ppg_menu = mb.addMenu("PPG")
        hr_act = QAction("Heart Rate", self)
        hr_act.triggered.connect(lambda: self._show_dashboard("Heart Rate"))
        ppg_menu.addAction(hr_act)

        # ── Productivity ─────────────────────────────────────────────
        prod_menu = mb.addMenu("Productivity")
        for name in ["Productivity Tab", "Concentration Index", "Fatigue Score",
                      "Reverse Fatigue Score", "Alpha Gravity", "Productivity Score"]:
            act = QAction(name, self)
            act.triggered.connect(lambda checked, n=name: self._show_dashboard(n))
            prod_menu.addAction(act)

        # ── Emotions ─────────────────────────────────────────────────
        emo_menu = mb.addMenu("Emotions")
        cog_act = QAction("Cognitive States", self)
        cog_act.triggered.connect(lambda: self._show_dashboard("Emotions"))
        emo_menu.addAction(cog_act)

        training_menu = mb.addMenu("Training")
        training_lab_act = QAction("Training Lab", self)
        training_lab_act.triggered.connect(lambda: self._stack.setCurrentIndex(PAGE_TRAINING))
        training_menu.addAction(training_lab_act)

        # ── Settings ─────────────────────────────────────────────────
        settings_menu = mb.addMenu("Settings")
        filter_act = QAction("Filter Signal", self)
        filter_act.setCheckable(True)
        filter_act.setChecked(True)
        settings_menu.addAction(filter_act)

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
        """Switch to dashboard page (menu items navigate here)."""
        self._stack.setCurrentIndex(PAGE_DASHBOARD)

    # ==================================================================
    #  Toolbar actions
    # ==================================================================
    def _on_stop_signal(self):
        if self._streaming:
            self._dm.stop_streaming()
            self._streaming = False
            self._stop_session()
            log.info("Signal stopped by user")

    def _on_start_signal(self):
        if not self._streaming:
            self._safe_start_streaming()
            if self._streaming:
                self._begin_session()
                log.info("Signal started by user")

    # ==================================================================
    #  Device-level signals
    # ==================================================================
    def _connect_device_signals(self):
        self._dm.connection_changed.connect(self._on_device_connected)
        self._dm.battery_updated.connect(self._on_battery_updated)
        self._dm.resistance_updated.connect(self._on_resistance_updated)
        self._dm.mode_changed.connect(self._on_mode_updated)
        self._dm.error_occurred.connect(self._on_error)

    def _on_battery_updated(self, pct: int):
        self._dash_screen.set_battery(pct)

    def _on_resistance_updated(self, data: dict):
        self._dash_screen.on_resistance(data)

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
        self._dash_screen.set_mode(mode_map.get(int(mode), "Unspecified"))

    def _on_device_connected(self, status: int):
        try:
            status = int(status)
        except (ValueError, TypeError):
            log.warning("Invalid connection status: %r", status)
            return

        if status == 1:
            log.info("Device connected – serial %s", self._dm.device_serial)
            self._disconnect_timer.stop()
            self._dash_screen.set_session_info(
                connected=True,
                serial=self._dm.device_serial or "",
            )

            if not self._classifiers_created:
                self._create_classifiers()

            serial = self._dm.device_serial or ""
            if self._cal_mgr and self._cal_mgr.can_import(serial):
                self._conn_screen.show_skip_button(True)
        elif status == 0:
            log.info("Device disconnected signal – starting debounce timer")
            if not self._disconnect_timer.isActive():
                self._disconnect_timer.start()

    def _confirm_disconnected(self):
        if not self._dm.is_connected():
            log.info("Device confirmed disconnected")
            self._dash_screen.set_session_info(connected=False)
            self._streaming = False
            self._stop_session()

    # ==================================================================
    #  Classifier creation (post-connection, pre-start)
    # ==================================================================
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
            self._mems_h = MemsHandler(dev, lib, parent=self)
        except Exception as exc:
            log.error("Failed to create classifiers: %s", _safe_str(exc))
            return

        self._classifiers_created = True

        self._cal_mgr = CalibrationManager(
            dev, lib, self._prod_h, self._physio_h, parent=self
        )

        self._status_mon = DeviceStatusMonitor(self._dm, parent=self)

        # ── Connect classifier → dashboard ───────────────────────────
        self._emotions_h.states_updated.connect(self._on_emotions)
        self._prod_h.metrics_updated.connect(self._on_productivity)
        self._prod_h.indexes_updated.connect(self._dash_screen.on_indexes)
        self._cardio_h.cardio_updated.connect(self._on_cardio)
        self._cardio_h.ppg_updated.connect(self._dash_screen.on_ppg)
        self._cardio_h.calibrated.connect(lambda: self._dash_screen.set_ppg_calibrated(True))
        self._physio_h.states_updated.connect(self._on_physio_states)
        self._mems_h.mems_updated.connect(self._dash_screen.on_mems)

        # ── Connect raw signal → dashboard ───────────────────────────
        self._dm.psd_received.connect(self._dash_screen.on_psd)
        self._dm.eeg_received.connect(self._dash_screen.on_eeg)
        self._dm.artifacts_received.connect(self._dash_screen.on_artifacts)

        # Connect classifier errors
        self._emotions_h.error_occurred.connect(self._on_error)

        # Calibration manager → calibration screen
        self._cal_mgr.stage_changed.connect(self._cal_screen.set_stage)
        self._cal_mgr.progress_updated.connect(self._cal_screen.set_progress)
        self._cal_mgr.calibration_complete.connect(self._on_calibration_done)
        self._cal_mgr.calibration_failed.connect(self._on_calibration_failed)

        # Cal screen cancel
        self._cal_screen.cancel_button.clicked.connect(self._cancel_calibration)

        # Status monitor
        self._status_mon.battery_polled.connect(self._on_battery_updated)
        self._status_mon.disconnection_detected.connect(self._on_disconnect_detected)
        self._status_mon.reconnection_failed.connect(self._on_reconnect_failed)
        self._status_mon.reconnection_succeeded.connect(self._on_reconnect_ok)

    # ==================================================================
    #  Calibration flow
    # ==================================================================
    def _start_calibration(self):
        if not self._cal_mgr:
            return
        serial = self._dm.device_serial or ""
        self._safe_start_streaming()
        self._stack.setCurrentIndex(PAGE_CALIBRATION)
        self._cal_mgr.start(serial)

    def _import_calibration(self):
        if not self._cal_mgr:
            return
        serial = self._dm.device_serial or ""
        ok = self._cal_mgr.import_saved(serial)
        if ok:
            self._cal_screen.set_result_text("Previous calibration imported ✓")
            self._begin_session()
        else:
            QMessageBox.warning(self, "Import Error", "Could not load saved calibration.")

    def _on_calibration_done(self, cal_data: dict):
        log.info("Calibration complete")
        self._cal_screen.set_result_text("Calibration complete ✓")
        QTimer.singleShot(1200, self._begin_session)

    def _on_calibration_failed(self, reason: str):
        log.warning("Calibration failed: %s", reason)
        QMessageBox.warning(self, "Calibration Failed", reason)
        self._stack.setCurrentIndex(PAGE_CONNECTION)

    def _cancel_calibration(self):
        self._dm.stop_streaming()
        self._streaming = False
        self._stack.setCurrentIndex(PAGE_CONNECTION)

    # ==================================================================
    #  Session start / stop
    # ==================================================================
    def _begin_session(self):
        log.info("Session started")
        self._safe_start_streaming()

        self._csv.start_session()
        if self._csv.file_path:
            self._dash_screen.set_session_file(self._csv.file_path)
        self._dash_screen.reset_session()
        self._log_timer.start()

        if self._status_mon:
            self._status_mon.start()

        self._stack.setCurrentIndex(PAGE_DASHBOARD)

    def _safe_start_streaming(self):
        if self._streaming:
            return
        try:
            self._dm.start_streaming()
            self._streaming = True
        except Exception as exc:
            log.error("Failed to start streaming: %s", _safe_str(exc))
            self._streaming = False

    def _stop_session(self):
        log.info("Session stopped")
        self._log_timer.stop()
        self._csv.stop_session()
        self._dash_screen.stop_eeg_timer()
        if self._status_mon:
            self._status_mon.stop()

    # ==================================================================
    #  Data slots
    # ==================================================================
    def _on_emotions(self, data: dict):
        self._latest_emo = data
        self._dash_screen.on_emotions(data)
        self._training_screen.on_emotions(data)

    def _on_productivity(self, data: dict):
        self._latest_prod = data
        self._dash_screen.on_productivity(data)
        self._training_screen.on_productivity(data)

    def _on_cardio(self, data: dict):
        self._latest_cardio = data
        self._dash_screen.on_cardio(data)
        self._training_screen.on_cardio(data)

    def _on_physio_states(self, data: dict):
        self._dash_screen.on_physio_states(data)
        self._training_screen.on_physio_states(data)

    def _log_tick(self):
        """Called every 1 s to push a row into the CSV logger."""
        self._csv.log_row(
            emotions=self._latest_emo,
            productivity=self._latest_prod,
            cardio=self._latest_cardio,
            band_powers=self._dash_screen.band_powers,
            peak_freqs=self._dash_screen.peak_frequencies,
        )

    # ==================================================================
    #  Disconnection / reconnection
    # ==================================================================
    def _on_disconnect_detected(self):
        log.warning("Headband disconnected – attempting to reconnect…")
        self._dash_screen.set_session_info(connected=False)

    def _on_reconnect_failed(self):
        log.error("Reconnection failed after max attempts")
        QMessageBox.warning(
            self,
            "Disconnected",
            "Could not reconnect to the headband.\n"
            "Please check the device and try again.",
        )
        self._stop_session()
        self._stack.setCurrentIndex(PAGE_CONNECTION)

    def _on_reconnect_ok(self):
        log.info("Reconnected successfully")
        self._dash_screen.set_session_info(
            connected=True, serial=self._dm.device_serial or ""
        )

    # ==================================================================
    #  Error handling
    # ==================================================================
    def _on_error(self, msg):
        log.error("Error: %s", _safe_str(msg))

    # ==================================================================
    #  Cleanup
    # ==================================================================
    def closeEvent(self, event):
        log.info("Application closing")
        self._stop_session()
        self._training_screen.stop_audio()
        self._dm.disconnect()
        self._streaming = False
        self._bridge.shutdown()
        super().closeEvent(event)


def _safe_str(value) -> str:
    """Convert a value to str, handling bytes from CapsuleException."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, Exception) and hasattr(value, "message"):
        return _safe_str(value.message)
    return str(value)
