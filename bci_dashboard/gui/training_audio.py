"""
Adaptive soundtrack generation and mixing for EEG training modes.
"""
from __future__ import annotations

import math
import os
import struct
import wave
from typing import Any

from PySide6.QtCore import QUrl

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on local Qt multimedia install
    QSoundEffect = None


STEM_NAMES = ("base", "relax", "focus", "concentration", "sleep")

PROFILE_DEFAULTS = {
    "sleep": {"base": 0.34, "relax": 0.22, "focus": 0.04, "concentration": 0.03, "sleep": 0.26},
    "calm": {"base": 0.30, "relax": 0.26, "focus": 0.06, "concentration": 0.03, "sleep": 0.15},
    "focus": {"base": 0.22, "relax": 0.05, "focus": 0.25, "concentration": 0.24, "sleep": 0.04},
    "concentration": {"base": 0.18, "relax": 0.04, "focus": 0.26, "concentration": 0.30, "sleep": 0.02},
    "memory": {"base": 0.22, "relax": 0.13, "focus": 0.20, "concentration": 0.18, "sleep": 0.05},
    "arcade": {"base": 0.16, "relax": 0.07, "focus": 0.23, "concentration": 0.25, "sleep": 0.02},
}

STEM_LIMITS = {
    "base": 0.28,
    "relax": 0.24,
    "focus": 0.21,
    "concentration": 0.18,
    "sleep": 0.25,
}


def compute_adaptive_mix(
    profile: str,
    conc_delta: float,
    relax_delta: float,
    view_state: dict[str, Any] | None = None,
) -> dict[str, float]:
    view_state = view_state or {}
    base = dict(PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS["focus"]))

    calm_bias = max(0.0, min(1.0, (relax_delta - conc_delta + 3.0) / 6.0))
    focus_bias = max(0.0, min(1.0, (conc_delta - relax_delta + 3.0) / 6.0))
    steady_bias = max(0.0, 1.0 - min(1.0, abs(conc_delta - relax_delta) / 3.0))
    serenity = max(0.0, min(1.0, float(view_state.get("serenity", 60.0)) / 100.0))
    restlessness = max(0.0, min(1.0, float(view_state.get("restlessness", 20.0)) / 100.0))
    scene = str(view_state.get("music_scene", profile))
    music_bias = max(-1.0, min(1.0, float(view_state.get("music_bias", relax_delta - conc_delta))))

    if profile in {"sleep", "calm"}:
        base["relax"] += (calm_bias * 0.16) + (steady_bias * 0.05)
        base["sleep"] += (serenity * 0.20) + (max(0.0, music_bias) * 0.08)
        base["focus"] *= 1.0 - (0.55 * calm_bias)
        base["concentration"] *= 1.0 - (0.70 * calm_bias)
        if scene == "sleep_descent":
            base["sleep"] += 0.08
            base["focus"] *= 0.72
            base["concentration"] *= 0.65
        elif scene == "body_drift":
            base["relax"] += 0.05
    elif profile in {"focus", "concentration"}:
        base["focus"] += (focus_bias * 0.12) + (steady_bias * 0.05)
        base["concentration"] += (focus_bias * 0.15)
        base["relax"] *= 1.0 - (0.45 * focus_bias)
        base["sleep"] *= 1.0 - (0.80 * focus_bias)
    elif profile == "memory":
        base["focus"] += focus_bias * 0.10
        base["concentration"] += focus_bias * 0.08
        base["relax"] += calm_bias * 0.10
        base["sleep"] *= 1.0 - (0.35 * focus_bias)
    elif profile == "arcade":
        base["focus"] += focus_bias * 0.10
        base["concentration"] += focus_bias * 0.14
        base["relax"] += calm_bias * 0.06
        base["sleep"] *= 1.0 - (0.85 * max(focus_bias, steady_bias * 0.3))

    if restlessness > 0.45:
        base["focus"] += restlessness * 0.04
        base["concentration"] += restlessness * 0.03
        base["sleep"] *= 1.0 - (restlessness * 0.55)

    total = sum(max(0.0, value) for value in base.values()) or 1.0
    normalized: dict[str, float] = {}
    for stem in STEM_NAMES:
        normalized[stem] = min(STEM_LIMITS[stem], max(0.0, base[stem] / total))
    return normalized


class AdaptiveMusicEngine:
    def __init__(self, parent, audio_dir: str, soundtracks: dict[str, dict[str, Any]]):
        self._parent = parent
        self._audio_dir = audio_dir
        self._soundtracks = soundtracks
        self._effects: dict[str, QSoundEffect] = {}
        self._current_soundtrack: str | None = None
        self._enabled = QSoundEffect is not None

    @property
    def available(self) -> bool:
        return self._enabled

    def ensure_assets(self) -> None:
        os.makedirs(self._audio_dir, exist_ok=True)
        for soundtrack_name, spec in self._soundtracks.items():
            for stem in STEM_NAMES:
                path = self._stem_path(soundtrack_name, stem)
                if not os.path.exists(path):
                    self._write_stem(path, spec["tone"], stem)

    def start(self, soundtrack_name: str) -> None:
        if not self._enabled or soundtrack_name not in self._soundtracks:
            return
        self.ensure_assets()
        if self._current_soundtrack != soundtrack_name:
            self.stop()
            self._current_soundtrack = soundtrack_name
            for stem in STEM_NAMES:
                effect = QSoundEffect(self._parent)
                # Some PySide6 builds expose Loop.Infinite but still bind int.
                effect.setLoopCount(int(QSoundEffect.Loop.Infinite.value))
                effect.setVolume(0.0)
                effect.setSource(QUrl.fromLocalFile(self._stem_path(soundtrack_name, stem)))
                effect.play()
                self._effects[stem] = effect
        else:
            for effect in self._effects.values():
                if not effect.isPlaying():
                    effect.play()

    def update_mix(
        self,
        profile: str,
        conc_delta: float,
        relax_delta: float,
        view_state: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled or not self._effects:
            return
        mix = compute_adaptive_mix(profile, conc_delta, relax_delta, view_state)
        for stem, effect in self._effects.items():
            effect.setVolume(mix.get(stem, 0.0))

    def stop(self) -> None:
        for effect in self._effects.values():
            effect.stop()
        self._effects.clear()
        self._current_soundtrack = None

    def _stem_path(self, soundtrack_name: str, stem: str) -> str:
        safe_name = soundtrack_name.lower().replace(" ", "_")
        return os.path.join(self._audio_dir, f"{safe_name}_{stem}.wav")

    def _write_stem(self, path: str, tone: tuple[float, float, float], stem: str) -> None:
        carrier, accent, depth = tone
        stem_carrier, stem_accent, stem_depth, harmonic, pulse = self._stem_recipe(
            carrier, accent, depth, stem
        )
        sample_rate = 22050
        duration = 6
        frames = bytearray()
        for index in range(sample_rate * duration):
            t = index / sample_rate
            envelope = 0.58 + 0.42 * math.sin(2 * math.pi * stem_depth * t)
            layer = (
                0.32 * math.sin(2 * math.pi * stem_carrier * t)
                + 0.18 * math.sin(2 * math.pi * stem_accent * t)
                + 0.12 * math.sin(2 * math.pi * harmonic * t)
            )
            sample = layer * envelope * (0.74 + 0.26 * math.sin(2 * math.pi * pulse * t))
            sample = max(-1.0, min(1.0, sample))
            frames.extend(struct.pack("<h", int(sample * 32767)))
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(frames))

    def _stem_recipe(
        self,
        carrier: float,
        accent: float,
        depth: float,
        stem: str,
    ) -> tuple[float, float, float, float, float]:
        if stem == "base":
            return carrier, accent * 0.72, max(0.05, depth * 0.5), carrier / 2.0, 0.07
        if stem == "relax":
            return carrier * 0.78, accent * 0.58, max(0.04, depth * 0.35), carrier / 3.0, 0.05
        if stem == "focus":
            return carrier * 1.10, accent * 1.03, max(0.10, depth * 1.8), carrier * 1.42, 0.16
        if stem == "concentration":
            return carrier * 1.18, accent * 1.22, max(0.12, depth * 2.2), accent * 1.55, 0.20
        return carrier * 0.52, accent * 0.44, max(0.03, depth * 0.22), carrier / 4.0, 0.03
