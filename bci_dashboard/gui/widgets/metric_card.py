"""
MetricCard – a reusable widget showing a percentage metric
with a coloured label and a small progress indicator.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt


class MetricCard(QWidget):
    """
    Displays a single metric:
        ┌──────────────┐
        │   67 %       │
        │  ━━━━━━━━━   │
        │  Focus       │
        └──────────────┘
    """

    def __init__(self, title: str = "", colour: str = "#69F0AE", parent=None):
        super().__init__(parent)
        self._colour = colour
        self._build_ui(title)

    def _build_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        self._value_label = QLabel("--")
        self._value_label.setAlignment(Qt.AlignCenter)
        self._value_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {self._colour};"
        )

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: #333;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {self._colour};
                border-radius: 3px;
            }}
            """
        )

        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet("font-size: 12px; color: #aaa;")

        layout.addWidget(self._value_label)
        layout.addWidget(self._bar)
        layout.addWidget(self._title_label)

    def set_value(self, value: float, suffix: str = "%"):
        """Update the displayed value (0–100 expected for %)."""
        if suffix == "%":
            display = f"{value:.0f}{suffix}"
            self._bar.setValue(int(min(100, max(0, value))))
        else:
            display = f"{value:.2f}"
            self._bar.setValue(int(min(100, max(0, value * 100))))
        self._value_label.setText(display)

    def set_title(self, title: str):
        self._title_label.setText(title)
