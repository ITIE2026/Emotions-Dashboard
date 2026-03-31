"""Graph window lifecycle, history, and refresh management mixin for MainWindow."""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Qt

from calibration.calibration_store import load_calibration
from gui.metric_graph_windows import (
    CognitiveStatesWindow,
    GRAPH_SPECS,
    TimeSeriesGraphWindow,
    graph_spec,
)

GRAPH_HISTORY_RETENTION_SEC = 15.0 * 60.0


class GraphWindowManagerMixin:
    """Mixin that manages metric graph windows, history deques, and reference lines."""

    def _show_metric_graph(self, graph_id: str):
        window = self._graph_windows.get(graph_id)
        if window is None:
            window = self._create_metric_graph_window(graph_id)
            if window is None:
                return
            self._graph_windows[graph_id] = window
        if not self.is_graph_active(graph_id):
            self.activate_graph(graph_id)
        else:
            self._refresh_metric_graph_window(graph_id)
        window.show()
        window.raise_()
        window.activateWindow()

    @staticmethod
    def _build_graph_history_store(graph_id: str):
        spec = graph_spec(graph_id)
        if spec is None:
            return {}
        return {series.key: deque() for series in spec.series}

    def _create_metric_graph_window(self, graph_id: str):
        if graph_id == "cognitive_states":
            window = CognitiveStatesWindow(self)
        else:
            spec = graph_spec(graph_id)
            if spec is None:
                return None
            window = TimeSeriesGraphWindow(spec, self)
        window.setAttribute(Qt.WA_DeleteOnClose, False)
        window.window_closed.connect(lambda gid=graph_id: self.deactivate_graph(gid))
        return window

    def is_graph_active(self, graph_id: str) -> bool:
        return graph_id in self._active_graphs

    def activate_graph(self, graph_id: str):
        if graph_id not in self._graph_windows:
            return
        self._active_graphs.add(graph_id)
        if self._bg_graph_session_start is not None and graph_id in self._bg_graph_histories:
            self._graph_session_starts[graph_id] = self._bg_graph_session_start
            self._graph_histories[graph_id] = {
                key: deque(pts) for key, pts in self._bg_graph_histories[graph_id].items()
            }
        else:
            self.reset_graph_history(graph_id)
            self._seed_graph_history(graph_id)
        self._refresh_metric_graph_window(graph_id)

    def deactivate_graph(self, graph_id: str):
        self._active_graphs.discard(graph_id)

    def reset_graph_history(self, graph_id: str):
        self._graph_session_starts[graph_id] = time.monotonic()
        self._graph_histories[graph_id] = self._build_graph_history_store(graph_id)

    def append_graph_point(self, graph_id: str, series_key: str, value, timestamp: float | None = None):
        ts = float(timestamp if timestamp is not None else time.monotonic())
        try:
            numeric = float(value) if value is not None else None
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None:
            self._append_bg_graph_point(graph_id, series_key, numeric, ts)
        if not self.is_graph_active(graph_id):
            return
        if numeric is None:
            return
        history_store = self._graph_histories.setdefault(
            graph_id,
            self._build_graph_history_store(graph_id),
        )
        if series_key not in history_store:
            return
        history = history_store[series_key]
        history.append((ts, numeric))

    def _seed_graph_history(self, graph_id: str):
        timestamp = time.monotonic()
        if graph_id == "frequency_peaks":
            self.append_graph_point(graph_id, "alpha_peak", self._latest_peak_freqs.get("alpha_peak"), timestamp)
            self.append_graph_point(graph_id, "beta_peak", self._latest_peak_freqs.get("beta_peak"), timestamp)
            self.append_graph_point(graph_id, "theta_peak", self._latest_peak_freqs.get("theta_peak"), timestamp)
            return

        graph_seed_values = {
            "concentration_index": ("concentrationScore", self._latest_prod.get("concentrationScore")),
            "relaxation_index": ("relaxationScore", self._latest_prod.get("relaxationScore")),
            "fatigue_score": ("fatigueScore", self._latest_prod.get("fatigueScore")),
            "reverse_fatigue_score": ("reverseFatigueScore", self._latest_prod.get("reverseFatigueScore")),
            "alpha_gravity": ("gravityScore", self._latest_prod.get("gravityScore")),
            "productivity_score": ("currentValue", self._latest_prod.get("currentValue")),
            "accumulated_fatigue": ("accumulatedFatigue", self._latest_prod.get("accumulatedFatigue")),
            "eeg_quality": ("eegQuality", self._latest_eeg_quality_value()),
        }
        series = graph_seed_values.get(graph_id)
        if series is not None:
            self.append_graph_point(graph_id, series[0], series[1], timestamp)

    def _refresh_metric_graph_window(self, graph_id: str):
        window = self._graph_windows.get(graph_id)
        if window is None or not self.is_graph_active(graph_id):
            return
        if graph_id == "cognitive_states":
            window.set_bar_values(
                {
                    "Attention": float(self._latest_emo.get("attention", 0.0) or 0.0),
                    "Relaxation": float(self._latest_emo.get("relaxation", 0.0) or 0.0),
                    "Cognitive Load": float(self._latest_emo.get("cognitiveLoad", 0.0) or 0.0),
                    "Cognitive Control": float(self._latest_emo.get("cognitiveControl", 0.0) or 0.0),
                }
            )
            return

        spec = graph_spec(graph_id)
        if spec is None:
            return
        history = {
            series.key: list(self._graph_histories.get(graph_id, {}).get(series.key, ()))
            for series in spec.series
        }
        window.set_session_start(self._graph_session_starts.get(graph_id, time.monotonic()))
        window.set_history_data(history, references=self._graph_references)

    def _refresh_all_metric_graphs(self):
        for graph_id in list(self._active_graphs):
            self._refresh_metric_graph_window(graph_id)

    def _reset_metric_graph_history(self):
        for graph_id in list(self._active_graphs):
            self.reset_graph_history(graph_id)
            self._seed_graph_history(graph_id)
        self._refresh_all_metric_graphs()

    def _load_saved_graph_references(self, serial: str):
        self._graph_references.clear()
        if not serial:
            self._refresh_all_metric_graphs()
            return
        try:
            data = load_calibration(serial) or {}
        except Exception:
            data = {}
        prod = data.get("prod_baselines") or {}
        if prod:
            self._graph_references.update(
                {
                    "gravityBaseline": float(prod.get("gravity")) if prod.get("gravity") is not None else None,
                    "productivityBaseline": float(prod.get("productivity")) if prod.get("productivity") is not None else None,
                    "fatigueBaseline": float(prod.get("fatigue")) if prod.get("fatigue") is not None else None,
                    "reverseFatigueBaseline": float(prod.get("reverseFatigue")) if prod.get("reverseFatigue") is not None else None,
                    "relaxationBaseline": float(prod.get("relaxation")) if prod.get("relaxation") is not None else None,
                    "concentrationBaseline": float(prod.get("concentration")) if prod.get("concentration") is not None else None,
                }
            )
        self._refresh_all_metric_graphs()

    def _update_graph_references_from_prod_baselines(self, data: dict):
        if not data:
            return
        mapping = {
            "gravity": "gravityBaseline",
            "productivity": "productivityBaseline",
            "fatigue": "fatigueBaseline",
            "reverseFatigue": "reverseFatigueBaseline",
            "relaxation": "relaxationBaseline",
            "concentration": "concentrationBaseline",
        }
        for source_key, target_key in mapping.items():
            value = data.get(source_key)
            if value is None:
                continue
            try:
                self._graph_references[target_key] = float(value)
            except (TypeError, ValueError):
                continue
        self._refresh_all_metric_graphs()

    def _update_graph_references_from_indexes(self, data: dict):
        if not data:
            return
        for key in (
            "gravityBaseline",
            "productivityBaseline",
            "fatigueBaseline",
            "reverseFatigueBaseline",
            "relaxationBaseline",
            "concentrationBaseline",
        ):
            value = data.get(key)
            if value is None:
                continue
            try:
                self._graph_references[key] = float(value)
            except (TypeError, ValueError):
                continue
        self._refresh_all_metric_graphs()

    def _append_eeg_quality_history(self, timestamp: float | None = None):
        self.append_graph_point(
            "eeg_quality",
            "eegQuality",
            self._latest_eeg_quality_value(),
            timestamp=timestamp,
        )

    def _latest_eeg_quality_value(self) -> float | None:
        has_prod_artifacts = bool(self._latest_indexes.get("hasArtifacts", False))
        has_physio_artifacts = bool(
            self._latest_physio.get("nfbArtifacts", False)
            or self._latest_physio.get("cardioArtifacts", False)
        )
        if not self._latest_indexes and not self._latest_physio:
            return None
        return 0.0 if (has_prod_artifacts or has_physio_artifacts) else 100.0

    # ── Background (session-long) graph history ──────────────────────────

    def _init_background_graph_histories(self):
        """Start recording all time-series graphs. Called on calibration done."""
        self._bg_graph_session_start = time.monotonic()
        self._bg_graph_histories = {}
        for graph_id, spec in GRAPH_SPECS.items():
            self._bg_graph_histories[graph_id] = {
                series.key: deque() for series in spec.series
            }

    def _clear_background_graph_histories(self):
        """Stop background recording and discard data. Called on disconnect."""
        self._bg_graph_histories = {}
        self._bg_graph_session_start = None

    def _append_bg_graph_point(self, graph_id: str, series_key: str, value: float, timestamp: float):
        """Unconditionally append a data point to the background store."""
        bg_store = self._bg_graph_histories.get(graph_id)
        if bg_store is None:
            return
        series_deque = bg_store.get(series_key)
        if series_deque is None:
            return
        series_deque.append((timestamp, value))
