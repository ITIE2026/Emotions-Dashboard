"""
FatiguePanel – dark-themed card showing fatigue %, growth rate badge,
and break recommendation.  Matches Mind Tracker BCI style.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from utils.helpers import fatigue_growth_label, recommendation_label
from utils.config import BG_CARD, BORDER_SUBTLE, TEXT_SECONDARY, ACCENT_GREEN


class FatiguePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(
            f"FatiguePanel {{ background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px; }}"
        )
        inner = QVBoxLayout(self)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(6)

        # Section header
        header = QLabel("Fatigue")
        header.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        inner.addWidget(header)

        # Top row: fatigue % + growth badge
        top = QHBoxLayout()
        self._pct_label = QLabel("0%")
        self._pct_label.setStyleSheet(
            f"font-size: 32px; font-weight: bold; color: {ACCENT_GREEN}; background: transparent; border: none;"
        )
        self._growth_label = QLabel("Low")
        self._growth_label.setStyleSheet(
            "font-size: 11px; color: #fff; background: #4CAF50; "
            "border-radius: 10px; padding: 3px 12px;"
        )
        self._growth_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self._pct_label)
        top.addStretch()
        top.addWidget(self._growth_label, alignment=Qt.AlignVCenter)
        inner.addLayout(top)

        # Recommendation text
        self._rec_label = QLabel("")
        self._rec_label.setWordWrap(True)
        self._rec_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        inner.addWidget(self._rec_label)

        # Accumulated fatigue
        self._accum_label = QLabel("Accumulated: 0%")
        self._accum_label.setStyleSheet(
            "font-size: 11px; color: #666; background: transparent; border: none;"
        )
        inner.addWidget(self._accum_label)

    def update_data(
        self,
        fatigue_score: float = 0,
        growth_rate: int = 0,
        accumulated: float = 0,
        recommendation: int = 0,
    ):
        self._pct_label.setText(f"{fatigue_score:.0f}%")
        growth_text = fatigue_growth_label(growth_rate)
        self._growth_label.setText(growth_text)

        # Colour badge by severity
        colours = {0: "#4CAF50", 1: "#4CAF50", 2: "#FFC107", 3: "#F44336"}
        bg = colours.get(growth_rate, "#4CAF50")
        self._growth_label.setStyleSheet(
            f"font-size: 11px; color: #fff; background: {bg}; "
            f"border-radius: 10px; padding: 3px 12px;"
        )

        rec_text = recommendation_label(recommendation)
        self._rec_label.setText(rec_text)
        self._accum_label.setText(f"Accumulated: {accumulated:.1f}%")

