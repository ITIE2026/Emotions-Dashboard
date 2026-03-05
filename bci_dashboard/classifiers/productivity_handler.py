"""
ProductivityHandler – wraps the Capsule Productivity classifier.

Signals:
  metrics_updated  – fatigueScore, relaxationScore, concentrationScore, etc.
  indexes_updated  – recommendation / stress level
  baselines_updated – Productivity_Baselines (for saving)
  calibration_progress – 0.0 → 1.0
"""
import sys
from PySide6.QtCore import QObject, Signal

from utils.config import CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Productivity import (       # noqa: E402
    Productivity,
    Productivity_Metrics,
    Productivity_Indexes,
    Productivity_Baselines,
)


class ProductivityHandler(QObject):
    """Create **after** Device, **before** device.start()."""

    metrics_updated = Signal(dict)
    indexes_updated = Signal(dict)
    baselines_updated = Signal(object)     # Productivity_Baselines
    calibration_progress = Signal(float)
    nfb_updated = Signal()

    def __init__(self, device, lib, parent=None):
        super().__init__(parent)
        self._lib = lib
        self._prod = Productivity(device, lib)
        self._prod.set_on_metrics_update(self._on_metrics)
        self._prod.set_on_indexes_update(self._on_indexes)
        self._prod.set_on_baseline_update(self._on_baselines)
        self._prod.set_on_calibration_progress(self._on_progress)
        self._prod.set_on_individual_nfb(self._on_nfb)

    # ── Public ────────────────────────────────────────────────────────
    def start_baseline_calibration(self):
        self._prod.calibrate_baselines()

    def import_baselines(self, baselines: Productivity_Baselines):
        self._prod.import_baselines(baselines)

    def reset_fatigue(self):
        self._prod.reset_accumulated_fatigue()

    # ── Capsule callbacks ─────────────────────────────────────────────
    def _on_metrics(self, prod_obj, m: Productivity_Metrics):
        try:
            self.metrics_updated.emit({
                "fatigueScore": float(m.fatigueScore),
                "reverseFatigueScore": float(m.reverseFatigueScore),
                "gravityScore": float(m.gravityScore),
                "relaxationScore": float(m.relaxationScore),
                "concentrationScore": float(m.concentrationScore),
                "productivityScore": float(m.productivityScore),
                "currentValue": float(m.currentValue),
                "alpha": float(m.alpha),
                "productivityBaseline": float(m.productivityBaseline),
                "accumulatedFatigue": float(m.accumulatedFatigue),
                "fatigueGrowthRate": m.fatigueGrowthRate.value,
                "timestamp": int(m.timestampMilli),
            })
        except Exception:
            pass

    def _on_indexes(self, prod_obj, idx: Productivity_Indexes):
        try:
            self.indexes_updated.emit({
                "relaxation_recommendation": idx.relaxation.value,
                "stress_level": idx.stress.value,
                "hasArtifacts": bool(idx.hasArtifacts),
                "timestamp": int(idx.timestampMilli),
            })
        except Exception:
            pass

    def _on_baselines(self, prod_obj, bl: Productivity_Baselines):
        self.baselines_updated.emit(bl)

    def _on_progress(self, prod_obj, progress: float):
        self.calibration_progress.emit(float(progress))

    def _on_nfb(self, prod_obj):
        self.nfb_updated.emit()
