from __future__ import annotations

from prosthetic_arm.sources import MetricSourceAdapter, normalized_metrics


class CapsuleMetricAdapter(MetricSourceAdapter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_changed.emit("Using live Capsule productivity metrics.")

    def ingest_productivity(self, data: dict | None) -> None:
        payload = data or {}
        metrics = normalized_metrics(
            payload.get("concentrationScore", 0.0),
            payload.get("relaxationScore", 0.0),
            raw=payload,
        )
        if not self.is_connected:
            self._set_connected(True, "Using live Capsule productivity metrics.")
        self.metrics_changed.emit(metrics)

    def reset(self) -> None:
        self._set_connected(False, "Capsule metrics idle.")
