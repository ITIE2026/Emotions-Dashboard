"""
PhysioHandler – wraps the Capsule PhysiologicalStates classifier.

Signals: states_updated, baselines_updated, calibration_progress
"""
import sys
import logging
from PySide6.QtCore import QObject, Signal

from utils.config import CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from PhysiologicalStates import (  # noqa: E402
    PhysiologicalStates,
    PhysiologicalStates_Value,
    PhysiologicalStates_Baselines,
)


log = logging.getLogger(__name__)


class PhysioHandler(QObject):
    """Create **after** Device, **before** device.start()."""

    states_updated = Signal(dict)
    baselines_updated = Signal(object)     # PhysiologicalStates_Baselines
    calibration_progress = Signal(float)

    def __init__(self, device, lib, parent=None):
        super().__init__(parent)
        self._phy = PhysiologicalStates(device, lib)
        self._progress_logged = False
        self._state_packets_seen = 0
        self._phy.set_on_states(self._on_states)
        self._phy.set_on_calibrated(self._on_calibrated)
        self._phy.set_on_calibration_progress(self._on_progress)

    # ── Public ────────────────────────────────────────────────────────
    def start_baseline_calibration(self):
        self._progress_logged = False
        self._state_packets_seen = 0
        self._phy.calibrate_baselines()

    def import_baselines(self, baselines: PhysiologicalStates_Baselines):
        self._phy.import_baselines(baselines)

    # ── Capsule callbacks ─────────────────────────────────────────────
    def _on_states(self, phy_obj, val: PhysiologicalStates_Value):
        try:
            self._state_packets_seen += 1
            if self._state_packets_seen == 1:
                log.info("PhysioHandler received the first physiological state packet")
            self.states_updated.emit({
                "none": float(val.none),
                "relaxation": float(val.relaxation),
                "fatigue": float(val.fatigue),
                "concentration": float(val.concentration),
                "involvement": float(val.involvement),
                "stress": float(val.stress),
                "nfbArtifacts": bool(val.nfbArtifacts),
                "cardioArtifacts": bool(val.cardioArtifacts),
                "timestamp": int(val.timestampMilli),
            })
        except Exception:
            pass

    def _on_calibrated(self, phy_obj, baselines: PhysiologicalStates_Baselines):
        try:
            log.info(
                "PhysioHandler received physiological calibration baselines "
                "(state_packets=%d)",
                self._state_packets_seen,
            )
            self.baselines_updated.emit(baselines)
        except Exception:
            pass

    def _on_progress(self, phy_obj, progress: float):
        try:
            progress_value = float(progress)
            if not self._progress_logged:
                log.info("PhysioHandler received physiological calibration progress: %.3f", progress_value)
                self._progress_logged = True
            elif progress_value >= 1.0:
                log.info("PhysioHandler physiological calibration progress reached %.3f", progress_value)
            self.calibration_progress.emit(progress_value)
        except Exception:
            pass
