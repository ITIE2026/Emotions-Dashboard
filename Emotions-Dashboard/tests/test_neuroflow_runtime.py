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

from gui.neuroflow_runtime import (  # noqa: E402
    CI_FOCUS_DROPOUT,
    CI_FOCUS_THRESHOLD,
    FOCUS_DWELL_SECONDS,
    LaunchResult,
    NeuroflowStateMachine,
    launch_app,
    threaded_launch,
)
from gui.neuroflow_training_page import NeuroflowTrainingPage  # noqa: E402


APP = QApplication.instance() or QApplication([])


class NeuroflowRuntimeTests(unittest.TestCase):
    def test_resistance_requires_two_channels_below_threshold(self):
        runtime = NeuroflowStateMachine()
        runtime.set_connected(True)

        self.assertFalse(runtime.set_resistances({"T3": 700_000.0, "T4": 650_000.0}))
        self.assertTrue(runtime.set_resistances({"T3": 120_000.0, "T4": 300_000.0}))

    def test_focus_trigger_requires_calibration(self):
        runtime = NeuroflowStateMachine()
        runtime.set_connected(True)
        runtime.set_resistances({"T3": 90_000.0, "T4": 120_000.0})

        triggered = runtime.ingest_band_powers(
            {"delta": 0.05, "theta": 0.11, "alpha": 0.12, "smr": 0.05, "beta": 0.21},
            now=10.0,
        )
        self.assertFalse(triggered)
        self.assertFalse(runtime.calibrated)

    def test_focus_trigger_uses_threshold_dwell_and_cooldown(self):
        runtime = NeuroflowStateMachine()
        runtime.set_connected(True)
        runtime.set_resistances({"T3": 90_000.0, "T4": 120_000.0})
        runtime.finish_calibration(True, "ready")

        high_focus = {
            "delta": 0.05,
            "theta": 0.10,
            "alpha": 0.10,
            "smr": 0.04,
            "beta": max(CI_FOCUS_THRESHOLD * 0.20, 0.20),
        }
        now = 20.0
        triggered = False
        for step in range(20):
            triggered = runtime.ingest_band_powers(high_focus, now=now + (step * 0.2))
            if triggered:
                break
        self.assertTrue(triggered)

        snapshot = runtime.snapshot(now=now + (step * 0.2))
        self.assertGreater(snapshot.cooldown_remaining, 0.0)

        immediate_retry = runtime.ingest_band_powers(high_focus, now=now + (step * 0.2) + 0.5)
        self.assertFalse(immediate_retry)

    def test_focus_drops_when_smoothed_ci_falls_below_dropout(self):
        runtime = NeuroflowStateMachine()
        runtime.set_connected(True)
        runtime.set_resistances({"T3": 90_000.0, "T4": 120_000.0})
        runtime.finish_calibration(True, "ready")

        high_focus = {"delta": 0.05, "theta": 0.10, "alpha": 0.10, "smr": 0.04, "beta": 0.25}
        for step in range(4):
            runtime.ingest_band_powers(high_focus, now=30.0 + (step * 0.2))

        low_focus = {
            "delta": 0.05,
            "theta": 0.30,
            "alpha": 0.30,
            "smr": 0.04,
            "beta": CI_FOCUS_DROPOUT * 0.20,
        }
        for step in range(20):
            runtime.ingest_band_powers(low_focus, now=31.0 + (step * 0.2))

        snapshot = runtime.snapshot(now=35.0)
        self.assertFalse(snapshot.in_focus)
        self.assertLess(snapshot.ci_smooth, CI_FOCUS_THRESHOLD)

    def test_launch_app_returns_failure_for_missing_target(self):
        result = launch_app({"name": "Missing App", "cmd": r"C:\missing.exe", "fallback": []})

        self.assertFalse(result.success)
        self.assertIn("not found", result.message.lower())

    def test_launch_app_uses_windows_start_fallback_for_shell_targets(self):
        with patch("gui.neuroflow_runtime.os.name", "nt"), patch("gui.neuroflow_runtime.subprocess.Popen") as popen:
            result = launch_app({"name": "System Settings", "cmd": None, "fallback": ["start", "ms-settings:"], "shell": True})

        self.assertTrue(result.success)
        popen.assert_called_once_with(["cmd", "/c", "start", "", "ms-settings:"], shell=False)

    def test_threaded_launch_reports_result_to_callback(self):
        results = []
        with patch("gui.neuroflow_runtime.launch_app", return_value=LaunchResult(True, "Google Chrome", "ok")):
            thread = threaded_launch({"name": "Google Chrome"}, callback=results.append)
            thread.join(timeout=2.0)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].message, "ok")


class NeuroflowTrainingPageTests(unittest.TestCase):
    def test_update_signal_snapshot_updates_all_supported_bands(self):
        page = NeuroflowTrainingPage()
        try:
            page.set_connection_state(True, "TEST-001")
            page.on_resistance({"T3": 90_000.0, "T4": 120_000.0})
            page.update_signal_snapshot(
                {"delta": 0.08, "theta": 0.21, "alpha": 0.18, "smr": 0.16, "beta": 0.29},
                {"alpha_peak": 10.4, "beta_peak": 18.6, "theta_peak": 6.1},
            )
            APP.processEvents()

            self.assertAlmostEqual(page._smr_gauge._value, 0.16)
            self.assertIn("SMR 0.160", page._band_summary_lbl.text())
            self.assertNotIn("Gamma", page._band_summary_lbl.text())
            self.assertIn("quick calibration completes", page._focus_hint_lbl.text().lower())
            self.assertIn("CI raw", page._ci_meta_lbl.text())
        finally:
            page.close()

    def test_manual_launch_surfaces_failure_message(self):
        page = NeuroflowTrainingPage()
        try:
            page.set_connection_state(True, "TEST-002")
            page.on_resistance({"T3": 90_000.0, "T4": 120_000.0})
            page.on_calibration_finished(True, "Calibration ready")

            def fake_threaded_launch(app, callback=None):
                if callback is not None:
                    callback(LaunchResult(False, app["name"], "Fallback launch failed: missing executable"))
                return type("DummyThread", (), {"join": lambda self, timeout=None: None})()

            with patch("gui.neuroflow_training_page.threaded_launch", side_effect=fake_threaded_launch):
                page._launch_current_app()
                APP.processEvents()

            self.assertIn("Last launch failed", page._launch_hint_lbl.text())
            self.assertIn("missing executable", page._launch_hint_lbl.text())
            self.assertIn("Launch failed", page._log.toPlainText())
        finally:
            page.close()

    def test_automatic_trigger_uses_same_launcher_path(self):
        page = NeuroflowTrainingPage()
        calls = []
        try:
            page.set_connection_state(True, "TEST-003")
            page.on_resistance({"T3": 90_000.0, "T4": 120_000.0})
            page.on_calibration_finished(True, "Calibration ready")

            def fake_threaded_launch(app, callback=None):
                calls.append(app["name"])
                if callback is not None:
                    callback(LaunchResult(True, app["name"], "launch ok"))
                return type("DummyThread", (), {"join": lambda self, timeout=None: None})()

            with patch.object(page._runtime, "ingest_band_powers", return_value=True), patch(
                "gui.neuroflow_training_page.threaded_launch",
                side_effect=fake_threaded_launch,
            ):
                page.update_signal_snapshot(
                    {"delta": 0.05, "theta": 0.10, "alpha": 0.10, "smr": 0.04, "beta": 0.26},
                    {"alpha_peak": 10.2, "beta_peak": 19.4, "theta_peak": 6.0},
                )
                APP.processEvents()

            self.assertEqual(calls, [page._runtime.current_app()["name"]])
            self.assertIn("Last launch ok", page._launch_hint_lbl.text())
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
