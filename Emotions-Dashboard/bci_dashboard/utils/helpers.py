"""
Utility helpers: formatting, colour mapping, clamping, EEG band power.
"""
import numpy as np
import math
from datetime import datetime
from utils.config import (
    RESIST_GOOD_THRESHOLD, RESIST_WARN_THRESHOLD,
    BAND_DELTA, BAND_THETA, BAND_ALPHA, BAND_SMR, BAND_BETA,
)


def timestamp_now() -> str:
    """Return ISO-style timestamp for the current moment."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp_filename() -> str:
    """Return a filename-safe timestamp: session_YYYYMMDD_HHMM."""
    return datetime.now().strftime("session_%Y%m%d_%H%M")


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def resist_color(value_ohms: float) -> str:
    """Return hex colour string for a resistance value."""
    if value_ohms is None or not math.isfinite(float(value_ohms)):
        return "#F44336"
    if value_ohms < RESIST_GOOD_THRESHOLD:
        return "#4CAF50"   # green
    elif value_ohms < RESIST_WARN_THRESHOLD:
        return "#FFC107"   # yellow/amber
    else:
        return "#F44336"   # red


def resist_label(value_ohms: float) -> str:
    """Human-readable resistance (kΩ)."""
    if value_ohms is None or not math.isfinite(float(value_ohms)):
        return "--"
    return f"{value_ohms / 1000:.0f} kΩ"


def format_percent(value: float) -> str:
    return f"{clamp(value):.0f}%"


def fatigue_growth_label(rate_enum_value: int) -> str:
    labels = {0: "None", 1: "Low", 2: "Medium", 3: "High"}
    return labels.get(rate_enum_value, "Unknown")


def recommendation_label(rec_value: int) -> str:
    labels = {
        0: "",
        1: "Try to stay more involved",
        2: "Take a moment to relax",
        3: "Slight fatigue — consider a short break",
        4: "Severe fatigue — take a break now",
        5: "Chronic fatigue detected — rest recommended",
    }
    return labels.get(rec_value, "")


def stress_label(stress_value: int) -> str:
    labels = {0: "No Stress", 1: "Anxiety", 2: "Stress"}
    return labels.get(stress_value, "Unknown")


# ── EEG band-power helpers ────────────────────────────────────────────

def compute_band_powers(freqs, psd_values):
    """Compute average power in each EEG band from PSD data.

    Args:
        freqs: 1-D array of frequency bin centres (Hz).
        psd_values: 1-D array of power values (µV²) matching *freqs*.

    Returns:
        dict with keys 'delta', 'theta', 'alpha', 'smr', 'beta' → float.
    """
    freqs = np.asarray(freqs, dtype=float)
    psd_values = np.asarray(psd_values, dtype=float)
    bands = {
        "delta": BAND_DELTA,
        "theta": BAND_THETA,
        "alpha": BAND_ALPHA,
        "smr":   BAND_SMR,
        "beta":  BAND_BETA,
    }
    result = {}
    for name, (lo, hi) in bands.items():
        mask = (freqs >= lo) & (freqs < hi)
        result[name] = float(np.mean(psd_values[mask])) if mask.any() else 0.0
    return result


def compute_peak_frequencies(freqs, psd_values):
    """Find peak frequency in Alpha, Beta, and Theta bands.

    Returns:
        dict with keys 'alpha_peak', 'beta_peak', 'theta_peak' → float Hz.
    """
    freqs = np.asarray(freqs, dtype=float)
    psd_values = np.asarray(psd_values, dtype=float)
    peaks = {}
    for name, (lo, hi) in [("alpha_peak", BAND_ALPHA),
                             ("beta_peak", BAND_BETA),
                             ("theta_peak", BAND_THETA)]:
        mask = (freqs >= lo) & (freqs < hi)
        if mask.any():
            sub_psd = psd_values[mask]
            sub_freq = freqs[mask]
            peaks[name] = float(sub_freq[np.argmax(sub_psd)])
        else:
            peaks[name] = 0.0
    return peaks


def resolve_hemisphere_channel_groups(channel_count: int) -> tuple[list[int], list[int]]:
    """Map PSD channels into left/right hemisphere groups.

    Current defaults:
    - 4 channels: O1/T3 = left, T4/O2 = right
    - 2 channels: first = left, second = right
    - 1 channel: mirror to both sides
    - other counts: split the list in half as a safe fallback
    """
    try:
        count = int(channel_count)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return [], []
    if count == 1:
        return [0], [0]
    if count == 2:
        return [0], [1]
    if count >= 4:
        return [0, 1], [2, 3]
    split = int(math.ceil(count / 2.0))
    left = list(range(split))
    right = list(range(split, count))
    if not right:
        right = [left[-1]]
    return left, right


def compute_hemisphere_band_powers(freqs, channel_psd_values):
    """Compute left/right hemisphere band powers from per-channel PSD arrays."""
    freqs = np.asarray(freqs, dtype=float)
    channel_psd_values = np.asarray(channel_psd_values, dtype=float)
    if freqs.size == 0 or channel_psd_values.size == 0:
        return {}, {}

    if channel_psd_values.ndim == 1:
        channel_psd_values = channel_psd_values.reshape(1, -1)

    width = min(freqs.size, channel_psd_values.shape[1])
    if width <= 0:
        return {}, {}

    freqs = freqs[:width]
    channel_psd_values = channel_psd_values[:, :width]
    left_indices, right_indices = resolve_hemisphere_channel_groups(channel_psd_values.shape[0])

    def _mean_power(indices):
        valid = [index for index in indices if 0 <= index < channel_psd_values.shape[0]]
        if not valid:
            return np.zeros_like(freqs, dtype=float)
        return np.mean(channel_psd_values[valid], axis=0)

    left_power = _mean_power(left_indices)
    right_power = _mean_power(right_indices)
    return compute_band_powers(freqs, left_power), compute_band_powers(freqs, right_power)
