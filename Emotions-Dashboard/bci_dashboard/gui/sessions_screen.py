"""
Browse saved session bundles and legacy CSV sessions.
"""
from __future__ import annotations

import json
import os

import pandas as pd
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_PINK,
    ACCENT_PURPLE,
    BG_CARD,
    BG_INPUT,
    BORDER_SUBTLE,
    SESSION_DIR,
    SESSION_FILE_NAMES,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# ---------------------------------------------------------------------------
# Timeline card colours – cycle through 4 accent colours by index
# ---------------------------------------------------------------------------
_PILL_COLORS = ["#69F0AE", "#4DD0E1", "#B388FF", "#F48FB1"]


class _SessionTimelineCard(QFrame):
    """A single row in the sessions timeline list."""

    clicked_entry = None  # set by parent after construction

    def __init__(self, entry: dict, index: int, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._selected = False
        self._accent = _PILL_COLORS[index % len(_PILL_COLORS)]
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(76)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build()
        self._apply_style(False)

    # ------------------------------------------------------------------
    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 14, 0)
        lay.setSpacing(0)

        # Left accent pill ------------------------------------------------
        self._pill = QWidget()
        self._pill.setFixedWidth(8)
        self._pill.setStyleSheet(
            f"background: {self._accent}; border-radius: 4px; margin: 10px 0px 10px 0px;"
        )
        lay.addWidget(self._pill)

        lay.addSpacing(12)

        # Date/time badge column ------------------------------------------
        badge_col = QVBoxLayout()
        badge_col.setSpacing(2)
        badge_col.setContentsMargins(0, 0, 0, 0)

        label = self._entry.get("label", "")
        # Try to parse a date from the folder/file name (YYYY-MM-DD or YYYY-MM-DD HH-MM)
        date_str, time_str = self._parse_label(label)

        date_lbl = QLabel(date_str)
        date_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {self._accent}; background: transparent;"
        )
        badge_col.addStretch()
        badge_col.addWidget(date_lbl)

        if time_str:
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(
                f"font-size: 10px; color: {TEXT_SECONDARY}; background: transparent;"
            )
            badge_col.addWidget(time_lbl)
        badge_col.addStretch()
        lay.addLayout(badge_col)
        lay.addSpacing(14)

        # Vertical divider ------------------------------------------------
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFixedWidth(1)
        div.setStyleSheet(f"background: {BORDER_SUBTLE};")
        lay.addWidget(div)
        lay.addSpacing(14)

        # Name + kind tags column -----------------------------------------
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.addStretch()

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        name_lbl.setMaximumWidth(220)
        name_lbl.setWordWrap(False)
        info_col.addWidget(name_lbl)

        kind = self._entry.get("kind", "bundle")
        tag_text = "Bundle" if kind == "bundle" else "Legacy CSV"
        tag_lbl = QLabel(tag_text)
        tag_lbl.setFixedWidth(72)
        tag_color = ACCENT_GREEN if kind == "bundle" else ACCENT_CYAN
        tag_lbl.setStyleSheet(
            f"font-size: 9px; font-weight: bold; color: {tag_color}; "
            f"background: rgba(105,240,174,0.10); border: 1px solid {tag_color}; "
            f"border-radius: 4px; padding: 1px 6px; background: transparent;"
        )
        info_col.addWidget(tag_lbl)
        info_col.addStretch()
        lay.addLayout(info_col, stretch=1)

        # Arrow indicator --------------------------------------------------
        arrow = QLabel("›")
        arrow.setStyleSheet(
            f"font-size: 20px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        lay.addWidget(arrow)

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_label(label: str):
        """Return (date_str, time_str) extracted from a session label."""
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})[\s_T]?(\d{2}[-:]\d{2})?", label)
        if m:
            date_part = m.group(1)
            time_part = m.group(2) or ""
            time_part = time_part.replace("-", ":")
            return date_part, time_part
        # Fall back to mtime
        return label[:18] if len(label) > 18 else label, ""

    # ------------------------------------------------------------------
    def _apply_style(self, selected: bool):
        self._selected = selected
        if selected:
            self.setStyleSheet(
                f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 rgba(105,240,174,0.08), stop:1 rgba(27,31,54,0.00)); "
                f"border: 1px solid {self._accent}; border-radius: 14px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; "
                f"border-radius: 14px; }}"
                f"QFrame:hover {{ background: #141826; border-color: #3A4060; }}"
            )

    # ------------------------------------------------------------------
    def set_selected(self, sel: bool):
        self._apply_style(sel)

    def get_entry(self):
        return self._entry

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if self.clicked_entry:
            self.clicked_entry(self._entry, self)
        super().mousePressEvent(event)


class SessionsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[_SessionTimelineCard] = []
        self._selected_card: _SessionTimelineCard | None = None
        self._build_ui()
        self.refresh_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title = QLabel("Sessions")
        title.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: {TEXT_PRIMARY}; "
            f"letter-spacing: 0.5px;"
        )
        header_row.addWidget(title)

        subtitle = QLabel("Recorded brain-data sessions")
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; padding-top: 6px;"
        )
        header_row.addWidget(subtitle)
        header_row.addStretch()

        self._open_folder_btn = QPushButton("📁  Open Folder")
        self._open_folder_btn.setCursor(Qt.PointingHandCursor)
        self._open_folder_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ACCENT_GREEN}; "
            f"border: 1px solid {ACCENT_GREEN}; border-radius: 10px; "
            f"padding: 7px 18px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: rgba(105,240,174,0.08); }}"
        )
        self._open_folder_btn.clicked.connect(self._open_folder)
        header_row.addWidget(self._open_folder_btn)

        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 10px; "
            f"padding: 7px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: #242842; border-color: #3A4060; }}"
        )
        self._refresh_btn.clicked.connect(self.refresh_list)
        header_row.addWidget(self._refresh_btn)
        root.addLayout(header_row)

        # ── Search bar ────────────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search sessions…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(38)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {BG_INPUT}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 10px; "
            f"padding: 0 12px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT_CYAN}; }}"
        )
        self._search.textChanged.connect(self._filter_cards)
        root.addWidget(self._search)

        # ── Two-column body ───────────────────────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(16)

        # Left: timeline list ──────────────────────────────────────────────
        list_col = QVBoxLayout()
        list_col.setSpacing(8)

        list_header = QHBoxLayout()
        list_lbl = QLabel("SAVED SESSIONS")
        list_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {TEXT_SECONDARY}; "
            f"letter-spacing: 1px;"
        )
        list_header.addWidget(list_lbl)
        self._count_lbl = QLabel("0")
        self._count_lbl.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: rgba(255,255,255,0.07); "
            f"border-radius: 8px; padding: 1px 8px;"
        )
        list_header.addWidget(self._count_lbl)
        list_header.addStretch()
        list_col.addLayout(list_header)

        # Scroll area for timeline cards
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setMinimumWidth(340)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: #0D0F1A; width: 5px; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #2A2E48; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        self._scroll_area.setWidget(self._cards_container)
        list_col.addWidget(self._scroll_area, stretch=1)
        content.addLayout(list_col)

        # Right: summary panel ─────────────────────────────────────────────
        summary_col = QVBoxLayout()
        summary_col.setSpacing(8)

        sum_hdr = QLabel("SESSION DETAIL")
        sum_hdr.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {TEXT_SECONDARY}; "
            f"letter-spacing: 1px;"
        )
        summary_col.addWidget(sum_hdr)

        self._summary_widget = QWidget()
        self._summary_widget.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 16px;"
        )
        sw_layout = QVBoxLayout(self._summary_widget)
        sw_layout.setContentsMargins(20, 18, 20, 18)
        sw_layout.setSpacing(10)

        # Placeholder text shown when no session is selected
        self._placeholder = QLabel("Select a session\nto view details")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            f"font-size: 14px; color: {TEXT_SECONDARY}; background: transparent; "
            f"line-height: 1.6;"
        )
        sw_layout.addStretch()
        sw_layout.addWidget(self._placeholder)
        sw_layout.addStretch()

        self._sum_file = QLabel("")
        self._sum_file.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._sum_file.setWordWrap(True)
        self._sum_file.hide()
        sw_layout.addWidget(self._sum_file)

        self._sum_duration = QLabel("")
        self._sum_duration.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._sum_duration.hide()
        sw_layout.addWidget(self._sum_duration)

        self._sum_device = QLabel("")
        self._sum_device.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._sum_device.hide()
        sw_layout.addWidget(self._sum_device)

        self._sum_options = QLabel("")
        self._sum_options.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._sum_options.setWordWrap(True)
        self._sum_options.hide()
        sw_layout.addWidget(self._sum_options)

        # Divider
        self._sum_divider = QFrame()
        self._sum_divider.setFrameShape(QFrame.HLine)
        self._sum_divider.setStyleSheet(f"color: {BORDER_SUBTLE};")
        self._sum_divider.hide()
        sw_layout.addWidget(self._sum_divider)

        # Metrics grid label
        self._metrics_title = QLabel("AVG. METRICS")
        self._metrics_title.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {TEXT_SECONDARY}; "
            f"letter-spacing: 1px; background: transparent;"
        )
        self._metrics_title.hide()
        sw_layout.addWidget(self._metrics_title)

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
        _metric_accent = [ACCENT_GREEN, ACCENT_CYAN, ACCENT_PURPLE, ACCENT_PINK]
        for i, (display_name, col_name) in enumerate(metrics_display):
            acc = _metric_accent[i % len(_metric_accent)]
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
            )
            val_lbl = QLabel("--")
            val_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: bold; color: {acc}; background: transparent;"
            )
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._metric_grid.addWidget(name_lbl, i // 2, (i % 2) * 2)
            self._metric_grid.addWidget(val_lbl, i // 2, (i % 2) * 2 + 1)
            self._metric_labels[col_name] = val_lbl
        sw_layout.addLayout(self._metric_grid)
        sw_layout.addStretch()

        summary_col.addWidget(self._summary_widget, stretch=1)
        content.addLayout(summary_col, stretch=1)
        root.addLayout(content, stretch=1)

    # ── Timeline card helpers ─────────────────────────────────────────────

    def _clear_cards(self):
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected_card = None

    def _add_card(self, entry: dict, index: int):
        card = _SessionTimelineCard(entry, index)
        card.clicked_entry = self._on_card_clicked
        # Insert before the trailing stretch
        insert_pos = self._cards_layout.count() - 1
        self._cards_layout.insertWidget(insert_pos, card)
        self._cards.append(card)

    def _on_card_clicked(self, entry: dict, card: _SessionTimelineCard):
        if self._selected_card and self._selected_card is not card:
            self._selected_card.set_selected(False)
        card.set_selected(True)
        self._selected_card = card
        self._load_summary(entry)

    def _filter_cards(self, text: str):
        text = text.strip().lower()
        for card in self._cards:
            label = card.get_entry().get("label", "").lower()
            card.setVisible(not text or text in label)

    def _show_detail_widgets(self, visible: bool):
        for w in (
            self._sum_file,
            self._sum_duration,
            self._sum_device,
            self._sum_options,
            self._sum_divider,
            self._metrics_title,
        ):
            w.setVisible(visible)
        self._placeholder.setVisible(not visible)

    def refresh_list(self):
        self._clear_cards()
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
            # Show empty state card
            empty_card = QFrame()
            empty_card.setStyleSheet(
                f"QFrame {{ background: {BG_CARD}; border: 1px dashed {BORDER_SUBTLE}; "
                f"border-radius: 14px; }}"
            )
            empty_layout = QVBoxLayout(empty_card)
            empty_lbl = QLabel("No sessions found\n\nStart a recording session to see it here.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(
                f"font-size: 13px; color: {TEXT_SECONDARY}; background: transparent; line-height: 1.6;"
            )
            empty_card.setFixedHeight(120)
            empty_layout.addWidget(empty_lbl)
            insert_pos = self._cards_layout.count() - 1
            self._cards_layout.insertWidget(insert_pos, empty_card)
            self._count_lbl.setText("0")
            return

        for idx, entry in enumerate(entries):
            self._add_card(entry, idx)

        self._count_lbl.setText(str(len(entries)))

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
                self._show_detail_widgets(True)
                return

        self._show_detail_widgets(True)
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
        self._show_detail_widgets(True)
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
