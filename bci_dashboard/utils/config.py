"""
Application configuration constants and paths.
"""
import os
import sys

# ── Paths ──────────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(APP_DIR, "lib")
CAPSULE_DLL_PATH = os.path.join(LIB_DIR, "CapsuleClient.dll")
CAPSULE_SDK_DIR = os.path.join(APP_DIR, "capsule_sdk")
LOG_DIR = os.path.join(APP_DIR, "logs")
SESSION_DIR = os.path.join(APP_DIR, "sessions")
CALIBRATION_DIR = os.path.join(APP_DIR, "calibration_data")

# Ensure directories exist
for d in (LOG_DIR, SESSION_DIR, CALIBRATION_DIR):
    os.makedirs(d, exist_ok=True)

# ── Device ─────────────────────────────────────────────────────────────
DEVICE_SEARCH_TIMEOUT_SEC = 15
BIPOLAR_CHANNELS = True

# ── Resistance thresholds (Ohms) ──────────────────────────────────────
RESIST_GOOD_THRESHOLD = 500_000        # < 500 kΩ → green
RESIST_WARN_THRESHOLD = 1_000_000      # < 1 MΩ   → yellow, else red

# ── Calibration ────────────────────────────────────────────────────────
CALIBRATION_EYES_CLOSED_SEC = 30       # Quick NFB calibration duration

# ── Streaming / update intervals ──────────────────────────────────────
CAPSULE_UPDATE_INTERVAL_MS = 20        # QTimer interval for locator.update()
GRAPH_UPDATE_INTERVAL_MS = 1000        # Graph refresh rate (1 Hz)
STATUS_POLL_INTERVAL_MS = 5000         # Battery / connection poll
RECONNECT_INTERVAL_MS = 5000           # Retry interval on disconnect
MAX_RECONNECT_ATTEMPTS = 10

# ── Graph ──────────────────────────────────────────────────────────────
GRAPH_1MIN_POINTS = 60
GRAPH_15MIN_POINTS = 900

# Graph colours
COLOR_FOCUS = "#B388FF"           # purple
COLOR_COGNITIVE = "#64B5F6"       # blue
COLOR_RELAXATION = "#69F0AE"      # green

# ── Dark-theme palette ────────────────────────────────────────────────
BG_PRIMARY = "#0D0D0D"           # main background (pure black)
BG_CARD = "#1A1A1A"              # card / panel surfaces
BG_CARD_HOVER = "#222222"        # card hover state
BG_NAV = "#111111"               # bottom nav bar
BG_INPUT = "#1E1E1E"             # text input / list backgrounds
BORDER_SUBTLE = "#2A2A2A"        # subtle borders
TEXT_PRIMARY = "#FFFFFF"          # primary text
TEXT_SECONDARY = "#AAAAAA"       # secondary / muted text
TEXT_DISABLED = "#555555"         # disabled text
ACCENT_GREEN = "#69F0AE"         # accents / success
ACCENT_RED = "#EF5350"           # danger / heart rate
ACCENT_YELLOW = "#FFC107"        # warnings

# ── CSV ────────────────────────────────────────────────────────────────
CSV_COLUMNS = [
    "time",
    "cognitive score",
    "focus",
    "chill",
    "stress",
    "self-control",
    "anger",
    "relaxation index",
    "concentration index",
    "fatigue score",
    "reverse fatigue",
    "alpha gravity",
    "heart rate",
]

CSV_FLUSH_INTERVAL_SEC = 30
CSV_AGGREGATE_PER_MINUTE = True        # match existing data format

# ── Window ─────────────────────────────────────────────────────────────
WINDOW_TITLE = "BCI Dashboard"
WINDOW_MIN_WIDTH = 450
WINDOW_MIN_HEIGHT = 800
