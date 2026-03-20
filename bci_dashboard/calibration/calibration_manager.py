"""
CalibrationManager – orchestrates the multi-stage calibration workflow.

Stages:
  1. Closed-eyes NFB calibration
  2. Productivity baseline calibration
  3. PhysiologicalStates baseline calibration

Supports importing saved calibration to skip the process.
"""
import sys
import logging
from PySide6.QtCore import QObject, QTimer, Signal

from utils.config import CAPSULE_SDK_DIR
from utils.sdk_scalars import coerce_float

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Calibrator import Calibrator, IndividualNFBData  # noqa: E402

from calibration.calibration_store import (
    has_saved_calibration,
    save_calibration,
    load_calibration,
    nfb_to_dict,
    dict_to_nfb,
    prod_baselines_to_dict,
    dict_to_prod_baselines,
    phy_baselines_to_dict,
    dict_to_phy_baselines,
)


log = logging.getLogger(__name__)


class CalibrationManager(QObject):
    """
    Drives calibration and emits progress / completion signals.

    Usage:
        cm = CalibrationManager(device, lib, prod_handler, physio_handler)
        cm.start()   # or cm.import_saved(serial)
    """

    # stage_num (1-3), description
    stage_changed = Signal(int, str)
    # overall progress 0.0 – 1.0
    progress_updated = Signal(float)
    # all cal data dict (for saving)
    calibration_complete = Signal(dict)
    # failure reason
    calibration_failed = Signal(str)
    # iAPF status payload
    iapf_updated = Signal(dict)

    STAGE_NFB = 1
    STAGE_PROD = 2
    STAGE_PHY = 3
    MODE_DETECT = "detect"
    MODE_QUICK = "quick"
    STAGE_1_END = 0.33
    STAGE_2_END = 0.66
    STAGE_3_END = 1.0

    def __init__(self, device, lib, prod_handler, physio_handler, parent=None):
        super().__init__(parent)
        self._device = device
        self._lib = lib
        self._prod_h = prod_handler
        self._phy_h = physio_handler

        self._calibrator = None
        self._current_stage = 0
        self._nfb_data = None
        self._nfb_payload = None
        self._prod_baselines = None
        self._phy_baselines = None
        self._prod_payload = None
        self._phy_payload = None
        self._serial = None
        self._mode = self.MODE_QUICK
        self._last_progress = 0.0

        # Connect classifier baseline signals
        self._prod_h.baselines_updated.connect(self._on_prod_baselines)
        self._prod_h.calibration_progress.connect(self._on_prod_progress)
        self._phy_h.baselines_updated.connect(self._on_phy_baselines)
        self._phy_h.calibration_progress.connect(self._on_phy_progress)

    # ── Public API ────────────────────────────────────────────────────
    def can_import(self, serial: str) -> bool:
        return has_saved_calibration(serial)

    def import_saved(self, serial: str) -> bool:
        """Import previously saved calibration. Returns True on success."""
        data = load_calibration(serial)
        if data is None:
            return False

        self._serial = serial
        self._calibrator = Calibrator(self._device, self._lib)

        try:
            # Stage 1 – NFB
            if "nfb" in data:
                nfb = dict_to_nfb(data["nfb"])
                self._calibrator.import_alpha(nfb)
                self._nfb_data = nfb

            # Stage 2 – Productivity baselines
            if "prod_baselines" in data:
                bl = dict_to_prod_baselines(data["prod_baselines"])
                self._prod_h.import_baselines(bl)
                self._prod_baselines = bl

            # Stage 3 – PhysiologicalStates baselines
            if "phy_baselines" in data:
                bl = dict_to_phy_baselines(data["phy_baselines"])
                self._phy_h.import_baselines(bl)
                self._phy_baselines = bl

            nfb_dict = data.get("nfb", {})
            self.iapf_updated.emit(
                {
                    "mode": "import",
                    "source": "Imported",
                    "status": "Imported saved calibration",
                    "applied": True,
                    "frequency": float(nfb_dict.get("individualFrequency", 0.0) or 0.0),
                    "peak_frequency": float(nfb_dict.get("individualPeakFrequency", 0.0) or 0.0),
                    "band": [
                        float(nfb_dict.get("lowerFrequency", 0.0) or 0.0),
                        float(nfb_dict.get("upperFrequency", 0.0) or 0.0),
                    ],
                }
            )
            return True
        except Exception as exc:
            msg = str(exc)
            if hasattr(exc, 'message') and isinstance(exc.message, bytes):
                msg = exc.message.decode('utf-8', errors='replace')
            self.calibration_failed.emit(msg)
            return False

    def start(self, serial: str, mode: str = MODE_QUICK):
        """Begin the requested live calibration process."""
        self._serial = serial
        self._mode = mode if mode in {self.MODE_DETECT, self.MODE_QUICK} else self.MODE_QUICK
        self._nfb_data = None
        self._nfb_payload = None
        self._prod_baselines = None
        self._prod_payload = None
        self._phy_baselines = None
        self._phy_payload = None
        self._last_progress = 0.0
        try:
            self._calibrator = Calibrator(self._device, self._lib)
            self._calibrator.set_on_calibration_finished(self._on_nfb_finished)
            self._calibrator.set_on_calibration_stage_finished(self._on_nfb_stage)

            self._current_stage = self.STAGE_NFB
            description = (
                "Close your eyes for 30 seconds to detect your iAPF"
                if self._mode == self.MODE_DETECT
                else "Close your eyes for 30 seconds to calibrate iAPF"
            )
            self.stage_changed.emit(self.STAGE_NFB, description)
            self._emit_progress(0.0)

            # Local 1-Hz timer to animate progress during the 30 s NFB stage
            self._nfb_elapsed = 0
            self._nfb_duration = 30          # seconds
            self._nfb_timer = QTimer(self)
            self._nfb_timer.setInterval(1000)
            self._nfb_timer.timeout.connect(self._nfb_tick)
            self._nfb_timer.start()

            self._calibrator.calibrate_quick()
        except Exception as exc:
            msg = str(exc)
            if hasattr(exc, 'message') and isinstance(exc.message, bytes):
                msg = exc.message.decode('utf-8', errors='replace')
            self.calibration_failed.emit(msg)

    def start_detect(self, serial: str):
        self.start(serial, mode=self.MODE_DETECT)

    def start_quick(self, serial: str):
        self.start(serial, mode=self.MODE_QUICK)

    def _nfb_tick(self):
        """Called every 1 s during the NFB stage to update progress."""
        self._nfb_elapsed += 1
        if self._nfb_elapsed >= self._nfb_duration:
            self._nfb_timer.stop()
            return
        fraction = self._nfb_elapsed / self._nfb_duration
        self._emit_progress(fraction * self.STAGE_1_END)

    # ── NFB callbacks ─────────────────────────────────────────────────
    def _on_nfb_stage(self, calibrator_obj):
        pass  # quick mode has a single stage

    def _on_nfb_finished(self, calibrator_obj, nfb_data: IndividualNFBData):
        try:
            # Stop the local countdown timer
            if hasattr(self, '_nfb_timer') and self._nfb_timer.isActive():
                self._nfb_timer.stop()

            if self._calibrator.has_calibration_failed():
                self.calibration_failed.emit("NFB calibration failed \u2013 too many artifacts")
                return

            self._nfb_data = nfb_data
            nfb_dict = self._serialize_nfb(nfb_data)
            self._nfb_payload = dict(nfb_dict)
            self.iapf_updated.emit(
                {
                    "mode": self._mode,
                    "source": "Detected" if self._mode == self.MODE_DETECT else "Applied",
                    "status": (
                        "iAPF detected"
                        if self._mode == self.MODE_DETECT
                        else "iAPF applied; collecting baselines"
                    ),
                    "applied": self._mode == self.MODE_QUICK,
                    "frequency": coerce_float(nfb_dict.get("individualFrequency"), 0.0) or 0.0,
                    "peak_frequency": coerce_float(nfb_dict.get("individualPeakFrequency"), 0.0) or 0.0,
                    "band": [
                        coerce_float(nfb_dict.get("lowerFrequency"), 0.0) or 0.0,
                        coerce_float(nfb_dict.get("upperFrequency"), 0.0) or 0.0,
                    ],
                }
            )

            if self._mode == self.MODE_DETECT:
                self._emit_progress(1.0)
                self.calibration_complete.emit(
                    {
                        "mode": self.MODE_DETECT,
                        "nfb": nfb_dict,
                        "applied": False,
                    }
                )
                return

            self._emit_progress(self.STAGE_1_END)
            self._current_stage = self.STAGE_PROD
            self.stage_changed.emit(
                self.STAGE_PROD,
                "Calibrating productivity baseline",
            )
            self._prod_h.start_baseline_calibration()
        except Exception as exc:
            self.calibration_failed.emit(self._safe_message(exc))

    # ── Productivity callbacks ────────────────────────────────────────
    def _on_prod_progress(self, progress: float):
        if self._mode != self.MODE_QUICK or self._current_stage != self.STAGE_PROD:
            return
        fraction = max(0.0, min(1.0, float(progress)))
        overall = self.STAGE_1_END + ((self.STAGE_2_END - self.STAGE_1_END) * fraction)
        self._emit_progress(overall)

    def _on_prod_baselines(self, baselines):
        self._prod_baselines = baselines
        self._prod_payload = self._serialize_prod_baselines(baselines)
        if self._mode != self.MODE_QUICK or self._current_stage != self.STAGE_PROD:
            return
        self._emit_progress(self.STAGE_2_END)
        self._current_stage = self.STAGE_PHY
        self.stage_changed.emit(
            self.STAGE_PHY,
            "Calibrating physiological baseline",
        )
        self._phy_h.start_baseline_calibration()

    # ── PhysStates callbacks ──────────────────────────────────────────
    def _on_phy_progress(self, progress: float):
        if self._mode != self.MODE_QUICK or self._current_stage != self.STAGE_PHY:
            return
        fraction = max(0.0, min(1.0, float(progress)))
        overall = self.STAGE_2_END + ((self.STAGE_3_END - self.STAGE_2_END) * fraction)
        self._emit_progress(overall)

    def _on_phy_baselines(self, baselines):
        self._phy_baselines = baselines
        self._phy_payload = self._serialize_phy_baselines(baselines)
        if self._mode != self.MODE_QUICK or self._current_stage != self.STAGE_PHY:
            return
        self._emit_progress(1.0)
        self._finish()

    # ── Finish ────────────────────────────────────────────────────────
    def _finish(self):
        cal_data = {}
        if self._nfb_payload:
            cal_data["nfb"] = dict(self._nfb_payload)
        if self._prod_payload:
            cal_data["prod_baselines"] = dict(self._prod_payload)
        if self._phy_payload:
            cal_data["phy_baselines"] = dict(self._phy_payload)

        if self._serial:
            try:
                save_calibration(self._serial, cal_data)
            except Exception as exc:
                log.warning(
                    "Calibration finished but saving failed for %s: %s",
                    self._serial,
                    self._safe_message(exc),
                )

        cal_data["mode"] = self.MODE_QUICK
        cal_data["applied"] = True
        self.calibration_complete.emit(cal_data)

    def _emit_progress(self, value: float):
        bounded = max(0.0, min(1.0, float(value)))
        if bounded < self._last_progress:
            bounded = self._last_progress
        self._last_progress = bounded
        self.progress_updated.emit(round(bounded, 4))

    def _serialize_nfb(self, nfb_data):
        try:
            return nfb_to_dict(nfb_data)
        except Exception as exc:
            log.warning("Falling back to safe NFB serialization: %s", self._safe_message(exc))
            return {
                "individualFrequency": coerce_float(getattr(nfb_data, "individualFrequency", None), 0.0) or 0.0,
                "individualPeakFrequency": coerce_float(getattr(nfb_data, "individualPeakFrequency", None), 0.0) or 0.0,
                "lowerFrequency": coerce_float(getattr(nfb_data, "lowerFrequency", None), 0.0) or 0.0,
                "upperFrequency": coerce_float(getattr(nfb_data, "upperFrequency", None), 0.0) or 0.0,
            }

    def _serialize_prod_baselines(self, baselines):
        try:
            return prod_baselines_to_dict(baselines)
        except Exception as exc:
            log.warning("Skipping productivity baseline serialization: %s", self._safe_message(exc))
            return {}

    def _serialize_phy_baselines(self, baselines):
        try:
            return phy_baselines_to_dict(baselines)
        except Exception as exc:
            log.warning("Skipping physiological baseline serialization: %s", self._safe_message(exc))
            return {}

    @staticmethod
    def _safe_message(exc) -> str:
        if hasattr(exc, "message") and isinstance(exc.message, bytes):
            return exc.message.decode("utf-8", errors="replace")
        return str(exc)
