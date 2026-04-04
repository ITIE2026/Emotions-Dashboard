import os
import sys
import types
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)


def _install_import_stubs():
    if "PySide6" not in sys.modules:
        pyside6 = types.ModuleType("PySide6")
        qtcore = types.ModuleType("PySide6.QtCore")
        qtwidgets = types.ModuleType("PySide6.QtWidgets")

        class _QTimer:
            @staticmethod
            def singleShot(_ms, callback):
                callback()

        class _QMessageBox:
            @staticmethod
            def warning(*args, **kwargs):
                return None

        qtcore.QTimer = _QTimer
        qtwidgets.QMessageBox = _QMessageBox
        pyside6.QtCore = qtcore
        pyside6.QtWidgets = qtwidgets
        sys.modules["PySide6"] = pyside6
        sys.modules["PySide6.QtCore"] = qtcore
        sys.modules["PySide6.QtWidgets"] = qtwidgets

    stub_modules = {
        "calibration.calibration_manager": "CalibrationManager",
        "classifiers.cardio_handler": "CardioHandler",
        "classifiers.emotions_handler": "EmotionsHandler",
        "classifiers.mems_handler": "MemsHandler",
        "classifiers.physio_handler": "PhysioHandler",
        "classifiers.productivity_handler": "ProductivityHandler",
        "device.device_status_monitor": "DeviceStatusMonitor",
    }
    for module_name, class_name in stub_modules.items():
        if module_name in sys.modules:
            continue
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules[module_name] = module


_install_import_stubs()

import gui.screen_router as screen_router  # noqa: E402
from gui.signal_dispatcher import SignalDispatcherMixin  # noqa: E402


class _FakeStack:
    def __init__(self, index):
        self._index = index

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        self._index = index


class _NavBarStub:
    def __init__(self):
        self.last_active_tab = None

    def set_active_tab(self, index):
        self.last_active_tab = index


class _ScreenStub:
    def __init__(self):
        self.emotions = []
        self.productivity = []

    def on_emotions(self, data):
        self.emotions.append(data)

    def on_productivity(self, data):
        self.productivity.append(data)


class _PhaseonRuntimeStub:
    def __init__(self):
        self.productivity = []

    def ingest_productivity(self, data):
        self.productivity.append(data)


class _RecorderStub:
    def __init__(self):
        self.emotions = []
        self.productivity = []

    def record_emotions(self, data):
        self.emotions.append(data)

    def record_productivity_metrics(self, data):
        self.productivity.append(data)


class MediaNavigationTests(unittest.TestCase):
    def test_screen_router_defines_youtube_page_constant(self):
        self.assertEqual(getattr(screen_router, "PAGE_YOUTUBE", None), 7)

    def test_nav_tab_selected_routes_multiplayer_tab_to_multiplayer_page(self):
        dummy = type("Dummy", (), {})()
        dummy._stack = _FakeStack(screen_router.PAGE_CONNECTION)

        screen_router.ScreenRouterMixin._on_nav_tab_selected(dummy, 4)

        self.assertEqual(dummy._stack.currentIndex(), screen_router.PAGE_MULTIPLAYER)

    def test_nav_tab_selected_routes_media_tab_to_youtube_page(self):
        dummy = type("Dummy", (), {})()
        dummy._stack = _FakeStack(screen_router.PAGE_CONNECTION)

        screen_router.ScreenRouterMixin._on_nav_tab_selected(dummy, 6)

        self.assertEqual(dummy._stack.currentIndex(), screen_router.PAGE_YOUTUBE)

    def test_sync_nav_bar_maps_multiplayer_page_to_multiplayer_tab(self):
        dummy = type("Dummy", (), {})()
        dummy._nav_bar = _NavBarStub()

        screen_router.ScreenRouterMixin._sync_nav_bar(dummy, screen_router.PAGE_MULTIPLAYER)

        self.assertEqual(dummy._nav_bar.last_active_tab, 4)

    def test_sync_nav_bar_maps_youtube_page_to_media_tab(self):
        dummy = type("Dummy", (), {})()
        dummy._nav_bar = _NavBarStub()

        screen_router.ScreenRouterMixin._sync_nav_bar(dummy, screen_router.PAGE_YOUTUBE)

        self.assertEqual(dummy._nav_bar.last_active_tab, 6)


class MediaSignalFanoutTests(unittest.TestCase):
    def _make_host(self):
        host = type("Dummy", (), {})()
        host._latest_emo = {}
        host._latest_prod = {}
        host._session_active = False
        host._dash_screen = _ScreenStub()
        host._training_screen = _ScreenStub()
        host._youtube_screen = _ScreenStub()
        host._phaseon_runtime = _PhaseonRuntimeStub()
        host._recorder = _RecorderStub()
        host.is_graph_active = lambda _graph_id: False
        host._refresh_metric_graph_window = lambda _graph_id: None
        host.append_graph_point = lambda *args, **kwargs: None
        return host

    def test_emotions_are_forwarded_to_media_screen(self):
        host = self._make_host()
        payload = {"attention": 88.0}

        SignalDispatcherMixin._on_emotions(host, payload)

        self.assertEqual(host._dash_screen.emotions, [payload])
        self.assertEqual(host._training_screen.emotions, [payload])
        self.assertEqual(host._youtube_screen.emotions, [payload])

    def test_productivity_is_forwarded_to_media_screen(self):
        host = self._make_host()
        payload = {"currentValue": 0.42, "concentrationScore": 0.9}

        SignalDispatcherMixin._on_productivity(host, payload)

        self.assertEqual(host._dash_screen.productivity, [payload])
        self.assertEqual(host._training_screen.productivity, [payload])
        self.assertEqual(host._youtube_screen.productivity, [payload])
        self.assertEqual(host._phaseon_runtime.productivity, [payload])


if __name__ == "__main__":
    unittest.main()
