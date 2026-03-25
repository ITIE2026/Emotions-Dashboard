import os
import sys
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from gui.widgets.eeg_graph_panel import ToggleableEegGraphPanel  # noqa: E402
from gui.widgets.spectrum_chart import SpectrumChart  # noqa: E402


APP = QApplication.instance() or QApplication([])


class SpectrumChartTests(unittest.TestCase):
    @staticmethod
    def _curve_arrays(item):
        curve = item["curve"] if isinstance(item, dict) else item
        x_data, y_data = curve.getData()
        x_arr = np.asarray([] if x_data is None else x_data, dtype=float)
        y_arr = np.asarray([] if y_data is None else y_data, dtype=float)
        return x_arr, y_arr

    def test_update_psd_splits_curve_into_colored_band_segments(self):
        chart = SpectrumChart()
        try:
            freqs = np.asarray([1.5, 3.2, 5.1, 7.4, 9.2, 11.6, 13.5, 14.7, 18.0, 26.0, 32.0], dtype=float)
            powers = np.asarray([2.0, 6.0, 18.0, 24.0, 35.0, 22.0, 10.0, 12.0, 8.0, 6.0, 1.5], dtype=float)

            chart.update_psd(freqs, powers)

            expected_ranges = {
                "delta": (1.0, 4.0),
                "theta": (4.0, 8.0),
                "alpha": (8.0, 12.0),
                "smr": (12.0, 15.0),
                "beta": (15.0, 30.0),
            }
            for band, (lo, hi) in expected_ranges.items():
                x_arr, y_arr = self._curve_arrays(chart._band_items[band])
                self.assertGreater(len(x_arr), 0, band)
                self.assertTrue(np.all(x_arr >= lo - 1e-9), band)
                self.assertTrue(np.all(x_arr <= hi + 1e-9), band)
                self.assertGreater(np.max(y_arr), 0.0, band)
        finally:
            chart.close()


class ToggleableEegGraphPanelTests(unittest.TestCase):
    @staticmethod
    def _curve_arrays(item):
        curve = item["curve"] if isinstance(item, dict) else item
        x_data, y_data = curve.getData()
        x_arr = np.asarray([] if x_data is None else x_data, dtype=float)
        y_arr = np.asarray([] if y_data is None else y_data, dtype=float)
        return x_arr, y_arr

    def test_panel_starts_in_spectrum_mode_and_click_toggles_views(self):
        panel = ToggleableEegGraphPanel()
        try:
            panel.resize(800, 320)
            panel.show()
            APP.processEvents()

            self.assertEqual(panel.view_mode(), panel.VIEW_SPECTRUM)

            QTest.mouseClick(panel._click_surface, Qt.LeftButton)
            self.assertEqual(panel.view_mode(), panel.VIEW_HEMISPHERE_RADAR)

            QTest.mouseClick(panel._click_surface, Qt.LeftButton)
            self.assertEqual(panel.view_mode(), panel.VIEW_SPECTRUM)
        finally:
            panel.close()

    def test_panel_updates_hemisphere_band_powers(self):
        panel = ToggleableEegGraphPanel()
        try:
            left = {"delta": 1.0, "theta": 2.0, "alpha": 3.0, "smr": 4.0, "beta": 5.0}
            right = {"delta": 5.0, "theta": 4.0, "alpha": 3.0, "smr": 2.0, "beta": 1.0}

            panel.update_hemisphere_band_powers(left, right)

            stored_left, stored_right = panel.hemisphere_band_powers()
            self.assertEqual(stored_left, left)
            self.assertEqual(stored_right, right)
        finally:
            panel.close()

    def test_update_psd_keeps_one_continuous_master_projection(self):
        chart = SpectrumChart()
        try:
            freqs = np.asarray([1.5, 3.2, 5.1, 7.4, 9.2, 11.6, 13.5, 14.7, 18.0, 26.0, 32.0, 36.5], dtype=float)
            powers = np.asarray([2.0, 6.0, 18.0, 24.0, 35.0, 22.0, 10.0, 12.0, 8.0, 6.0, 1.5, 0.3], dtype=float)

            chart.update_psd(freqs, powers)

            x_arr, y_arr = self._curve_arrays(chart._main_curve)
            np.testing.assert_allclose(x_arr, freqs[freqs <= 35.0])
            np.testing.assert_allclose(y_arr, powers[freqs <= 35.0])

            zx_arr, zy_arr = self._curve_arrays(chart._main_zero_curve)
            np.testing.assert_allclose(zx_arr, x_arr)
            np.testing.assert_allclose(zy_arr, np.zeros_like(y_arr))
        finally:
            chart.close()

    def test_update_psd_clears_segments_for_empty_input(self):
        chart = SpectrumChart()
        try:
            freqs = np.asarray([2.0, 4.5, 8.0, 12.0, 16.0], dtype=float)
            powers = np.asarray([1.0, 2.0, 3.0, 2.0, 1.0], dtype=float)
            chart.update_psd(freqs, powers)

            chart.update_psd([], [])

            x_arr, y_arr = self._curve_arrays(chart._main_curve)
            self.assertEqual(len(x_arr), 0)
            self.assertEqual(len(y_arr), 0)
            for band in chart._band_items.values():
                x_arr, y_arr = self._curve_arrays(band)
                self.assertEqual(len(x_arr), 0)
                self.assertEqual(len(y_arr), 0)
        finally:
            chart.close()

    def test_update_psd_autoscales_with_segmented_rendering(self):
        chart = SpectrumChart()
        try:
            freqs = np.linspace(1.0, 30.0, 80)
            powers = np.sin(np.linspace(0.0, 8.0, 80)) ** 2 * 40.0
            chart.update_psd(freqs, powers)

            y_range = chart._plot.getViewBox().viewRange()[1]
            self.assertGreater(y_range[1], float(np.max(powers)))
            self.assertLessEqual(y_range[0], 0.0)
            self.assertGreater(y_range[1] - y_range[0], float(np.max(powers)))
        finally:
            chart.close()


if __name__ == "__main__":
    unittest.main()
