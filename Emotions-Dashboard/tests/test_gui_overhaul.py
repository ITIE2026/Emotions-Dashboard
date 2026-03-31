import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from calibration.calibration_manager import CalibrationManager  # noqa: E402
from gui.connection_screen import ConnectionScreen  # noqa: E402
from gui.sessions_screen import SessionsScreen  # noqa: E402
from storage.session_recorder import SessionRecorder  # noqa: E402


APP = QApplication.instance() or QApplication([])


class _FakeDeviceManager(QObject):
    devices_found = Signal(list)
    connection_changed = Signal(int)
    resistance_updated = Signal(dict)
    battery_updated = Signal(int)
    scan_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.last_scan_type = None
        self.connected_serial = None

    def scan_devices(self, device_type, timeout_sec=15):
        self.last_scan_type = device_type

    def connect_device(self, serial):
        self.connected_serial = serial

    def disconnect(self):
        self.connected_serial = None


class _FakeProdHandler(QObject):
    baselines_updated = Signal(object)
    calibration_progress = Signal(float)

    def __init__(self):
        super().__init__()
        self.started = False
        self.imported = None

    def import_baselines(self, baselines):
        self.imported = baselines

    def start_baseline_calibration(self):
        self.started = True


class _FakePhysioHandler(QObject):
    baselines_updated = Signal(object)
    calibration_progress = Signal(float)

    def __init__(self):
        super().__init__()
        self.started = False
        self.imported = None

    def import_baselines(self, baselines):
        self.imported = baselines

    def start_baseline_calibration(self):
        self.started = True


class _FakeCalibrator:
    def __init__(self, device, lib):
        self._finished = None
        self._stage = None

    def set_on_calibration_finished(self, callback):
        self._finished = callback

    def set_on_calibration_stage_finished(self, callback):
        self._stage = callback

    def calibrate_quick(self):
        return None

    def has_calibration_failed(self):
        return False

    def import_alpha(self, nfb):
        return None


class GuiOverhaulTests(unittest.TestCase):
    def test_connection_screen_defaults_write_options_and_device_type(self):
        dm = _FakeDeviceManager()
        screen = ConnectionScreen(dm)
        try:
            self.assertEqual(screen.selected_device_type_label, "Headband")
            self.assertEqual(screen._device_type_combo.count(), 2)
            self.assertEqual(len(screen.selected_write_options), 12)
            self.assertTrue(all(screen.selected_write_options.values()))

            screen._device_type_combo.setCurrentIndex(1)
            screen._on_scan()
            self.assertEqual(dm.last_scan_type, 2)
        finally:
            screen.close()

    def test_calibration_manager_detect_mode_stops_after_iapf_detection(self):
        prod = _FakeProdHandler()
        phys = _FakePhysioHandler()
        completed = []
        updates = []
        with patch("calibration.calibration_manager.Calibrator", _FakeCalibrator):
            manager = CalibrationManager(object(), object(), prod, phys)
            manager.calibration_complete.connect(completed.append)
            manager.iapf_updated.connect(updates.append)
            manager.start_detect("SER123")

            nfb = SimpleNamespace(
                timestampMilli=1,
                failReason=0,
                individualFrequency=10.4,
                individualPeakFrequency=10.6,
                individualPeakFrequencyPower=1.2,
                individualPeakFrequencySuppression=0.4,
                individualBandwidth=4.0,
                individualNormalizedPower=0.7,
                lowerFrequency=8.0,
                upperFrequency=12.0,
            )
            manager._on_nfb_finished(manager._calibrator, nfb)

        self.assertFalse(prod.started)
        self.assertFalse(phys.started)
        self.assertEqual(completed[-1]["mode"], "detect")
        self.assertFalse(completed[-1]["applied"])
        self.assertEqual(updates[-1]["source"], "Detected")

    def test_calibration_manager_quick_mode_keeps_baseline_stages(self):
        prod = _FakeProdHandler()
        phys = _FakePhysioHandler()
        completed = []
        with patch("calibration.calibration_manager.Calibrator", _FakeCalibrator):
            manager = CalibrationManager(object(), object(), prod, phys)
            manager.calibration_complete.connect(completed.append)
            manager.start_quick("SER456")
            APP.processEvents()
            self.assertFalse(prod.started)
            self.assertTrue(phys.started)

            nfb = SimpleNamespace(
                timestampMilli=1,
                failReason=0,
                individualFrequency=9.8,
                individualPeakFrequency=10.0,
                individualPeakFrequencyPower=1.1,
                individualPeakFrequencySuppression=0.3,
                individualBandwidth=4.0,
                individualNormalizedPower=0.6,
                lowerFrequency=8.0,
                upperFrequency=12.0,
            )
            manager._on_nfb_finished(manager._calibrator, nfb)
            self.assertFalse(prod.started)
            APP.processEvents()
            self.assertTrue(prod.started)
            self.assertTrue(phys.started)

            prod.baselines_updated.emit(SimpleNamespace(
                timestampMilli=1,
                gravity=1.0,
                productivity=2.0,
                fatigue=3.0,
                reverseFatigue=4.0,
                relaxation=5.0,
                concentration=6.0,
            ))
            phys.baselines_updated.emit(SimpleNamespace(
                timestampMilli=1,
                alpha=1.0,
                beta=2.0,
                alphaGravity=3.0,
                betaGravity=4.0,
                concentration=5.0,
            ))

        self.assertEqual(completed[-1]["mode"], "quick")
        self.assertTrue(completed[-1]["applied"])
        self.assertEqual(completed[-1]["phy_status"], "complete")

    def test_session_recorder_creates_bundle_and_optional_csv(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch("storage.session_recorder.SESSION_DIR", tempdir), patch(
                "storage.session_recorder.h5py", None
            ):
                recorder = SessionRecorder()
                recorder.start_session(
                    metadata={"deviceInfo": {"deviceTypeLabel": "Headband", "serial": "820628"}},
                    write_options={"export_to_csv": False},
                )
                session_dir = recorder.session_dir
                json_path = os.path.join(session_dir, "session.json")
                recorder.record_emotions({"focus": 60})
                recorder.stop_session()
                self.assertTrue(os.path.isdir(session_dir))
                self.assertTrue(os.path.isfile(json_path))
                self.assertFalse(os.path.exists(os.path.join(session_dir, "metrics.csv")))
                with open(json_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self.assertEqual(data["deviceInfo"]["serial"], "820628")
                self.assertIn("writeOptions", data)

    def test_sessions_screen_lists_bundle_sessions(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_dir = os.path.join(tempdir, "session-1")
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
                            "export_to_csv": {"label": "Export to csv", "enabled": True},
                            "raw_eeg": {"label": "Raw EEG", "enabled": True},
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
                    self.assertGreater(screen._session_list.count(), 0)
                    item = screen._session_list.item(0)
                    screen._on_select(item, None)
                    self.assertIn("Headband", screen._sum_device.text())
                    self.assertIn("Raw EEG", screen._sum_options.text())
                finally:
                    screen.close()


if __name__ == "__main__":
    unittest.main()
