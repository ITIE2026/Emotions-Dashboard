from __future__ import annotations

from dataclasses import dataclass
import time


OPEN_STATE = "OPEN"
NEUTRAL_STATE = "NEUTRAL"
CLOSED_STATE = "CLOSED"

STATE_TO_COMMAND = {
    OPEN_STATE: "O",
    NEUTRAL_STATE: "N",
    CLOSED_STATE: "C",
}

STATE_TO_LABEL = {
    OPEN_STATE: "Open",
    NEUTRAL_STATE: "Neutral",
    CLOSED_STATE: "Closed",
}


@dataclass(frozen=True)
class ArmStateSnapshot:
    state: str
    candidate_state: str
    attention: float
    relaxation: float
    stable_ms: int
    debounce_ratio: float
    command: str


def state_label(state: str) -> str:
    return STATE_TO_LABEL.get(state.upper(), STATE_TO_LABEL[OPEN_STATE])


def dominant_state_for_metrics(attention: float, relaxation: float) -> str:
    delta = attention - relaxation
    if delta >= 6.0:
        return "Focused"
    if delta <= -6.0:
        return "Relaxed"
    return "Balanced"


class ArmStateEngine:
    def __init__(
        self,
        *,
        close_threshold: float = 50.0,
        open_threshold: float = 30.0,
        debounce_ms: int = 600,
    ):
        self.close_threshold = close_threshold
        self.open_threshold = open_threshold
        self.debounce_ms = debounce_ms
        self.reset()

    def reset(self) -> None:
        self._state = OPEN_STATE
        self._pending_state = OPEN_STATE
        self._pending_since = 0

    def candidate_state(self, attention: float) -> str:
        if attention >= self.close_threshold:
            return CLOSED_STATE
        if attention < self.open_threshold:
            return OPEN_STATE
        return NEUTRAL_STATE

    def update(
        self,
        attention: float,
        relaxation: float,
        *,
        now_ms: int | None = None,
    ) -> ArmStateSnapshot:
        if now_ms is None:
            now_ms = int(time.monotonic() * 1000)

        candidate = self.candidate_state(attention)
        stable_ms = 0

        if candidate == self._state:
            self._pending_state = candidate
            self._pending_since = now_ms
            stable_ms = self.debounce_ms
        else:
            if candidate != self._pending_state:
                self._pending_state = candidate
                self._pending_since = now_ms
            else:
                stable_ms = max(0, now_ms - self._pending_since)
                if stable_ms >= self.debounce_ms:
                    self._state = candidate
                    stable_ms = self.debounce_ms

        ratio = max(0.0, min(1.0, stable_ms / max(1, self.debounce_ms)))
        return ArmStateSnapshot(
            state=self._state,
            candidate_state=candidate,
            attention=float(attention),
            relaxation=float(relaxation),
            stable_ms=int(stable_ms),
            debounce_ratio=ratio,
            command=STATE_TO_COMMAND[self._state],
        )
