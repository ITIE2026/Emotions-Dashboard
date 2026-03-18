from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from prosthetic_arm.arm_state import dominant_state_for_metrics


def normalized_metrics(attention: float, relaxation: float, raw: dict | None = None) -> dict:
    return {
        "attention": float(attention),
        "relaxation": float(relaxation),
        "dominant_state": dominant_state_for_metrics(float(attention), float(relaxation)),
        "raw": dict(raw or {}),
    }


class MetricSourceAdapter(QObject):
    status_changed = Signal(str)
    connection_changed = Signal(bool)
    metrics_changed = Signal(dict)
    resistance_changed = Signal(dict)
    raw_uv_changed = Signal(list)
    waves_changed = Signal(float, float)
    calibration_mode_changed = Signal(str)
    calibration_progress_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _set_connected(self, connected: bool, status: str | None = None) -> None:
        self._connected = bool(connected)
        self.connection_changed.emit(self._connected)
        if status:
            self.status_changed.emit(status)

    def shutdown(self) -> None:
        self._set_connected(False)
