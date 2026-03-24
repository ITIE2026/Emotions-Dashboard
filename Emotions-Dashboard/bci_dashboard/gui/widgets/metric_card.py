"""
MetricCard – glass-style dark card showing a percentage metric
with a coloured label and thin progress indicator.
Matches the Mind Tracker BCI monitoring screen style.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from utils.config import BG_CARD, BORDER_SUBTLE, TEXT_SECONDARY


class MetricCard(QWidget):
    """
    Displays a single metric in a dark rounded card:
        ┌──────────────────┐
        │     67%          │  ← large coloured value
        │  ━━━━━━━━━━━━━   │  ← thin progress bar
        │     Focus        │  ← small muted label
        └──────────────────┘
    """

    def __init__(self, title: str = "", colour: str = "#69F0AE", parent=None):
        super().__init__(parent)
        self._colour = colour
        self._build_ui(title)

    def _build_ui(self, title: str):
        self.setStyleSheet(
            f"MetricCard {{ background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self._value_label = QLabel("--")
        self._value_label.setAlignment(Qt.AlignCenter)
        self._value_label.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: {self._colour}; "
            f"background: transparent; border: none;"
        )

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background-color: #2A2A2A; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background-color: {self._colour}; border-radius: 2px; }}"
        )

        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )

        layout.addWidget(self._value_label)
        layout.addWidget(self._bar)
        layout.addWidget(self._title_label)

    def set_value(self, value: float, suffix: str = "%"):
        """Update the displayed value (0–100 expected)."""
        clamped = int(min(100, max(0, value)))
        if suffix == "%":
            display = f"{value:.0f}{suffix}"
        else:
            display = f"{value:.0f}"
        self._bar.setValue(clamped)
        self._value_label.setText(display)

    def set_title(self, title: str):
        self._title_label.setText(title)
