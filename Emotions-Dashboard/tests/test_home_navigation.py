import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BCI_ROOT = REPO_ROOT / "bci_dashboard"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BCI_ROOT) not in sys.path:
    sys.path.insert(0, str(BCI_ROOT))

from bci_dashboard.gui.main_window import (
    MainWindow,
    PAGE_CALIBRATION,
    PAGE_DASHBOARD,
    PAGE_MEMS,
    PAGE_TRAINING,
)
from bci_dashboard.gui.training_screen import TrainingScreen


class _FakeStack:
    def __init__(self, index):
        self._index = index

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        self._index = index


class _TrainingStub:
    def __init__(self):
        self.calls = []

    def stop_active_flow(self):
        self.calls.append("stop_active_flow")


class _ControllerStub:
    def __init__(self, calls):
        self._calls = calls

    def reset_run(self):
        self._calls.append("reset_run")


class HomeNavigationTests(unittest.TestCase):
    def test_go_home_from_training_stops_training_and_shows_dashboard(self):
        training = _TrainingStub()
        dummy = type("Dummy", (), {})()
        dummy._stack = _FakeStack(PAGE_TRAINING)
        dummy._training_screen = training
        dummy._cancel_calibration = lambda: None
        dummy._calibration_return_page = None

        MainWindow._go_home(dummy)

        self.assertEqual(training.calls, ["stop_active_flow"])
        self.assertEqual(dummy._stack.currentIndex(), PAGE_DASHBOARD)

    def test_go_home_from_calibration_routes_cancel_back_to_dashboard(self):
        calls = []
        dummy = type("Dummy", (), {})()
        dummy._stack = _FakeStack(PAGE_CALIBRATION)
        dummy._training_screen = _TrainingStub()
        dummy._calibration_return_page = None

        def _cancel():
            calls.append("cancel")

        dummy._cancel_calibration = _cancel

        MainWindow._go_home(dummy)

        self.assertEqual(calls, ["cancel"])
        self.assertEqual(dummy._calibration_return_page, PAGE_DASHBOARD)

    def test_go_home_from_other_pages_switches_dashboard_only(self):
        dummy = type("Dummy", (), {})()
        dummy._stack = _FakeStack(PAGE_MEMS)
        dummy._training_screen = _TrainingStub()
        dummy._cancel_calibration = lambda: None
        dummy._calibration_return_page = None

        MainWindow._go_home(dummy)

        self.assertEqual(dummy._stack.currentIndex(), PAGE_DASHBOARD)


class TrainingScreenExitTests(unittest.TestCase):
    def test_stop_active_flow_stops_runtime_resets_run_and_returns_catalog(self):
        calls = []
        dummy = type("Dummy", (), {})()
        dummy._stop_runtime_loops = lambda: calls.append("stop_runtime_loops")
        dummy._controller = _ControllerStub(calls)
        dummy._show_catalog = lambda: calls.append("show_catalog")

        TrainingScreen.stop_active_flow(dummy)

        self.assertEqual(
            calls,
            ["stop_runtime_loops", "reset_run", "show_catalog"],
        )


if __name__ == "__main__":
    unittest.main()
