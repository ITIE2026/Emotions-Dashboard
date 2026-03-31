"""
CalibrationManager orchestrates the multi-stage calibration workflow.

Stages:
  1. Closed-eyes NFB calibration
  2. Productivity baseline calibration
  3. PhysiologicalStates baseline calibration

Quick mode keeps the same 3-step UI, but the physiological baseline starts
quietly during the NFB stage to match the SDK sample flow. Stage 3 becomes
visible only after productivity completes.
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

    stage_changed = Signal(int, str)
    progress_updated = Signal(float)
    calibration_complete = Signal(dict)
    calibration_failed = Signal(str)
    iapf_updated = Signal(dict)

    STAGE_NFB = 1
    STAGE_PROD = 2
    STAGE_PHY = 3
    MODE_DETECT = "detect"
    MODE_QUICK = "quick"
    STAGE_1_END = 0.33
    STAGE_2_END = 0.66
    STAGE_3_END = 1.0
    BASELINE_TIMEOUT_MS = 90_000
    MAX_PHY_RETRIES = 1
    PHY_HARD_DEADLINE_MS = 120_000
    PHY_STATUS_PENDING = "pending"
    PHY_STATUS_COMPLETE = "complete"
    PHY_STATUS_TIMED_OUT = "timed_out"

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
        self._terminal_emitted = False

        self._prod_started = False
        self._prod_completed = False
        self._latest_prod_progress = 0.0

        self._phy_started = False
        self._phy_completed = False
        self._latest_phy_progress = 0.0
        self._phy_retry_count = 0
        self._pending_phy_retry = False
        self._phy_status = self.PHY_STATUS_PENDING
        self._phy_progress_seen = False
        self._phy_baselines_seen = False
        self._phy_state_packets_seen = 0

        self._prod_start_timer = QTimer(self)
        self._prod_start_timer.setSingleShot(True)
        self._prod_start_timer.timeout.connect(self._start_prod_stage)

        self._phy_start_timer = QTimer(self)
        self._phy_start_timer.setSingleShot(True)
        self._phy_start_timer.timeout.connect(self._start_phy_stage)

        self._prod_watchdog = QTimer(self)
        self._prod_watchdog.setSingleShot(True)
        self._prod_watchdog.timeout.connect(self._on_prod_timeout)

        self._phy_watchdog = QTimer(self)
        self._phy_watchdog.setSingleShot(True)
        self._phy_watchdog.timeout.connect(self._on_phy_timeout)

        self._phy_deadline = QTimer(self)
        self._phy_deadline.setSingleShot(True)
        self._phy_deadline.timeout.connect(self._on_phy_hard_deadline)

        self._prod_h.baselines_updated.connect(self._on_prod_baselines)
        self._prod_h.calibration_progress.connect(self._on_prod_progress)
        self._phy_h.baselines_updated.connect(self._on_phy_baselines)
        self._phy_h.calibration_progress.connect(self._on_phy_progress)
        if hasattr(self._phy_h, "states_updated"):
            self._phy_h.states_updated.connect(self._on_phy_states)

    def can_import(self, serial: str) -> bool:
        return has_saved_calibration(serial)

    def import_saved(self, serial: str) -> bool:
        """Import previously saved calibration. Returns True on success."""
        self._reset_runtime_state()
        data = load_calibration(serial)
        if data is None:
            return False

        self._serial = serial
        self._calibrator = Calibrator(self._device, self._lib)

        try:
            if "nfb" in data:
                nfb = dict_to_nfb(data["nfb"])
                self._calibrator.import_alpha(nfb)
                self._nfb_data = nfb

            if "prod_baselines" in data:
                bl = dict_to_prod_baselines(data["prod_baselines"])
                self._prod_h.import_baselines(bl)
                self._prod_baselines = bl

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
            self.calibration_failed.emit(self._safe_message(exc))
            return False

    def start(self, serial: str, mode: str = MODE_QUICK):
        """Begin the requested live calibration process."""
        self._reset_runtime_state()
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
            log.info("Calibration started: mode=%s serial=%s", self._mode, self._serial or "")
            self.stage_changed.emit(self.STAGE_NFB, description)
            self._emit_progress(0.0)

            self._nfb_elapsed = 0
            self._nfb_duration = 30
            self._nfb_timer = QTimer(self)
            self._nfb_timer.setInterval(1000)
            self._nfb_timer.timeout.connect(self._nfb_tick)
            self._nfb_timer.start()

            if self._mode == self.MODE_QUICK:
                self._queue_phy_stage_start()

            self._calibrator.calibrate_quick()
        except Exception as exc:
            self._fail(self._safe_message(exc))

    def start_detect(self, serial: str):
        self.start(serial, mode=self.MODE_DETECT)

    def start_quick(self, serial: str):
        self.start(serial, mode=self.MODE_QUICK)

    def _nfb_tick(self):
        self._nfb_elapsed += 1
        if self._nfb_elapsed >= self._nfb_duration:
            self._nfb_timer.stop()
            return
        fraction = self._nfb_elapsed / self._nfb_duration
        self._emit_progress(fraction * self.STAGE_1_END)

    def _on_nfb_stage(self, calibrator_obj):
        pass

    def _on_nfb_finished(self, calibrator_obj, nfb_data: IndividualNFBData):
        if self._terminal_emitted or self._current_stage != self.STAGE_NFB:
            return
        try:
            if hasattr(self, "_nfb_timer") and self._nfb_timer.isActive():
                self._nfb_timer.stop()

            if self._calibrator.has_calibration_failed():
                self._fail("NFB calibration failed - too many artifacts")
                return

            log.info("Calibration NFB stage finished")
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
            self._queue_prod_stage_start()
        except Exception as exc:
            self._fail(self._safe_message(exc))

    def _on_prod_progress(self, progress: float):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._prod_completed
            or self._current_stage not in {self.STAGE_PROD, self.STAGE_PHY}
        ):
            return
        fraction = max(0.0, min(1.0, float(progress)))
        self._latest_prod_progress = fraction
        self._arm_prod_watchdog()
        if self._current_stage == self.STAGE_PROD:
            overall = self.STAGE_1_END + ((self.STAGE_2_END - self.STAGE_1_END) * fraction)
            self._emit_progress(overall)

    def _on_prod_baselines(self, baselines):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._prod_completed
            or self._current_stage not in {self.STAGE_PROD, self.STAGE_PHY}
        ):
            return

        self._prod_baselines = baselines
        self._prod_payload = self._serialize_prod_baselines(baselines)
        self._prod_completed = True
        self._latest_prod_progress = 1.0
        log.info("Calibration productivity baseline finished")
        self._clear_prod_watchdog()
        self._emit_progress(self.STAGE_2_END)
        self._show_phy_stage()

        if self._phy_completed or self._phy_status == self.PHY_STATUS_TIMED_OUT:
            self._emit_progress(1.0)
            self._finish()
            return

        self._emit_phy_stage_progress()

    def _on_phy_states(self, data: dict):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or not self._phy_started
            or self._phy_status != self.PHY_STATUS_PENDING
            or self._current_stage not in {self.STAGE_NFB, self.STAGE_PROD, self.STAGE_PHY}
        ):
            return
        self._phy_state_packets_seen += 1
        if self._phy_state_packets_seen == 1:
            log.info("Calibration physiological baseline is receiving physiological state packets")

    def _on_phy_progress(self, progress: float):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._phy_status != self.PHY_STATUS_PENDING
            or self._phy_completed
            or self._current_stage not in {self.STAGE_NFB, self.STAGE_PROD, self.STAGE_PHY}
        ):
            return

        fraction = max(0.0, min(1.0, float(progress)))
        if fraction > self._latest_phy_progress:
            self._latest_phy_progress = fraction
            self._arm_phy_watchdog()

        if not self._phy_progress_seen:
            self._phy_progress_seen = True
            log.info("Calibration physiological baseline progress started: %.3f", fraction)
        elif fraction >= 1.0:
            log.info("Calibration physiological baseline progress reached completion")

        if self._current_stage == self.STAGE_PHY and self._prod_completed:
            self._emit_phy_stage_progress()

    def _on_phy_baselines(self, baselines):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._phy_status == self.PHY_STATUS_TIMED_OUT
            or self._phy_completed
            or self._current_stage not in {self.STAGE_NFB, self.STAGE_PROD, self.STAGE_PHY}
        ):
            return

        self._phy_baselines = baselines
        self._phy_payload = self._serialize_phy_baselines(baselines)
        self._phy_completed = True
        self._phy_status = self.PHY_STATUS_COMPLETE
        self._phy_baselines_seen = True
        self._latest_phy_progress = 1.0
        log.info(
            "Calibration physiological baseline finished "
            "(progress_seen=%s, state_packets=%d)",
            self._phy_progress_seen,
            self._phy_state_packets_seen,
        )
        self._clear_phy_watchdog()

        if not self._prod_completed:
            log.info("Calibration physiological baseline finished before productivity baseline")
            return

        if self._current_stage != self.STAGE_PHY:
            self._show_phy_stage()
        self._emit_progress(1.0)
        self._finish()

    def _finish(self):
        if self._terminal_emitted:
            return
        self._terminal_emitted = True
        self._stop_runtime_timers()

        save_data = {}
        if self._nfb_payload:
            save_data["nfb"] = dict(self._nfb_payload)
        if self._prod_payload:
            save_data["prod_baselines"] = dict(self._prod_payload)
        if self._phy_payload:
            save_data["phy_baselines"] = dict(self._phy_payload)

        if self._serial:
            try:
                save_calibration(self._serial, save_data)
            except Exception as exc:
                log.warning(
                    "Calibration finished but saving failed for %s: %s",
                    self._serial,
                    self._safe_message(exc),
                )

        result = dict(save_data)
        result["mode"] = self.MODE_QUICK
        result["applied"] = True
        result["phy_status"] = self._resolved_phy_status()
        self.calibration_complete.emit(result)

    def _resolved_phy_status(self) -> str:
        if self._phy_status == self.PHY_STATUS_PENDING:
            if self._phy_completed or self._phy_payload:
                return self.PHY_STATUS_COMPLETE
            return self.PHY_STATUS_TIMED_OUT
        return self._phy_status

    def _fail(self, reason: str):
        if self._terminal_emitted:
            return
        self._terminal_emitted = True
        self._stop_runtime_timers()
        self.calibration_failed.emit(reason)

    def _emit_progress(self, value: float):
        bounded = max(0.0, min(1.0, float(value)))
        if bounded < self._last_progress:
            bounded = self._last_progress
        self._last_progress = bounded
        self.progress_updated.emit(round(bounded, 4))

    def _emit_phy_stage_progress(self):
        if self._current_stage != self.STAGE_PHY:
            return
        fraction = self._latest_phy_progress if not self._phy_completed else 1.0
        overall = self.STAGE_2_END + ((self.STAGE_3_END - self.STAGE_2_END) * fraction)
        self._emit_progress(overall)

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

    def stop(self):
        """Cancel any in-progress calibration without emitting failure signals."""
        if not self._terminal_emitted:
            self._terminal_emitted = True
        self._stop_runtime_timers()
        self._current_stage = 0

    def _reset_runtime_state(self):
        self._stop_runtime_timers()
        self._current_stage = 0
        self._terminal_emitted = False
        self._prod_started = False
        self._prod_completed = False
        self._latest_prod_progress = 0.0
        self._phy_started = False
        self._phy_completed = False
        self._latest_phy_progress = 0.0
        self._phy_retry_count = 0
        self._pending_phy_retry = False
        self._phy_status = self.PHY_STATUS_PENDING
        self._phy_progress_seen = False
        self._phy_baselines_seen = False
        self._phy_state_packets_seen = 0

    def _stop_runtime_timers(self):
        if hasattr(self, "_nfb_timer") and self._nfb_timer is not None:
            self._nfb_timer.stop()
        self._prod_start_timer.stop()
        self._phy_start_timer.stop()
        self._prod_watchdog.stop()
        self._phy_watchdog.stop()
        self._phy_deadline.stop()

    def _queue_prod_stage_start(self):
        if self._terminal_emitted or self._mode != self.MODE_QUICK or self._current_stage != self.STAGE_PROD:
            return
        self.stage_changed.emit(self.STAGE_PROD, "Calibrating productivity baseline")
        if not self._prod_start_timer.isActive():
            self._prod_start_timer.start(0)

    def _start_prod_stage(self):
        if self._terminal_emitted or self._mode != self.MODE_QUICK or self._prod_completed:
            return
        try:
            self._prod_started = True
            log.info("Calibration productivity baseline started")
            self._prod_h.start_baseline_calibration()
            self._arm_prod_watchdog()
        except Exception as exc:
            self._fail(f"Unable to start productivity baseline calibration: {self._safe_message(exc)}")

    def _queue_phy_stage_start(self, retry: bool = False):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._current_stage not in {self.STAGE_NFB, self.STAGE_PROD, self.STAGE_PHY}
            or self._phy_completed
            or self._phy_status == self.PHY_STATUS_TIMED_OUT
        ):
            return
        self._pending_phy_retry = retry
        if not self._phy_start_timer.isActive():
            self._phy_start_timer.start(0)

    def _start_phy_stage(self):
        retry = self._pending_phy_retry
        self._pending_phy_retry = False
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._current_stage not in {self.STAGE_NFB, self.STAGE_PROD, self.STAGE_PHY}
            or self._phy_completed
            or self._phy_status == self.PHY_STATUS_TIMED_OUT
        ):
            return
        try:
            self._phy_started = True
            if retry:
                log.warning(
                    "Calibration physiological baseline retry started (%d/%d)",
                    self._phy_retry_count,
                    self.MAX_PHY_RETRIES,
                )
            else:
                log.info("Calibration physiological baseline started")
            self._phy_h.start_baseline_calibration()
            self._arm_phy_watchdog()
            if not self._phy_deadline.isActive():
                self._phy_deadline.start(self.PHY_HARD_DEADLINE_MS)
        except Exception as exc:
            self._fail(f"Unable to start physiological baseline calibration: {self._safe_message(exc)}")

    def _show_phy_stage(self):
        if self._terminal_emitted or self._mode != self.MODE_QUICK:
            return
        self._current_stage = self.STAGE_PHY
        self.stage_changed.emit(self.STAGE_PHY, self._phy_stage_description())

    def _phy_stage_description(self) -> str:
        if self._phy_status == self.PHY_STATUS_TIMED_OUT:
            return "Physiological baseline timed out"
        if self._phy_retry_count > 0 and not self._phy_completed:
            return "Retrying physiological baseline..."
        return "Calibrating physiological baseline"

    def _arm_prod_watchdog(self):
        self._prod_watchdog.start(self.BASELINE_TIMEOUT_MS)

    def _clear_prod_watchdog(self):
        self._prod_watchdog.stop()

    def _arm_phy_watchdog(self):
        timeout = int(self.BASELINE_TIMEOUT_MS * (1.0 + 0.25 * self._phy_retry_count))
        self._phy_watchdog.start(timeout)

    def _clear_phy_watchdog(self):
        self._phy_watchdog.stop()

    def _on_prod_timeout(self):
        if self._terminal_emitted or self._mode != self.MODE_QUICK or self._prod_completed:
            return
        log.warning("Calibration productivity baseline timed out after %d ms", self.BASELINE_TIMEOUT_MS)
        self._fail("Productivity baseline calibration timed out. Please retry.")

    def _on_phy_timeout(self):
        if (
            self._terminal_emitted
            or self._mode != self.MODE_QUICK
            or self._phy_completed
            or self._phy_status == self.PHY_STATUS_TIMED_OUT
        ):
            return

        elapsed_ms = int(self.BASELINE_TIMEOUT_MS * (1.0 + 0.25 * self._phy_retry_count))
        diagnostics = self._phy_diagnostics_summary()
        if self._phy_retry_count < self.MAX_PHY_RETRIES:
            self._phy_retry_count += 1
            log.warning(
                "Calibration physiological baseline timed out after %d ms; retrying (%d/%d). %s",
                elapsed_ms,
                self._phy_retry_count,
                self.MAX_PHY_RETRIES,
                diagnostics,
            )
            if self._current_stage == self.STAGE_PHY:
                self.stage_changed.emit(self.STAGE_PHY, self._phy_stage_description())
            self._queue_phy_stage_start(retry=True)
            return

        self._phy_status = self.PHY_STATUS_TIMED_OUT
        log.warning(
            "Calibration physiological baseline timed out after %d ms and %d retries; "
            "completing with NFB + productivity data only. %s",
            elapsed_ms,
            self.MAX_PHY_RETRIES,
            diagnostics,
        )

        if self._prod_completed:
            if self._current_stage != self.STAGE_PHY:
                self._show_phy_stage()
            self._emit_progress(1.0)
            self._finish()

    def _phy_diagnostics_summary(self) -> str:
        return (
            "Diagnostics: "
            f"state_packets={self._phy_state_packets_seen}, "
            f"progress_seen={self._phy_progress_seen}, "
            f"baselines_seen={self._phy_baselines_seen}"
        )

    def _on_phy_hard_deadline(self):
        """Absolute ceiling – fires once regardless of progress resets."""
        if (
            self._terminal_emitted
            or self._phy_completed
            or self._phy_status == self.PHY_STATUS_TIMED_OUT
        ):
            return
        self._phy_status = self.PHY_STATUS_TIMED_OUT
        self._phy_watchdog.stop()
        log.warning(
            "Calibration physiological baseline hit hard deadline (%d ms); "
            "completing without physio baselines. %s",
            self.PHY_HARD_DEADLINE_MS,
            self._phy_diagnostics_summary(),
        )
        if self._prod_completed:
            if self._current_stage != self.STAGE_PHY:
                self._show_phy_stage()
            self._emit_progress(1.0)
            self._finish()
