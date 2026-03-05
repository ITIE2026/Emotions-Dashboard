"""
Utility helpers: formatting, colour mapping, clamping.
"""
from datetime import datetime
from utils.config import RESIST_GOOD_THRESHOLD, RESIST_WARN_THRESHOLD


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
    if value_ohms < RESIST_GOOD_THRESHOLD:
        return "#4CAF50"   # green
    elif value_ohms < RESIST_WARN_THRESHOLD:
        return "#FFC107"   # yellow/amber
    else:
        return "#F44336"   # red


def resist_label(value_ohms: float) -> str:
    """Human-readable resistance (kΩ)."""
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
