"""
EmotionsHandler – wraps the Capsule Emotions classifier.

Emits a Qt signal every time Emotions_States are received:
  focus, chill, stress, anger, selfControl  (all 0–100 floats)
"""
import sys
from PySide6.QtCore import QObject, Signal

from utils.config import CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Emotions import Emotions, Emotions_States  # noqa: E402


class EmotionsHandler(QObject):
    """Create **after** Device, **before** device.start()."""

    states_updated = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, device, lib, parent=None):
        super().__init__(parent)
        self._emotions = Emotions(device, lib)
        self._emotions.set_on_states_update(self._on_states)
        self._emotions.set_on_error(self._on_error)

    # ── Capsule callbacks ─────────────────────────────────────────────
    def _on_states(self, emotions_obj, states: Emotions_States):
        try:
            self.states_updated.emit({
                "focus": float(states.focus),
                "chill": float(states.chill),
                "stress": float(states.stress),
                "anger": float(states.anger),
                "selfControl": float(states.selfControl),
                "timestamp": int(states.timestampMilli),
            })
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def _on_error(self, emotions_obj, msg):
        cleaned = msg
        if isinstance(cleaned, bytes):
            cleaned = cleaned.decode('utf-8', errors='replace')
        elif isinstance(cleaned, str) and cleaned.startswith("b'"):
            cleaned = cleaned[2:-1]
        self.error_occurred.emit(cleaned)
