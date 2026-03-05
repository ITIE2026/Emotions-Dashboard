"""
CalibrationScreen – progress UI for the 3-stage calibration.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton,
)
from PySide6.QtCore import Qt


class CalibrationScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        self._title = QLabel("Calibration")
        self._title.setStyleSheet("font-size: 24px; font-weight: bold;")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        layout.addSpacing(20)

        # Instruction
        self._instruction = QLabel("Preparing…")
        self._instruction.setStyleSheet("font-size: 18px;")
        self._instruction.setAlignment(Qt.AlignCenter)
        self._instruction.setWordWrap(True)
        layout.addWidget(self._instruction)

        layout.addSpacing(30)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMinimumHeight(24)
        self._progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #555;
                border-radius: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #69F0AE;
                border-radius: 8px;
            }
            """
        )
        layout.addWidget(self._progress)

        # Percentage & time label
        self._detail = QLabel("0%")
        self._detail.setStyleSheet("font-size: 14px; color: #aaa;")
        self._detail.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._detail)

        layout.addSpacing(20)

        # Stage label
        self._stage_label = QLabel("Stage 1 / 3")
        self._stage_label.setStyleSheet("font-size: 13px; color: #888;")
        self._stage_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._stage_label)

        layout.addStretch()

        # iAPF result (shown after NFB stage)
        self._result_label = QLabel("")
        self._result_label.setStyleSheet("font-size: 14px; color: #69F0AE;")
        self._result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._result_label)

        # Cancel
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMinimumHeight(36)
        layout.addWidget(self._cancel_btn)

    # ── Public API ────────────────────────────────────────────────────
    def set_stage(self, stage_num: int, description: str):
        self._stage_label.setText(f"Stage {stage_num} / 3")
        self._instruction.setText(description)

    def set_progress(self, fraction: float):
        pct = int(fraction * 100)
        self._progress.setValue(pct)
        self._detail.setText(f"{pct}%")

    def set_result_text(self, text: str):
        self._result_label.setText(text)

    @property
    def cancel_button(self):
        return self._cancel_btn
