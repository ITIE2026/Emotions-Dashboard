"""Background PSD computation worker using QThread."""
from __future__ import annotations

import logging
import time

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from utils.helpers import (
    compute_band_powers,
    compute_hemisphere_band_powers,
    compute_peak_frequencies,
)

log = logging.getLogger(__name__)


class _PsdComputer(QObject):
    result_ready = Signal(dict)

    @Slot(object, object)
    def compute(self, freqs: np.ndarray, channel_powers: np.ndarray):
        try:
            avg_power = np.mean(channel_powers, axis=0)
            band_powers = compute_band_powers(freqs, avg_power)
            left_bp, right_bp = compute_hemisphere_band_powers(freqs, channel_powers)
            peak_freqs = compute_peak_frequencies(freqs, avg_power)
            self.result_ready.emit({
                "freqs": freqs.tolist(),
                "avg_power": avg_power.tolist(),
                "band_powers": dict(band_powers),
                "left_band_powers": dict(left_bp),
                "right_band_powers": dict(right_bp),
                "peak_frequencies": dict(peak_freqs),
                "received_at": time.monotonic(),
            })
        except Exception:
            log.debug("PSD computation failed", exc_info=True)


class PsdWorker(QObject):
    """Offloads heavy PSD NumPy computation to a dedicated QThread."""

    _request = Signal(object, object)
    result_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self._thread.setObjectName("psd-worker")
        self._computer = _PsdComputer()
        self._computer.moveToThread(self._thread)
        self._request.connect(self._computer.compute)
        self._computer.result_ready.connect(self.result_ready)
        self._thread.start()

    def submit(self, freqs: np.ndarray, channel_powers: np.ndarray):
        """Queue a PSD computation. Call from main thread only."""
        self._request.emit(freqs, channel_powers)

    def shutdown(self):
        self._thread.quit()
        self._thread.wait(2000)
