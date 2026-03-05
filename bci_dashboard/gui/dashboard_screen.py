"""
DashboardScreen – the main monitoring view.

Layout:
  ┌─────────────────────────────────┐
  │  Metric cards (3 primary)       │
  │  Real-time graph                │
  │  Secondary metric cards row     │
  │  Fatigue panel                  │
  │  Heart rate section             │
  └─────────────────────────────────┘
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout,
    QScrollArea,
)
from PySide6.QtCore import Qt, QTimer

from gui.widgets.metric_card import MetricCard
from gui.widgets.fatigue_panel import FatiguePanel
from gui.realtime_graph import RealtimeGraph
from utils.config import GRAPH_UPDATE_INTERVAL_MS, COLOR_FOCUS, COLOR_COGNITIVE, COLOR_RELAXATION


class DashboardScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions = {}
        self._latest_productivity = {}
        self._latest_cardio = {}
        self._latest_indexes = {}
        self._latest_physio = {}
        self._build_ui()

        # Graph update timer (1 Hz)
        self._graph_timer = QTimer(self)
        self._graph_timer.setInterval(GRAPH_UPDATE_INTERVAL_MS)
        self._graph_timer.timeout.connect(self._push_graph_data)

    # ── UI construction ───────────────────────────────────────────────
    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Primary metric cards ──────────────────────────────────────
        cards_row = QHBoxLayout()
        self._card_cognitive = MetricCard("Cognitive Score", COLOR_COGNITIVE)
        self._card_focus = MetricCard("Focus", COLOR_FOCUS)
        self._card_relaxation = MetricCard("Relaxation", COLOR_RELAXATION)
        cards_row.addWidget(self._card_cognitive)
        cards_row.addWidget(self._card_focus)
        cards_row.addWidget(self._card_relaxation)
        layout.addLayout(cards_row)

        # ── Real-time graph ───────────────────────────────────────────
        self._graph = RealtimeGraph()
        self._graph.setMinimumHeight(260)
        layout.addWidget(self._graph)

        # ── Secondary metrics ─────────────────────────────────────────
        sec_group = QGroupBox("Details")
        sec_grid = QGridLayout(sec_group)
        self._card_chill = MetricCard("Calmness", "#81C784")
        self._card_stress = MetricCard("Tension", "#FF8A65")
        self._card_self_ctrl = MetricCard("Self-control", "#4DD0E1")
        self._card_anger = MetricCard("Anger", "#E57373")
        self._card_concentration = MetricCard("Concentration", "#FFD54F")
        sec_grid.addWidget(self._card_chill, 0, 0)
        sec_grid.addWidget(self._card_stress, 0, 1)
        sec_grid.addWidget(self._card_self_ctrl, 0, 2)
        sec_grid.addWidget(self._card_anger, 1, 0)
        sec_grid.addWidget(self._card_concentration, 1, 1)
        layout.addWidget(sec_group)

        # ── Fatigue panel ─────────────────────────────────────────────
        self._fatigue_panel = FatiguePanel()
        layout.addWidget(self._fatigue_panel)

        # ── Heart rate ────────────────────────────────────────────────
        hr_group = QGroupBox("Heart Rate")
        hr_layout = QHBoxLayout(hr_group)
        self._hr_label = QLabel("-- bpm")
        self._hr_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #EF5350;")
        self._hr_label.setAlignment(Qt.AlignCenter)
        hr_layout.addWidget(self._hr_label)
        self._stress_idx_label = QLabel("Stress Index: --")
        self._stress_idx_label.setStyleSheet("font-size: 13px; color: #aaa;")
        self._stress_idx_label.setAlignment(Qt.AlignCenter)
        hr_layout.addWidget(self._stress_idx_label)
        layout.addWidget(hr_group)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Data input slots ──────────────────────────────────────────────
    def on_emotions(self, data: dict):
        try:
            self._latest_emotions = data
            self._card_focus.set_value(data.get("focus", 0))
            self._card_chill.set_value(data.get("chill", 0))
            self._card_stress.set_value(data.get("stress", 0))
            self._card_anger.set_value(data.get("anger", 0))
            self._card_self_ctrl.set_value(data.get("selfControl", 0))
        except Exception:
            pass

    def on_productivity(self, data: dict):
        try:
            self._latest_productivity = data
            self._card_cognitive.set_value(data.get("productivityScore", 0))
            self._card_relaxation.set_value(data.get("relaxationScore", 0))
            self._card_concentration.set_value(data.get("concentrationScore", 0), suffix="")
            self._fatigue_panel.update_data(
                fatigue_score=data.get("fatigueScore", 0),
                growth_rate=data.get("fatigueGrowthRate", 0),
                accumulated=data.get("accumulatedFatigue", 0),
                recommendation=self._latest_indexes.get("relaxation_recommendation", 0),
            )
        except Exception:
            pass

    def on_indexes(self, data: dict):
        try:
            self._latest_indexes = data
        except Exception:
            pass

    def on_cardio(self, data: dict):
        self._latest_cardio = data
        hr = data.get("heartRate", 0)
        self._hr_label.setText(f"{hr:.0f} bpm")
        si = data.get("stressIndex", 0)
        self._stress_idx_label.setText(f"Stress Index: {si:.1f}")

    def on_physio_states(self, data: dict):
        """Receive PhysiologicalStates probabilities – use to enrich cards."""
        self._latest_physio = data

    # ── Graph updates ─────────────────────────────────────────────────
    def start_graph(self):
        self._graph.clear()
        self._graph_timer.start()

    def stop_graph(self):
        self._graph_timer.stop()

    def _push_graph_data(self):
        focus = self._latest_emotions.get("focus", 0)
        cognitive = self._latest_productivity.get("productivityScore", 0)
        relaxation = self._latest_productivity.get("relaxationScore", 0)
        self._graph.add_data(focus, cognitive, relaxation)
