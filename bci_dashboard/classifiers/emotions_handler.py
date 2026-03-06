"""
EmotionsHandler – wraps the Capsule Emotions classifier.

Emits a Qt signal every time Emotions_States are received:
  focus, chill, stress, anger, selfControl  (all 0–100 floats)

Values from the SDK are raw floats (typically 0–1 but can exceed 1).
We apply *100, clamp to [0,100], and smooth with EMA to prevent jitter.
"""
import sys
import logging
from PySide6.QtCore import QObject, Signal

from utils.config import CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Emotions import Emotions, Emotions_States  # noqa: E402

log = logging.getLogger(__name__)

_ALPHA = 0.3   # EMA smoothing factor (higher = more responsive)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _ema(prev: float | None, raw: float, alpha: float = _ALPHA) -> float:
    if prev is None:
        return raw
    return prev + alpha * (raw - prev)


class EmotionsHandler(QObject):
    """Create **after** Device, **before** device.start()."""

    states_updated = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, device, lib, parent=None):
        super().__init__(parent)
        self._emotions = Emotions(device, lib)
        self._emotions.set_on_states_update(self._on_states)
        self._emotions.set_on_error(self._on_error)

        # EMA state per emotion (None = first sample)
        self._ema = {
            "focus": None, "chill": None, "stress": None,
            "anger": None, "selfControl": None,
        }

    # ── Capsule callbacks ─────────────────────────────────────────────
    def _on_states(self, emotions_obj, states: Emotions_States):
        try:
            # Emotions SDK values are already in 0–100 range – use directly.
            raw = {
                "focus":       _clamp(float(states.focus)),
                "chill":       _clamp(float(states.chill)),
                "stress":      _clamp(float(states.stress)),
                "anger":       _clamp(float(states.anger)),
                "selfControl": _clamp(float(states.selfControl)),
            }

            data = {}
            for key, val in raw.items():
                self._ema[key] = _ema(self._ema[key], val)
                data[key] = round(self._ema[key], 1)

            data["timestamp"] = int(states.timestampMilli)

            log.debug(
                "Emotions → focus=%.1f%% chill=%.1f%% stress=%.1f%%",
                data["focus"], data["chill"], data["stress"],
            )
            self.states_updated.emit(data)
        except Exception as exc:
            log.error("EmotionsHandler._on_states error: %s", exc)
            self.error_occurred.emit(str(exc))

    def _on_error(self, emotions_obj, msg):
        cleaned = msg
        if isinstance(cleaned, bytes):
            cleaned = cleaned.decode('utf-8', errors='replace')
        elif isinstance(cleaned, str) and cleaned.startswith("b'"):
            cleaned = cleaned[2:-1]
        self.error_occurred.emit(cleaned)
