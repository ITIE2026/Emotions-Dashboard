"""
MainWindow – central orchestrator.

Owns every backend object, wires signals, and manages screen navigation
via a QStackedWidget.

Screen indices:
  0 = ConnectionScreen
  1 = CalibrationScreen
  2 = DashboardScreen
  3 = TrackingScreen
"""
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from utils.config import WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT

# ── Backend ───────────────────────────────────────────────────────────
from device.capsule_bridge import CapsuleBridge
from device.device_manager import DeviceManager
from device.device_status_monitor import DeviceStatusMonitor

from classifiers.emotions_handler import EmotionsHandler
from classifiers.productivity_handler import ProductivityHandler
from classifiers.cardio_handler import CardioHandler
from classifiers.physio_handler import PhysioHandler

from calibration.calibration_manager import CalibrationManager
from storage.csv_logger import CSVLogger

# ── GUI ───────────────────────────────────────────────────────────────
from gui.widgets.status_bar import StatusBar
from gui.widgets.nav_bar import NavBar
from gui.connection_screen import ConnectionScreen
from gui.calibration_screen import CalibrationScreen
from gui.dashboard_screen import DashboardScreen
from gui.tracking_screen import TrackingScreen

log = logging.getLogger(__name__)

PAGE_CONNECTION = 0
PAGE_CALIBRATION = 1
PAGE_DASHBOARD = 2
PAGE_TRACKING = 3


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # ── Backend objects (order matters) ───────────────────────────
        self._bridge = CapsuleBridge()
        self._dm = DeviceManager(self._bridge, parent=self)

        # Classifier & calibration objects — created lazily after
        # device connection so Device instance is available.
        self._emotions_h: EmotionsHandler | None = None
        self._prod_h: ProductivityHandler | None = None
        self._cardio_h: CardioHandler | None = None
        self._physio_h: PhysioHandler | None = None
        self._cal_mgr: CalibrationManager | None = None
        self._status_mon: DeviceStatusMonitor | None = None
        self._csv = CSVLogger()

        # Guards
        self._classifiers_created = False
        self._streaming = False

        # ── GUI ───────────────────────────────────────────────────────
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

        # Status bar (top)
        self._status_bar = StatusBar()
        root.addWidget(self._status_bar)

        # Stacked pages
        self._stack = QStackedWidget()
        self._conn_screen = ConnectionScreen(self._dm)
        self._cal_screen = CalibrationScreen()
        self._dash_screen = DashboardScreen()
        self._track_screen = TrackingScreen()

        self._stack.addWidget(self._conn_screen)     # 0
        self._stack.addWidget(self._cal_screen)      # 1
        self._stack.addWidget(self._dash_screen)      # 2
        self._stack.addWidget(self._track_screen)     # 3
        root.addWidget(self._stack, stretch=1)

        # Navigation bar (bottom)
        self._nav = NavBar()
        self._nav.tab_selected.connect(self._on_tab)
        root.addWidget(self._nav)

        # Wire connection-screen buttons
        self._conn_screen.start_cal_button.clicked.connect(self._start_calibration)
        self._conn_screen.skip_cal_button.clicked.connect(self._import_calibration)

    # ==================================================================
    #  Device-level signals
    # ==================================================================
    def _connect_device_signals(self):
        self._dm.connection_changed.connect(self._on_device_connected)
        self._dm.battery_updated.connect(self._status_bar.set_battery)
        self._dm.error_occurred.connect(self._on_error)

    def _on_device_connected(self, status: int):
        try:
            status = int(status)
        except (ValueError, TypeError):
            log.warning("Invalid connection status: %r", status)
            return

        if status == 1:
            log.info("Device connected – serial %s", self._dm.device_serial)
            self._status_bar.set_connected(True, self._dm.device_serial or "")

            if not self._classifiers_created:
                self._create_classifiers()

            # Show "Import Previous" button if calibration is saved
            serial = self._dm.device_serial or ""
            if self._cal_mgr and self._cal_mgr.can_import(serial):
                self._conn_screen.show_skip_button(True)
        elif status == 0:
            log.info("Device disconnected")
            self._status_bar.set_connected(False)
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
        except Exception as exc:
            log.error("Failed to create classifiers: %s", _safe_str(exc))
            return

        self._classifiers_created = True

        self._cal_mgr = CalibrationManager(
            dev, lib, self._prod_h, self._physio_h, parent=self
        )

        self._status_mon = DeviceStatusMonitor(self._dm, parent=self)

        # Connect classifier → dashboard
        self._emotions_h.states_updated.connect(self._on_emotions)
        self._prod_h.metrics_updated.connect(self._on_productivity)
        self._prod_h.indexes_updated.connect(self._dash_screen.on_indexes)
        self._cardio_h.cardio_updated.connect(self._on_cardio)
        self._physio_h.states_updated.connect(self._on_physio_states)

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
        self._status_mon.battery_polled.connect(self._status_bar.set_battery)
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
        # Short delay then go to dashboard
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
        # Ensure streaming is active (idempotent)
        self._safe_start_streaming()

        # Start subsystems
        self._csv.start_session()
        self._dash_screen.start_graph()
        self._track_screen.start_session()
        self._log_timer.start()

        if self._status_mon:
            self._status_mon.start()

        self._stack.setCurrentIndex(PAGE_DASHBOARD)

    def _safe_start_streaming(self):
        """Start device streaming only if not already streaming."""
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
        self._dash_screen.stop_graph()
        if self._status_mon:
            self._status_mon.stop()

    # ==================================================================
    #  Data slots
    # ==================================================================
    def _on_emotions(self, data: dict):
        self._latest_emo = data
        self._dash_screen.on_emotions(data)
        self._track_screen.update_data(emotions=data)

    def _on_productivity(self, data: dict):
        self._latest_prod = data
        self._dash_screen.on_productivity(data)
        self._track_screen.update_data(productivity=data)

    def _on_cardio(self, data: dict):
        self._latest_cardio = data
        self._dash_screen.on_cardio(data)
        self._track_screen.update_data(cardio=data)

    def _on_physio_states(self, data: dict):
        self._dash_screen.on_physio_states(data)
        self._track_screen.update_data(physio=data)

    def _log_tick(self):
        """Called every 1 s to push a row into the CSV logger."""
        self._csv.log_row(
            emotions=self._latest_emo,
            productivity=self._latest_prod,
            cardio=self._latest_cardio,
        )

    # ==================================================================
    #  Disconnection / reconnection
    # ==================================================================
    def _on_disconnect_detected(self):
        log.warning("Headband disconnected – attempting to reconnect…")
        self._status_bar.set_connected(False)

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
        self._status_bar.set_connected(True, self._dm.device_serial or "")

    # ==================================================================
    #  Navigation
    # ==================================================================
    def _on_tab(self, idx: int):
        """NavBar tabs: 0=Home/Connection, 1=Monitoring, 2=Training(=Monitoring), 3=Tracking."""
        if idx == 0:
            self._stack.setCurrentIndex(PAGE_CONNECTION)
        elif idx in (1, 2):
            self._stack.setCurrentIndex(PAGE_DASHBOARD)
        elif idx == 3:
            self._stack.setCurrentIndex(PAGE_TRACKING)

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
