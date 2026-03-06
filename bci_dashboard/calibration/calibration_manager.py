"""
CalibrationManager – orchestrates the multi-stage calibration workflow.

Stages:
  1. Closed-eyes NFB calibration  (30 s via calibrator.calibrate_quick)
  2. Productivity baseline calibration
  3. PhysiologicalStates baseline calibration

Supports importing saved calibration to skip the process.
"""
import sys
from PySide6.QtCore import QObject, QTimer, Signal

from utils.config import CAPSULE_SDK_DIR

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

    STAGE_NFB = 1
    STAGE_PROD = 2
    STAGE_PHY = 3

    def __init__(self, device, lib, prod_handler, physio_handler, parent=None):
        super().__init__(parent)
        self._device = device
        self._lib = lib
        self._prod_h = prod_handler
        self._phy_h = physio_handler

        self._calibrator = None
        self._current_stage = 0
        self._nfb_data = None
        self._prod_baselines = None
        self._phy_baselines = None
        self._serial = None

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

            self.calibration_complete.emit(data)
            return True
        except Exception as exc:
            msg = str(exc)
            if hasattr(exc, 'message') and isinstance(exc.message, bytes):
                msg = exc.message.decode('utf-8', errors='replace')
            self.calibration_failed.emit(msg)
            return False

    def start(self, serial: str):
        """Begin the 3-stage live calibration process."""
        self._serial = serial
        try:
            self._calibrator = Calibrator(self._device, self._lib)
            self._calibrator.set_on_calibration_finished(self._on_nfb_finished)
            self._calibrator.set_on_calibration_stage_finished(self._on_nfb_stage)

            self._current_stage = self.STAGE_NFB
            self.stage_changed.emit(self.STAGE_NFB, "Close your eyes for 30 seconds")
            self.progress_updated.emit(0.0)

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

    def _nfb_tick(self):
        """Called every 1 s during the NFB stage to update progress."""
        self._nfb_elapsed += 1
        if self._nfb_elapsed >= self._nfb_duration:
            self._nfb_timer.stop()
            return
        # NFB stage spans 0.0 → 0.33 of overall progress
        fraction = self._nfb_elapsed / self._nfb_duration
        self.progress_updated.emit(fraction * 0.33)

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
            self.progress_updated.emit(0.33)

            # Flags for parallel baseline completion
            self._prod_baseline_done = False
            self._phy_baseline_done = False

            # Transition → stage 2+3: run BOTH baselines in parallel
            self._current_stage = self.STAGE_PROD
            self.stage_changed.emit(
                self.STAGE_PROD,
                "Baseline calibration (productivity & physiological)",
            )
            self._prod_h.start_baseline_calibration()
            self._phy_h.start_baseline_calibration()
        except Exception as exc:
            self.calibration_failed.emit(str(exc))

    # ── Productivity callbacks ────────────────────────────────────────
    def _on_prod_progress(self, progress: float):
        # Prod progress contributes to 0.33 → 0.66
        overall = 0.33 + 0.33 * progress
        self.progress_updated.emit(min(overall, 0.99))

    def _on_prod_baselines(self, baselines):
        self._prod_baselines = baselines
        self._prod_baseline_done = True
        self._check_baselines_done()

    # ── PhysStates callbacks ──────────────────────────────────────────
    def _on_phy_progress(self, progress: float):
        pass  # prod progress is the longer one; use it for the bar

    def _on_phy_baselines(self, baselines):
        self._phy_baselines = baselines
        self._phy_baseline_done = True
        self._check_baselines_done()

    def _check_baselines_done(self):
        """Finish calibration only when BOTH baseline calibrations are done."""
        if self._prod_baseline_done and self._phy_baseline_done:
            self.progress_updated.emit(1.0)
            self._finish()

    # ── Finish ────────────────────────────────────────────────────────
    def _finish(self):
        cal_data = {}
        if self._nfb_data:
            cal_data["nfb"] = nfb_to_dict(self._nfb_data)
        if self._prod_baselines:
            cal_data["prod_baselines"] = prod_baselines_to_dict(self._prod_baselines)
        if self._phy_baselines:
            cal_data["phy_baselines"] = phy_baselines_to_dict(self._phy_baselines)

        # Save for next session
        if self._serial:
            save_calibration(self._serial, cal_data)

        self.calibration_complete.emit(cal_data)
