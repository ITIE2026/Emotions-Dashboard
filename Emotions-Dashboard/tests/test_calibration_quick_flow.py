import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)


class _BoundSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


class _SignalDescriptor:
    def __init__(self, *args, **kwargs):
        self._storage_name = None

    def __set_name__(self, owner, name):
        self._storage_name = f"__signal_{name}"

    def __get__(self, instance, owner):
        if instance is None:
            return self
        signal = instance.__dict__.get(self._storage_name)
        if signal is None:
            signal = _BoundSignal()
            instance.__dict__[self._storage_name] = signal
        return signal


class _QObject:
    def __init__(self, parent=None):
        self._parent = parent


class _QTimer:
    def __init__(self, parent=None):
        self._parent = parent
        self.timeout = _BoundSignal()
        self._active = False
        self._single_shot = False
        self._interval = 0

    def setSingleShot(self, value):
        self._single_shot = bool(value)

    def setInterval(self, interval):
        self._interval = interval

    def start(self, interval=None):
        if interval is not None:
            self._interval = interval
        self._active = True

    def stop(self):
        self._active = False

    def isActive(self):
        return self._active

    def trigger(self):
        if not self._active:
            return
        if self._single_shot:
            self._active = False
        self.timeout.emit()


qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QObject = _QObject
qtcore.QTimer = _QTimer
qtcore.Signal = _SignalDescriptor

pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore

sys.modules.setdefault("PySide6", pyside6)
sys.modules["PySide6.QtCore"] = qtcore


from calibration.calibration_manager import CalibrationManager  # noqa: E402


class _FakeHandler(_QObject):
    def __init__(self):
        super().__init__()
        self.baselines_updated = _BoundSignal()
        self.calibration_progress = _BoundSignal()
        self.started = 0

    def start_baseline_calibration(self):
        self.started += 1

    def import_baselines(self, baselines):
        self.imported = baselines


class _FakeCalibrator:
    def __init__(self, device, lib):
        self._failed = False

    def set_on_calibration_finished(self, callback):
        self._finished = callback

    def set_on_calibration_stage_finished(self, callback):
        self._stage = callback

    def calibrate_quick(self):
        return None

    def has_calibration_failed(self):
        return self._failed

    def import_alpha(self, nfb):
        return None


def _nfb_data():
    return SimpleNamespace(
        timestampMilli=1,
        failReason=0,
        individualFrequency=9.4,
        individualPeakFrequency=9.6,
        individualPeakFrequencyPower=1.2,
        individualPeakFrequencySuppression=0.4,
        individualBandwidth=4.0,
        individualNormalizedPower=0.7,
        lowerFrequency=8.0,
        upperFrequency=12.0,
    )


class QuickCalibrationFlowTests(unittest.TestCase):
    def test_quick_mode_starts_physio_during_nfb_and_prod_after_nfb(self):
        prod = _FakeHandler()
        phys = _FakeHandler()

        with patch("calibration.calibration_manager.Calibrator", _FakeCalibrator):
            manager = CalibrationManager(object(), object(), prod, phys)
            manager.start_quick("SER123")

            self.assertTrue(manager._phy_start_timer.isActive())
            self.assertFalse(manager._prod_start_timer.isActive())

            manager._phy_start_timer.trigger()
            self.assertEqual(phys.started, 1)
            self.assertEqual(prod.started, 0)

            manager._on_nfb_finished(manager._calibrator, _nfb_data())
            self.assertTrue(manager._prod_start_timer.isActive())
            manager._prod_start_timer.trigger()

        self.assertEqual(prod.started, 1)
        self.assertEqual(phys.started, 1)

    def test_quick_mode_finishes_after_productivity_when_physio_finished_early(self):
        prod = _FakeHandler()
        phys = _FakeHandler()
        completed = []

        with patch("calibration.calibration_manager.Calibrator", _FakeCalibrator):
            manager = CalibrationManager(object(), object(), prod, phys)
            manager.calibration_complete.connect(completed.append)
            manager.start_quick("SER456")

            manager._phy_start_timer.trigger()
            phys.baselines_updated.emit(SimpleNamespace(
                timestampMilli=10,
                alpha=1.0,
                beta=2.0,
                alphaGravity=3.0,
                betaGravity=4.0,
                concentration=5.0,
            ))
            self.assertEqual(completed, [])

            manager._on_nfb_finished(manager._calibrator, _nfb_data())
            manager._prod_start_timer.trigger()
            prod.baselines_updated.emit(SimpleNamespace(
                concentration=1.0,
                fatigue=2.0,
                gravity=3.0,
                productivity=4.0,
                relaxation=5.0,
                reverseFatigue=6.0,
                timestampMilli=20,
            ))

        self.assertEqual(completed[-1]["phy_status"], manager.PHY_STATUS_COMPLETE)


if __name__ == "__main__":
    unittest.main()
