"""
Runtime logic for the embedded Neuroflow launcher page.

This module preserves the original Neuroflow focus-trigger behavior:
- CI = Beta / (Theta + Alpha)
- primary averaging over BETA_WINDOW_SIZE PSD frames
- secondary smoothing over CI_FOCUS_SMOOTH_FRAMES
- above-threshold dwell start with hysteresis dropout
- trigger cooldown between app launches
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import os
import random
import subprocess
import threading
import time


BETA_WINDOW_SIZE = 30
CI_FOCUS_THRESHOLD = 0.38
CI_FOCUS_DROPOUT = 0.15
CI_FOCUS_CONSEC_REQUIRED = 2
CI_FOCUS_SMOOTH_FRAMES = 12
FOCUS_DWELL_SECONDS = 2.0
TRIGGER_COOLDOWN = 5.0
EEG_BUFFER_SAMPLES = 1250
SIM_START_DELAY_S = 15.0

STAGE_DETECTING = 0
STAGE_RESISTANCE = 1
STAGE_CALIBRATING = 2
STAGE_EEG = 3
STAGE_SPECTRAL = 4
STAGE_FOCUS = 5

STAGES = [
    ("Detect", STAGE_DETECTING),
    ("Resistance", STAGE_RESISTANCE),
    ("Calibration", STAGE_CALIBRATING),
    ("EEG", STAGE_EEG),
    ("Spectral", STAGE_SPECTRAL),
    ("Focus", STAGE_FOCUS),
]

APPS = [
    {
        "name": "Google Chrome",
        "icon": "🌐",
        "cmd": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "fallback": ["start", "chrome"],
        "shell": False,
    },
    {
        "name": "System Settings",
        "icon": "⚙️",
        "cmd": None,
        "fallback": ["start", "ms-settings:"],
        "shell": True,
    },
    {
        "name": "Microsoft Word",
        "icon": "📝",
        "cmd": None,
        "fallback": ["start", "winword"],
        "shell": True,
    },
    {
        "name": "Microsoft Excel",
        "icon": "📊",
        "cmd": None,
        "fallback": ["start", "excel"],
        "shell": True,
    },
    {
        "name": "Microsoft PowerPoint",
        "icon": "📑",
        "cmd": None,
        "fallback": ["start", "powerpnt"],
        "shell": True,
    },
]


def launch_app(app: dict) -> None:
    cmd = app.get("cmd")
    fallback = app.get("fallback", [])
    shell = bool(app.get("shell", False))
    if cmd and os.path.exists(cmd):
        try:
            subprocess.Popen([cmd])
            return
        except Exception:
            pass
    if fallback:
        subprocess.Popen(" ".join(fallback) if shell else fallback, shell=shell)


@dataclass(frozen=True)
class NeuroflowSnapshot:
    stage: int
    connected: bool
    simulation_active: bool
    ready_to_calibrate: bool
    calibrated: bool
    calibration_active: bool
    ci_raw: float
    ci_primary: float
    ci_smooth: float
    in_focus: bool
    dwell_progress: float
    cooldown_remaining: float
    band_powers: dict[str, float]
    last_message: str
    app_index: int


class NeuroflowStateMachine:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.connected = False
        self.simulation_active = False
        self.ready_to_calibrate = False
        self.calibrated = False
        self.calibration_active = False
        self.stage = STAGE_DETECTING
        self.band_powers = {band: 0.0 for band in ("delta", "theta", "alpha", "smr", "beta")}
        self.resistances = {}
        self.ci_raw = 0.0
        self.ci_primary = 0.0
        self.ci_smooth = 0.0
        self._ci_primary_history: deque[float] = deque(maxlen=BETA_WINDOW_SIZE)
        self._ci_smooth_history: deque[float] = deque(maxlen=CI_FOCUS_SMOOTH_FRAMES)
        self._consecutive_focus_frames = 0
        self._in_focus = False
        self._focus_start = 0.0
        self._last_trigger_time = 0.0
        self._message = "Waiting for device detection."
        self._app_index = 0
        self._has_eeg = False
        self._has_psd = False

    def snapshot(self, now: float | None = None) -> NeuroflowSnapshot:
        now = float(now if now is not None else time.monotonic())
        cooldown_remaining = max(0.0, TRIGGER_COOLDOWN - (now - self._last_trigger_time))
        dwell_progress = 0.0
        if self._in_focus and self._focus_start > 0.0:
            dwell_progress = min(1.0, (now - self._focus_start) / FOCUS_DWELL_SECONDS)
        return NeuroflowSnapshot(
            stage=self.stage,
            connected=self.connected,
            simulation_active=self.simulation_active,
            ready_to_calibrate=self.ready_to_calibrate,
            calibrated=self.calibrated,
            calibration_active=self.calibration_active,
            ci_raw=self.ci_raw,
            ci_primary=self.ci_primary,
            ci_smooth=self.ci_smooth,
            in_focus=self._in_focus,
            dwell_progress=dwell_progress,
            cooldown_remaining=cooldown_remaining,
            band_powers=dict(self.band_powers),
            last_message=self._message,
            app_index=self._app_index,
        )

    @property
    def app_index(self) -> int:
        return self._app_index

    def set_current_app(self, index: int) -> None:
        self._app_index = max(0, min(index, len(APPS) - 1))

    def cycle_next_app(self) -> int:
        self._app_index = (self._app_index + 1) % len(APPS)
        return self._app_index

    def current_app(self) -> dict:
        return APPS[self._app_index]

    def set_connected(self, connected: bool, simulation: bool = False) -> None:
        self.connected = bool(connected)
        self.simulation_active = bool(simulation)
        if not self.connected:
            self.ready_to_calibrate = False
            self.calibration_active = False
            self._has_eeg = False
            self._has_psd = False
            self.stage = STAGE_DETECTING
            self._message = "Searching for a Capsule device."
            self._reset_focus()
            return
        self.stage = STAGE_RESISTANCE
        self._message = "Device detected. Checking electrode resistance."

    def set_resistances(self, resistances: dict[str, float]) -> bool:
        self.resistances = dict(resistances or {})
        good = [value for value in self.resistances.values() if float(value) <= 500_000.0]
        self.ready_to_calibrate = len(good) >= 2
        if not self.connected:
            self.stage = STAGE_DETECTING
        elif self.calibration_active:
            self.stage = STAGE_CALIBRATING
        elif self.ready_to_calibrate:
            self.stage = max(self.stage, STAGE_RESISTANCE)
            self._message = "Resistance passed. Start quick calibration."
        else:
            self.stage = STAGE_RESISTANCE
            self._message = "Waiting for at least two clean electrodes <= 500 kΩ."
        return self.ready_to_calibrate

    def start_calibration(self) -> None:
        if not self.connected:
            self._message = "Connect the device before calibration."
            return
        self.calibration_active = True
        self.calibrated = False
        self.stage = STAGE_CALIBRATING
        self._message = "Quick calibration started. Close your eyes and relax."
        self._has_eeg = False
        self._has_psd = False
        self._reset_focus()

    def finish_calibration(self, success: bool, message: str = "") -> None:
        self.calibration_active = False
        self.calibrated = bool(success)
        if self.calibrated:
            self.stage = STAGE_SPECTRAL
            self._message = message or "Calibration completed. Waiting for EEG and PSD."
        else:
            self.stage = STAGE_RESISTANCE if self.connected else STAGE_DETECTING
            self._message = message or "Calibration did not complete."

    def note_eeg_seen(self) -> None:
        if not self.connected:
            return
        self._has_eeg = True
        if self.calibrated and self.stage < STAGE_EEG:
            self.stage = STAGE_EEG
            self._message = "EEG streaming. Waiting for spectral analysis."

    def ingest_band_powers(self, band_powers: dict[str, float], now: float | None = None) -> bool:
        now = float(now if now is not None else time.monotonic())
        self.band_powers = {band: float(band_powers.get(band, 0.0)) for band in self.band_powers}
        theta = max(0.0, self.band_powers.get("theta", 0.0))
        alpha = max(0.0, self.band_powers.get("alpha", 0.0))
        beta = max(0.0, self.band_powers.get("beta", 0.0))
        denom = theta + alpha
        self.ci_raw = beta / denom if denom > 1e-9 else 0.0
        self._ci_primary_history.append(self.ci_raw)
        self.ci_primary = sum(self._ci_primary_history) / max(1, len(self._ci_primary_history))
        self._ci_smooth_history.append(self.ci_primary)
        self.ci_smooth = sum(self._ci_smooth_history) / max(1, len(self._ci_smooth_history))

        if not self.connected or not self.calibrated:
            return False

        self._has_psd = True
        self.stage = STAGE_FOCUS
        cooldown_remaining = max(0.0, TRIGGER_COOLDOWN - (now - self._last_trigger_time))
        if cooldown_remaining > 0.0:
            self._message = f"Cooldown active. Next launch in {cooldown_remaining:.1f}s."
        elif self.ci_smooth >= CI_FOCUS_THRESHOLD:
            self._consecutive_focus_frames += 1
            if self._consecutive_focus_frames >= CI_FOCUS_CONSEC_REQUIRED:
                if not self._in_focus:
                    self._in_focus = True
                    self._focus_start = now
                self._message = f"Focus locked. Hold for {FOCUS_DWELL_SECONDS:.1f}s to launch."
        elif self.ci_smooth < CI_FOCUS_DROPOUT:
            self._reset_focus()
            self._message = "Focus dropped below reset threshold. Build concentration again."
        else:
            self._message = "Stay above threshold to begin dwell."

        if self._in_focus and self._focus_start > 0.0:
            if (now - self._focus_start) >= FOCUS_DWELL_SECONDS and cooldown_remaining <= 0.0:
                self._last_trigger_time = now
                self._message = f"Focus confirmed. Launching {self.current_app()['name']}."
                self._reset_focus()
                return True
        return False

    def _reset_focus(self) -> None:
        self._in_focus = False
        self._focus_start = 0.0
        self._consecutive_focus_frames = 0


class NeuroflowSimulationEngine:
    CHANNEL_NAMES = ["T3", "T4", "O1", "O2"]
    SAMPLE_RATE_HZ = 250.0

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._t = 0.0
        self._sdk_time = 0.0
        self._rand = random.Random(7)

    def generate_eeg_chunk(self, duration_s: float = 0.05) -> list[list[float]]:
        sample_count = max(1, int(round(self.SAMPLE_RATE_HZ * duration_s)))
        chunk: list[list[float]] = [[] for _ in self.CHANNEL_NAMES]
        focus_wave = (math.sin(self._t / 7.0) + 1.0) / 2.0
        for _ in range(sample_count):
            focus_wave = (math.sin(self._t / 7.0) + 1.0) / 2.0
            alpha_amp = 18e-6 * (1.2 - focus_wave)
            beta_amp = 11e-6 * (0.7 + focus_wave)
            theta_amp = 14e-6 * (1.1 - (focus_wave * 0.6))
            for ch_idx in range(len(self.CHANNEL_NAMES)):
                phase_offset = ch_idx * 0.35
                value = (
                    alpha_amp * math.sin((2.0 * math.pi * 10.0 * self._t) + phase_offset)
                    + beta_amp * math.sin((2.0 * math.pi * 19.0 * self._t) + (phase_offset * 1.7))
                    + theta_amp * math.sin((2.0 * math.pi * 6.0 * self._t) + (phase_offset * 0.6))
                    + (self._rand.uniform(-1.0, 1.0) * 3.2e-6)
                )
                chunk[ch_idx].append(value)
            self._t += 1.0 / self.SAMPLE_RATE_HZ
            self._sdk_time += 1.0 / self.SAMPLE_RATE_HZ
        return chunk

    def generate_band_powers(self) -> dict[str, float]:
        focus_wave = (math.sin(self._t / 7.0) + 1.0) / 2.0
        relax_wave = (math.cos(self._t / 9.0) + 1.0) / 2.0
        delta = 0.05 + (0.03 * relax_wave)
        theta = 0.16 + (0.18 * (1.0 - focus_wave))
        alpha = 0.18 + (0.15 * (1.0 - (focus_wave * 0.5)))
        smr = 0.05 + (0.04 * focus_wave)
        beta = 0.10 + (0.26 * focus_wave)
        return {
            "delta": delta,
            "theta": theta,
            "alpha": alpha,
            "smr": smr,
            "beta": beta,
        }

    def generate_resistances(self) -> dict[str, float]:
        return {"T3": 42_000.0, "T4": 61_000.0, "O1": 58_000.0, "O2": 73_000.0}

    def current_timestamp(self) -> float:
        return self._sdk_time


def threaded_launch(app: dict) -> None:
    def _run():
        try:
            launch_app(app)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
