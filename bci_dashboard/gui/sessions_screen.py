"""
SessionsScreen – browse past session CSV files.

Accessible via File → Sessions Data.
Lists sessions from the sessions/ directory, shows summary statistics,
and allows opening/exporting.
"""
import os
from datetime import datetime

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QGroupBox, QGridLayout,
    QScrollArea, QMessageBox,
)
from PySide6.QtCore import Qt

from utils.config import (
    SESSION_DIR, BG_CARD, BG_INPUT, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, BG_PRIMARY,
)


class SessionsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title = QLabel("Sessions Data")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self._open_folder_btn = QPushButton("📂 Open Folder")
        self._open_folder_btn.setCursor(Qt.PointingHandCursor)
        self._open_folder_btn.setStyleSheet(
            f"QPushButton {{ background: #1E3A2F; color: {ACCENT_GREEN}; "
            f"border: 1px solid {ACCENT_GREEN}; border-radius: 8px; "
            f"padding: 6px 14px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #264D3B; }}"
        )
        self._open_folder_btn.clicked.connect(self._open_folder)
        header_row.addWidget(self._open_folder_btn)

        self._refresh_btn = QPushButton("🔄 Refresh")
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; "
            f"padding: 6px 14px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: #242842; }}"
        )
        self._refresh_btn.clicked.connect(self.refresh_list)
        header_row.addWidget(self._refresh_btn)
        root.addLayout(header_row)

        # ── Content: list + summary side by side ──────────────────────
        content = QHBoxLayout()
        content.setSpacing(16)

        # Session list
        list_col = QVBoxLayout()
        list_lbl = QLabel("Saved Sessions")
        list_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_SECONDARY};"
        )
        list_col.addWidget(list_lbl)

        self._session_list = QListWidget()
        self._session_list.setMinimumWidth(300)
        self._session_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 10px; color: {TEXT_PRIMARY}; font-size: 13px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 10px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: #2a2e48; }}"
        )
        self._session_list.currentItemChanged.connect(self._on_select)
        list_col.addWidget(self._session_list, stretch=1)
        content.addLayout(list_col)

        # Summary panel
        summary_col = QVBoxLayout()
        summary_lbl = QLabel("Session Summary")
        summary_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_SECONDARY};"
        )
        summary_col.addWidget(summary_lbl)

        self._summary_widget = QWidget()
        self._summary_widget.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 12px;"
        )
        sw_layout = QVBoxLayout(self._summary_widget)
        sw_layout.setContentsMargins(16, 14, 16, 14)
        sw_layout.setSpacing(8)

        self._sum_file = QLabel("Select a session to view details")
        self._sum_file.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )
        self._sum_file.setWordWrap(True)
        sw_layout.addWidget(self._sum_file)

        self._sum_duration = QLabel("")
        self._sum_duration.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        sw_layout.addWidget(self._sum_duration)

        # Metric averages grid
        self._metric_grid = QGridLayout()
        self._metric_grid.setSpacing(8)
        self._metric_labels = {}
        metrics_display = [
            ("Cognitive Score", "cognitive score"),
            ("Focus", "focus"),
            ("Chill", "chill"),
            ("Stress", "stress"),
            ("Self-control", "self-control"),
            ("Anger", "anger"),
            ("Relaxation Index", "relaxation index"),
            ("Concentration Index", "concentration index"),
            ("Fatigue Score", "fatigue score"),
            ("Heart Rate", "heart rate"),
            ("Stress Index", "stress index"),
            ("Alpha Gravity", "alpha gravity"),
        ]
        for i, (display_name, col_name) in enumerate(metrics_display):
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
            )
            val_lbl = QLabel("--")
            val_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; "
                f"background: transparent; border: none;"
            )
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._metric_grid.addWidget(name_lbl, i // 3, (i % 3) * 2)
            self._metric_grid.addWidget(val_lbl, i // 3, (i % 3) * 2 + 1)
            self._metric_labels[col_name] = val_lbl
        sw_layout.addLayout(self._metric_grid)
        sw_layout.addStretch()

        summary_col.addWidget(self._summary_widget, stretch=1)
        content.addLayout(summary_col, stretch=1)

        root.addLayout(content, stretch=1)

    def refresh_list(self):
        self._session_list.clear()
        os.makedirs(SESSION_DIR, exist_ok=True)
        files = sorted(
            [f for f in os.listdir(SESSION_DIR) if f.endswith(".csv")],
            reverse=True,
        )
        if not files:
            self._session_list.addItem("No sessions found")
            return

        for fname in files:
            item = QListWidgetItem(fname)
            item.setData(Qt.UserRole, os.path.join(SESSION_DIR, fname))
            self._session_list.addItem(item)

    def _on_select(self, current, previous):
        if not current:
            return
        fpath = current.data(Qt.UserRole)
        if not fpath or not os.path.isfile(fpath):
            return
        self._load_summary(fpath)

    def _load_summary(self, fpath: str):
        try:
            df = pd.read_csv(fpath)
        except Exception as exc:
            self._sum_file.setText(f"Error: {exc}")
            return

        fname = os.path.basename(fpath)
        self._sum_file.setText(fname)

        # Duration
        if "time" in df.columns and len(df) > 0:
            self._sum_duration.setText(
                f"Rows: {len(df)} | "
                f"From: {df['time'].iloc[0]} → {df['time'].iloc[-1]}"
            )
        else:
            self._sum_duration.setText(f"Rows: {len(df)}")

        # Averages
        for col_name, lbl in self._metric_labels.items():
            if col_name in df.columns:
                avg = df[col_name].mean()
                lbl.setText(f"{avg:.2f}")
            else:
                lbl.setText("--")

    def _open_folder(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        os.startfile(SESSION_DIR)
