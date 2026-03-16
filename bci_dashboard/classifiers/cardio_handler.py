"""
CardioHandler – wraps the Capsule Cardio classifier.

Emits cardio_updated signal with heartRate, stressIndex, etc.
"""
import sys
from PySide6.QtCore import QObject, Signal

from utils.config import CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Cardio import Cardio, Cardio_Data  # noqa: E402


class CardioHandler(QObject):
    """Create **after** Device, **before** device.start()."""

    cardio_updated = Signal(dict)
    ppg_updated = Signal(object)
    calibrated = Signal()

    def __init__(self, device, lib, parent=None):
        super().__init__(parent)
        self._cardio = Cardio(device, lib)
        self._is_calibrated = False
        self._cardio.set_on_indexes_update(self._on_data)
        self._cardio.set_on_ppg(self._on_ppg)
        self._cardio.set_on_calibrated(self._on_calibrated)

    # ── Capsule callbacks ─────────────────────────────────────────────
    def _on_data(self, cardio_obj, data: Cardio_Data):
        try:
            self.cardio_updated.emit({
                "heartRate": float(data.heartRate),
                "stressIndex": float(data.stressIndex),
                "kaplanIndex": float(data.kaplanIndex),
                "hasArtifacts": bool(data.hasArtifacts),
                "skinContact": bool(data.skinContact),
                "motionArtifacts": bool(data.motionArtifacts),
                "metricsAvailable": bool(data.metricsAvailable),
                "timestamp": int(data.timestampMilli),
                "isCalibrated": bool(self._is_calibrated),
            })
        except Exception:
            pass

    def _on_ppg(self, cardio_obj, ppg_timed_data):
        try:
            self.ppg_updated.emit(ppg_timed_data)
        except Exception:
            pass

    def _on_calibrated(self, cardio_obj):
        self._is_calibrated = True
        self.calibrated.emit()
