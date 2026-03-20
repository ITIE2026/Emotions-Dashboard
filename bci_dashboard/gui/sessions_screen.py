"""
Browse saved session bundles and legacy CSV sessions.
"""
from __future__ import annotations

import json
import os

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.config import (
    ACCENT_GREEN,
    BG_CARD,
    BG_INPUT,
    BORDER_SUBTLE,
    SESSION_DIR,
    SESSION_FILE_NAMES,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
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

        header_row = QHBoxLayout()
        title = QLabel("Sessions Data")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self._open_folder_btn = QPushButton("Open Folder")
        self._open_folder_btn.setCursor(Qt.PointingHandCursor)
        self._open_folder_btn.setStyleSheet(
            f"QPushButton {{ background: #1E3A2F; color: {ACCENT_GREEN}; "
            f"border: 1px solid {ACCENT_GREEN}; border-radius: 8px; "
            f"padding: 6px 14px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #264D3B; }}"
        )
        self._open_folder_btn.clicked.connect(self._open_folder)
        header_row.addWidget(self._open_folder_btn)

        self._refresh_btn = QPushButton("Refresh")
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

        content = QHBoxLayout()
        content.setSpacing(16)

        list_col = QVBoxLayout()
        list_lbl = QLabel("Saved Sessions")
        list_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_SECONDARY};"
        )
        list_col.addWidget(list_lbl)

        self._session_list = QListWidget()
        self._session_list.setMinimumWidth(320)
        self._session_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 10px; color: {TEXT_PRIMARY}; font-size: 13px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 10px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: #2a2e48; }}"
        )
        self._session_list.currentItemChanged.connect(self._on_select)
        list_col.addWidget(self._session_list, stretch=1)
        content.addLayout(list_col)

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
            f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._sum_file.setWordWrap(True)
        sw_layout.addWidget(self._sum_file)

        self._sum_duration = QLabel("")
        self._sum_duration.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        sw_layout.addWidget(self._sum_duration)

        self._sum_device = QLabel("")
        self._sum_device.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        sw_layout.addWidget(self._sum_device)

        self._sum_options = QLabel("")
        self._sum_options.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._sum_options.setWordWrap(True)
        sw_layout.addWidget(self._sum_options)

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
                f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
            )
            val_lbl = QLabel("--")
            val_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
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

        entries = []
        for name in os.listdir(SESSION_DIR):
            path = os.path.join(SESSION_DIR, name)
            if os.path.isdir(path):
                json_path = os.path.join(path, SESSION_FILE_NAMES["json"])
                metrics_path = os.path.join(path, SESSION_FILE_NAMES["metrics"])
                if os.path.isfile(json_path) or os.path.isfile(metrics_path):
                    entries.append(
                        {
                            "kind": "bundle",
                            "label": name,
                            "path": path,
                            "mtime": os.path.getmtime(path),
                        }
                    )
            elif name.endswith(".csv"):
                entries.append(
                    {
                        "kind": "legacy_csv",
                        "label": name,
                        "path": path,
                        "mtime": os.path.getmtime(path),
                    }
                )

        entries.sort(key=lambda item: item["mtime"], reverse=True)
        if not entries:
            empty = QListWidgetItem("No sessions found")
            empty.setFlags(Qt.NoItemFlags)
            self._session_list.addItem(empty)
            return

        for entry in entries:
            label = entry["label"]
            if entry["kind"] == "legacy_csv":
                label = f"{label} (legacy CSV)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry)
            self._session_list.addItem(item)

    def _on_select(self, current, previous):
        if not current:
            return
        entry = current.data(Qt.UserRole)
        if not entry:
            return
        self._load_summary(entry)

    def _load_summary(self, entry: dict):
        if entry["kind"] == "bundle":
            self._load_bundle_summary(entry["path"])
        else:
            self._load_legacy_summary(entry["path"])

    def _load_bundle_summary(self, session_dir: str):
        json_path = os.path.join(session_dir, SESSION_FILE_NAMES["json"])
        metrics_path = os.path.join(session_dir, SESSION_FILE_NAMES["metrics"])
        data = {}
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception as exc:
                self._sum_file.setText(f"Error: {exc}")
                return

        self._sum_file.setText(os.path.basename(session_dir))
        session_info = data.get("sessionInfo", {})
        start_ts = session_info.get("startUTCUnixTimestamp")
        end_ts = session_info.get("endUTCUnixTimestamp")
        self._sum_duration.setText(
            f"Start: {start_ts or '--'} | End: {end_ts or '--'}"
        )

        device_info = data.get("deviceInfo", {})
        device_label = device_info.get("deviceTypeLabel") or device_info.get("deviceType")
        self._sum_device.setText(
            f"Device: {device_label or '--'} | Serial: {device_info.get('serial', '--')}"
        )

        write_options = data.get("writeOptions", {})
        enabled = [
            option.get("label", key)
            for key, option in write_options.items()
            if option.get("enabled")
        ]
        self._sum_options.setText(
            "Write options: " + (", ".join(enabled) if enabled else "None")
        )

        if os.path.isfile(metrics_path):
            self._load_metrics_summary(metrics_path)
        else:
            for lbl in self._metric_labels.values():
                lbl.setText("--")

    def _load_legacy_summary(self, csv_path: str):
        self._sum_file.setText(os.path.basename(csv_path))
        self._sum_duration.setText("Legacy CSV session")
        self._sum_device.setText("Device: --")
        self._sum_options.setText("Write options: metrics.csv only")
        self._load_metrics_summary(csv_path)

    def _load_metrics_summary(self, csv_path: str):
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            self._sum_file.setText(f"Error: {exc}")
            return

        if "time" in df.columns and len(df) > 0:
            self._sum_duration.setText(
                f"Rows: {len(df)} | From: {df['time'].iloc[0]} -> {df['time'].iloc[-1]}"
            )

        for col_name, lbl in self._metric_labels.items():
            if col_name in df.columns:
                lbl.setText(f"{df[col_name].mean():.2f}")
            else:
                lbl.setText("--")

    def _open_folder(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        os.startfile(SESSION_DIR)
