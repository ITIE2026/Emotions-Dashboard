"""
ElectrodeTable – per-channel status table showing electrode name,
artifact flag, average µV, and a horizontal signal-strength bar.
Matches the Capsule reference app's electrode table.
"""
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QGridLayout,
)
from PySide6.QtCore import Qt

from utils.config import BG_CARD, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


_CHANNEL_COLORS = {
    "O1-T3": "#4FC3F7",
    "O2-T4": "#81C784",
}


class ElectrodeTable(QWidget):
    """
    Feed with:
      - ``update_eeg(eeg_timed_data)``  – computes average µV
      - ``update_artifacts(artifacts)``  – sets artifact flags
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._avg_uv = {}
        self._has_artifacts = {}
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)

        # Header row
        header = QHBoxLayout()
        for text, width in [("Electrode", 80), ("Artifacts", 60),
                             ("Average µV", 80), ("EEG Signal", 0)]:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: bold; color: {TEXT_SECONDARY}; "
                f"background: transparent; border: none; padding: 2px;"
            )
            if width:
                lbl.setFixedWidth(width)
            header.addWidget(lbl, stretch=(0 if width else 1))
        layout.addLayout(header)

        # Channel rows
        self._rows = {}
        for ch_name, colour in _CHANNEL_COLORS.items():
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent; border: none;")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(4)

            name_lbl = QLabel(ch_name)
            name_lbl.setFixedWidth(80)
            name_lbl.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {colour}; "
                f"background: {BORDER_SUBTLE}; border: none; border-radius: 4px; "
                f"padding: 4px;"
            )

            art_lbl = QLabel("No")
            art_lbl.setFixedWidth(60)
            art_lbl.setAlignment(Qt.AlignCenter)
            art_lbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_PRIMARY}; background: transparent; border: none;"
            )

            avg_lbl = QLabel("0.000")
            avg_lbl.setFixedWidth(80)
            avg_lbl.setAlignment(Qt.AlignCenter)
            avg_lbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_PRIMARY}; background: transparent; border: none;"
            )

            bar = QProgressBar()
            bar.setRange(0, 200)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setStyleSheet(
                f"QProgressBar {{ background: #1a1e30; border: none; border-radius: 4px; }}"
                f"QProgressBar::chunk {{ background: {colour}; border-radius: 4px; }}"
            )

            row.addWidget(name_lbl)
            row.addWidget(art_lbl)
            row.addWidget(avg_lbl)
            row.addWidget(bar, stretch=1)

            self._rows[ch_name] = {
                "widget": row_widget,
                "art_lbl": art_lbl,
                "avg_lbl": avg_lbl,
                "bar": bar,
            }
            layout.addWidget(row_widget)

    _CH_NAMES = {0: "O1-T3", 1: "O2-T4"}

    def update_eeg(self, eeg_timed_data):
        """Compute average µV from latest EEG packet."""
        try:
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()
            for ch_idx in range(n_channels):
                ch_name = self._CH_NAMES.get(ch_idx)
                if ch_name not in self._rows:
                    continue
                vals = []
                for s_idx in range(n_samples):
                    vals.append(abs(float(
                        eeg_timed_data.get_raw_value(ch_idx, s_idx)
                    )))
                if vals:
                    avg = float(np.mean(vals))
                    self._avg_uv[ch_name] = avg
                    self._rows[ch_name]["avg_lbl"].setText(f"{avg:.3f}")
                    bar_val = min(int(avg), 200)
                    self._rows[ch_name]["bar"].setValue(bar_val)
        except Exception:
            pass

    def update_artifacts(self, artifacts):
        """Update artifact flags from EEGArtifacts object."""
        try:
            n = artifacts.get_channels_count()
            for ch_idx in range(n):
                ch_name = self._CH_NAMES.get(ch_idx)
                if ch_name not in self._rows:
                    continue
                has_art = bool(artifacts.get_artifacts_by_channel(ch_idx))
                self._has_artifacts[ch_name] = has_art
                label = "Yes" if has_art else "No"
                colour = "#EF5350" if has_art else "#69F0AE"
                self._rows[ch_name]["art_lbl"].setText(label)
                self._rows[ch_name]["art_lbl"].setStyleSheet(
                    f"font-size: 11px; color: {colour}; background: transparent; border: none;"
                )
        except Exception:
            pass
