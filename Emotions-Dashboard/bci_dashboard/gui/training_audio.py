"""
Adaptive soundtrack loading and mixing for EEG training modes.
"""
from __future__ import annotations

import math
import os
import struct
import tempfile
import wave
from typing import Any

from PySide6.QtCore import QUrl

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on local Qt multimedia install
    QSoundEffect = None


STEM_NAMES = ("base", "relax", "focus", "concentration", "sleep")
TRAINING_AUDIO_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets", "training_audio")

FALLBACK_BUNDLE_TONES = {
    "aurora_drift": (174.0, 208.0, 0.10),
    "velvet_horizon": (160.0, 196.0, 0.08),
    "ember_pulse": (148.0, 192.0, 0.18),
    "monsoon_strings": (146.0, 219.0, 0.11),
    "saffron_sunset": (164.0, 246.0, 0.09),
    "mehfil_glow": (156.0, 234.0, 0.12),
}

PROFILE_DEFAULTS = {
    "sleep": {"base": 0.34, "relax": 0.22, "focus": 0.04, "concentration": 0.03, "sleep": 0.26},
    "calm": {"base": 0.30, "relax": 0.26, "focus": 0.06, "concentration": 0.03, "sleep": 0.15},
    "focus": {"base": 0.22, "relax": 0.05, "focus": 0.25, "concentration": 0.24, "sleep": 0.04},
    "concentration": {"base": 0.18, "relax": 0.04, "focus": 0.26, "concentration": 0.30, "sleep": 0.02},
    "memory": {"base": 0.22, "relax": 0.13, "focus": 0.20, "concentration": 0.18, "sleep": 0.05},
    "arcade": {"base": 0.16, "relax": 0.07, "focus": 0.23, "concentration": 0.25, "sleep": 0.02},
    "music_flow": {"base": 0.22, "relax": 0.23, "focus": 0.15, "concentration": 0.11, "sleep": 0.15},
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
    band_powers: dict[str, float] | None = None,
) -> dict[str, float]:
    view_state = view_state or {}
    band_powers = band_powers or {}
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
    elif profile == "music_flow":
        band_values = {
            band: max(0.0, float(band_powers.get(band, 0.0)))
            for band in ("delta", "theta", "alpha", "smr", "beta")
        }
        band_total = sum(band_values.values())
        if band_total > 1e-9:
            normalized_bands = {band: value / band_total for band, value in band_values.items()}
        else:
            normalized_bands = {band: 0.0 for band in band_values}

        calm_drive = (
            (normalized_bands["delta"] * 1.02)
            + (normalized_bands["theta"] * 0.90)
            + (normalized_bands["alpha"] * 0.38)
        )
        focus_drive = (
            (normalized_bands["beta"] * 0.98)
            + (normalized_bands["smr"] * 0.86)
            + (normalized_bands["alpha"] * 0.24)
        )
        balance_drive = (normalized_bands["alpha"] * 0.75) + (steady_bias * 0.58)

        # Neuro Music Flow uses guitar-oriented stems: warm fingerstyle for calm,
        # brighter picked rhythm and melodic lead for concentration.
        base["relax"] += (calm_bias * 0.15) + (calm_drive * 0.22) + (serenity * 0.08) + (balance_drive * 0.03)
        base["sleep"] += (
            (normalized_bands["delta"] * 0.20)
            + (normalized_bands["theta"] * 0.12)
            + (serenity * 0.06)
            + (max(0.0, calm_bias - focus_bias) * 0.04)
        )
        base["focus"] += (focus_bias * 0.12) + (focus_drive * 0.17) + (balance_drive * 0.04)
        base["concentration"] += (
            (focus_bias * 0.13)
            + (normalized_bands["beta"] * 0.21)
            + (normalized_bands["smr"] * 0.11)
            + (restlessness * 0.02)
        )
        base["base"] += (normalized_bands["alpha"] * 0.10) + (balance_drive * 0.06) + (steady_bias * 0.03)

        if calm_drive > focus_drive:
            calm_margin = calm_drive - focus_drive
            base["focus"] *= 1.0 - min(0.26, calm_margin * 0.30)
            base["concentration"] *= 1.0 - min(0.32, calm_margin * 0.35)
        elif focus_drive > calm_drive:
            focus_margin = focus_drive - calm_drive
            base["relax"] *= 1.0 - min(0.20, focus_margin * 0.22)
            base["sleep"] *= 1.0 - min(0.24, focus_margin * 0.28)

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
    def __init__(
        self,
        parent,
        audio_dir: str,
        soundtracks: dict[str, dict[str, Any]],
        fallback_dir: str | None = None,
    ):
        self._parent = parent
        self._audio_dir = audio_dir
        self._soundtracks = soundtracks
        self._fallback_dir = fallback_dir or os.path.join(tempfile.gettempdir(), "bci_training_audio_fallback")
        self._effects: dict[str, QSoundEffect] = {}
        self._current_soundtrack: str | None = None
        self._enabled = QSoundEffect is not None

    @property
    def available(self) -> bool:
        return self._enabled

    def ensure_assets(self) -> None:
        for soundtrack_name in self._soundtracks:
            self.resolve_soundtrack_paths(soundtrack_name)

    def resolve_soundtrack_paths(self, soundtrack_name: str) -> dict[str, str]:
        spec = self._soundtracks.get(soundtrack_name, {})
        bundle = str(spec.get("bundle", soundtrack_name.lower().replace(" ", "_")))
        resolved = {}
        for stem in STEM_NAMES:
            resolved[stem] = self._resolve_stem_path(bundle, stem)
        return resolved

    def _resolve_stem_path(self, bundle: str, stem: str) -> str:
        packaged = self._packaged_stem_path(bundle, stem)
        if os.path.exists(packaged):
            return packaged
        os.makedirs(os.path.join(self._fallback_dir, bundle), exist_ok=True)
        fallback = self._fallback_stem_path(bundle, stem)
        if not os.path.exists(fallback):
            tone = FALLBACK_BUNDLE_TONES.get(bundle, FALLBACK_BUNDLE_TONES["aurora_drift"])
            self._write_stem(fallback, tone, stem)
        return fallback

    def _packaged_stem_path(self, bundle: str, stem: str) -> str:
        return os.path.join(self._audio_dir, bundle, f"{stem}.wav")

    def _fallback_stem_path(self, bundle: str, stem: str) -> str:
        return os.path.join(self._fallback_dir, bundle, f"{stem}.wav")

    def _current_stem_bias(self) -> dict[str, float]:
        if not self._current_soundtrack:
            return {}
        spec = self._soundtracks.get(self._current_soundtrack, {})
        return dict(spec.get("stem_bias", {}))

    def _apply_stem_bias(self, stem: str, volume: float) -> float:
        bias = float(self._current_stem_bias().get(stem, 1.0))
        return min(STEM_LIMITS[stem], max(0.0, volume * bias))

    def start(self, soundtrack_name: str) -> None:
        if not self._enabled or soundtrack_name not in self._soundtracks:
            return
        stem_paths = self.resolve_soundtrack_paths(soundtrack_name)
        if self._current_soundtrack != soundtrack_name:
            self.stop()
            self._current_soundtrack = soundtrack_name
            for stem in STEM_NAMES:
                effect = QSoundEffect(self._parent)
                # Some PySide6 builds expose Loop.Infinite but still bind int.
                effect.setLoopCount(int(QSoundEffect.Loop.Infinite.value))
                effect.setVolume(0.0)
                effect.setSource(QUrl.fromLocalFile(stem_paths[stem]))
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
        band_powers: dict[str, float] | None = None,
    ) -> None:
        if not self._enabled or not self._effects:
            return
        mix = compute_adaptive_mix(profile, conc_delta, relax_delta, view_state, band_powers=band_powers)
        for stem, effect in self._effects.items():
            effect.setVolume(self._apply_stem_bias(stem, mix.get(stem, 0.0)))

    def stop(self) -> None:
        for effect in self._effects.values():
            effect.stop()
        self._effects.clear()
        self._current_soundtrack = None

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
