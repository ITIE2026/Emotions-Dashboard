"""
Low-latency EEG display filtering helpers.

The dashboard only needs a stable, readable trace. Heavy batch filtering adds
visible lag, so this module keeps a tiny streaming state per channel and
performs cheap baseline removal only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from utils.config import EEG_FILTER_SFREQ


@dataclass
class _ChannelState:
    baseline: float = 0.0
    initialized: bool = False


class EEGDisplayFilter:
    """Stateful display-only EEG filter optimized for low latency."""

    def __init__(
        self,
        *,
        loader=None,
        l_freq: float | None = None,
        h_freq: float | None = None,
        notch_freq: float | None = None,
        default_sample_rate: float = EEG_FILTER_SFREQ,
        context_seconds: float = 0.0,
        baseline_tau_seconds: float = 0.45,
        clip_sigma: float = 10.0,
    ):
        # Keep the historical constructor surface for compatibility even
        # though the low-latency path no longer loads MNE filters.
        del loader, l_freq, h_freq, notch_freq, context_seconds
        self._default_sample_rate = float(default_sample_rate)
        self._baseline_tau_seconds = float(max(baseline_tau_seconds, 0.05))
        self._clip_sigma = float(max(clip_sigma, 0.0))
        self._states: dict[str, _ChannelState] = {}
        self._runtime_error = None

    @property
    def available(self) -> bool:
        return True

    def reset(self):
        self._states.clear()
        self._runtime_error = None

    def status_text(self, enabled: bool) -> str:
        if not enabled:
            return "Off"
        if self._runtime_error is not None:
            return "Fallback"
        return "Fast"

    def apply(
        self,
        samples,
        sample_rate: float | None = None,
        channel_name: str = "__single__",
    ):
        """Compatibility wrapper used by tests and one-shot callers."""
        return self.process_chunk(channel_name, samples, sample_rate)

    def process_chunk(
        self,
        channel_name: str,
        samples,
        sample_rate: float | None = None,
    ) -> np.ndarray:
        data = np.asarray(samples, dtype=float)
        if data.size == 0:
            return data

        sfreq = self._coerce_sample_rate(sample_rate)
        state = self._states.get(channel_name)
        if state is None:
            state = _ChannelState()
            self._states[channel_name] = state

        try:
            filtered = self._remove_baseline(data, sfreq, state)
            if self._clip_sigma > 0.0:
                filtered = self._clip_outliers(filtered)
            self._runtime_error = None
            return filtered
        except Exception as exc:  # pragma: no cover - unexpected runtime path
            self._runtime_error = exc
            return data - float(np.median(data))

    def _remove_baseline(
        self,
        samples: np.ndarray,
        sfreq: float,
        state: _ChannelState,
    ) -> np.ndarray:
        if not state.initialized:
            state.baseline = float(np.median(samples))
            state.initialized = True

        alpha = np.exp(-1.0 / max(sfreq * self._baseline_tau_seconds, 1.0))
        baseline = float(state.baseline)
        filtered = np.empty_like(samples, dtype=float)
        for idx, sample in enumerate(samples):
            baseline = (alpha * baseline) + ((1.0 - alpha) * float(sample))
            filtered[idx] = float(sample) - baseline
        state.baseline = baseline
        return filtered

    def _clip_outliers(self, samples: np.ndarray) -> np.ndarray:
        if samples.size < 4:
            return samples
        median = float(np.median(samples))
        mad = float(np.median(np.abs(samples - median)))
        if not np.isfinite(mad) or mad <= 1e-9:
            return samples
        clip_limit = max(self._clip_sigma * 1.4826 * mad, 15.0)
        return np.clip(samples, -clip_limit, clip_limit)

    def _coerce_sample_rate(self, sample_rate: float | None) -> float:
        try:
            value = float(sample_rate)
        except (TypeError, ValueError):
            value = self._default_sample_rate
        if not np.isfinite(value) or value <= 0.0:
            return self._default_sample_rate
        return float(np.clip(value, 50.0, 1000.0))
