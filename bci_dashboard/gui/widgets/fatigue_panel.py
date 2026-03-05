"""
FatiguePanel – shows fatigue percentage, growth rate, and break recommendation.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox
from PySide6.QtCore import Qt

from utils.helpers import fatigue_growth_label, recommendation_label


class FatiguePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        group = QGroupBox("Fatigue")
        vlayout = QVBoxLayout(self)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.addWidget(group)

        inner = QVBoxLayout(group)

        # Top row: fatigue % + growth badge
        top = QHBoxLayout()
        self._pct_label = QLabel("0%")
        self._pct_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #69F0AE;")
        self._growth_label = QLabel("Low")
        self._growth_label.setStyleSheet(
            "font-size: 12px; color: #fff; background: #4CAF50; "
            "border-radius: 8px; padding: 2px 10px;"
        )
        self._growth_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self._pct_label)
        top.addStretch()
        top.addWidget(self._growth_label)
        inner.addLayout(top)

        # Recommendation text
        self._rec_label = QLabel("")
        self._rec_label.setWordWrap(True)
        self._rec_label.setStyleSheet("font-size: 12px; color: #aaa;")
        inner.addWidget(self._rec_label)

        # Accumulated fatigue
        self._accum_label = QLabel("Accumulated: 0%")
        self._accum_label.setStyleSheet("font-size: 11px; color: #888;")
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
            f"font-size: 12px; color: #fff; background: {bg}; "
            f"border-radius: 8px; padding: 2px 10px;"
        )

        rec_text = recommendation_label(recommendation)
        self._rec_label.setText(rec_text)
        self._accum_label.setText(f"Accumulated: {accumulated:.1f}%")
