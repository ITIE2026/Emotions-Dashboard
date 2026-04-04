import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from gui.dashboard_screen import DashboardScreen  # noqa: E402
from gui.screen_router import PAGE_INSTAGRAM, PAGE_MULTIPLAYER, PAGE_YOUTUBE  # noqa: E402
from gui.sessions_screen import SessionsScreen  # noqa: E402


APP = QApplication.instance() or QApplication([])


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)


class _DeviceManagerStub:
    def __init__(self, *args, **kwargs):
        self.connection_changed = _SignalStub()
        self.battery_updated = _SignalStub()
        self.resistance_updated = _SignalStub()
        self.mode_changed = _SignalStub()
        self.error_occurred = _SignalStub()
        self.psd_received = _SignalStub()
        self.eeg_received = _SignalStub()
        self.artifacts_received = _SignalStub()
        self.device = None
        self.device_serial = ""

    def stop_streaming(self):
        return None

    def start_streaming(self):
        return None

    def disconnect(self):
        return None

    def is_connected(self):
        return False


class _BridgeStub:
    def __init__(self, *args, **kwargs):
        self.lib = None

    def shutdown(self):
        return None


class _RecorderStub:
    def __init__(self, *args, **kwargs):
        self.file_path = ""
        self.session_id = "session-test"

    def start_session(self, *args, **kwargs):
        return None

    def stop_session(self):
        return None

    def update_calibration_info(self, *args, **kwargs):
        return None

    def record_mems_packet(self, *args, **kwargs):
        return None

    def record_resistances(self, *args, **kwargs):
        return None

    def record_emotions(self, *args, **kwargs):
        return None

    def record_productivity_metrics(self, *args, **kwargs):
        return None

    def record_productivity_indexes(self, *args, **kwargs):
        return None

    def record_ppg_packet(self, *args, **kwargs):
        return None

    def record_raw_eeg_packet(self, *args, **kwargs):
        return None

    def record_artifacts(self, *args, **kwargs):
        return None

    def log_metrics_row(self, *args, **kwargs):
        return None

    def record_cardio_metrics(self, *args, **kwargs):
        return None

    def record_rhythms(self, *args, **kwargs):
        return None

    def record_eeg_summary(self, *args, **kwargs):
        return None

    def shutdown(self):
        return None


class _SignalButtonStub:
    def __init__(self):
        self.clicked = _SignalStub()


class _ConnectionScreenStub(QWidget):
    filter_signal_changed = _SignalStub()
    selected_device_type_value = 0
    selected_device_type_label = "Headband"
    selected_write_options = {"raw_eeg": True}

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.filter_signal_changed = _SignalStub()

    def set_filter_signal_checked(self, *args, **kwargs):
        return None


class _CalibrationScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.cancel_button = _SignalButtonStub()

    def set_mode(self, *args, **kwargs):
        return None

    def set_result_text(self, *args, **kwargs):
        return None

    def set_stage(self, *args, **kwargs):
        return None

    def set_progress(self, *args, **kwargs):
        return None


class _DashboardScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def set_iapf_status(self, *args, **kwargs):
        return None

    def set_eeg_filter_enabled(self, *args, **kwargs):
        return None

    def set_streaming_active(self, *args, **kwargs):
        return None

    def set_session_info(self, *args, **kwargs):
        return None

    def set_battery(self, *args, **kwargs):
        return None

    def set_mode(self, *args, **kwargs):
        return None

    def set_view_active(self, *args, **kwargs):
        return None

    def set_eeg_stream_metadata(self, *args, **kwargs):
        return None

    def set_ppg_calibrated(self, *args, **kwargs):
        return None

    def on_resistance(self, *args, **kwargs):
        return None

    def on_emotions(self, *args, **kwargs):
        return None

    def on_productivity(self, *args, **kwargs):
        return None

    def on_indexes(self, *args, **kwargs):
        return None

    def on_cardio(self, *args, **kwargs):
        return None

    def on_ppg(self, *args, **kwargs):
        return None

    def on_physio_states(self, *args, **kwargs):
        return None

    def on_psd(self, *args, **kwargs):
        return None

    def on_psd_snapshot(self, *args, **kwargs):
        return None

    def on_eeg(self, *args, **kwargs):
        return None

    def on_eeg_snapshot(self, *args, **kwargs):
        return None

    def on_artifacts(self, *args, **kwargs):
        return None

    def reset_session(self, *args, **kwargs):
        return None

    def set_session_file(self, *args, **kwargs):
        return None

    def stop_eeg_timer(self):
        return None


class _MemsScreenStub(QWidget):
    def set_battery(self, *args, **kwargs):
        return None

    def set_mode(self, *args, **kwargs):
        return None

    def set_session_info(self, *args, **kwargs):
        return None

    def reset_session(self, *args, **kwargs):
        return None

    def set_streaming_active(self, *args, **kwargs):
        return None

    def on_band_powers(self, *args, **kwargs):
        return None

    def on_mems(self, *args, **kwargs):
        return None

    def set_view_active(self, *args, **kwargs):
        return None


class _TrainingScreenStub(QWidget):
    neuroflow_quick_calibration_requested = _SignalStub()

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.neuroflow_quick_calibration_requested = _SignalStub()

    def on_emotions(self, *args, **kwargs):
        return None

    def on_productivity(self, *args, **kwargs):
        return None

    def on_cardio(self, *args, **kwargs):
        return None

    def on_physio_states(self, *args, **kwargs):
        return None

    def on_connection_state(self, *args, **kwargs):
        return None

    def set_streaming_active(self, *args, **kwargs):
        return None

    def set_eeg_stream_metadata(self, *args, **kwargs):
        return None

    def is_neuroflow_active(self, *args, **kwargs):
        return False

    def on_resistance(self, *args, **kwargs):
        return None

    def on_iapf_status(self, *args, **kwargs):
        return None

    def update_signal_snapshot(self, *args, **kwargs):
        return None

    def on_mems(self, *args, **kwargs):
        return None

    def stop_active_flow(self, *args, **kwargs):
        return None

    def on_neuroflow_calibration_finished(self, *args, **kwargs):
        return None

    def shutdown(self):
        return None

    def set_view_active(self, *args, **kwargs):
        return None


class _SessionsScreenStub(QWidget):
    def refresh_list(self):
        return None


class _PhaseonRuntimeStub(QObject):
    def snapshot_state(self):
        return {}

    def snapshot_metrics(self):
        return {}

    def snapshot_resistances(self):
        return {}

    def snapshot_raw_payload(self):
        return {"channels": {}}

    def update_device_status(self, *args, **kwargs):
        return None

    def ingest_resistances(self, *args, **kwargs):
        return None

    def ingest_productivity(self, *args, **kwargs):
        return None

    def ingest_band_powers(self, *args, **kwargs):
        return None

    def ingest_eeg_packet(self, *args, **kwargs):
        return None

    def shutdown(self):
        return None


class _PhaseonScreenStub(QWidget):
    def __init__(self, runtime, *args, **kwargs):
        super().__init__()
        self.runtime = runtime


class _ToolWindowStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shutdown_called = False

    def set_streaming_active(self, *args, **kwargs):
        return None

    def set_view_active(self, *args, **kwargs):
        return None

    def shutdown(self):
        self.shutdown_called = True
        return None


class _InstagramScreenStub(_ToolWindowStub):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_active_calls = []
        self.app_active_calls = []

    def set_page_active(self, active):
        self.page_active_calls.append(bool(active))

    def set_app_active(self, active):
        self.app_active_calls.append(bool(active))
        return None


class _PsdWorkerStub(QObject):
    result_ready = Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__()

    def shutdown(self):
        return None


class _MouseControllerStub(QObject):
    toggled = Signal(bool)

    def __init__(self, *args, **kwargs):
        super().__init__()

    def toggle(self):
        self.toggled.emit(False)


class UiSmokeTests(unittest.TestCase):
    def _make_main_window(self):
        stack = ExitStack()
        for patcher in (
            patch("gui.main_window.CapsuleBridge", _BridgeStub),
            patch("gui.main_window.DeviceManager", _DeviceManagerStub),
            patch("gui.main_window.SessionRecorder", _RecorderStub),
            patch("gui.main_window.ConnectionScreen", _ConnectionScreenStub),
            patch("gui.main_window.CalibrationScreen", _CalibrationScreenStub),
            patch("gui.main_window.DashboardScreen", _DashboardScreenStub),
            patch("gui.main_window.MemsScreen", _MemsScreenStub),
            patch("gui.main_window.TrainingScreen", _TrainingScreenStub),
            patch("gui.main_window.SessionsScreen", _SessionsScreenStub),
            patch("gui.main_window.PhaseonRuntime", _PhaseonRuntimeStub),
            patch("gui.main_window.PhaseonScreen", _PhaseonScreenStub),
            patch("gui.main_window.GamesWindow", _ToolWindowStub),
            patch("gui.main_window.MultiplayerGameScreen", _ToolWindowStub),
            patch("gui.main_window.YouTubeScreen", _ToolWindowStub),
            patch("gui.main_window.InstagramScreen", _InstagramScreenStub),
            patch("gui.main_window.AimTrainerWindow", _ToolWindowStub),
            patch("gui.main_window.BrainSpellerWindow", _ToolWindowStub),
            patch("gui.main_window.BciMusicDjWindow", _ToolWindowStub),
            patch("gui.main_window.FocusTimerWindow", _ToolWindowStub),
            patch("gui.main_window.NeuroArtCanvasWindow", _ToolWindowStub),
            patch("gui.main_window.NeuroJournalWindow", _ToolWindowStub),
            patch("gui.main_window.BciMouseController", _MouseControllerStub),
            patch("gui.main_window.PsdWorker", _PsdWorkerStub),
            patch("gui.main_window.QTimer.singleShot", side_effect=lambda _ms, fn: fn()),
        ):
            stack.enter_context(patcher)
        self.addCleanup(stack.close)
        from gui.main_window import MainWindow
        window = MainWindow()
        self.addCleanup(window.close)
        return window

    def test_dashboard_filter_label_smoke(self):
        screen = DashboardScreen()
        try:
            self.assertEqual(screen._filter_label.text(), "EEG Filter: Fast")
        finally:
            screen.close()

    def test_sessions_screen_bundle_selection_smoke(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_dir = os.path.join(tempdir, "session-smoke")
            os.makedirs(session_dir, exist_ok=True)
            with open(os.path.join(session_dir, "session.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "sessionInfo": {
                            "startUTCUnixTimestamp": 1,
                            "endUTCUnixTimestamp": 2,
                        },
                        "deviceInfo": {"deviceTypeLabel": "Headband", "serial": "820628"},
                        "writeOptions": {
                            "raw_eeg": {"label": "Raw EEG", "enabled": True},
                            "export_to_csv": {"label": "Export to csv", "enabled": True},
                        },
                    },
                    handle,
                    indent=2,
                )
            with open(os.path.join(session_dir, "metrics.csv"), "w", encoding="utf-8") as handle:
                handle.write("time,cognitive score,focus\n")
                handle.write("2026-03-18 12:00,50,60\n")

            with patch("gui.sessions_screen.SESSION_DIR", tempdir):
                screen = SessionsScreen()
                try:
                    self.assertEqual(screen.session_count(), 1)
                    self.assertTrue(screen.select_session_index(0))
                    self.assertEqual(screen._sum_device.text(), "Device: Headband | Serial: 820628")
                    self.assertEqual(
                        screen._sum_options.text(),
                        "Write options: Raw EEG, Export to csv",
                    )
                finally:
                    screen.close()

    def test_main_window_multiplayer_and_media_routing_smoke(self):
        window = self._make_main_window()

        window._on_nav_tab_selected(4)
        self.assertEqual(window._stack.currentIndex(), PAGE_MULTIPLAYER)

        window._on_nav_tab_selected(6)
        self.assertEqual(window._stack.currentIndex(), PAGE_YOUTUBE)

        window._on_nav_tab_selected(7)
        self.assertEqual(window._stack.currentIndex(), PAGE_INSTAGRAM)

        captured_tabs = []
        original = window._nav_bar.set_active_tab

        def _spy(idx):
            captured_tabs.append(idx)
            return original(idx)

        window._nav_bar.set_active_tab = _spy
        window._sync_nav_bar(PAGE_MULTIPLAYER)
        window._sync_nav_bar(PAGE_YOUTUBE)
        window._sync_nav_bar(PAGE_INSTAGRAM)

        self.assertEqual(captured_tabs, [4, 6, 7])

    def test_main_window_instagram_host_active_when_window_is_active(self):
        window = self._make_main_window()
        with patch.object(window, "isActiveWindow", return_value=True):
            self.assertTrue(
                window._is_instagram_host_app_active(Qt.ApplicationState.ApplicationInactive)
            )

    def test_main_window_instagram_lifecycle_smoke(self):
        window = self._make_main_window()
        instagram = window._instagram_screen

        window._on_nav_tab_selected(7)
        APP.processEvents()

        self.assertEqual(window._stack.currentIndex(), PAGE_INSTAGRAM)
        self.assertIn(True, instagram.page_active_calls)


if __name__ == "__main__":
    unittest.main()
