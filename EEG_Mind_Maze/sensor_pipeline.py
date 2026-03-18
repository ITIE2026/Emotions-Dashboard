from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any


APP_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_DIR = os.path.join(APP_DIR, "capsule_sdk")
DLL_PATH = os.path.join(APP_DIR, "CapsuleClient.dll")
LOG_DIR = os.path.join(APP_DIR, "logs")

SEARCH_TIMEOUT_SEC = 15
CONNECT_TIMEOUT_SEC = 12
FRESH_METRIC_SEC = 2.0
UPDATE_INTERVAL_SEC = 0.02
NFB_DURATION_SEC = 30.0
EMA_ALPHA = 0.25

if SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

from Capsule import Capsule  # noqa: E402
from Calibrator import Calibrator  # noqa: E402
from Device import Device, Device_Connection_Status  # noqa: E402
from DeviceLocator import DeviceLocator  # noqa: E402
from DeviceType import DeviceType  # noqa: E402
from PhysiologicalStates import PhysiologicalStates  # noqa: E402
from Productivity import Productivity  # noqa: E402


@dataclass(frozen=True)
class SensorSnapshot:
    mode: str
    status: str
    calibration_stage: str
    progress: float
    device_name: str
    device_serial: str
    concentration: float
    relaxation: float
    productivity: float
    fatigue: float
    fresh: bool
    has_artifacts: bool
    nfb_artifacts: bool
    cardio_artifacts: bool
    live_calibration_complete: bool
    fallback_mode: bool
    demo_available: bool


def _ema(previous: float | None, raw: float) -> float:
    if previous is None:
        return raw
    return previous + EMA_ALPHA * (raw - previous)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


class SensorPipeline:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._capsule: Capsule | None = None
        self._locator: DeviceLocator | None = None
        self._device: Device | None = None
        self._prod: Productivity | None = None
        self._physio: PhysiologicalStates | None = None
        self._calibrator: Calibrator | None = None

        self._discovery_event = threading.Event()
        self._connected_event = threading.Event()
        self._selected_device_info: Any = None
        self._scan_failure_reason = ""
        self._prod_baseline_done = False
        self._phy_baseline_done = False
        self._nfb_started_at: float | None = None

        self._ema_productivity: float | None = None
        self._ema_relax: float | None = None
        self._ema_conc: float | None = None
        self._ema_fatigue: float | None = None
        self._latest_metric_at = 0.0
        self._prod_has_artifacts = False
        self._nfb_artifacts = False
        self._cardio_artifacts = False

        self._mode = "idle"
        self._status = "Waiting to start."
        self._calibration_stage = ""
        self._progress = 0.0
        self._device_name = ""
        self._device_serial = ""
        self._concentration = 0.0
        self._relaxation = 0.0
        self._productivity = 0.0
        self._fatigue = 0.0
        self._live_calibration_complete = False
        self._fallback_mode = False
        self._demo_available = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="mind-maze-sensor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._safe_shutdown()

    def snapshot(self) -> SensorSnapshot:
        with self._lock:
            fresh = (time.monotonic() - self._latest_metric_at) <= FRESH_METRIC_SEC if self._latest_metric_at else False
            return SensorSnapshot(
                mode=self._mode,
                status=self._status,
                calibration_stage=self._calibration_stage,
                progress=self._progress,
                device_name=self._device_name,
                device_serial=self._device_serial,
                concentration=self._concentration,
                relaxation=self._relaxation,
                productivity=self._productivity,
                fatigue=self._fatigue,
                fresh=fresh,
                has_artifacts=self._prod_has_artifacts or self._nfb_artifacts or self._cardio_artifacts,
                nfb_artifacts=self._nfb_artifacts,
                cardio_artifacts=self._cardio_artifacts,
                live_calibration_complete=self._live_calibration_complete,
                fallback_mode=self._fallback_mode,
                demo_available=self._demo_available,
            )

    def _run(self) -> None:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            if not os.path.isfile(DLL_PATH):
                self._enter_fallback("CapsuleClient.dll is missing. Press Enter for keyboard demo mode.")
                return

            self._set_state("scanning", "Scanning for a compatible headband...", "Device discovery", 0.0)
            self._capsule = Capsule(DLL_PATH)
            lib = self._capsule.get_lib()
            self._locator = DeviceLocator(LOG_DIR, lib)
            self._locator.set_on_devices_list(self._on_devices_list)
            self._locator.request_devices(DeviceType.Band, SEARCH_TIMEOUT_SEC)

            scan_deadline = time.monotonic() + SEARCH_TIMEOUT_SEC + 2.0
            while not self._stop_event.is_set() and not self._discovery_event.is_set() and time.monotonic() < scan_deadline:
                self._locator.update()
                time.sleep(UPDATE_INTERVAL_SEC)

            if self._selected_device_info is None:
                reason = self._scan_failure_reason or "No compatible headband found. Press Enter for keyboard demo mode."
                self._enter_fallback(reason)
                return

            self._device_name = self._selected_device_info.get_name()
            self._device_serial = self._selected_device_info.get_serial()
            self._set_state("connecting", f"Connecting to {self._device_name}...", "Connecting", 0.0)

            self._device = Device(self._locator, self._device_serial, lib)
            self._device.set_on_connection_status_changed(self._on_connection_changed)
            self._device.set_on_error(self._on_device_error)

            self._prod = Productivity(self._device, lib)
            self._prod.set_on_metrics_update(self._on_productivity_metrics)
            self._prod.set_on_indexes_update(self._on_productivity_indexes)
            self._prod.set_on_baseline_update(self._on_prod_baselines)
            self._prod.set_on_calibration_progress(self._on_prod_progress)

            self._physio = PhysiologicalStates(self._device, lib)
            self._physio.set_on_states(self._on_physio_states)
            self._physio.set_on_calibrated(self._on_phy_baselines)
            self._physio.set_on_calibration_progress(self._on_phy_progress)

            self._calibrator = Calibrator(self._device, lib)
            self._calibrator.set_on_calibration_finished(self._on_nfb_finished)
            self._calibrator.set_on_calibration_stage_finished(self._on_nfb_stage)

            self._device.connect(True)
            connect_deadline = time.monotonic() + CONNECT_TIMEOUT_SEC
            while not self._stop_event.is_set() and not self._connected_event.is_set() and time.monotonic() < connect_deadline:
                self._locator.update()
                time.sleep(UPDATE_INTERVAL_SEC)

            if not self._connected_event.is_set():
                self._enter_fallback("Headband connection timed out. Press Enter for keyboard demo mode.")
                return

            self._device.start()
            self._nfb_started_at = time.monotonic()
            self._set_state("calibrating", "Close your eyes for the quick calibration.", "Closed-eyes calibration", 0.0)
            self._calibrator.calibrate_quick()

            while not self._stop_event.is_set():
                self._locator.update()
                self._tick_nfb_progress()
                time.sleep(UPDATE_INTERVAL_SEC)
        except Exception as exc:
            self._enter_fallback(f"{exc}. Press Enter for keyboard demo mode.")

    def _tick_nfb_progress(self) -> None:
        with self._lock:
            if self._mode != "calibrating" or self._calibration_stage != "Closed-eyes calibration" or self._nfb_started_at is None:
                return
            elapsed = time.monotonic() - self._nfb_started_at
            self._progress = min(0.33, (elapsed / NFB_DURATION_SEC) * 0.33)

    def _set_state(self, mode: str, status: str, calibration_stage: str, progress: float) -> None:
        with self._lock:
            self._mode = mode
            self._status = status
            self._calibration_stage = calibration_stage
            self._progress = progress

    def _enter_fallback(self, reason: str) -> None:
        with self._lock:
            self._mode = "fallback"
            self._status = reason
            self._calibration_stage = "Keyboard demo"
            self._progress = 0.0
            self._fallback_mode = True
            self._demo_available = True
        self._safe_shutdown()

    def _safe_shutdown(self) -> None:
        try:
            if self._device:
                try:
                    self._device.stop()
                except Exception:
                    pass
                try:
                    self._device.disconnect()
                except Exception:
                    pass
        finally:
            self._device = None

    def _on_devices_list(self, locator: DeviceLocator, device_info_list: DeviceLocator.DeviceInfoList, fail_reason: Any) -> None:
        if len(device_info_list) > 0:
            self._selected_device_info = device_info_list[0]
        else:
            fail_value = int(getattr(fail_reason, "value", fail_reason))
            if fail_value == 1:
                self._scan_failure_reason = "Bluetooth is disabled. Press Enter for keyboard demo mode."
            else:
                self._scan_failure_reason = "No compatible headband found. Press Enter for keyboard demo mode."
        self._discovery_event.set()

    def _on_connection_changed(self, device: Device, status: Any) -> None:
        status_value = int(getattr(status, "value", status))
        if status_value == Device_Connection_Status.Device_ConnectionState_Connected:
            self._connected_event.set()
            self._set_state("connected", f"Connected to {self._device_name}. Preparing live calibration...", "Connected", 0.0)
        elif status_value == Device_Connection_Status.Device_ConnectionState_Disconnected and not self._stop_event.is_set():
            self._enter_fallback("Headband disconnected. Press Enter for keyboard demo mode.")

    def _on_device_error(self, device: Device, error_message: Any) -> None:
        if self._stop_event.is_set():
            return
        message = str(error_message)
        with self._lock:
            self._status = message

    def _on_productivity_metrics(self, prod_obj: Productivity, metrics: Any) -> None:
        cognitive_raw = _clamp(float(metrics.currentValue) * 100.0)
        relax_raw = _clamp(float(metrics.relaxationScore))
        conc_raw = _clamp(float(metrics.concentrationScore))
        fatigue_raw = _clamp(float(metrics.fatigueScore))
        with self._lock:
            self._ema_productivity = _ema(self._ema_productivity, cognitive_raw)
            self._ema_relax = _ema(self._ema_relax, relax_raw)
            self._ema_conc = _ema(self._ema_conc, conc_raw)
            self._ema_fatigue = _ema(self._ema_fatigue, fatigue_raw)
            self._productivity = round(self._ema_productivity or 0.0, 1)
            self._relaxation = round(self._ema_relax or 0.0, 1)
            self._concentration = round(self._ema_conc or 0.0, 1)
            self._fatigue = round(self._ema_fatigue or 0.0, 1)
            self._latest_metric_at = time.monotonic()
            if self._live_calibration_complete:
                self._mode = "ready"
                self._status = "Live metrics ready. Hold steady for the Mind Maze start zone."

    def _on_productivity_indexes(self, prod_obj: Productivity, indexes: Any) -> None:
        with self._lock:
            self._prod_has_artifacts = bool(indexes.hasArtifacts)

    def _on_physio_states(self, phy_obj: PhysiologicalStates, value: Any) -> None:
        with self._lock:
            self._nfb_artifacts = bool(value.nfbArtifacts)
            self._cardio_artifacts = bool(value.cardioArtifacts)

    def _on_nfb_stage(self, calibrator_obj: Calibrator) -> None:
        return

    def _on_nfb_finished(self, calibrator_obj: Calibrator, nfb_data: Any) -> None:
        if calibrator_obj.has_calibration_failed():
            self._enter_fallback("Closed-eyes calibration failed. Press Enter for keyboard demo mode.")
            return
        self._prod_baseline_done = False
        self._phy_baseline_done = False
        self._set_state("calibrating", "Calibrating productivity and physiological baselines...", "Baseline calibration", 0.33)
        if self._prod:
            self._prod.calibrate_baselines()
        if self._physio:
            self._physio.calibrate_baselines()

    def _on_prod_progress(self, prod_obj: Productivity, progress: float) -> None:
        with self._lock:
            self._progress = min(0.99, 0.33 + (0.33 * float(progress)))

    def _on_phy_progress(self, phy_obj: PhysiologicalStates, progress: float) -> None:
        with self._lock:
            self._progress = max(self._progress, min(0.99, 0.66 + (0.34 * float(progress))))

    def _on_prod_baselines(self, prod_obj: Productivity, baselines: Any) -> None:
        self._prod_baseline_done = True
        self._check_baselines_done()

    def _on_phy_baselines(self, phy_obj: PhysiologicalStates, baselines: Any) -> None:
        self._phy_baseline_done = True
        self._check_baselines_done()

    def _check_baselines_done(self) -> None:
        if not (self._prod_baseline_done and self._phy_baseline_done):
            return
        with self._lock:
            self._mode = "ready"
            self._status = "Live calibration complete. Waiting for fresh concentration and relaxation metrics."
            self._calibration_stage = "Live metrics"
            self._progress = 1.0
            self._live_calibration_complete = True
