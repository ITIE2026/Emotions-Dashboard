"""
Application configuration constants and paths.
"""
import os
import sys

from utils.platform import native_lib_name

# ── Paths ──────────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(APP_DIR, "lib")
CAPSULE_DLL_PATH = os.path.join(LIB_DIR, native_lib_name("CapsuleClient"))
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
DEVICE_TYPE_OPTIONS = [
    ("Headband", 0),
    ("Headphones", 2),
]

WRITE_OPTION_SPECS = [
    ("cardio_metrics", "Cardio Metrics"),
    ("eeg", "EEG"),
    ("eeg_artifacts", "EEG Artifacts"),
    ("emotions", "Emotions"),
    ("export_to_csv", "Export to csv"),
    ("mems", "MEMS"),
    ("ppg", "PPG"),
    ("productivity", "Productivity"),
    ("productivity_baselines", "Productivity baselines"),
    ("raw_eeg", "Raw EEG"),
    ("resistances", "Resistances"),
    ("rhythms", "Rhythms"),
]
WRITE_OPTION_DEFAULTS = {key: True for key, _label in WRITE_OPTION_SPECS}
SESSION_JSON_NAME = "session.json"
SESSION_H5_NAME = "session.h5"
SESSION_METRICS_NAME = "metrics.csv"
SESSION_FILE_NAMES = {
    "json": SESSION_JSON_NAME,
    "h5": SESSION_H5_NAME,
    "metrics": SESSION_METRICS_NAME,
}

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
COLOR_DELTA = "#7986CB"           # indigo-light
COLOR_THETA = "#4DD0E1"           # cyan
COLOR_ALPHA = "#81C784"           # green
COLOR_SMR = "#AED581"             # light-green
COLOR_BETA = "#FFD54F"            # amber

# ── EEG frequency bands (Hz) ─────────────────────────────────────────
BAND_DELTA = (1.0, 4.0)
BAND_THETA = (4.0, 8.0)
BAND_ALPHA = (8.0, 12.0)
BAND_SMR   = (12.0, 15.0)
BAND_BETA  = (15.0, 30.0)

# ── Dark-theme palette ────────────────────────────────────────────────
BG_PRIMARY = "#131624"           # dark navy background
BG_CARD = "#1B1F36"              # card / panel surfaces
BG_CARD_HOVER = "#242842"        # card hover state
BG_NAV = "#0F1220"               # top menu bar
BG_INPUT = "#1E2238"             # text input / list backgrounds
BORDER_SUBTLE = "#2A2E48"        # subtle borders
TEXT_PRIMARY = "#E0E0E0"          # primary text
TEXT_SECONDARY = "#8890AA"       # secondary / muted text
TEXT_DISABLED = "#555555"         # disabled text
ACCENT_GREEN = "#69F0AE"         # accents / success
ACCENT_RED = "#EF5350"           # danger / heart rate
ACCENT_YELLOW = "#FFC107"        # warnings
ACCENT_CYAN = "#4DD0E1"          # section header: Rhythms
ACCENT_ORANGE = "#FFB74D"        # section header: Frequency Peaks
ACCENT_TEAL = "#26A69A"          # section header: State
ACCENT_PURPLE = "#B388FF"        # Focus metric
ACCENT_BLUE = "#64B5F6"          # Cognitive metric
ACCENT_PINK = "#F48FB1"          # Self-control metric

# ── Extended gradient / glow palette ──────────────────────────────────
GRAD_BG_START = "#0D0F1A"        # deep gradient background start
GRAD_BG_END = "#131624"          # gradient background end (same as BG_PRIMARY)
GLOW_GREEN = "rgba(105,240,174,0.30)"   # green card glow
GLOW_CYAN = "rgba(77,208,225,0.30)"    # cyan card glow
GLOW_PURPLE = "rgba(179,136,255,0.30)" # purple card glow
GLOW_BLUE = "rgba(100,181,246,0.30)"   # blue card glow
GLOW_RED = "rgba(239,83,80,0.30)"      # red card glow
GLOW_ORANGE = "rgba(255,183,77,0.30)"  # orange card glow

BG_GLASS = "rgba(27,31,54,0.85)"       # translucent card glass surface
BORDER_GLOW_GREEN = "rgba(105,240,174,0.45)"
BORDER_GLOW_CYAN = "rgba(77,208,225,0.45)"

# ── Typography scale ───────────────────────────────────────────────────
FONT_GIANT = 36   # hero numbers
FONT_H1 = 26      # screen titles
FONT_H2 = 20      # section headings
FONT_H3 = 16      # card headings
FONT_BODY = 13    # body text
FONT_SMALL = 11   # captions / labels
FONT_TINY = 10    # badges / timestamps

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
    "accumulated fatigue",
    "heart rate",
    "stress index",
    "alpha rhythm",
    "beta rhythm",
    "theta rhythm",
    "smr rhythm",
    "alpha peak hz",
    "beta peak hz",
    "theta peak hz",
]

CSV_FLUSH_INTERVAL_SEC = 30
CSV_AGGREGATE_PER_MINUTE = True        # match existing data format

# ── EEG display filter ─────────────────────────────────────────────────
EEG_FILTER_ENABLED_DEFAULT = True
EEG_FILTER_SFREQ = 250.0
EEG_FILTER_L_FREQ = 1.0
EEG_FILTER_H_FREQ = 40.0
EEG_FILTER_NOTCH_FREQ = 50.0

# ── Window ─────────────────────────────────────────────────────────────
WINDOW_TITLE = "BCI Dashboard"
WINDOW_MIN_WIDTH = 1280
WINDOW_MIN_HEIGHT = 720
