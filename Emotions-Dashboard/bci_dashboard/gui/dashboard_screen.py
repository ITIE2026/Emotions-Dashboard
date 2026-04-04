"""
DashboardScreen - full raw-data monitoring dashboard.
"""
from __future__ import annotations

import os
import time
import uuid
from collections import deque
from datetime import datetime

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.raw_metrics import aggregate_band_history, derive_ppg_metrics
from gui.widgets.electrode_table import ElectrodeTable
from gui.widgets.eeg_graph_panel import ToggleableEegGraphPanel
from gui.widgets.fatigue_panel import FatiguePanel
from gui.widgets.metric_card import MetricCard
from gui.widgets.raw_data_widgets import (
    CollapsibleSection,
    RhythmsPieChartWidget,
    TriAxisChartWidget,
)
from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_ORANGE,
    ACCENT_RED,
    BG_CARD,
    BG_PRIMARY,
    BORDER_SUBTLE,
    EEG_FILTER_ENABLED_DEFAULT,
    SESSION_DIR,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.eeg_filter import EEGDisplayFilter
from utils.helpers import (
    compute_hemisphere_band_powers,
    compute_band_powers,
    compute_peak_frequencies,
    recommendation_label,
    resist_color,
    resist_label,
    stress_label,
)


PPG_WINDOW_SAMPLES = 9000
BAND_HISTORY_POINTS = 5000
MEMS_WINDOW_SAMPLES = 2000
MEMS_WINDOW_SEC = 5.0


def _section_header(text: str, colour: str = ACCENT_GREEN) -> QLabel:
    """Section header with a coloured left accent stripe."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 13px; font-weight: bold; color: {colour}; "
        f"padding: 7px 12px 5px 14px; background: transparent; "
        f"border-left: 3px solid {colour}; letter-spacing: 0.5px; "
        f"text-transform: uppercase;"
    )
    return lbl


def _metric_tile(title: str, initial: str = "0.00") -> tuple[QWidget, QLabel]:
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(1)

    title_lbl = QLabel(f"<b>{title}</b>")
    title_lbl.setStyleSheet(
        f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
    )
    value_lbl = QLabel(initial)
    value_lbl.setStyleSheet(
        f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
    )
    layout.addWidget(title_lbl)
    layout.addWidget(value_lbl)
    return container, value_lbl


class DashboardScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions = {}
        self._latest_productivity = {}
        self._latest_cardio = {}
        self._latest_indexes = {}
        self._latest_physio = {}
        self._latest_band_powers = {}
        self._latest_left_band_powers = {}
        self._latest_right_band_powers = {}
        self._latest_peaks = {}
        self._latest_ppg_metrics = {}

        self._last_psd_t = 0.0
        self._session_file: str | None = None
        self._session_id = str(uuid.uuid4())
        self._session_start = datetime.now()
        self._session_start_wall = time.time()

        self._ppg_calibrated = False
        self._ppg_state: dict = {}
        self._ppg_samples = deque(maxlen=PPG_WINDOW_SAMPLES)
        self._ppg_timestamps = deque(maxlen=PPG_WINDOW_SAMPLES)
        self._band_history = deque(maxlen=BAND_HISTORY_POINTS)
        self._last_nonempty_band_history = None
        self._eeg_dirty = False
        self._psd_dirty = False
        self._psd_refresh_interval = 0.08
        self._streaming_active = False
        self._view_active = False
        self._eeg_filter_enabled = bool(EEG_FILTER_ENABLED_DEFAULT)
        self._eeg_display_filter = EEGDisplayFilter()
        self._iapf_status = {
            "frequency": None,
            "source": "Not set",
            "status": "Not set",
            "applied": False,
        }

        self._build_ui()

        self._dur_timer = QTimer(self)
        self._dur_timer.setInterval(1000)
        self._dur_timer.timeout.connect(self._update_duration)
        self._dur_timer.start()

        self._eeg_timer = QTimer(self)
        self._eeg_timer.setInterval(50)
        self._eeg_timer.timeout.connect(self._refresh_live_panels)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        info_bar = QWidget()
        info_bar.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 #0C0F1E, stop:0.5 {BG_CARD}, stop:1 #0C0F1E);"
            f" border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        info_bar.setFixedHeight(46)
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(16, 0, 16, 0)
        info_layout.setSpacing(20)

        self._conn_label = QLabel("IsConnected: false")
        self._serial_label = QLabel("Serial: --")
        self._mode_label = QLabel("Mode: Unspecified")
        self._battery_label = QLabel("Battery: ?")
        self._iapf_label = QLabel("iAPF: Not set")
        self._filter_label = QLabel(
            f"EEG Filter: {self._eeg_display_filter.status_text(self._eeg_filter_enabled)}"
        )
        for lbl in (
            self._conn_label,
            self._serial_label,
            self._mode_label,
            self._battery_label,
            self._iapf_label,
            self._filter_label,
        ):
            lbl.setStyleSheet(
                f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
            )
            info_layout.addWidget(lbl)

        session_col = QVBoxLayout()
        session_col.setSpacing(0)
        self._start_label = QLabel(
            f"Session Start: {self._session_start.strftime('%H:%M:%S')}"
        )
        self._duration_label = QLabel("Session Duration: 00:00:00")
        self._id_label = QLabel(f"Session ID: {self._session_id}")
        self._start_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._duration_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._id_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        session_col.addWidget(self._start_label)
        session_col.addWidget(self._duration_label)
        session_col.addWidget(self._id_label)
        info_layout.addLayout(session_col)

        self._resist_labels = {}
        resist_col = QHBoxLayout()
        resist_col.setSpacing(12)
        for ch in ["O1", "T3", "T4", "O2"]:
            lbl = QLabel(f"{ch}: -- kΩ")
            lbl.setStyleSheet(
                f"font-size: 12px; color: {ACCENT_RED}; background: transparent;"
            )
            resist_col.addWidget(lbl)
            self._resist_labels[ch] = lbl
        info_layout.addStretch()
        info_layout.addLayout(resist_col)
        outer.addWidget(info_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter {{ background: {BG_PRIMARY}; }}"
            f"QSplitter::handle {{ background: {BORDER_SUBTLE}; width: 2px; }}"
        )

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 4, 8)
        left_layout.setSpacing(6)

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.setChildrenCollapsible(False)
        left_splitter.setHandleWidth(2)
        left_splitter.setStyleSheet(
            f"QSplitter {{ background: {BG_PRIMARY}; }}"
            f"QSplitter::handle {{ background: {BORDER_SUBTLE}; height: 2px; }}"
        )

        self._spectrum = ToggleableEegGraphPanel()
        self._spectrum.setMinimumHeight(300)
        left_splitter.addWidget(self._spectrum)

        self._electrode_table = ElectrodeTable()
        self._electrode_table.setMinimumHeight(220)
        self._electrode_table.set_display_filter(
            self._eeg_filter_enabled,
            self._eeg_display_filter,
        )
        left_splitter.addWidget(self._electrode_table)
        left_splitter.setStretchFactor(0, 4)
        left_splitter.setStretchFactor(1, 2)
        left_splitter.setSizes([560, 240])
        left_layout.addWidget(left_splitter, stretch=1)
        splitter.addWidget(left_widget)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._right_scroll = right_scroll
        right_widget = QWidget()
        self._right_widget = right_widget
        self._sections = {}
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 12)
        right_layout.setSpacing(6)

        emotions_header = _section_header("Emotions", "#B388FF")
        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        self._card_focus = MetricCard("Focus", "#B388FF")
        self._card_chill = MetricCard("Calmness", "#81C784")
        self._card_stress = MetricCard("Tension", "#FF8A65")
        self._card_anger = MetricCard("Anger", "#E57373")
        self._card_self_ctrl = MetricCard("Self-ctrl", "#4DD0E1")
        for card in (
            self._card_focus,
            self._card_chill,
            self._card_stress,
            self._card_anger,
            self._card_self_ctrl,
        ):
            cards_row.addWidget(card)
        right_layout.addWidget(emotions_header)
        right_layout.addLayout(cards_row)

        right_layout.addWidget(_section_header("Indices and Scores", ACCENT_GREEN))
        idx_grid = QGridLayout()
        idx_grid.setHorizontalSpacing(12)
        idx_grid.setVerticalSpacing(6)
        self._idx_labels = {}
        idx_items = [
            ("Relaxation Index", "relaxation_idx", 0, 0),
            ("Concentration Index", "concentration_idx", 0, 1),
            ("Fatigue Score", "fatigue_score", 0, 2),
            ("Reverse Fatigue Score", "reverse_fatigue", 1, 0),
            ("Productivity Score", "productivity_pct", 1, 1),
            ("Alpha Gravity", "alpha_gravity", 1, 2),
            ("Accumulated Fatigue", "accumulated_fatigue", 2, 0),
        ]
        for title, key, row, col in idx_items:
            tile, value_lbl = _metric_tile(title)
            idx_grid.addWidget(tile, row, col)
            self._idx_labels[key] = value_lbl
        right_layout.addLayout(idx_grid)

        right_layout.addWidget(_section_header("Rhythms", ACCENT_CYAN))
        rhythm_row = QHBoxLayout()
        rhythm_row.setSpacing(16)
        self._rhythm_labels = {}
        for name in ["Alpha", "Beta", "Theta", "SMR"]:
            tile, value_lbl = _metric_tile(f"{name}:")
            rhythm_row.addWidget(tile)
            self._rhythm_labels[name.lower()] = value_lbl
        rhythm_row.addStretch()
        right_layout.addLayout(rhythm_row)

        right_layout.addWidget(_section_header("Instant Frequency Peaks", ACCENT_ORANGE))
        peaks_row = QHBoxLayout()
        peaks_row.setSpacing(16)
        self._peak_labels = {}
        for title, key in [
            ("Alpha Peak", "alpha_peak"),
            ("Beta Peak", "beta_peak"),
            ("Theta Peak", "theta_peak"),
        ]:
            tile, value_lbl = _metric_tile(f"{title}:")
            peaks_row.addWidget(tile)
            self._peak_labels[key] = value_lbl
        peaks_row.addStretch()
        right_layout.addLayout(peaks_row)

        right_layout.addWidget(_section_header("State Characteristics", ACCENT_RED))
        state_row = QHBoxLayout()
        state_row.setSpacing(24)
        self._recommendation_lbl = QLabel("No recommendation")
        self._stress_state_lbl = QLabel("No Stress")
        self._valid_state_lbl = QLabel("Valid State")
        for lbl, colour in (
            (self._recommendation_lbl, ACCENT_GREEN),
            (self._stress_state_lbl, ACCENT_RED),
            (self._valid_state_lbl, ACCENT_GREEN),
        ):
            lbl.setStyleSheet(
                f"font-size: 12px; color: {colour}; background: transparent;"
            )
            state_row.addWidget(lbl)
        state_row.addStretch()
        right_layout.addLayout(state_row)

        hr_card = QWidget()
        hr_card.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; border-radius: 10px;"
        )
        hr_layout = QHBoxLayout(hr_card)
        hr_layout.setContentsMargins(14, 10, 14, 10)
        hr_icon = QLabel("♥")
        hr_icon.setStyleSheet(
            f"font-size: 24px; color: {ACCENT_RED}; background: transparent; border: none;"
        )
        self._hr_value = QLabel("0.00 bpm")
        self._hr_value.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {ACCENT_RED}; background: transparent; border: none;"
        )
        self._si_value = QLabel("Stress Index: 0.0")
        self._si_value.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        hr_text = QVBoxLayout()
        hr_text.setSpacing(1)
        hr_text.addWidget(self._hr_value)
        hr_text.addWidget(self._si_value)
        hr_layout.addWidget(hr_icon)
        hr_layout.addLayout(hr_text)
        hr_layout.addStretch()
        right_layout.addWidget(hr_card)

        self._fatigue_panel = FatiguePanel()
        right_layout.addWidget(self._fatigue_panel)

        right_layout.addWidget(_section_header("PPG Metrics", ACCENT_CYAN))
        ppg_grid = QGridLayout()
        ppg_grid.setHorizontalSpacing(12)
        ppg_grid.setVerticalSpacing(6)
        ppg_items = [
            ("Perfusion", "perfusion", 0, 0),
            ("PPG signal quality avg", "ppg_quality", 0, 1),
            ("HR", "ppg_hr", 0, 2),
            ("SI", "ppg_si", 0, 3),
            ("SAT", "sat", 0, 4),
            ("CV", "cv", 1, 0),
            ("Is Calibrated", "is_calibrated", 1, 1),
            ("RR(M)", "rr_mean", 1, 2),
            ("SDNN", "sdnn", 1, 3),
            ("Skin Contact Artifacts", "skin_contact_artifacts", 1, 4),
            ("Mo", "mo", 2, 0),
            ("AMo", "amo", 2, 1),
            ("MxDMn", "mxdmn", 2, 2),
            ("MxDMn(total)", "mxdmn_total", 2, 3),
            ("Motion Artifacts", "motion_artifacts", 2, 4),
        ]
        self._ppg_labels = {}
        for title, key, row, col in ppg_items:
            tile, value_lbl = _metric_tile(title, "Calculating")
            ppg_grid.addWidget(tile, row, col)
            self._ppg_labels[key] = value_lbl
        right_layout.addLayout(ppg_grid)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)
        splitter.setSizes([670, 660])
        outer.addWidget(splitter, stretch=1)

        self._update_ppg_metrics_panel()
        self._refresh_filter_label()

    def set_streaming_active(self, active: bool):
        self._streaming_active = bool(active)
        if not self._streaming_active:
            self._eeg_dirty = False
            self._psd_dirty = False
            self._electrode_table.reset_interaction_state()
            self._eeg_timer.stop()
            return
        if self._view_active and not self._eeg_timer.isActive():
            self._eeg_timer.start()

    def set_view_active(self, active: bool):
        self._view_active = bool(active)
        if self._streaming_active and self._view_active:
            if not self._eeg_timer.isActive():
                self._eeg_timer.start()
            return
        self._eeg_timer.stop()

    def show_section(self, section_id: str):
        section = self._sections.get(section_id)
        if section is None:
            return
        section.set_expanded(True)
        if section_id == "rhythms_diagram":
            self._update_rhythms_diagram()
        QTimer.singleShot(
            0,
            lambda: self._right_scroll.ensureWidgetVisible(section, 0, 24),
        )

    def on_emotions(self, data: dict):
        try:
            self._latest_emotions = data or {}
            self._card_focus.set_value(self._latest_emotions.get("focus", 0))
            self._card_chill.set_value(self._latest_emotions.get("chill", 0))
            self._card_stress.set_value(self._latest_emotions.get("stress", 0))
            self._card_anger.set_value(self._latest_emotions.get("anger", 0))
            self._card_self_ctrl.set_value(self._latest_emotions.get("selfControl", 0))
            # Feed Neural Art Generator
            self._spectrum.update_brain_metrics(
                attention=self._latest_emotions.get("focus", 0),
                relaxation=self._latest_emotions.get("chill", 0),
                stress=self._latest_emotions.get("anger", 0),
                cognitive_load=self._latest_emotions.get("stress", 0),
            )
        except Exception:
            pass

    def on_productivity(self, data: dict):
        try:
            self._latest_productivity = data or {}
            self._idx_labels["relaxation_idx"].setText(
                f"{self._latest_productivity.get('relaxationScore', 0):.2f}"
            )
            self._idx_labels["concentration_idx"].setText(
                f"{self._latest_productivity.get('concentrationScore', 0):.2f}"
            )
            self._idx_labels["fatigue_score"].setText(
                f"{self._latest_productivity.get('fatigueScore', 0):.2f}"
            )
            self._idx_labels["reverse_fatigue"].setText(
                f"{self._latest_productivity.get('reverseFatigueScore', 0):.2f}"
            )
            self._idx_labels["productivity_pct"].setText(
                f"{self._latest_productivity.get('productivityScore', 0):.0f}%"
            )
            self._idx_labels["alpha_gravity"].setText(
                f"{self._latest_productivity.get('gravityScore', 0):.2f}"
            )
            self._idx_labels["accumulated_fatigue"].setText(
                f"{self._latest_productivity.get('accumulatedFatigue', 0):.2f}"
            )
            self._fatigue_panel.update_data(
                fatigue_score=self._latest_productivity.get("fatigueScore", 0),
                growth_rate=self._latest_productivity.get("fatigueGrowthRate", 0),
                accumulated=self._latest_productivity.get("accumulatedFatigue", 0),
                recommendation=self._latest_indexes.get("relaxation_recommendation", 0),
            )
        except Exception:
            pass

    def on_indexes(self, data: dict):
        try:
            self._latest_indexes = data or {}
            rec = self._latest_indexes.get("relaxation_recommendation", 0)
            self._recommendation_lbl.setText(recommendation_label(rec) or "No recommendation")

            stress_val = self._latest_indexes.get("stress", 0)
            stress_text = stress_label(stress_val)
            stress_colour = ACCENT_GREEN if stress_val == 0 else ACCENT_RED
            self._stress_state_lbl.setText(stress_text)
            self._stress_state_lbl.setStyleSheet(
                f"font-size: 12px; color: {stress_colour}; background: transparent;"
            )
        except Exception:
            pass

    def on_cardio(self, data: dict):
        self._latest_cardio = data or {}
        self._ppg_calibrated = bool(self._latest_cardio.get("isCalibrated", self._ppg_calibrated))
        hr = float(self._latest_cardio.get("heartRate", 0.0))
        self._hr_value.setText(f"{hr:.2f} bpm")
        si = float(self._latest_cardio.get("stressIndex", 0.0))
        self._si_value.setText(f"Stress Index: {si:.1f}")
        self._update_ppg_metrics_panel()

    def on_ppg(self, ppg_timed_data):
        try:
            for idx in range(len(ppg_timed_data)):
                self._ppg_samples.append(float(ppg_timed_data.get_value(idx)))
                self._ppg_timestamps.append(float(ppg_timed_data.get_timestamp(idx)) / 1000.0)
            derived = derive_ppg_metrics(
                list(self._ppg_samples),
                list(self._ppg_timestamps),
                self._ppg_state,
            )
            self._ppg_state = derived.pop("state", {})
            self._latest_ppg_metrics = derived
            self._update_ppg_metrics_panel()
        except Exception:
            pass

    def on_physio_states(self, data: dict):
        self._latest_physio = data or {}
        has_nfb_art = self._latest_physio.get("nfbArtifacts", False)
        has_cardio_art = self._latest_physio.get("cardioArtifacts", False)
        if not has_nfb_art and not has_cardio_art:
            self._valid_state_lbl.setText("Valid State")
            self._valid_state_lbl.setStyleSheet(
                f"font-size: 12px; color: {ACCENT_GREEN}; background: transparent;"
            )
        else:
            self._valid_state_lbl.setText("Artifacts Detected")
            self._valid_state_lbl.setStyleSheet(
                f"font-size: 12px; color: {ACCENT_RED}; background: transparent;"
            )
        self._update_ppg_metrics_panel()

    def on_psd(self, psd_data):
        if not self._streaming_active or not self._view_active:
            return
        now = time.monotonic()
        if now - self._last_psd_t < self._psd_refresh_interval:
            return
        self._last_psd_t = now
        try:
            n_freq = psd_data.get_frequencies_count()
            n_channels = psd_data.get_channels_count()
            freqs = [float(psd_data.get_frequency(idx)) for idx in range(n_freq)]
            avg_power = [0.0] * n_freq
            channel_powers = [[0.0] * n_freq for _ in range(n_channels)]
            for ch_idx in range(n_channels):
                for f_idx in range(n_freq):
                    value = float(psd_data.get_psd(ch_idx, f_idx))
                    channel_powers[ch_idx][f_idx] = value
                    avg_power[f_idx] += value
            if n_channels > 0:
                avg_power = [value / n_channels for value in avg_power]

            self._spectrum.update_psd(freqs, avg_power)
            left_band_powers, right_band_powers = compute_hemisphere_band_powers(
                np.asarray(freqs, dtype=float),
                np.asarray(channel_powers if n_channels > 0 else [], dtype=float),
            )
            self._latest_left_band_powers = dict(left_band_powers)
            self._latest_right_band_powers = dict(right_band_powers)
            self._spectrum.update_hemisphere_band_powers(
                self._latest_left_band_powers,
                self._latest_right_band_powers,
            )

            f_arr = np.asarray(freqs, dtype=float)
            p_arr = np.asarray(avg_power, dtype=float)
            self._latest_band_powers = compute_band_powers(f_arr, p_arr)
            self._latest_peaks = compute_peak_frequencies(f_arr, p_arr)
            self._band_history.append((time.monotonic(), dict(self._latest_band_powers)))

            for name in ["alpha", "beta", "theta", "smr"]:
                value = self._latest_band_powers.get(name, 0.0)
                self._rhythm_labels[name].setText(self._format_rhythm_value(value))
            for key in ["alpha_peak", "beta_peak", "theta_peak"]:
                self._peak_labels[key].setText(f"{self._latest_peaks.get(key, 0.0):.1f} Hz")

            self._psd_dirty = True
        except Exception:
            pass

    def on_psd_snapshot(self, psd_snapshot: dict):
        if not self._streaming_active or not self._view_active or not psd_snapshot:
            return
        now = float(psd_snapshot.get("received_at", time.monotonic()))
        if now - self._last_psd_t < self._psd_refresh_interval:
            return
        freqs = list(psd_snapshot.get("freqs", []))
        avg_power = list(psd_snapshot.get("avg_power", []))
        if not freqs or not avg_power:
            return

        self._last_psd_t = now
        try:
            self._spectrum.update_psd(freqs, avg_power)
            self._latest_band_powers = dict(psd_snapshot.get("band_powers", {}))
            self._latest_left_band_powers = dict(psd_snapshot.get("left_band_powers", {}))
            self._latest_right_band_powers = dict(psd_snapshot.get("right_band_powers", {}))
            self._latest_peaks = dict(psd_snapshot.get("peak_frequencies", {}))
            self._spectrum.update_hemisphere_band_powers(
                self._latest_left_band_powers,
                self._latest_right_band_powers,
            )
            self._band_history.append((now, dict(self._latest_band_powers)))

            for name in ["alpha", "beta", "theta", "smr"]:
                value = self._latest_band_powers.get(name, 0.0)
                self._rhythm_labels[name].setText(self._format_rhythm_value(value))
            for key in ["alpha_peak", "beta_peak", "theta_peak"]:
                self._peak_labels[key].setText(f"{self._latest_peaks.get(key, 0.0):.1f} Hz")

            self._psd_dirty = True
        except Exception:
            pass

    def on_eeg(self, eeg_timed_data):
        if not self._streaming_active or not self._view_active:
            return
        had_data = self._electrode_table.has_data()
        self._electrode_table.add_eeg_data(eeg_timed_data)
        self._eeg_dirty = True
        if not self._eeg_timer.isActive():
            self._eeg_timer.start()
        if not had_data:
            self._electrode_table.refresh()
            self._eeg_dirty = False

    def on_eeg_snapshot(self, eeg_snapshot: dict):
        if not self._streaming_active or not self._view_active or not eeg_snapshot:
            return
        had_data = self._electrode_table.has_data()
        self._electrode_table.add_eeg_snapshot(eeg_snapshot)
        self._eeg_dirty = True
        if not self._eeg_timer.isActive():
            self._eeg_timer.start()
        if not had_data:
            self._electrode_table.refresh()
            self._eeg_dirty = False

    def on_artifacts(self, artifacts):
        self._electrode_table.update_artifacts(artifacts)

    def on_mems(self, mems_timed_data):
        return

    def on_resistance(self, data: dict):
        for ch, lbl in self._resist_labels.items():
            ohms = _resistance_value_for_channel(data, ch)
            lbl.setText(f"{ch}: {resist_label(ohms)}")
            lbl.setStyleSheet(
                f"font-size: 12px; color: {resist_color(ohms)}; background: transparent;"
            )

    def set_session_info(self, connected: bool = False, serial: str = "--", battery: int = -1):
        self._conn_label.setText(f"IsConnected: {str(connected).lower()}")
        self._serial_label.setText(f"Serial: {serial}")
        if battery >= 0:
            self._battery_label.setText(f"Battery: {battery}%")

    def set_mode(self, mode_str: str):
        self._mode_label.setText(f"Mode: {mode_str}")

    def set_battery(self, pct: int):
        try:
            pct = int(pct)
        except (TypeError, ValueError):
            pct = -1
        if 0 <= pct <= 100:
            self._battery_label.setText(f"Battery: {pct}%")
            return
        self._battery_label.setText("Battery: ?")

    def set_ppg_calibrated(self, calibrated: bool = True):
        self._ppg_calibrated = bool(calibrated)
        self._update_ppg_metrics_panel()

    def set_eeg_filter_enabled(self, enabled: bool):
        self._eeg_filter_enabled = bool(enabled)
        self._electrode_table.set_display_filter(
            self._eeg_filter_enabled,
            self._eeg_display_filter,
        )
        self._eeg_dirty = True
        self._refresh_filter_label()
        self._electrode_table.refresh()
        self._eeg_dirty = False

    def set_eeg_stream_metadata(
        self,
        sample_rate_hz: float | None = None,
        channel_names: list[str] | None = None,
    ):
        self._electrode_table.set_sample_rate(sample_rate_hz)
        self._electrode_table.set_channel_names(channel_names)

    def set_iapf_status(
        self,
        frequency: float | None = None,
        source: str = "Not set",
        status: str = "Not set",
        applied: bool = False,
    ):
        self._iapf_status = {
            "frequency": frequency,
            "source": source,
            "status": status,
            "applied": bool(applied),
        }
        if frequency in (None, 0):
            self._iapf_label.setText("iAPF: Not set")
        else:
            self._iapf_label.setText(f"iAPF: {float(frequency):.2f} Hz ({source})")

    def reset_session(self, session_id: str | None = None):
        self._session_id = session_id or str(uuid.uuid4())
        self._session_start = datetime.now()
        self._session_start_wall = time.time()
        self._start_label.setText(
            f"Session Start: {self._session_start.strftime('%H:%M:%S')}"
        )
        self._id_label.setText(f"Session ID: {self._session_id}")

        self._ppg_state = {}
        self._latest_ppg_metrics = {}
        self._latest_band_powers = {}
        self._latest_left_band_powers = {}
        self._latest_right_band_powers = {}
        self._latest_peaks = {}
        self._ppg_samples.clear()
        self._ppg_timestamps.clear()
        self._band_history.clear()
        self._last_nonempty_band_history = None
        self._last_psd_t = 0.0
        self._eeg_dirty = False
        self._psd_dirty = False

        self._eeg_display_filter.reset()
        self._electrode_table.set_session_start(self._session_start_wall)
        self._electrode_table.clear()
        self._electrode_table.reset_interaction_state()
        self._spectrum.clear_data()
        self._spectrum.reset_view()
        self._update_ppg_metrics_panel()
        self._refresh_filter_label()
        if self._streaming_active and self._view_active:
            self._eeg_timer.start()

    def set_session_file(self, path: str):
        self._session_file = path

    def stop_eeg_timer(self):
        self._eeg_timer.stop()

    def _update_duration(self):
        elapsed = (datetime.now() - self._session_start).total_seconds()
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        self._duration_label.setText(f"Session Duration: {h:02d}:{m:02d}:{s:02d}")

    def _open_sessions_folder(self):
        from utils.platform import open_folder
        open_folder(SESSION_DIR)

    def _refresh_live_panels(self):
        if not self._streaming_active or not self._view_active:
            return

        refreshed = False
        if self._eeg_dirty or self._electrode_table.has_pending_refresh():
            self._electrode_table.refresh()
            self._eeg_dirty = False
            refreshed = True

        if self._psd_dirty:
            self._update_rhythms_diagram()
            self._psd_dirty = False
            refreshed = True

        if refreshed:
            self._refresh_filter_label()

    def _refresh_filter_label(self):
        state = self._eeg_display_filter.status_text(self._eeg_filter_enabled)
        self._filter_label.setText(f"EEG Filter: {state}")

    def _update_ppg_metrics_panel(self):
        metrics = self._latest_ppg_metrics or {}
        cardio = self._latest_cardio or {}

        self._set_ppg_value("perfusion", self._fmt_float(metrics.get("perfusion"), 5, calculating=True))
        self._set_ppg_value("ppg_quality", self._fmt_float(metrics.get("signal_quality_avg"), 2, calculating=True))
        self._set_ppg_value("ppg_hr", f"{float(cardio.get('heartRate', 0.0)):.2f} bpm")
        si_value = cardio.get("stressIndex", None)
        if cardio.get("metricsAvailable", False) or si_value not in (None, 0):
            self._set_ppg_value("ppg_si", f"{float(si_value or 0.0):.2f}")
        else:
            self._set_ppg_value("ppg_si", "Calculating")
        self._set_ppg_value("sat", "--")
        self._set_ppg_value("cv", self._fmt_percent(metrics.get("cv")))
        self._set_boolean_metric("is_calibrated", self._ppg_calibrated)
        self._set_ppg_value("rr_mean", self._fmt_seconds(metrics.get("rr_mean")))
        self._set_ppg_value("sdnn", self._fmt_milliseconds(metrics.get("sdnn")))
        self._set_boolean_metric("skin_contact_artifacts", not bool(cardio.get("skinContact", True)))
        self._set_ppg_value("mo", self._fmt_seconds(metrics.get("mo")))
        self._set_ppg_value("amo", self._fmt_percent(metrics.get("amo")))
        self._set_ppg_value("mxdmn", self._fmt_milliseconds(metrics.get("mxdmn")))
        self._set_ppg_value("mxdmn_total", self._fmt_milliseconds(metrics.get("mxdmn_total")))
        self._set_boolean_metric("motion_artifacts", bool(cardio.get("motionArtifacts", False)))

    def _set_ppg_value(self, key: str, text: str):
        self._ppg_labels[key].setText(text)
        self._ppg_labels[key].setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
        )

    def _set_boolean_metric(self, key: str, value: bool):
        colour = ACCENT_RED if value else ACCENT_GREEN
        text = "Yes" if value else "No"
        self._ppg_labels[key].setText(text)
        self._ppg_labels[key].setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {colour}; background: transparent;"
        )

    def _update_rhythms_diagram(self):
        if not hasattr(self, "_rhythms_pie") or not hasattr(self, "_rhythm_scale_combo"):
            return
        window_lookup = {"1min": 60.0, "5min": 300.0, "15min": 900.0}
        window_seconds = window_lookup.get(self._rhythm_scale_combo.currentText(), 60.0)
        aggregated = aggregate_band_history(
            self._band_history,
            window_seconds,
            now=time.monotonic(),
        )
        if aggregated is not None:
            self._last_nonempty_band_history = dict(aggregated)
            self._rhythms_pie.set_band_powers(aggregated)
            return
        if any(float(value) > 0.0 for value in self._latest_band_powers.values()):
            self._last_nonempty_band_history = dict(self._latest_band_powers)
            self._rhythms_pie.set_band_powers(self._latest_band_powers)
            return
        if self._last_nonempty_band_history is not None:
            self._rhythms_pie.set_band_powers(self._last_nonempty_band_history)
            return
        self._rhythms_pie.set_waiting("Waiting for PSD data")

    def _refresh_mems_charts(self):
        if not hasattr(self, "_accel_chart") or not hasattr(self, "_gyro_chart"):
            return
        accel = self._mems_buffers["accelerometer"]
        gyro = self._mems_buffers["gyroscope"]
        self._accel_chart.set_series(
            accel["times"],
            accel["x"],
            accel["y"],
            accel["z"],
            current_vector=accel["current"],
            span_seconds=MEMS_WINDOW_SEC,
            fixed_range=(-1.0, 1.0),
        )
        self._gyro_chart.set_series(
            gyro["times"],
            gyro["x"],
            gyro["y"],
            gyro["z"],
            current_vector=gyro["current"],
            span_seconds=MEMS_WINDOW_SEC,
            fixed_range=(-50.0, 50.0),
        )

    def _clear_vector_buffers(self):
        for buf in self._mems_buffers.values():
            buf["times"].clear()
            buf["x"].clear()
            buf["y"].clear()
            buf["z"].clear()
            buf["current"] = (0.0, 0.0, 0.0)

    @staticmethod
    def _new_vector_buffer():
        return {
            "times": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "x": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "y": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "z": deque(maxlen=MEMS_WINDOW_SAMPLES),
            "current": (0.0, 0.0, 0.0),
        }

    @staticmethod
    def _append_vector_sample(buffer: dict, mapped_ts: float, vector: tuple[float, float, float]):
        buffer["times"].append(mapped_ts)
        buffer["x"].append(vector[0])
        buffer["y"].append(vector[1])
        buffer["z"].append(vector[2])
        buffer["current"] = vector

    def _map_sdk_time(self, sdk_ts: float, origin_attr_name: str) -> float:
        origin = getattr(self, origin_attr_name)
        if origin is None:
            setattr(self, origin_attr_name, sdk_ts)
            origin = sdk_ts
        return self._session_start_wall + (float(sdk_ts) - float(origin))

    @staticmethod
    def _format_rhythm_value(value: float) -> str:
        if value >= 0.01:
            return f"{value:.3f}"
        if value >= 0.000001:
            return f"{value:.6f}"
        return f"{value:.2e}"

    @staticmethod
    def _fmt_float(value, decimals: int = 2, calculating: bool = False) -> str:
        if value is None:
            return "Calculating" if calculating else "--"
        return f"{float(value):.{decimals}f}"

    @staticmethod
    def _fmt_percent(value) -> str:
        if value is None:
            return "Calculating"
        return f"{float(value):.2f}%"

    @staticmethod
    def _fmt_seconds(value) -> str:
        if value is None:
            return "Calculating"
        return f"{float(value):.2f} s"

    @staticmethod
    def _fmt_milliseconds(value) -> str:
        if value is None:
            return "Calculating"
        return f"{float(value) * 1000.0:.2f} ms"

    @property
    def band_powers(self) -> dict:
        return self._latest_band_powers

    @property
    def peak_frequencies(self) -> dict:
        return self._latest_peaks

    @property
    def ppg_metrics(self) -> dict:
        return dict(self._latest_ppg_metrics)

    @property
    def filter_enabled(self) -> bool:
        return self._eeg_filter_enabled

    @property
    def iapf_status(self) -> dict:
        return dict(self._iapf_status)


def _resistance_value_for_channel(data: dict, channel: str) -> float:
    if not data:
        return float("inf")
    aliases = {
        "O1": ("O1", "01"),
        "O2": ("O2", "02"),
        "T3": ("T3",),
        "T4": ("T4",),
    }
    for key in aliases.get(channel, (channel,)):
        if key in data:
            return data[key]
    return float("inf")
