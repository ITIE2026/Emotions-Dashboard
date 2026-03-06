"""
ProductivityHandler – wraps the Capsule Productivity classifier.

Signals:
  metrics_updated  – fatigueScore, relaxationScore, concentrationScore, etc.
  indexes_updated  – recommendation / stress level
  baselines_updated – Productivity_Baselines (for saving)
  calibration_progress – 0.0 → 1.0
"""
import sys
import logging
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

log = logging.getLogger(__name__)

# EMA smoothing factor (0 = no smoothing, 1 = no memory)
_ALPHA = 0.25


def _ema(prev: float, raw: float, alpha: float = _ALPHA) -> float:
    """Exponential moving average."""
    if prev is None:
        return raw
    return prev + alpha * (raw - prev)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


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

        # EMA state (None = first sample)
        self._ema_cognitive = None
        self._ema_relax = None
        self._ema_conc = None
        self._ema_fatigue = None

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
            # Extract growth rate safely (it's a ctypes enum)
            try:
                gr = m.fatigueGrowthRate
                growth = int(gr.value) if hasattr(gr, "value") else int(gr)
            except Exception:
                growth = 0

            # ── Scaling ───────────────────────────────────────────────
            # currentValue is the NORMALISED productivity score [0,1] → *100
            cognitive_raw = _clamp(float(m.currentValue) * 100.0)

            # relaxation, concentration & fatigue are already in 0-100 range
            # (reference mainn.py stores them as-is with no scaling)
            relax_raw = _clamp(float(m.relaxationScore))
            conc_raw  = _clamp(float(m.concentrationScore))
            fatigue_raw = _clamp(float(m.fatigueScore))

            # ── EMA smoothing ─────────────────────────────────────────
            self._ema_cognitive = _ema(self._ema_cognitive, cognitive_raw)
            self._ema_relax     = _ema(self._ema_relax,     relax_raw)
            self._ema_conc      = _ema(self._ema_conc,      conc_raw)
            self._ema_fatigue   = _ema(self._ema_fatigue,   fatigue_raw)

            data = {
                "productivityScore":   round(self._ema_cognitive, 1),
                "relaxationScore":     round(self._ema_relax, 1),
                "concentrationScore":  round(self._ema_conc, 1),
                "fatigueScore":        round(self._ema_fatigue, 1),
                "reverseFatigueScore": _clamp(float(m.reverseFatigueScore)),
                "gravityScore":        float(m.gravityScore),
                "currentValue":        float(m.currentValue),
                "alpha":               float(m.alpha),
                "productivityBaseline":float(m.productivityBaseline),
                "accumulatedFatigue":  float(m.accumulatedFatigue),
                "fatigueGrowthRate":   growth,
                "timestamp":           int(m.timestampMilli),
            }
            log.debug(
                "Productivity → cognitive=%.1f%% relax=%.1f%% conc=%.1f%% fatigue=%.1f%%",
                data["productivityScore"], data["relaxationScore"],
                data["concentrationScore"], data["fatigueScore"],
            )
            self.metrics_updated.emit(data)
        except Exception as e:
            log.error("ProductivityHandler._on_metrics error: %s", e)

    def _on_indexes(self, prod_obj, idx: Productivity_Indexes):
        try:
            try:
                rel_raw = idx.relaxation
                rel = int(rel_raw.value) if hasattr(rel_raw, "value") else int(rel_raw)
            except Exception:
                rel = 0
            try:
                stress_raw = idx.stress
                stress = int(stress_raw.value) if hasattr(stress_raw, "value") else int(stress_raw)
            except Exception:
                stress = 0

            self.indexes_updated.emit({
                "relaxation_recommendation": rel,
                "stress_level": stress,
                "hasArtifacts": bool(idx.hasArtifacts),
                "timestamp": int(idx.timestampMilli),
            })
        except Exception as e:
            log.error("ProductivityHandler._on_indexes error: %s", e)

    def _on_baselines(self, prod_obj, bl: Productivity_Baselines):
        self.baselines_updated.emit(bl)

    def _on_progress(self, prod_obj, progress: float):
        self.calibration_progress.emit(float(progress))

    def _on_nfb(self, prod_obj):
        self.nfb_updated.emit()

