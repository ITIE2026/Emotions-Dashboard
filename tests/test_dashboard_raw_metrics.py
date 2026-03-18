import os
import sys
import unittest

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui.raw_metrics import aggregate_band_history, derive_ppg_metrics  # noqa: E402


class DashboardRawMetricsTests(unittest.TestCase):
    def test_aggregate_band_history_uses_requested_window(self):
        history = [
            (100.0, {"delta": 1.0, "theta": 2.0, "alpha": 3.0, "smr": 4.0, "beta": 5.0}),
            (130.0, {"delta": 2.0, "theta": 4.0, "alpha": 6.0, "smr": 8.0, "beta": 10.0}),
            (170.0, {"delta": 3.0, "theta": 6.0, "alpha": 9.0, "smr": 12.0, "beta": 15.0}),
        ]
        aggregated = aggregate_band_history(history, 60.0, now=180.0)
        self.assertAlmostEqual(aggregated["delta"], 2.5)
        self.assertAlmostEqual(aggregated["beta"], 12.5)

    def test_aggregate_band_history_returns_none_when_window_is_empty(self):
        history = [
            (10.0, {"delta": 1.0, "theta": 2.0, "alpha": 3.0, "smr": 4.0, "beta": 5.0}),
        ]
        aggregated = aggregate_band_history(history, 10.0, now=40.0)
        self.assertIsNone(aggregated)

    def test_derive_ppg_metrics_returns_rr_and_quality(self):
        timestamps = np.arange(0.0, 12.0, 0.05)
        samples = 1.0 + (0.02 * np.sin(2.0 * np.pi * timestamps * 0.4))
        for beat in range(1, 11):
            samples += 0.75 * np.exp(-((timestamps - beat) / 0.08) ** 2)

        metrics = derive_ppg_metrics(samples, timestamps, {})

        self.assertIsNotNone(metrics["perfusion"])
        self.assertIsNotNone(metrics["signal_quality_avg"])
        self.assertIsNotNone(metrics["rr_mean"])
        self.assertIsNotNone(metrics["sdnn"])
        self.assertIsNotNone(metrics["cv"])
        self.assertGreater(metrics["signal_quality_avg"], 0.1)
        self.assertAlmostEqual(metrics["rr_mean"], 1.0, delta=0.2)
        self.assertLess(metrics["sdnn"], 0.2)


if __name__ == "__main__":
    unittest.main()
