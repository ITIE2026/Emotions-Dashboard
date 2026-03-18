"""
Pure helpers for raw-data dashboard metrics.

These functions keep the raw PPG and band-history math testable without Qt.
"""
from __future__ import annotations

import time
from typing import Iterable

import numpy as np


BAND_KEYS = ("delta", "theta", "alpha", "smr", "beta")


def aggregate_band_history(
    history,
    window_seconds: float,
    now: float | None = None,
) -> dict | None:
    """Average band powers from the requested rolling window.

    Returns ``None`` when the requested window has no samples so callers can
    distinguish "no data yet" from a real all-zero aggregate.
    """
    if window_seconds <= 0:
        return None

    now_ts = float(now if now is not None else time.time())
    relevant = [
        bands
        for ts, bands in history
        if (now_ts - float(ts)) <= window_seconds
    ]
    if not relevant:
        return None

    return {
        band: float(np.mean([float(entry.get(band, 0.0)) for entry in relevant]))
        for band in BAND_KEYS
    }


def derive_ppg_metrics(samples, timestamps, session_state=None) -> dict:
    """Derive rolling PPG metrics from raw samples.

    Returns a metrics dictionary plus an updated ``state`` field that callers
    should store and pass back on the next invocation.
    """
    state = {
        "rr_total": list((session_state or {}).get("rr_total", [])),
        "quality_history": list((session_state or {}).get("quality_history", [])),
    }
    metrics = {
        "perfusion": None,
        "signal_quality_avg": None,
        "rr_mean": None,
        "sdnn": None,
        "cv": None,
        "mo": None,
        "amo": None,
        "mxdmn": None,
        "mxdmn_total": None,
        "state": state,
    }

    samples_arr = np.asarray(samples, dtype=float)
    timestamps_arr = np.asarray(timestamps, dtype=float)
    if (
        samples_arr.size < 8
        or timestamps_arr.size != samples_arr.size
        or np.allclose(samples_arr, samples_arr[0])
    ):
        return metrics

    order = np.argsort(timestamps_arr)
    samples_arr = samples_arr[order]
    timestamps_arr = timestamps_arr[order]

    unique_mask = np.ones(samples_arr.size, dtype=bool)
    unique_mask[1:] = np.diff(timestamps_arr) > 0
    samples_arr = samples_arr[unique_mask]
    timestamps_arr = timestamps_arr[unique_mask]
    if samples_arr.size < 8:
        return metrics

    centered = samples_arr - float(np.mean(samples_arr))
    dc_level = float(np.mean(np.abs(samples_arr)))
    ac_span = float(np.percentile(centered, 95) - np.percentile(centered, 5))
    if dc_level > 1e-9:
        metrics["perfusion"] = abs(ac_span / (2.0 * dc_level))
    else:
        metrics["perfusion"] = 0.0

    smoothed = _smooth_signal(centered)
    peaks = _find_ppg_peaks(smoothed, timestamps_arr)
    rr_intervals = np.diff(timestamps_arr[peaks]) if peaks.size >= 2 else np.asarray([], dtype=float)
    valid_rr = rr_intervals[(rr_intervals >= 0.35) & (rr_intervals <= 1.6)]

    state["rr_total"].extend(float(v) for v in valid_rr.tolist())
    if len(state["rr_total"]) > 2048:
        state["rr_total"] = state["rr_total"][-2048:]

    quality = _estimate_ppg_quality(
        perfusion=metrics["perfusion"] or 0.0,
        valid_rr_count=int(valid_rr.size),
        peak_count=int(peaks.size),
        signal=smoothed,
    )
    state["quality_history"].append((float(timestamps_arr[-1]), quality))
    state["quality_history"] = [
        (ts, q)
        for ts, q in state["quality_history"]
        if (float(timestamps_arr[-1]) - float(ts)) <= 30.0
    ]
    if state["quality_history"]:
        metrics["signal_quality_avg"] = float(
            np.mean([float(q) for _, q in state["quality_history"]])
        )

    if valid_rr.size >= 2:
        rr_mean = float(np.mean(valid_rr))
        sdnn = float(np.std(valid_rr, ddof=0))
        metrics["rr_mean"] = rr_mean
        metrics["sdnn"] = sdnn
        metrics["cv"] = (100.0 * sdnn / rr_mean) if rr_mean > 1e-9 else 0.0
        metrics["mxdmn"] = float(np.max(valid_rr) - np.min(valid_rr))

        hist_bins = np.arange(float(np.min(valid_rr)), float(np.max(valid_rr)) + 0.05, 0.05)
        if hist_bins.size < 2:
            hist_bins = np.array([rr_mean - 0.025, rr_mean + 0.025], dtype=float)
        hist, bins = np.histogram(valid_rr, bins=hist_bins)
        mode_idx = int(np.argmax(hist))
        metrics["mo"] = float((bins[mode_idx] + bins[mode_idx + 1]) / 2.0)
        metrics["amo"] = (100.0 * float(hist[mode_idx]) / float(valid_rr.size)) if valid_rr.size else 0.0

    total_rr = np.asarray(state["rr_total"], dtype=float)
    if total_rr.size >= 2:
        metrics["mxdmn_total"] = float(np.max(total_rr) - np.min(total_rr))

    return metrics


def _smooth_signal(signal: np.ndarray) -> np.ndarray:
    if signal.size < 5:
        return signal
    window = min(7, signal.size if signal.size % 2 == 1 else signal.size - 1)
    window = max(window, 3)
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(signal, kernel, mode="same")


def _find_ppg_peaks(signal: np.ndarray, timestamps: np.ndarray) -> np.ndarray:
    if signal.size < 3:
        return np.asarray([], dtype=int)

    diffs = np.diff(timestamps)
    positive_diffs = diffs[diffs > 0]
    if positive_diffs.size == 0:
        return np.asarray([], dtype=int)

    sample_period = float(np.median(positive_diffs))
    min_distance = max(1, int(round(0.35 / sample_period)))
    threshold = max(
        float(np.mean(signal) + 0.35 * np.std(signal)),
        float(np.percentile(signal, 70)),
    )

    peaks: list[int] = []
    for idx in range(1, signal.size - 1):
        if signal[idx] < threshold:
            continue
        if signal[idx] < signal[idx - 1] or signal[idx] <= signal[idx + 1]:
            continue

        if not peaks or (idx - peaks[-1]) >= min_distance:
            peaks.append(idx)
            continue

        if signal[idx] > signal[peaks[-1]]:
            peaks[-1] = idx

    return np.asarray(peaks, dtype=int)


def _estimate_ppg_quality(
    perfusion: float,
    valid_rr_count: int,
    peak_count: int,
    signal: np.ndarray,
) -> float:
    amplitude_factor = float(np.clip(perfusion / 0.12, 0.0, 1.0))
    beat_factor = float(np.clip(valid_rr_count / max(1, peak_count - 1), 0.0, 1.0))
    noise_floor = float(np.std(np.diff(signal))) if signal.size >= 3 else 0.0
    stability_factor = 1.0 / (1.0 + max(0.0, noise_floor) * 4.0)
    return float(np.clip((0.45 * amplitude_factor) + (0.35 * beat_factor) + (0.20 * stability_factor), 0.0, 1.0))
