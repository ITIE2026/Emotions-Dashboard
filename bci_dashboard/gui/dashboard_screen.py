"""
DashboardScreen – wide-format laptop dashboard matching the Capsule reference app.

Two-column layout:
  LEFT:   Session info bar, electrode resistances, PSD spectrum, electrode table
  RIGHT:  Indices & Scores, Rhythms, Frequency Peaks, State Characteristics, Heart Rate
"""
import os
import uuid
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QScrollArea, QPushButton, QSplitter, QFrame,
)
from PySide6.QtCore import Qt, QTimer

from gui.widgets.metric_card import MetricCard
from gui.widgets.fatigue_panel import FatiguePanel
from gui.widgets.spectrum_chart import SpectrumChart
from gui.widgets.electrode_table import ElectrodeTable
from utils.config import (
    BG_CARD, BG_PRIMARY, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT_GREEN, ACCENT_RED, ACCENT_CYAN, ACCENT_ORANGE, ACCENT_TEAL,
    SESSION_DIR,
)
from utils.helpers import (
    resist_color, resist_label, stress_label,
    recommendation_label, compute_band_powers, compute_peak_frequencies,
)


def _section_header(text: str, colour: str = ACCENT_GREEN) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 14px; font-weight: bold; color: {colour}; "
        f"padding: 6px 0 2px 0; background: transparent;"
    )
    return lbl


def _metric_row(label: str, initial: str = "0.00") -> tuple:
    """Return (name_label, value_label) pair for a metrics grid."""
    name = QLabel(label)
    name.setStyleSheet(
        f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
    )
    val = QLabel(initial)
    val.setStyleSheet(
        f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
    )
    return name, val


class DashboardScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions = {}
        self._latest_productivity = {}
        self._latest_cardio = {}
        self._latest_indexes = {}
        self._latest_physio = {}
        self._latest_band_powers = {}
        self._latest_peaks = {}
        # Rate-limiting timestamps for high-frequency callbacks
        self._last_psd_t = 0.0
        self._session_file: str | None = None
        self._session_id = str(uuid.uuid4())
        self._session_start = datetime.now()
        self._build_ui()

        # 1-Hz timer for session duration
        self._dur_timer = QTimer(self)
        self._dur_timer.setInterval(1000)
        self._dur_timer.timeout.connect(self._update_duration)
        self._dur_timer.start()

        # 10-Hz timer for EEG trace refresh
        self._eeg_timer = QTimer(self)
        self._eeg_timer.setInterval(100)
        self._eeg_timer.timeout.connect(self._electrode_table.refresh)

    # ══════════════════════════════════════════════════════════════════
    #  UI construction
    # ══════════════════════════════════════════════════════════════════
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Session info bar (top) ────────────────────────────────────
        info_bar = QWidget()
        info_bar.setStyleSheet(
            f"background: {BG_CARD}; border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(16, 6, 16, 6)
        info_layout.setSpacing(24)

        # Connection + serial
        self._conn_label = QLabel("IsConnected: false")
        self._conn_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._serial_label = QLabel("Serial: --")
        self._serial_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        info_layout.addWidget(self._conn_label)
        info_layout.addWidget(self._serial_label)

        # Mode + battery
        self._mode_label = QLabel("Mode: Unspecified")
        self._mode_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._battery_label = QLabel("Battery: ?")
        self._battery_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        info_layout.addWidget(self._mode_label)
        info_layout.addWidget(self._battery_label)

        # Session times
        session_col = QVBoxLayout()
        session_col.setSpacing(0)
        self._start_label = QLabel(
            f"Session Start: {self._session_start.strftime('%H:%M:%S')}"
        )
        self._start_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._duration_label = QLabel("Session Duration: 00:00:00")
        self._duration_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._id_label = QLabel(f"Session ID: {self._session_id}")
        self._id_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        session_col.addWidget(self._start_label)
        session_col.addWidget(self._duration_label)
        session_col.addWidget(self._id_label)
        info_layout.addLayout(session_col)

        # Electrode resistances (top right)
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

        # ── Main content: two-column splitter ─────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter {{ background: {BG_PRIMARY}; }}"
            f"QSplitter::handle {{ background: {BORDER_SUBTLE}; width: 2px; }}"
        )

        # ═══════ LEFT COLUMN ═══════
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 4, 8)
        left_layout.setSpacing(6)

        # PSD Spectrum chart
        self._spectrum = SpectrumChart()
        left_layout.addWidget(self._spectrum, stretch=3)

        # Electrode table
        self._electrode_table = ElectrodeTable()
        left_layout.addWidget(self._electrode_table, stretch=2)

        splitter.addWidget(left_widget)

        # ═══════ RIGHT COLUMN ═══════
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 8, 8, 8)
        right_layout.setSpacing(4)

        # ── Indices and Scores ────────────────────────────────────────
        right_layout.addWidget(_section_header("Indices and Scores", ACCENT_GREEN))

        idx_grid = QGridLayout()
        idx_grid.setSpacing(6)
        idx_grid.setColumnStretch(0, 1)
        idx_grid.setColumnStretch(1, 1)
        idx_grid.setColumnStretch(2, 1)

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
        for display_name, key, row, col in idx_items:
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            v = QVBoxLayout(container)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(1)
            nlbl = QLabel(f"<b>{display_name}</b>")
            nlbl.setStyleSheet(
                f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent;"
            )
            vlbl = QLabel("0.00")
            vlbl.setStyleSheet(
                f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
            )
            v.addWidget(nlbl)
            v.addWidget(vlbl)
            idx_grid.addWidget(container, row, col)
            self._idx_labels[key] = vlbl

        right_layout.addLayout(idx_grid)

        # ── Rhythms ──────────────────────────────────────────────────
        right_layout.addWidget(_section_header("Rhythms", ACCENT_CYAN))

        rhythm_row = QHBoxLayout()
        rhythm_row.setSpacing(16)
        self._rhythm_labels = {}
        for name in ["Alpha", "Beta", "Theta", "SMR"]:
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            v = QVBoxLayout(container)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(1)
            nlbl = QLabel(f"<b>{name}:</b>")
            nlbl.setStyleSheet(
                f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
            )
            vlbl = QLabel("0.000")
            vlbl.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
            )
            v.addWidget(nlbl)
            v.addWidget(vlbl)
            rhythm_row.addWidget(container)
            self._rhythm_labels[name.lower()] = vlbl
        rhythm_row.addStretch()
        right_layout.addLayout(rhythm_row)

        # ── Instant Frequency Peaks ──────────────────────────────────
        right_layout.addWidget(_section_header("Instant Frequency Peaks", ACCENT_ORANGE))

        peaks_row = QHBoxLayout()
        peaks_row.setSpacing(16)
        self._peak_labels = {}
        for name, key in [("Alpha Peak", "alpha_peak"),
                           ("Beta Peak", "beta_peak"),
                           ("Theta Peak", "theta_peak")]:
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            v = QVBoxLayout(container)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(1)
            nlbl = QLabel(f"<b>{name}:</b>")
            nlbl.setStyleSheet(
                f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;"
            )
            vlbl = QLabel("0.0 Hz")
            vlbl.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent;"
            )
            v.addWidget(nlbl)
            v.addWidget(vlbl)
            peaks_row.addWidget(container)
            self._peak_labels[key] = vlbl
        peaks_row.addStretch()
        right_layout.addLayout(peaks_row)

        # ── State Characteristics ────────────────────────────────────
        right_layout.addWidget(_section_header("State Characteristics", ACCENT_RED))

        state_row = QHBoxLayout()
        state_row.setSpacing(24)

        self._recommendation_lbl = QLabel("No recommendation")
        self._recommendation_lbl.setStyleSheet(
            f"font-size: 12px; color: {ACCENT_GREEN}; background: transparent;"
        )
        self._stress_state_lbl = QLabel("No stress")
        self._stress_state_lbl.setStyleSheet(
            f"font-size: 12px; color: {ACCENT_RED}; background: transparent;"
        )
        self._valid_state_lbl = QLabel("Valid State")
        self._valid_state_lbl.setStyleSheet(
            f"font-size: 12px; color: {ACCENT_GREEN}; background: transparent;"
        )
        state_row.addWidget(self._recommendation_lbl)
        state_row.addWidget(self._stress_state_lbl)
        state_row.addWidget(self._valid_state_lbl)
        state_row.addStretch()
        right_layout.addLayout(state_row)

        # ── Heart Rate card ──────────────────────────────────────────
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
        hr_layout.addWidget(hr_icon)

        hr_text = QVBoxLayout()
        hr_text.setSpacing(1)
        self._hr_value = QLabel("0.00 bpm")
        self._hr_value.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {ACCENT_RED}; "
            f"background: transparent; border: none;"
        )
        self._si_value = QLabel("Stress Index: 0.0")
        self._si_value.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        hr_text.addWidget(self._hr_value)
        hr_text.addWidget(self._si_value)
        hr_layout.addLayout(hr_text)
        hr_layout.addStretch()
        right_layout.addWidget(hr_card)

        # ── Fatigue panel ────────────────────────────────────────────
        self._fatigue_panel = FatiguePanel()
        right_layout.addWidget(self._fatigue_panel)

        # ── Primary metric cards row ─────────────────────────────────
        right_layout.addWidget(_section_header("Emotions", "#B388FF"))
        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        self._card_focus = MetricCard("Focus", "#B388FF")
        self._card_chill = MetricCard("Calmness", "#81C784")
        self._card_stress = MetricCard("Tension", "#FF8A65")
        self._card_anger = MetricCard("Anger", "#E57373")
        self._card_self_ctrl = MetricCard("Self-ctrl", "#4DD0E1")
        for c in [self._card_focus, self._card_chill, self._card_stress,
                   self._card_anger, self._card_self_ctrl]:
            cards_row.addWidget(c)
        right_layout.addLayout(cards_row)

        right_layout.addStretch()

        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)

        # Set initial splitter sizes (55:45)
        splitter.setSizes([600, 500])
        outer.addWidget(splitter, stretch=1)

    # ══════════════════════════════════════════════════════════════════
    #  Data input slots
    # ══════════════════════════════════════════════════════════════════
    def on_emotions(self, data: dict):
        try:
            self._latest_emotions = data
            self._card_focus.set_value(data.get("focus", 0))
            self._card_chill.set_value(data.get("chill", 0))
            self._card_stress.set_value(data.get("stress", 0))
            self._card_anger.set_value(data.get("anger", 0))
            self._card_self_ctrl.set_value(data.get("selfControl", 0))
        except Exception:
            pass

    def on_productivity(self, data: dict):
        try:
            self._latest_productivity = data
            self._idx_labels["relaxation_idx"].setText(f"{data.get('relaxationScore', 0):.2f}")
            self._idx_labels["concentration_idx"].setText(f"{data.get('concentrationScore', 0):.2f}")
            self._idx_labels["fatigue_score"].setText(f"{data.get('fatigueScore', 0):.2f}")
            self._idx_labels["reverse_fatigue"].setText(f"{data.get('reverseFatigueScore', 0):.2f}")
            self._idx_labels["productivity_pct"].setText(f"{data.get('productivityScore', 0):.0f}%")
            self._idx_labels["alpha_gravity"].setText(f"{data.get('gravityScore', 0):.2f}")
            self._idx_labels["accumulated_fatigue"].setText(f"{data.get('accumulatedFatigue', 0):.2f}")

            self._fatigue_panel.update_data(
                fatigue_score=data.get("fatigueScore", 0),
                growth_rate=data.get("fatigueGrowthRate", 0),
                accumulated=data.get("accumulatedFatigue", 0),
                recommendation=self._latest_indexes.get("relaxation_recommendation", 0),
            )
        except Exception:
            pass

    def on_indexes(self, data: dict):
        try:
            self._latest_indexes = data
            # Update recommendation from indexes
            rec = data.get("relaxation_recommendation", 0)
            rec_text = recommendation_label(rec) or "No recommendation"
            self._recommendation_lbl.setText(rec_text)

            stress_val = data.get("stress", 0)
            s_text = stress_label(stress_val)
            s_colour = ACCENT_GREEN if stress_val == 0 else ACCENT_RED
            self._stress_state_lbl.setText(s_text)
            self._stress_state_lbl.setStyleSheet(
                f"font-size: 12px; color: {s_colour}; background: transparent;"
            )
        except Exception:
            pass

    def on_cardio(self, data: dict):
        self._latest_cardio = data
        hr = data.get("heartRate", 0)
        self._hr_value.setText(f"{hr:.2f} bpm")
        si = data.get("stressIndex", 0)
        self._si_value.setText(f"Stress Index: {si:.1f}")

    def on_physio_states(self, data: dict):
        self._latest_physio = data
        # Update valid state indicator
        has_nfb_art = data.get("nfbArtifacts", False)
        has_cardio_art = data.get("cardioArtifacts", False)
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

    def on_psd(self, psd_data):
        """Receive PSD data from DeviceManager (rate-limited to 5 Hz)."""
        import time
        now = time.monotonic()
        if now - self._last_psd_t < 0.2:
            return
        self._last_psd_t = now
        try:
            # Extract frequency and power arrays from SDK PSD object
            n_freq = psd_data.get_frequencies_count()
            n_channels = psd_data.get_channels_count()

            freqs = []
            for f_idx in range(n_freq):
                freqs.append(float(psd_data.get_frequency(f_idx)))

            # Average power across channels
            avg_power = [0.0] * n_freq
            for ch_idx in range(n_channels):
                for f_idx in range(n_freq):
                    avg_power[f_idx] += float(psd_data.get_psd(ch_idx, f_idx))
            if n_channels > 0:
                avg_power = [p / n_channels for p in avg_power]

            # Update spectrum chart
            self._spectrum.update_psd(freqs, avg_power)

            # Compute and update band powers
            import numpy as np
            f_arr = np.array(freqs)
            p_arr = np.array(avg_power)
            self._latest_band_powers = compute_band_powers(f_arr, p_arr)
            self._latest_peaks = compute_peak_frequencies(f_arr, p_arr)

            # Update rhythm labels
            for name in ["alpha", "beta", "theta", "smr"]:
                val = self._latest_band_powers.get(name, 0.0)
                if val >= 0.01:
                    txt = f"{val:.3f}"
                elif val >= 0.000001:
                    txt = f"{val:.6f}"
                else:
                    txt = f"{val:.2e}"
                self._rhythm_labels[name].setText(txt)

            # Update peak labels
            for key in ["alpha_peak", "beta_peak", "theta_peak"]:
                val = self._latest_peaks.get(key, 0.0)
                self._peak_labels[key].setText(f"{val:.1f} Hz")

        except Exception:
            pass

    def on_eeg(self, eeg_timed_data):
        """Receive EEG data from DeviceManager.

        Buffer all samples for the live per-channel EEG traces.
        """
        self._electrode_table.add_eeg_data(eeg_timed_data)

    def on_artifacts(self, artifacts):
        """Receive artifact data from DeviceManager."""
        self._electrode_table.update_artifacts(artifacts)

    def on_resistance(self, data: dict):
        """Update electrode resistance display in the info bar."""
        for ch, lbl in self._resist_labels.items():
            ohms = data.get(ch, float("inf"))
            text = resist_label(ohms)
            colour = resist_color(ohms)
            lbl.setText(f"{ch}: {text}")
            lbl.setStyleSheet(
                f"font-size: 12px; color: {colour}; background: transparent;"
            )

    # ── Session info ──────────────────────────────────────────────────
    def set_session_info(self, connected: bool = False, serial: str = "--",
                         battery: int = -1):
        self._conn_label.setText(f"IsConnected: {str(connected).lower()}")
        self._serial_label.setText(f"Serial: {serial}")
        if battery >= 0:
            self._battery_label.setText(f"Battery: {battery}%")

    def set_mode(self, mode_str: str):
        self._mode_label.setText(f"Mode: {mode_str}")

    def set_battery(self, pct: int):
        self._battery_label.setText(f"Battery: {pct}%")

    def reset_session(self):
        """Reset session counters for a new session."""
        self._session_id = str(uuid.uuid4())
        self._session_start = datetime.now()
        self._start_label.setText(
            f"Session Start: {self._session_start.strftime('%H:%M:%S')}"
        )
        self._id_label.setText(f"Session ID: {self._session_id}")
        self._electrode_table.set_session_start()
        self._electrode_table.clear()
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
        os.makedirs(SESSION_DIR, exist_ok=True)
        os.startfile(SESSION_DIR)

    # ── Expose band/peak data for CSV logger ─────────────────────────
    @property
    def band_powers(self) -> dict:
        return self._latest_band_powers

    @property
    def peak_frequencies(self) -> dict:
        return self._latest_peaks
