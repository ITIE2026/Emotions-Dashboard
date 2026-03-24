import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from classifiers.emotions_handler import EmotionsHandler  # noqa: E402
from classifiers.productivity_handler import ProductivityHandler  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.metric_graph_windows import (  # noqa: E402
    CognitiveStatesWindow,
    TimeSeriesGraphWindow,
    graph_spec,
)


APP = QApplication.instance() or QApplication([])


class _FakeEmotionsSdk:
    def __init__(self, device, lib):
        self._on_states = None
        self._on_error = None

    def set_on_states_update(self, callback):
        self._on_states = callback

    def set_on_error(self, callback):
        self._on_error = callback


class _FakeProductivitySdk:
    def __init__(self, device, lib):
        self._on_metrics = None
        self._on_indexes = None
        self._on_baseline = None
        self._on_progress = None
        self._on_nfb = None

    def set_on_metrics_update(self, callback):
        self._on_metrics = callback

    def set_on_indexes_update(self, callback):
        self._on_indexes = callback

    def set_on_baseline_update(self, callback):
        self._on_baseline = callback

    def set_on_calibration_progress(self, callback):
        self._on_progress = callback

    def set_on_individual_nfb(self, callback):
        self._on_nfb = callback


class MetricGraphWindowTests(unittest.TestCase):
    def test_cognitive_states_window_emits_close_signal(self):
        window = CognitiveStatesWindow()
        closed = []
        try:
            window.window_closed.connect(lambda: closed.append(True))
            window.show()
            APP.processEvents()
            window.close()
            APP.processEvents()
            self.assertEqual(closed, [True])
        finally:
            window.close()

    def test_cognitive_states_window_updates_live_bar_values(self):
        window = CognitiveStatesWindow()
        try:
            window.set_bar_values(
                {
                    "Attention": 88.0,
                    "Relaxation": 43.0,
                    "Cognitive Load": 65.0,
                    "Cognitive Control": 33.0,
                }
            )
            self.assertAlmostEqual(window._canvas._values["Attention"], 88.0)
            self.assertAlmostEqual(window._canvas._values["Cognitive Control"], 33.0)
        finally:
            window.close()

    def test_time_series_graph_window_emits_close_signal(self):
        spec = graph_spec("concentration_index")
        window = TimeSeriesGraphWindow(spec)
        closed = []
        try:
            window.window_closed.connect(lambda: closed.append(True))
            window.show()
            APP.processEvents()
            window.close()
            APP.processEvents()
            self.assertEqual(closed, [True])
        finally:
            window.close()

    def test_time_series_graph_window_shows_span_and_baseline_summary(self):
        spec = graph_spec("concentration_index")
        window = TimeSeriesGraphWindow(spec)
        try:
            window.set_session_start(100.0)
            window.set_time_scale("1 min")
            window.set_history_data(
                {"concentrationScore": [(120.0, 1.35), (150.0, 0.565)]},
                references={"concentrationBaseline": 1.117},
            )

            self.assertEqual(window._span_label.text(), "Span: 60 sec")
            self.assertEqual(window._scale_badge.text(), "1 min")
            self.assertIn("Concentration: 0.565", window._summary_label.text())
            self.assertIn("Concentration Baseline: 1.117", window._summary_label.text())
        finally:
            window.close()

    def test_frequency_peaks_window_formats_latest_summary(self):
        spec = graph_spec("frequency_peaks")
        window = TimeSeriesGraphWindow(spec)
        try:
            window.set_session_start(0.0)
            window.set_history_data(
                {
                    "alpha_peak": [(10.0, 8.6)],
                    "beta_peak": [(10.0, 18.7)],
                    "theta_peak": [(10.0, 5.4)],
                },
                references={},
            )

            self.assertIn("Alpha peak: 8.6 Hz", window._summary_label.text())
            self.assertIn("Beta peak: 18.7 Hz", window._summary_label.text())
            self.assertIn("Theta peak: 5.4 Hz", window._summary_label.text())
        finally:
            window.close()


class _GraphWindowStub:
    def __init__(self):
        self.session_start = None
        self.history = None
        self.references = None

    def set_session_start(self, start):
        self.session_start = float(start)

    def set_history_data(self, history, references=None):
        self.history = {
            key: list(values or [])
            for key, values in (history or {}).items()
        }
        self.references = dict(references or {})


class MainWindowGraphLifecycleTests(unittest.TestCase):
    def _bind_main_window_graph_methods(self, host):
        for name in (
            "is_graph_active",
            "activate_graph",
            "deactivate_graph",
            "reset_graph_history",
            "append_graph_point",
            "_seed_graph_history",
            "_refresh_metric_graph_window",
            "_latest_eeg_quality_value",
        ):
            setattr(host, name, getattr(MainWindow, name).__get__(host, type(host)))
        host._build_graph_history_store = MainWindow._build_graph_history_store

    def test_main_window_graph_history_collects_only_while_open_and_restarts_fresh(self):
        host = type("GraphHost", (), {})()
        host._graph_windows = {"concentration_index": _GraphWindowStub()}
        host._active_graphs = set()
        host._graph_histories = {}
        host._graph_references = {"concentrationBaseline": 1.117}
        host._graph_session_starts = {}
        host._latest_emo = {}
        host._latest_prod = {"concentrationScore": 0.565}
        host._latest_peak_freqs = {}
        host._latest_indexes = {}
        host._latest_physio = {}
        self._bind_main_window_graph_methods(host)

        MainWindow.append_graph_point(host, "concentration_index", "concentrationScore", 0.9, timestamp=10.0)
        self.assertEqual(host._graph_histories, {})

        MainWindow.activate_graph(host, "concentration_index")
        first_session_start = host._graph_session_starts["concentration_index"]
        first_history = list(host._graph_histories["concentration_index"]["concentrationScore"])
        self.assertEqual(len(first_history), 1)
        self.assertAlmostEqual(first_history[0][1], 0.565)
        self.assertEqual(
            host._graph_windows["concentration_index"].history["concentrationScore"],
            first_history,
        )

        MainWindow.append_graph_point(host, "concentration_index", "concentrationScore", 0.72, timestamp=first_session_start + 5.0)
        MainWindow._refresh_metric_graph_window(host, "concentration_index")
        self.assertEqual(
            len(host._graph_windows["concentration_index"].history["concentrationScore"]),
            2,
        )

        MainWindow.deactivate_graph(host, "concentration_index")
        MainWindow.append_graph_point(host, "concentration_index", "concentrationScore", 0.88, timestamp=first_session_start + 12.0)
        self.assertFalse(MainWindow.is_graph_active(host, "concentration_index"))
        self.assertNotIn("concentration_index", host._graph_histories)

        MainWindow.activate_graph(host, "concentration_index")
        second_session_start = host._graph_session_starts["concentration_index"]
        reopened_history = host._graph_windows["concentration_index"].history["concentrationScore"]
        self.assertGreaterEqual(second_session_start, first_session_start)
        self.assertEqual(len(reopened_history), 1)
        self.assertAlmostEqual(reopened_history[0][1], 0.565)
        self.assertNotEqual(reopened_history, first_history + [(first_session_start + 12.0, 0.88)])


class HandlerPayloadTests(unittest.TestCase):
    def test_emotions_handler_emits_direct_and_compatibility_keys(self):
        with patch("classifiers.emotions_handler.Emotions", _FakeEmotionsSdk):
            handler = EmotionsHandler(object(), object())
            payloads = []
            handler.states_updated.connect(lambda data: payloads.append(data))

            state = type(
                "State",
                (),
                {
                    "attention": 88.0,
                    "relaxation": 43.0,
                    "cognitiveLoad": 65.0,
                    "cognitiveControl": 33.0,
                    "selfControl": 56.0,
                    "timestampMilli": 123456,
                },
            )()
            handler._on_states(None, state)

            self.assertEqual(len(payloads), 1)
            payload = payloads[0]
            self.assertEqual(payload["attention"], 88.0)
            self.assertEqual(payload["relaxation"], 43.0)
            self.assertEqual(payload["cognitiveLoad"], 65.0)
            self.assertEqual(payload["cognitiveControl"], 33.0)
            self.assertEqual(payload["focus"], 88.0)
            self.assertEqual(payload["chill"], 43.0)
            self.assertEqual(payload["stress"], 65.0)
            self.assertEqual(payload["anger"], 33.0)

    def test_productivity_indexes_include_baselines_and_stress_alias(self):
        with patch("classifiers.productivity_handler.Productivity", _FakeProductivitySdk):
            handler = ProductivityHandler(object(), object())
            payloads = []
            handler.indexes_updated.connect(lambda data: payloads.append(data))

            idx = type(
                "Indexes",
                (),
                {
                    "relaxation": 2,
                    "stress": 1,
                    "gravityBaseline": 0.65,
                    "productivityBaseline": 0.14,
                    "fatigueBaseline": 6.9,
                    "reverseFatigueBaseline": 0.14,
                    "relaxationBaseline": 4.6,
                    "concentrationBaseline": 0.22,
                    "hasArtifacts": False,
                    "timestampMilli": 123,
                },
            )()
            handler._on_indexes(None, idx)

            self.assertEqual(len(payloads), 1)
            payload = payloads[0]
            self.assertEqual(payload["stress"], 1)
            self.assertEqual(payload["stress_level"], 1)
            self.assertAlmostEqual(payload["gravityBaseline"], 0.65)
            self.assertAlmostEqual(payload["concentrationBaseline"], 0.22)
            self.assertFalse(payload["hasArtifacts"])


if __name__ == "__main__":
    unittest.main()
