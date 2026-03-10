"""
DashboardScreen – the main monitoring view.
Dark-themed layout matching the Mind Tracker BCI app:

  ┌─────────────────────────────────┐
  │  Primary metric cards (3)       │
  │  Details section (5 cards)      │
  │  Fatigue panel                  │
  │  Heart rate section             │
  │  Save CSV row                  │
  └─────────────────────────────────┘
"""
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QScrollArea, QPushButton,
)
from PySide6.QtCore import Qt

from gui.widgets.metric_card import MetricCard
from gui.widgets.fatigue_panel import FatiguePanel
from utils.config import (
    COLOR_FOCUS, COLOR_COGNITIVE, COLOR_RELAXATION,
    BG_CARD, BORDER_SUBTLE, TEXT_SECONDARY, ACCENT_RED,
)
from utils.config import SESSION_DIR


def _section_label(text: str) -> QLabel:
    """Create a small section header label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 13px; font-weight: bold; color: {TEXT_SECONDARY}; "
        f"padding-top: 8px; padding-bottom: 2px;"
    )
    return lbl


class DashboardScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions = {}
        self._latest_productivity = {}
        self._latest_cardio = {}
        self._latest_indexes = {}
        self._latest_physio = {}
        self._session_file: str | None = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────
    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(10)

        # ── Primary metric cards ──────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._card_cognitive = MetricCard("Cognitive Score", COLOR_COGNITIVE)
        self._card_focus = MetricCard("Focus", COLOR_FOCUS)
        self._card_relaxation = MetricCard("Relaxation", COLOR_RELAXATION)
        cards_row.addWidget(self._card_cognitive)
        cards_row.addWidget(self._card_focus)
        cards_row.addWidget(self._card_relaxation)
        layout.addLayout(cards_row)

        # ── Details section ───────────────────────────────────────────
        layout.addWidget(_section_label("Details"))

        details_grid = QGridLayout()
        details_grid.setSpacing(8)
        self._card_chill = MetricCard("Calmness", "#81C784")
        self._card_stress = MetricCard("Tension", "#FF8A65")
        self._card_self_ctrl = MetricCard("Self-control", "#4DD0E1")
        self._card_anger = MetricCard("Anger", "#E57373")
        self._card_concentration = MetricCard("Concentration", "#FFD54F")
        details_grid.addWidget(self._card_chill, 0, 0)
        details_grid.addWidget(self._card_stress, 0, 1)
        details_grid.addWidget(self._card_self_ctrl, 0, 2)
        details_grid.addWidget(self._card_anger, 1, 0)
        details_grid.addWidget(self._card_concentration, 1, 1)
        layout.addLayout(details_grid)

        # ── Fatigue panel ─────────────────────────────────────────────
        self._fatigue_panel = FatiguePanel()
        layout.addWidget(self._fatigue_panel)

        # ── Heart rate card ───────────────────────────────────────────
        hr_card = QWidget()
        hr_card.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )
        hr_layout = QHBoxLayout(hr_card)
        hr_layout.setContentsMargins(16, 12, 16, 12)

        hr_icon = QLabel("♥")
        hr_icon.setStyleSheet(
            f"font-size: 28px; color: {ACCENT_RED}; background: transparent; border: none;"
        )
        hr_layout.addWidget(hr_icon)

        hr_text_col = QVBoxLayout()
        hr_text_col.setSpacing(2)
        self._hr_label = QLabel("-- bpm")
        self._hr_label.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {ACCENT_RED}; "
            f"background: transparent; border: none;"
        )
        self._stress_idx_label = QLabel("Stress Index: --")
        self._stress_idx_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        hr_text_col.addWidget(self._hr_label)
        hr_text_col.addWidget(self._stress_idx_label)
        hr_layout.addLayout(hr_text_col)
        hr_layout.addStretch()
        layout.addWidget(hr_card)

        # ── Save CSV row ──────────────────────────────────────────────
        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 4, 0, 0)

        self._save_info = QLabel("💾 Session data is auto-saved as CSV")
        self._save_info.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        save_row.addWidget(self._save_info, stretch=1)

        self._open_folder_btn = QPushButton("📂 Open Sessions Folder")
        self._open_folder_btn.setCursor(Qt.PointingHandCursor)
        self._open_folder_btn.setStyleSheet(
            "QPushButton { background: #1E3A2F; color: #69F0AE; border: 1px solid #69F0AE;"
            " border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #264D3B; }"
            "QPushButton:pressed { background: #1A2E25; }"
        )
        self._open_folder_btn.clicked.connect(self._open_sessions_folder)
        save_row.addWidget(self._open_folder_btn)

        layout.addLayout(save_row)
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

    # ── Session file info ─────────────────────────────────────────────
    def set_session_file(self, path: str):
        """Called by MainWindow when a session CSV file is opened."""
        self._session_file = path
        fname = os.path.basename(path) if path else ""
        self._save_info.setText(f"💾 Saving: {fname}")

    def _open_sessions_folder(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        os.startfile(SESSION_DIR)

