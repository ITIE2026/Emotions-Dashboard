"""
TrackingScreen – session summary / timeline view.

Shows overall session parameters and timeline-style breakdown
of productivity.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QGridLayout, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer
from datetime import datetime

from gui.widgets.metric_card import MetricCard


class TrackingScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_start = None

        # Cache latest data – UI only updated at 1 Hz to prevent lag
        self._latest_emotions: dict = {}
        self._latest_productivity: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}
        self._dirty = False

        self._build_ui()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._flush_ui)

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Title
        title = QLabel("Tracking")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        # Session info
        self._session_label = QLabel("Session: --")
        self._session_label.setStyleSheet("font-size: 13px; color: #aaa;")
        layout.addWidget(self._session_label)

        # ── Overall score section ─────────────────────────────────────
        score_group = QGroupBox("Productivity")
        score_layout = QVBoxLayout(score_group)

        self._overall_label = QLabel("Cognitive Score")
        self._overall_label.setStyleSheet("font-size: 14px;")
        self._overall_label.setAlignment(Qt.AlignCenter)
        score_layout.addWidget(self._overall_label)

        self._overall_value = QLabel("--%")
        self._overall_value.setStyleSheet("font-size: 48px; font-weight: bold; color: #69F0AE;")
        self._overall_value.setAlignment(Qt.AlignCenter)
        score_layout.addWidget(self._overall_value)

        # Sub cards
        cards_row = QHBoxLayout()
        self._t_cognitive = MetricCard("Cognitive", "#64B5F6")
        self._t_focus = MetricCard("Focus", "#B388FF")
        self._t_concentration = MetricCard("Concentration", "#FFD54F")
        cards_row.addWidget(self._t_cognitive)
        cards_row.addWidget(self._t_focus)
        cards_row.addWidget(self._t_concentration)
        score_layout.addLayout(cards_row)
        layout.addWidget(score_group)

        # ── Parameters grid ───────────────────────────────────────────
        params_group = QGroupBox("Parameters")
        params_grid = QGridLayout(params_group)
        self._p_cards = {}
        names = [
            ("cognitive", "Cognitive", "#64B5F6"),
            ("focus", "Focus", "#B388FF"),
            ("calmness", "Calmness", "#81C784"),
            ("tension", "Tension", "#FF8A65"),
            ("self_ctrl", "Self-c.", "#4DD0E1"),
            ("anger", "Anger", "#E57373"),
            ("relax_idx", "Relax.", "#69F0AE"),
            ("conc_idx", "Conc.", "#FFD54F"),
        ]
        for i, (key, label, colour) in enumerate(names):
            card = MetricCard(label, colour)
            params_grid.addWidget(card, i // 4, i % 4)
            self._p_cards[key] = card
        layout.addWidget(params_group)

        # Fatigue summary
        self._fatigue_label = QLabel("Fatigue: --%")
        self._fatigue_label.setStyleSheet("font-size: 14px; color: #aaa;")
        layout.addWidget(self._fatigue_label)

        # Session duration
        self._duration_label = QLabel("Duration: 0 min")
        self._duration_label.setStyleSheet("font-size: 13px; color: #888;")
        layout.addWidget(self._duration_label)

        layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────────────
    def start_session(self):
        self._session_start = datetime.now()
        self._session_label.setText(
            f"Session: {self._session_start.strftime('%H:%M – ')}…"
        )
        self._ui_timer.start()

    def update_data(
        self,
        emotions: dict | None = None,
        productivity: dict | None = None,
        cardio: dict | None = None,
        physio: dict | None = None,
    ):
        """Cache latest data; UI is flushed by the 1-Hz timer."""
        if emotions is not None:
            self._latest_emotions = emotions
        if productivity is not None:
            self._latest_productivity = productivity
        if cardio is not None:
            self._latest_cardio = cardio
        if physio is not None:
            self._latest_physio = physio
        self._dirty = True

    def _flush_ui(self):
        """Actually update all widget labels – called at 1 Hz."""
        if not self._dirty:
            # still update duration label each second
            if self._session_start:
                elapsed = (datetime.now() - self._session_start).total_seconds()
                mins = int(elapsed // 60)
                self._duration_label.setText(f"Duration: {mins} min")
            return
        self._dirty = False

        e = self._latest_emotions
        p = self._latest_productivity

        cog = p.get("productivityScore", 0)
        self._overall_value.setText(f"{cog:.0f}%")
        self._t_cognitive.set_value(cog)
        self._t_focus.set_value(e.get("focus", 0))
        self._t_concentration.set_value(p.get("concentrationScore", 0), suffix="")

        self._p_cards["cognitive"].set_value(cog)
        self._p_cards["focus"].set_value(e.get("focus", 0))
        self._p_cards["calmness"].set_value(e.get("chill", 0))
        self._p_cards["tension"].set_value(e.get("stress", 0))
        self._p_cards["self_ctrl"].set_value(e.get("selfControl", 0))
        self._p_cards["anger"].set_value(e.get("anger", 0))
        self._p_cards["relax_idx"].set_value(p.get("relaxationScore", 0))
        self._p_cards["conc_idx"].set_value(p.get("concentrationScore", 0), suffix="")

        self._fatigue_label.setText(f"Fatigue: {p.get('fatigueScore', 0):.0f}%")

        if self._session_start:
            elapsed = (datetime.now() - self._session_start).total_seconds()
            mins = int(elapsed // 60)
            self._duration_label.setText(f"Duration: {mins} min")
