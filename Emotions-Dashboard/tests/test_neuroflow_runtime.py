import time
import unittest

from bci_dashboard.gui.neuroflow_runtime import (
    CI_FOCUS_DROPOUT,
    CI_FOCUS_THRESHOLD,
    FOCUS_DWELL_SECONDS,
    NeuroflowStateMachine,
)


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


if __name__ == "__main__":
    unittest.main()
