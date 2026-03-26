"""
TrainingScreen - shared EEG training suite with multiple neurofeedback games.
"""
from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.eeg_game_base import READY_STREAK_TARGET, TrainingGameSpec
from gui.neuroflow_training_page import NeuroflowTrainingPage
from gui.training_audio import AdaptiveMusicEngine, TRAINING_AUDIO_ASSET_DIR
from gui.training_games import TRAINING_SPECS, active_training_specs
from gui.widgets.mind_maze_board import MindMazeBoard, MindMazeControlBar
from gui.widgets.training_game_widgets import (
    BubbleBurstWidget,
    CandyCascadeWidget,
    CalmCurrentWidget,
    FullRebootWidget,
    JumpBallWidget,
    NeonDriftArenaWidget,
    NeuroMusicFlowWidget,
    NeuroRacerWidget,
    PatternRecallWidget,
    ProstheticArmWidget,
    SpaceShooterWidget,
    TugOfWarWidget,
)
from prosthetic_arm.arm_lab_panel import ArmLabPanel
from prosthetic_arm.arm_state import ArmStateEngine, dominant_state_for_metrics
from prosthetic_arm.arduino_arm import ArduinoArmController
from prosthetic_arm.brainbit_backend import BrainBitMetricAdapter
from prosthetic_arm.capsule_backend import CapsuleMetricAdapter
from utils.config import ACCENT_GREEN, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


class TrainingCard(QFrame):
    def __init__(
        self,
        eyebrow: str,
        title: str,
        duration: str,
        description: str,
        preview_label: str,
        colors: tuple[str, str],
        enabled: bool = False,
        callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self._enabled = enabled
        self._callback = callback
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        preview = QLabel(preview_label)
        preview.setAlignment(Qt.AlignCenter)
        preview.setFixedSize(220, 150)
        preview.setStyleSheet(
            "QLabel { border-radius: 26px; font-size: 22px; font-weight: bold; color: #f8fafc; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors[0]}, stop:1 {colors[1]}); }}"
        )
        layout.addWidget(preview)

        text_col = QVBoxLayout()
        text_col.setSpacing(8)
        eyebrow_lbl = QLabel(eyebrow)
        eyebrow_lbl.setStyleSheet(f"font-size: 12px; color: {ACCENT_GREEN};")
        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {TEXT_PRIMARY};")
        meta_lbl = QLabel(duration if enabled else f"{duration}   Coming soon")
        meta_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        description_lbl = QLabel(description)
        description_lbl.setWordWrap(True)
        description_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        text_col.addWidget(eyebrow_lbl)
        text_col.addWidget(title_lbl)
        text_col.addWidget(meta_lbl)
        text_col.addWidget(description_lbl)
        text_col.addStretch()
        layout.addLayout(text_col, stretch=1)

        border = "#35313a" if enabled else "#26272c"
        hover = "#1e212b" if enabled else "#16181d"
        self.setStyleSheet(
            f"QFrame {{ background: #0d0f13; border: 1px solid {border}; border-radius: 30px; }}"
            f"QFrame:hover {{ background: {hover}; }}"
        )

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API
        if self._enabled and self._callback and event.button() == Qt.LeftButton:
            self._callback()
        super().mouseReleaseEvent(event)


class SoundtrackCard(QFrame):
    def __init__(self, name: str, description: str, colors: tuple[str, str], callback, parent=None):
        super().__init__(parent)
        self._name = name
        self._callback = callback
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        tile = QLabel(self._name.split()[0].upper())
        tile.setAlignment(Qt.AlignCenter)
        tile.setFixedSize(120, 120)
        tile.setStyleSheet(
            "QLabel { border-radius: 24px; font-size: 18px; font-weight: bold; color: #f8fafc; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors[0]}, stop:1 {colors[1]}); }}"
        )
        layout.addWidget(tile)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        self._state_lbl = QLabel("Tap to select")
        self._state_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        name_lbl = QLabel(self._name)
        name_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {TEXT_PRIMARY};")
        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        text_col.addWidget(self._state_lbl)
        text_col.addWidget(name_lbl)
        text_col.addWidget(desc_lbl)
        text_col.addStretch()
        layout.addLayout(text_col, stretch=1)
        self._apply_style()

    @property
    def name(self) -> str:
        return self._name

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(
                "QFrame { background: #f6f5f3; border: 1px solid #f6f5f3; border-radius: 28px; }"
            )
            self._state_lbl.setText("Selected")
            self._state_lbl.setStyleSheet("font-size: 12px; color: #434343;")
        else:
            self.setStyleSheet(
                f"QFrame {{ background: #17191f; border: 1px solid {BORDER_SUBTLE}; border-radius: 28px; }}"
            )
            self._state_lbl.setText("Tap to select")
            self._state_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._callback(self._name)
        super().mouseReleaseEvent(event)


class TrainingScreen(QWidget):
    neuroflow_quick_calibration_requested = Signal()
    IMMERSIVE_GAME_IDS = {"tug_of_war", "space_shooter", "neuro_racer", "bubble_burst", "neon_drift_arena"}

    SOUNDTRACKS = {
        "Aurora Drift": {
            "description": "Glassy ambient pads with a cool cinematic horizon and gentle focus lift.",
            "colors": ("#21405b", "#8fd8e8"),
            "bundle": "aurora_drift",
            "stem_bias": {"base": 1.03, "relax": 1.06, "focus": 0.98, "concentration": 0.95, "sleep": 1.02},
        },
        "Velvet Horizon": {
            "description": "Deep warm cinematic beds with softer edges for calm and sleep-oriented sessions.",
            "colors": ("#3a304f", "#c1b7e5"),
            "bundle": "velvet_horizon",
            "stem_bias": {"base": 1.02, "relax": 1.10, "focus": 0.92, "concentration": 0.90, "sleep": 1.10},
        },
        "Ember Pulse": {
            "description": "A warmer pulse-driven cinematic blend with brighter motion for focus and arcade play.",
            "colors": ("#5b271d", "#ef9c5f"),
            "bundle": "ember_pulse",
            "stem_bias": {"base": 0.98, "relax": 0.94, "focus": 1.06, "concentration": 1.08, "sleep": 0.92},
        },
    }

    MUSIC_FLOW_SOUNDTRACKS = {
        "Monsoon Strings": {
            "description": "Warm fingerstyle guitar and soft drone textures that deepen beautifully when relaxation rises.",
            "colors": ("#24443c", "#d8c27a"),
            "bundle": "monsoon_strings",
            "stem_bias": {"base": 1.04, "relax": 1.10, "focus": 0.96, "concentration": 0.94, "sleep": 1.03},
        },
        "Saffron Sunset": {
            "description": "A brighter picked-acoustic pack with gentle melodic lift for focused, balanced sessions.",
            "colors": ("#5a2e1d", "#f0b56a"),
            "bundle": "saffron_sunset",
            "stem_bias": {"base": 1.00, "relax": 0.96, "focus": 1.08, "concentration": 1.10, "sleep": 0.92},
        },
        "Mehfil Glow": {
            "description": "Intimate late-evening guitar loops with mellow resonance and smooth lead phrases.",
            "colors": ("#352a4f", "#caa9e5"),
            "bundle": "mehfil_glow",
            "stem_bias": {"base": 1.02, "relax": 1.06, "focus": 1.00, "concentration": 0.98, "sleep": 1.00},
        },
    }

    ALL_SOUNDTRACKS = {**SOUNDTRACKS, **MUSIC_FLOW_SOUNDTRACKS}

    PREVIEW_CARDS = [
        {
            "section": "Improve concentration",
            "eyebrow": "Skill builder",
            "title": "Training skills",
            "duration": "12 min",
            "description": "A roadmap card for a future procedural-learning trainer.",
            "preview_label": "FOCUS",
            "colors": ("#61533f", "#c9aa7a"),
        },
    ]

    def __init__(self, parent=None, runtime=None):
        super().__init__(parent)
        self._phaseon_runtime = runtime
        self._owns_arm_runtime = runtime is None
        self._latest_emotions: dict = {}
        self._latest_productivity: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}
        self._last_productivity_t = 0.0
        self._latest_connection = {"connected": False, "serial": "--"}
        self._streaming_active = False
        self._view_active = False
        self._latest_band_powers: dict = {}
        self._latest_peak_freqs: dict = {}
        self._latest_psd_t: float | None = None
        self._latest_resistances: dict = {}
        self._latest_iapf_status: dict = {
            "frequency": None,
            "source": "Not set",
            "status": "Not set",
            "applied": False,
        }
        self._eeg_sample_rate_hz: float | None = None
        self._eeg_channel_names: list[str] = []
        self._selected_soundtrack = "Aurora Drift"
        self._selected_music_flow_soundtrack = "Monsoon Strings"
        self._level_started_at = 0.0
        self._audio_dir = TRAINING_AUDIO_ASSET_DIR
        self._settings = QSettings("BCI Dashboard", "EEGTrainingSuite")
        self._game_specs = {spec.game_id: spec for spec in TRAINING_SPECS}
        self._active_specs = active_training_specs()
        self._current_game_id = "mind_maze"
        self._controller = self._game_specs[self._current_game_id].controller_factory()
        self._music_engine = AdaptiveMusicEngine(self, self._audio_dir, self.ALL_SOUNDTRACKS)
        self._arm_backend_mode = "capsule"
        self._arm_backend_status = "Using live Capsule productivity metrics."
        self._arm_live_metrics = {
            "attention": 0.0,
            "relaxation": 0.0,
            "dominant_state": "Balanced",
        }
        self._arm_last_metrics_t = 0.0
        self._arm_state_history: list[str] = []
        self._arm_preview_state = "OPEN"
        if runtime is not None:
            self._arm_state_engine = runtime.arm_state_engine
            self._capsule_arm_backend = runtime.capsule_backend
            self._brainbit_arm_backend = runtime.brainbit_backend
            self._arduino_arm = runtime.arduino_arm
        else:
            self._arm_state_engine = ArmStateEngine()
            self._capsule_arm_backend = CapsuleMetricAdapter(self)
            self._brainbit_arm_backend = BrainBitMetricAdapter(self)
            self._arduino_arm = ArduinoArmController(self)

        self._calibration_timer = QTimer(self)
        self._calibration_timer.setInterval(250)
        self._calibration_timer.timeout.connect(self._tick_calibration)

        self._gameplay_timer = QTimer(self)
        self._gameplay_timer.setInterval(250)
        self._gameplay_timer.timeout.connect(self._tick_gameplay)

        self._build_ui()
        self._wire_arm_lab()
        self._load_settings()
        self._ensure_audio_assets()
        self._rebuild_soundtrack_cards()
        self._refresh_live_labels()
        self._show_catalog()

    @property
    def _current_spec(self) -> TrainingGameSpec:
        return self._game_specs[self._current_game_id]

    def _build_ui(self):
        self.setStyleSheet("background: #000000; color: #f8fafc;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._stack = QStackedWidget()
        self._catalog_page = self._build_catalog_page()
        self._detail_page = self._build_detail_page()
        self._settings_page = self._build_settings_page()
        self._arm_lab_page = self._build_arm_lab_page()
        self._neuroflow_page = self._build_neuroflow_page()
        self._calibration_page = self._build_calibration_page()
        self._gameplay_page = self._build_gameplay_page()
        self._result_page = self._build_result_page()
        for page in [
            self._catalog_page,
            self._detail_page,
            self._settings_page,
            self._arm_lab_page,
            self._neuroflow_page,
            self._calibration_page,
            self._gameplay_page,
            self._result_page,
        ]:
            self._stack.addWidget(page)
        root.addWidget(self._stack)

    def _build_catalog_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setMaximumWidth(980)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(44, 28, 44, 40)
        layout.setSpacing(22)

        layout.addWidget(self._device_badge())
        title = QLabel("Trainings")
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title)

        self._catalog_live_lbl = QLabel("Waiting for concentration and relaxation metrics.")
        self._catalog_live_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._catalog_live_lbl)

        section_order = [
            "Reduce stress and tension",
            "Improve concentration",
            "Assistive motor control",
            "Arcade neurofeedback",
            "Memory and cognitive control",
            "Relax before sleep",
        ]
        for section in section_order:
            cards = [spec for spec in self._active_specs if spec.section == section]
            previews = [card for card in self.PREVIEW_CARDS if card["section"] == section]
            if not cards and not previews:
                continue
            layout.addWidget(self._section_header(section))
            for spec in cards:
                layout.addWidget(
                    TrainingCard(
                        spec.eyebrow,
                        spec.card_title,
                        spec.duration,
                        spec.description,
                        spec.preview_label,
                        spec.colors,
                        enabled=True,
                        callback=lambda game_id=spec.game_id: self._show_detail(game_id),
                    )
                )
            for preview in previews:
                layout.addWidget(
                    TrainingCard(
                        preview["eyebrow"],
                        preview["title"],
                        preview["duration"],
                        preview["description"],
                        preview["preview_label"],
                        preview["colors"],
                        enabled=False,
                    )
                )

        layout.addStretch()
        outer.addWidget(panel, alignment=Qt.AlignHCenter)
        scroll.setWidget(container)
        return scroll

    def _build_detail_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        layout.setSpacing(18)

        layout.addWidget(self._device_badge())
        self._detail_hero = QLabel("MIND MAZE")
        self._detail_hero.setAlignment(Qt.AlignCenter)
        self._detail_hero.setFixedHeight(220)
        layout.addWidget(self._detail_hero)

        self._detail_meta_lbl = QLabel("")
        self._detail_meta_lbl.setStyleSheet(f"font-size: 14px; color: {ACCENT_GREEN};")
        layout.addWidget(self._detail_meta_lbl)

        self._detail_title_lbl = QLabel("")
        self._detail_title_lbl.setWordWrap(True)
        self._detail_title_lbl.setStyleSheet("font-size: 46px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(self._detail_title_lbl)
        self._detail_body_lbl = QLabel("")
        self._detail_body_lbl.setWordWrap(True)
        self._detail_body_lbl.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._detail_body_lbl)

        layout.addWidget(self._section_header("Instruction"))
        self._detail_instruction_lbl = QLabel("")
        self._detail_instruction_lbl.setWordWrap(True)
        self._detail_instruction_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._detail_instruction_lbl)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)
        self._detail_conc_lbl = self._metric_chip("Concentration", "0.0")
        self._detail_relax_lbl = self._metric_chip("Relaxation", "0.0")
        metrics_row.addWidget(self._detail_conc_lbl)
        metrics_row.addWidget(self._detail_relax_lbl)
        metrics_row.addStretch()
        layout.addLayout(metrics_row)

        self._detail_availability_lbl = QLabel("")
        self._detail_availability_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._detail_availability_lbl)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self._detail_settings_btn = self._pill_button("Settings", filled=False)
        self._detail_settings_btn.clicked.connect(self._show_settings)
        self._detail_start_btn = self._pill_button("Start", filled=True)
        self._detail_start_btn.clicked.connect(self._begin_calibration_flow)
        self._detail_arm_lab_btn = self._pill_button("Arm Lab", filled=False)
        self._detail_arm_lab_btn.clicked.connect(self._show_arm_lab)
        back_btn = self._pill_button("Back", filled=False)
        back_btn.clicked.connect(self._show_catalog)
        buttons.addWidget(self._detail_settings_btn)
        buttons.addWidget(self._detail_start_btn)
        buttons.addWidget(self._detail_arm_lab_btn)
        buttons.addWidget(back_btn)
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        layout.setSpacing(16)

        layout.addWidget(self._device_badge())
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 46px; font-weight: bold; color: #f8fafc;")
        self._settings_subtitle_lbl = QLabel("")
        self._settings_subtitle_lbl.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        layout.addWidget(title)
        layout.addWidget(self._settings_subtitle_lbl)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 34px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(18)
        self._settings_heading_lbl = QLabel("Choose a soundtrack")
        self._settings_heading_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        self._settings_copy_lbl = QLabel("")
        self._settings_copy_lbl.setWordWrap(True)
        self._settings_copy_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        card_layout.addWidget(self._settings_heading_lbl)
        card_layout.addWidget(self._settings_copy_lbl)

        self._soundtrack_cards = []
        self._soundtrack_cards_layout = QVBoxLayout()
        self._soundtrack_cards_layout.setSpacing(18)
        card_layout.addLayout(self._soundtrack_cards_layout)

        layout.addWidget(card)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        back_btn = self._pill_button("Back", filled=False)
        back_btn.clicked.connect(lambda: self._show_detail(self._current_game_id))
        save_btn = self._pill_button("Save", filled=True)
        save_btn.clicked.connect(self._save_settings)
        buttons.addWidget(back_btn)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _build_arm_lab_page(self):
        panel = ArmLabPanel()
        panel.back_button.clicked.connect(lambda: self._show_detail(self._current_game_id))
        return panel

    def _build_neuroflow_page(self):
        page = NeuroflowTrainingPage()
        page.back_requested.connect(lambda: self._show_detail(self._current_game_id))
        page.quick_calibration_requested.connect(self.neuroflow_quick_calibration_requested.emit)
        return page

    def _wire_arm_lab(self):
        self._arm_lab_page.source_changed.connect(self._set_arm_backend_mode)
        self._arm_lab_page.brainbit_toggle_requested.connect(self._toggle_brainbit_connection)
        self._arm_lab_page.arduino_toggle_requested.connect(self._toggle_arduino_connection)
        self._arm_lab_page.iapf_requested.connect(self._start_arm_iapf)
        self._arm_lab_page.baseline_requested.connect(self._start_arm_baseline)

        self._capsule_arm_backend.status_changed.connect(lambda text: self._on_arm_source_status("capsule", text))
        self._capsule_arm_backend.connection_changed.connect(
            lambda connected: self._on_arm_source_connection("capsule", connected)
        )
        self._capsule_arm_backend.metrics_changed.connect(lambda data: self._on_arm_metrics("capsule", data))

        self._brainbit_arm_backend.status_changed.connect(lambda text: self._on_arm_source_status("brainbit", text))
        self._brainbit_arm_backend.connection_changed.connect(
            lambda connected: self._on_arm_source_connection("brainbit", connected)
        )
        self._brainbit_arm_backend.metrics_changed.connect(lambda data: self._on_arm_metrics("brainbit", data))
        self._brainbit_arm_backend.resistance_changed.connect(
            lambda data: self._on_arm_resistance("brainbit", data)
        )
        self._brainbit_arm_backend.waves_changed.connect(
            lambda alpha, beta: self._on_arm_waves("brainbit", alpha, beta)
        )
        self._brainbit_arm_backend.raw_uv_changed.connect(lambda data: self._on_arm_raw_uv("brainbit", data))
        self._brainbit_arm_backend.calibration_mode_changed.connect(
            lambda mode: self._arm_lab_page.set_calibration(mode, 0)
        )
        self._brainbit_arm_backend.calibration_progress_changed.connect(
            lambda progress: self._arm_lab_page.set_calibration("BrainBit", progress)
        )

        self._arduino_arm.connection_changed.connect(self._on_arduino_connection)
        self._arduino_arm.status_changed.connect(self._on_arduino_status)
        self._sync_arm_lab_panel()

    def _arm_feature_active(self) -> bool:
        current_page = self._stack.currentWidget()
        return self._current_game_id == "prosthetic_arm" and current_page in {
            self._detail_page,
            self._arm_lab_page,
            self._calibration_page,
            self._gameplay_page,
            self._result_page,
        }

    def _arm_metrics_are_fresh(self) -> bool:
        return (time.monotonic() - self._arm_last_metrics_t) <= 2.0

    def _current_metric_pair(self) -> tuple[float, float]:
        if self._current_game_id == "prosthetic_arm":
            return (
                float(self._arm_live_metrics.get("attention", 0.0)),
                float(self._arm_live_metrics.get("relaxation", 0.0)),
            )
        return (
            float(self._latest_productivity.get("concentrationScore", 0.0)),
            float(self._latest_productivity.get("relaxationScore", 0.0)),
        )

    def _current_metrics_fresh(self) -> bool:
        if self._current_game_id == "prosthetic_arm":
            return self._arm_metrics_are_fresh()
        return (time.monotonic() - self._last_productivity_t) <= 2.0

    def _show_arm_lab(self):
        self._stop_runtime_loops()
        self._sync_arm_lab_panel()
        self._stack.setCurrentWidget(self._arm_lab_page)

    def _set_arm_backend_mode(self, mode: str):
        if mode not in {"capsule", "brainbit"}:
            return
        if self._arm_backend_mode == mode:
            self._sync_arm_lab_panel()
            return
        self._arm_backend_mode = mode
        self._arm_state_engine.reset()
        self._arm_state_history = []
        self._arm_preview_state = "OPEN"
        self._arm_lab_page.clear_raw()
        self._arm_lab_page.clear_waves()
        if mode == "capsule":
            self._brainbit_arm_backend.disconnect_device()
            self._arm_backend_status = "Using live Capsule productivity metrics."
            if self._latest_productivity:
                self._capsule_arm_backend.ingest_productivity(self._latest_productivity)
            else:
                self._arm_last_metrics_t = 0.0
        else:
            self._arm_last_metrics_t = 0.0
            self._arm_live_metrics = {
                "attention": 0.0,
                "relaxation": 0.0,
                "dominant_state": "Balanced",
            }
            self._arm_backend_status = "BrainBit mode selected. Connect a device to begin streaming."
        self._sync_arm_lab_panel()
        self._refresh_live_labels()

    def _toggle_brainbit_connection(self):
        if self._arm_backend_mode != "brainbit":
            self._set_arm_backend_mode("brainbit")
        if self._brainbit_arm_backend.is_connected:
            self._brainbit_arm_backend.disconnect_device()
        else:
            self._brainbit_arm_backend.connect_device()

    def _toggle_arduino_connection(self):
        if self._arduino_arm.is_connected:
            self._arduino_arm.disconnect_device()
            return
        port_text = self._arm_lab_page.manual_port_edit.text().strip()
        self._arduino_arm.connect_device(port_text or None)

    def _start_arm_iapf(self):
        if self._arm_backend_mode != "brainbit":
            self._set_arm_backend_mode("brainbit")
        self._brainbit_arm_backend.start_iapf_calibration()

    def _start_arm_baseline(self):
        if self._arm_backend_mode != "brainbit":
            self._set_arm_backend_mode("brainbit")
        self._brainbit_arm_backend.start_baseline_calibration()

    def _on_arm_source_status(self, source: str, text: str):
        if source != self._arm_backend_mode:
            return
        self._arm_backend_status = text
        self._arm_lab_page.set_backend_status(text)

    def _on_arm_source_connection(self, source: str, connected: bool):
        if source != self._arm_backend_mode:
            return
        if source == "brainbit":
            self._arm_lab_page.set_brainbit_connection(connected)
        self._sync_arm_lab_panel()
        self._refresh_live_labels()

    def _on_arm_metrics(self, source: str, data: dict):
        if source != self._arm_backend_mode:
            return
        self._arm_live_metrics = data or {
            "attention": 0.0,
            "relaxation": 0.0,
            "dominant_state": "Balanced",
        }
        self._arm_last_metrics_t = time.monotonic()
        preview = self._arm_state_engine.update(
            float(self._arm_live_metrics.get("attention", 0.0)),
            float(self._arm_live_metrics.get("relaxation", 0.0)),
        )
        self._arm_preview_state = preview.state
        if not self._arm_state_history or self._arm_state_history[-1] != preview.state:
            self._arm_state_history.append(preview.state)
            self._arm_state_history = self._arm_state_history[-8:]
        self._arm_lab_page.set_metrics(
            float(self._arm_live_metrics.get("attention", 0.0)),
            float(self._arm_live_metrics.get("relaxation", 0.0)),
            str(self._arm_live_metrics.get("dominant_state", "Balanced")),
        )
        self._arm_lab_page.set_arm_state(
            preview.state,
            self._arduino_arm.is_connected,
            self._arm_backend_mode,
        )
        self._arm_lab_page.set_history(self._arm_state_history)
        if self._arm_feature_active():
            self._arduino_arm.send_state(preview.state)
        if self._current_game_id == "prosthetic_arm":
            self._refresh_live_labels()

    def _on_arm_resistance(self, source: str, data: dict):
        if source != self._arm_backend_mode:
            return
        self._arm_lab_page.update_resistance(data or {})

    def _on_arm_waves(self, source: str, alpha: float, beta: float):
        if source != self._arm_backend_mode:
            return
        self._arm_lab_page.append_waves(alpha, beta)

    def _on_arm_raw_uv(self, source: str, data: list):
        if source != self._arm_backend_mode:
            return
        self._arm_lab_page.append_raw_uv(data or [])

    def _on_arduino_connection(self, connected: bool):
        self._arm_lab_page.set_arduino_connection(connected)
        self._sync_arm_lab_panel()

    def _on_arduino_status(self, text: str):
        if text:
            self._arm_lab_page.set_backend_status(text)
            self._arm_backend_status = text

    def _sync_arm_lab_panel(self):
        self._arm_lab_page.set_source_mode(self._arm_backend_mode)
        self._arm_lab_page.set_backend_status(self._arm_backend_status)
        self._arm_lab_page.set_metrics(
            float(self._arm_live_metrics.get("attention", 0.0)),
            float(self._arm_live_metrics.get("relaxation", 0.0)),
            str(self._arm_live_metrics.get("dominant_state", "Balanced")),
        )
        self._arm_lab_page.set_arm_state(
            self._arm_preview_state,
            self._arduino_arm.is_connected,
            self._arm_backend_mode,
        )
        self._arm_lab_page.set_history(self._arm_state_history)
        self._arm_lab_page.set_brainbit_connection(self._brainbit_arm_backend.is_connected)
        self._arm_lab_page.set_arduino_connection(self._arduino_arm.is_connected)

    def _build_calibration_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        layout.setSpacing(18)

        layout.addWidget(self._device_badge())
        self._calibration_title_lbl = QLabel("Calibration...")
        self._calibration_title_lbl.setAlignment(Qt.AlignCenter)
        self._calibration_title_lbl.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        self._calibration_subtitle_lbl = QLabel("")
        self._calibration_subtitle_lbl.setAlignment(Qt.AlignCenter)
        self._calibration_subtitle_lbl.setWordWrap(True)
        self._calibration_subtitle_lbl.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        self._calibration_counter_lbl = QLabel("00:05")
        self._calibration_counter_lbl.setAlignment(Qt.AlignCenter)
        self._calibration_counter_lbl.setStyleSheet("font-size: 34px; font-weight: bold; color: #f8fafc;")
        self._calibration_value_lbl = QLabel("Ready delta: 0.0")
        self._calibration_value_lbl.setAlignment(Qt.AlignCenter)
        self._calibration_value_lbl.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        self._calibration_bar = MindMazeControlBar()
        self._calibration_status_lbl = QLabel("Waiting for clean productivity metrics.")
        self._calibration_status_lbl.setAlignment(Qt.AlignCenter)
        self._calibration_status_lbl.setWordWrap(True)
        self._calibration_status_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")

        layout.addWidget(self._calibration_title_lbl)
        layout.addWidget(self._calibration_subtitle_lbl)
        layout.addStretch()
        layout.addWidget(self._calibration_counter_lbl)
        layout.addWidget(self._calibration_value_lbl)
        layout.addWidget(self._calibration_bar)
        layout.addWidget(self._calibration_status_lbl)
        layout.addStretch()

        cancel_btn = self._pill_button("Cancel", filled=False, wide=True)
        cancel_btn.clicked.connect(self._cancel_calibration)
        layout.addWidget(cancel_btn)
        return page

    def _build_gameplay_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        layout.setSpacing(14)

        self._game_device_badge = self._device_badge()
        layout.addWidget(self._game_device_badge)
        self._game_level_lbl = QLabel("Level 1")
        self._game_level_lbl.setAlignment(Qt.AlignCenter)
        self._game_level_lbl.setStyleSheet("font-size: 38px; font-weight: bold; color: #f8fafc;")
        self._game_time_lbl = QLabel("00:00")
        self._game_time_lbl.setAlignment(Qt.AlignCenter)
        self._game_time_lbl.setStyleSheet(f"font-size: 28px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._game_level_lbl)
        layout.addWidget(self._game_time_lbl)

        self._game_views = QStackedWidget()
        self._maze_board = MindMazeBoard()
        self._current_widget = CalmCurrentWidget()
        self._neuro_music_flow_widget = NeuroMusicFlowWidget()
        self._full_reboot_widget = FullRebootWidget()
        self._tug_of_war_widget = TugOfWarWidget()
        self._space_shooter_widget = SpaceShooterWidget()
        self._jump_ball_widget = JumpBallWidget()
        self._neuro_racer_widget = NeuroRacerWidget()
        self._neon_drift_arena_widget = NeonDriftArenaWidget()
        self._bubble_burst_widget = BubbleBurstWidget()
        self._pattern_widget = PatternRecallWidget()
        self._candy_cascade_widget = CandyCascadeWidget()
        self._prosthetic_arm_widget = ProstheticArmWidget()
        self._tug_of_war_widget.set_menu_callback(self._cancel_gameplay)
        self._space_shooter_widget.set_menu_callback(self._cancel_gameplay)
        self._neuro_racer_widget.set_menu_callback(self._cancel_gameplay)
        self._neon_drift_arena_widget.set_menu_callback(self._cancel_gameplay)
        self._bubble_burst_widget.set_menu_callback(self._cancel_gameplay)
        self._bubble_burst_widget.set_swap_callback(self._swap_bubble_queue)
        self._game_widget_map = {
            "mind_maze": self._maze_board,
            "calm_current": self._current_widget,
            "neuro_music_flow": self._neuro_music_flow_widget,
            "full_reboot": self._full_reboot_widget,
            "tug_of_war": self._tug_of_war_widget,
            "space_shooter": self._space_shooter_widget,
            "jump_ball": self._jump_ball_widget,
            "neuro_racer": self._neuro_racer_widget,
            "neon_drift_arena": self._neon_drift_arena_widget,
            "bubble_burst": self._bubble_burst_widget,
            "pattern_recall": self._pattern_widget,
            "candy_cascade": self._candy_cascade_widget,
            "prosthetic_arm": self._prosthetic_arm_widget,
        }
        for widget in self._game_widget_map.values():
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._game_views.addWidget(widget)
        layout.addWidget(self._game_views, stretch=1)

        self._game_bar = MindMazeControlBar()
        layout.addWidget(self._game_bar)
        self._game_status_lbl = QLabel("Waiting for gameplay.")
        self._game_status_lbl.setAlignment(Qt.AlignCenter)
        self._game_status_lbl.setWordWrap(True)
        self._game_status_lbl.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._game_status_lbl)

        self._game_cancel_btn = self._pill_button("Cancel", filled=False, wide=True)
        self._game_cancel_btn.clicked.connect(self._cancel_gameplay)
        layout.addWidget(self._game_cancel_btn)
        return page

    def _build_result_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        layout.setSpacing(18)

        layout.addWidget(self._device_badge())
        self._result_title_lbl = QLabel("Result")
        self._result_title_lbl.setAlignment(Qt.AlignCenter)
        self._result_title_lbl.setStyleSheet("font-size: 48px; font-weight: bold; color: #f8fafc;")
        self._result_score_lbl = QLabel("0%")
        self._result_score_lbl.setAlignment(Qt.AlignCenter)
        self._result_score_lbl.setStyleSheet("font-size: 58px; font-weight: bold; color: #f8fafc;")
        self._result_completion_lbl = QLabel("Training summary")
        self._result_completion_lbl.setAlignment(Qt.AlignCenter)
        self._result_completion_lbl.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._result_title_lbl)
        layout.addWidget(self._result_score_lbl)
        layout.addWidget(self._result_completion_lbl)

        self._result_cards = []
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        for index in range(3):
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: #13161c; border: 1px solid {BORDER_SUBTLE}; border-radius: 26px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 18, 18, 18)
            card_layout.setSpacing(8)
            name_lbl = QLabel(f"Level {index + 1}")
            name_lbl.setStyleSheet("font-size: 18px; color: #f8fafc;")
            score_lbl = QLabel("0%")
            score_lbl.setStyleSheet("font-size: 36px; font-weight: bold; color: #f8fafc;")
            time_lbl = QLabel("Time --")
            time_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
            target_lbl = QLabel("--")
            target_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
            card_layout.addWidget(name_lbl)
            card_layout.addWidget(score_lbl)
            card_layout.addWidget(time_lbl)
            card_layout.addWidget(target_lbl)
            card_layout.addStretch()
            cards_row.addWidget(card)
            self._result_cards.append((name_lbl, score_lbl, time_lbl, target_lbl))
        layout.addLayout(cards_row)
        layout.addStretch()

        ok_btn = self._pill_button("Ok", filled=True, wide=True)
        ok_btn.clicked.connect(self._show_catalog)
        layout.addWidget(ok_btn)
        return page

    def _device_badge(self):
        badge = QFrame()
        badge.setStyleSheet("QFrame { background: #2b2f35; border: 1px solid #474b53; border-radius: 22px; }")
        layout = QHBoxLayout(badge)
        layout.setContentsMargins(12, 8, 14, 8)
        layout.setSpacing(10)
        dot = QLabel("BCI")
        dot.setAlignment(Qt.AlignCenter)
        dot.setFixedSize(44, 28)
        dot.setStyleSheet(
            "QLabel { background: #1778ff; color: #ffffff; border-radius: 14px; font-size: 11px; font-weight: bold; }"
        )
        text = QLabel("1 device")
        text.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(dot)
        layout.addWidget(text)
        layout.addStretch()
        return badge

    def _section_header(self, text: str):
        label = QLabel(text)
        label.setStyleSheet("font-size: 34px; font-weight: bold; color: #f8fafc;")
        return label

    def _metric_chip(self, name: str, value: str):
        chip = QLabel(f"{name}: {value}")
        chip.setStyleSheet(
            f"QLabel {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 18px; "
            f"padding: 10px 14px; font-size: 13px; color: #f8fafc; }}"
        )
        return chip

    def _pill_button(self, text: str, filled: bool, wide: bool = False):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(58)
        if wide:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if filled:
            btn.setStyleSheet(
                "QPushButton { background: #f5f3f0; color: #111111; border: none; border-radius: 28px; "
                "padding: 14px 24px; font-size: 20px; font-weight: bold; }"
                "QPushButton:hover { background: #ffffff; }"
                "QPushButton:disabled { background: #71717a; color: #d4d4d8; }"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: #1a1d23; color: #f8fafc; border: 1px solid {BORDER_SUBTLE}; border-radius: 28px; "
                "padding: 14px 24px; font-size: 20px; font-weight: bold; }}"
                "QPushButton:hover { background: #22262d; }"
            )
        return btn

    def _load_settings(self):
        saved = self._settings.value("soundtrack", self._selected_soundtrack)
        if saved in self.SOUNDTRACKS:
            self._selected_soundtrack = saved
        saved_music_flow = self._settings.value("music_flow_soundtrack", self._selected_music_flow_soundtrack)
        if saved_music_flow in self.MUSIC_FLOW_SOUNDTRACKS:
            self._selected_music_flow_soundtrack = saved_music_flow

    def _save_settings(self):
        self._settings.setValue("soundtrack", self._selected_soundtrack)
        self._settings.setValue("music_flow_soundtrack", self._selected_music_flow_soundtrack)
        self._show_detail(self._current_game_id)

    def _soundtrack_catalog(self) -> dict[str, dict]:
        if self._current_game_id == "neuro_music_flow":
            return self.MUSIC_FLOW_SOUNDTRACKS
        return self.SOUNDTRACKS

    def _selected_soundtrack_name(self) -> str:
        if self._current_game_id == "neuro_music_flow":
            return self._selected_music_flow_soundtrack
        return self._selected_soundtrack

    def _select_soundtrack(self, name: str):
        if self._current_game_id == "neuro_music_flow":
            self._selected_music_flow_soundtrack = name
        else:
            self._selected_soundtrack = name
        self._refresh_soundtrack_cards()

    def _rebuild_soundtrack_cards(self):
        while self._soundtrack_cards_layout.count():
            item = self._soundtrack_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._soundtrack_cards = []
        for name, spec in self._soundtrack_catalog().items():
            option = SoundtrackCard(name, spec["description"], spec["colors"], self._select_soundtrack)
            self._soundtrack_cards.append(option)
            self._soundtrack_cards_layout.addWidget(option)
        self._refresh_soundtrack_cards()

    def _refresh_soundtrack_cards(self):
        selected_name = self._selected_soundtrack_name()
        for card in getattr(self, "_soundtrack_cards", []):
            card.set_selected(card.name == selected_name)

    def _refresh_live_labels(self):
        concentration, relaxation = self._current_metric_pair()
        fresh = self._current_metrics_fresh()
        backend_suffix = (
            f" ({self._arm_backend_mode.title()})" if self._current_game_id == "prosthetic_arm" else ""
        )
        if self._current_game_id == "neuroflow":
            connected = bool(self._latest_connection.get("connected", False))
            serial = str(self._latest_connection.get("serial", "--"))
            if connected:
                live_text = f"Live device detected for Neuroflow   Serial {serial}"
            else:
                live_text = "No live device detected. Neuroflow can fall back to simulation."
            self._catalog_live_lbl.setText(live_text)
            self._detail_conc_lbl.setText(f"Concentration: {concentration:.1f}")
            self._detail_relax_lbl.setText(f"Relaxation: {relaxation:.1f}")
            self._detail_start_btn.setEnabled(True)
            self._detail_availability_lbl.setText(
                "Enter Neuroflow to use dashboard-owned live EEG state, PSD-driven focus control, or the built-in simulation fallback."
            )
            return
        live_text = (
            f"Live concentration {concentration:.1f}   Relaxation {relaxation:.1f}{backend_suffix}"
            if fresh
            else "Waiting for concentration and relaxation metrics."
        )
        self._catalog_live_lbl.setText(live_text)
        self._detail_conc_lbl.setText(f"Concentration: {concentration:.1f}")
        self._detail_relax_lbl.setText(f"Relaxation: {relaxation:.1f}")
        self._detail_start_btn.setEnabled(fresh)
        self._detail_availability_lbl.setText(
            "Live metrics detected. Start is ready."
            if fresh
            else "Waiting for clean live metrics before training can start."
        )

    def _select_game(self, game_id: str):
        if self._current_game_id == game_id:
            return
        self._current_game_id = game_id
        self._controller = self._game_specs[game_id].controller_factory()

    def _show_catalog(self):
        self._stop_runtime_loops()
        self._stack.setCurrentWidget(self._catalog_page)
        self._refresh_live_labels()

    def _show_detail(self, game_id: str | None = None):
        self._stop_runtime_loops()
        if game_id is not None:
            self._select_game(game_id)
        self._update_detail_content()
        self._stack.setCurrentWidget(self._detail_page)
        self._refresh_live_labels()

    def _show_settings(self):
        self._stop_runtime_loops()
        if not self._current_spec.soundtrack_enabled:
            self._show_detail(self._current_game_id)
            return
        self._settings_subtitle_lbl.setText(self._current_spec.detail_title)
        if self._current_game_id == "neuro_music_flow":
            self._settings_heading_lbl.setText("Choose a guitar pack")
            self._settings_copy_lbl.setText(
                "Select the original Hindi-acoustic inspired guitar pack used during Neuro Music Flow. "
                "Relaxation deepens the warmer fingerstyle layers, concentration brings out brighter picking and lead motion, "
                "and the selection is saved separately from the rest of Training Lab."
            )
        else:
            self._settings_heading_lbl.setText("Choose a soundtrack")
            self._settings_copy_lbl.setText(
                f"Select the adaptive soundtrack used during calibration and {self._current_spec.card_title} gameplay. "
                "The chosen preset is saved between runs, and its layers respond live to your EEG state."
            )
        self._rebuild_soundtrack_cards()
        self._stack.setCurrentWidget(self._settings_page)

    def _update_detail_content(self):
        spec = self._current_spec
        self._detail_hero.setText(spec.preview_label)
        self._detail_hero.setStyleSheet(
            "QLabel { border-radius: 36px; font-size: 44px; font-weight: bold; color: #fff8f0; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {spec.colors[0]}, stop:1 {spec.colors[1]}); }}"
        )
        self._detail_meta_lbl.setText(f"{spec.duration}   Live neurofeedback")
        self._detail_title_lbl.setText(spec.detail_title)
        self._detail_body_lbl.setText(spec.detail_body)
        self._detail_instruction_lbl.setText(spec.instructions)
        self._detail_settings_btn.setEnabled(spec.soundtrack_enabled)
        self._detail_arm_lab_btn.setVisible(spec.game_id == "prosthetic_arm")
        self._detail_start_btn.setText("Enter Neuroflow" if spec.game_id == "neuroflow" else "Start")
        if spec.game_id == "prosthetic_arm":
            self._detail_meta_lbl.setText(f"{spec.duration}   {self._arm_backend_mode.title()} arm control")

    def _begin_calibration_flow(self):
        if self._current_game_id == "neuroflow":
            self._begin_neuroflow_flow()
            return
        if not self._current_metrics_fresh():
            self._refresh_live_labels()
            return
        self._controller.reset_run()
        self._controller.begin_calibration()
        self._calibration_title_lbl.setText(f"{self._current_spec.card_title} Calibration")
        self._calibration_subtitle_lbl.setText(self._current_spec.calibration_copy)
        self._update_calibration_ui(None)
        if self._current_spec.soundtrack_enabled:
            self._music_engine.start(self._selected_soundtrack_name())
        self._stack.setCurrentWidget(self._calibration_page)
        self._calibration_timer.start()

    def _begin_neuroflow_flow(self):
        self._stop_runtime_loops()
        self._neuroflow_page.set_connection_state(
            bool(self._latest_connection.get("connected", False)),
            str(self._latest_connection.get("serial", "--")),
        )
        self._neuroflow_page.set_streaming_active(self._streaming_active)
        self._neuroflow_page.on_resistance(self._latest_resistances)
        self._neuroflow_page.on_iapf_status(self._latest_iapf_status)
        if self._latest_band_powers:
            self._neuroflow_page.update_signal_snapshot(
                self._latest_band_powers,
                self._latest_peak_freqs,
                self._latest_psd_t,
            )
        self._neuroflow_page.activate()
        self._stack.setCurrentWidget(self._neuroflow_page)

    def _cancel_calibration(self):
        self._stop_runtime_loops()
        self._show_detail(self._current_game_id)

    def _cancel_gameplay(self):
        elapsed = self._current_level_elapsed()
        self._stop_runtime_loops()
        self._show_result(self._controller.finish_run(elapsed, aborted=True))

    def _swap_bubble_queue(self):
        if self._current_game_id != "bubble_burst":
            return
        if hasattr(self._controller, "swap_bubbles") and self._controller.swap_bubbles():
            self._update_gameplay_labels()

    def _show_result(self, result):
        if self._current_game_id == "neuro_music_flow" and hasattr(self._controller, "session_summary"):
            summary = self._controller.session_summary(result.total_seconds)
            self._result_title_lbl.setText("Session Summary")
            self._result_score_lbl.setText(self._format_seconds(summary["total_seconds"]))
            self._result_completion_lbl.setText(
                f"Average concentration {summary['avg_concentration']:.1f}   "
                f"Average relaxation {summary['avg_relaxation']:.1f}"
            )
            cards = [
                (
                    "Serenity",
                    f"{summary['avg_serenity']:.0f}",
                    "Average calm response",
                    f"Restlessness {summary['avg_restlessness']:.0f}",
                ),
                (
                    "Dominant Band",
                    summary["dominant_band_label"],
                    summary["dominant_mode"],
                    "Live band trend",
                ),
                (
                    "Flow Balance",
                    f"{summary['focus_balance']:+.1f}",
                    "Focus minus calm",
                    f"Completion {result.completion_pct}%",
                ),
            ]
            for index, card in enumerate(self._result_cards):
                name_lbl, score_lbl, time_lbl, target_lbl = card
                name, score, time_text, target_text = cards[index]
                name_lbl.setText(name)
                score_lbl.setText(score)
                time_lbl.setText(time_text)
                target_lbl.setText(target_text)
            self._stack.setCurrentWidget(self._result_page)
            return

        self._result_title_lbl.setText("Result")
        self._result_score_lbl.setText(f"{result.final_score}%")
        self._result_completion_lbl.setText(
            f"{self._current_spec.card_title}   {result.completion_pct}% complete   Total time {self._format_seconds(result.total_seconds)}"
        )
        for index, card in enumerate(self._result_cards):
            name_lbl, score_lbl, time_lbl, target_lbl = card
            if index < len(result.level_results):
                level_result = result.level_results[index]
                name_lbl.setText(level_result.title)
                score_lbl.setText(f"{level_result.score}%")
                time_lbl.setText(
                    f"Time {self._format_seconds(level_result.elapsed_seconds)}"
                    if level_result.elapsed_seconds
                    else "Time --"
                )
                target_lbl.setText(
                    f"Target {level_result.target_seconds}s   {'Complete' if level_result.completed else 'Incomplete'}"
                )
            else:
                name_lbl.setText(f"Stage {index + 1}")
                score_lbl.setText("--")
                time_lbl.setText("Time --")
                target_lbl.setText("--")
        self._stack.setCurrentWidget(self._result_page)

    def _tick_calibration(self):
        concentration, relaxation = self._current_metric_pair()
        valid = self._current_metrics_fresh() and not self._has_artifacts()
        snapshot = self._controller.add_calibration_sample(concentration, relaxation, valid)
        self._update_calibration_ui(snapshot)
        if snapshot.complete:
            self._calibration_timer.stop()
            self._controller.start_game()
            self._level_started_at = time.monotonic()
            self._switch_game_widget()
            self._update_gameplay_labels()
            self._stack.setCurrentWidget(self._gameplay_page)
            self._gameplay_timer.start()

    def _tick_gameplay(self):
        if hasattr(self._controller, "ingest_band_powers"):
            self._controller.ingest_band_powers(self._latest_band_powers)
        concentration, relaxation = self._current_metric_pair()
        stale = not self._current_metrics_fresh()
        snapshot = self._controller.update_gameplay(
            concentration,
            relaxation,
            valid=(not stale and not self._has_artifacts()),
            stale=stale,
            elapsed_seconds=self._current_level_elapsed(),
        )
        self._update_gameplay_labels(snapshot)
        if snapshot.run_completed:
            self._stop_runtime_loops()
            self._show_result(self._controller.finish_run(None, aborted=False))
            return
        if snapshot.level_completed:
            self._level_started_at = time.monotonic()

    def _update_calibration_ui(self, snapshot):
        concentration, relaxation = self._current_metric_pair()
        if snapshot is None:
            seconds_left = 5
            self._calibration_counter_lbl.setText("00:05")
            self._calibration_value_lbl.setText("Ready delta: 0.0")
            self._calibration_status_lbl.setText("Collecting baseline samples...")
            self._calibration_bar.set_state(
                concentration - relaxation,
                0.0,
                0.0,
                "Relax to enter the ready zone",
                self._current_spec.calibration_copy,
                muted=not self._current_metrics_fresh(),
                timer_text=f"00:{seconds_left:02d}",
                countdown_ratio=1.0,
            )
            self._update_audio_mix(0.0, 0.0, {"music_scene": "calibration", "serenity": 50.0, "restlessness": 18.0})
            return

        if snapshot.conc_baseline is None:
            remaining_samples = max(0, snapshot.samples_needed - snapshot.sample_count)
            seconds_left = math.ceil(remaining_samples / 4)
        else:
            seconds_left = max(0, READY_STREAK_TARGET - snapshot.ready_streak)
        self._calibration_counter_lbl.setText(f"00:{seconds_left:02d}")
        self._calibration_value_lbl.setText(f"Ready delta: {snapshot.ready_delta:+.1f}")
        self._calibration_status_lbl.setText(snapshot.status)
        conc_delta = concentration - snapshot.conc_baseline if snapshot.conc_baseline is not None else 0.0
        relax_delta = relaxation - snapshot.relax_baseline if snapshot.relax_baseline is not None else 0.0
        self._calibration_bar.set_state(
            concentration - relaxation,
            conc_delta,
            relax_delta,
            f"Ready hold {snapshot.ready_streak}/{READY_STREAK_TARGET}",
            snapshot.status,
            muted=(not self._current_metrics_fresh() or self._has_artifacts()),
            timer_text=f"00:{seconds_left:02d}",
            countdown_ratio=max(0.0, min(1.0, seconds_left / 5.0)),
        )
        self._update_audio_mix(conc_delta, relax_delta, {"music_scene": "calibration", "serenity": 50.0, "restlessness": 18.0})

    def _switch_game_widget(self):
        self._game_views.setCurrentWidget(self._game_widget_map[self._current_game_id])
        self._update_gameplay_chrome(self._current_game_id in self.IMMERSIVE_GAME_IDS)

    def _apply_view_state(self, view_state: dict):
        widget = self._game_widget_map[self._current_game_id]
        if hasattr(widget, "set_view_state"):
            widget.set_view_state(view_state)
        else:
            widget.set_state(view_state)

    def _update_gameplay_chrome(self, immersive: bool):
        visible = not immersive
        self._game_device_badge.setVisible(visible)
        self._game_level_lbl.setVisible(visible)
        self._game_time_lbl.setVisible(False)
        self._game_bar.setVisible(False)
        self._game_status_lbl.setVisible(False)
        self._game_cancel_btn.setVisible(visible)

    def _build_gameplay_balance_panel(
        self,
        *,
        phase_label: str,
        recommended_label: str,
        status: str,
        muted: bool,
        balance: float,
        conc_delta: float,
        relax_delta: float,
        elapsed_seconds: float,
    ) -> dict:
        remaining = max(0, self._controller.current_level.target_seconds - int(round(elapsed_seconds)))
        headline = f"{phase_label} • {recommended_label}" if recommended_label else phase_label
        target_seconds = max(1, self._controller.current_level.target_seconds)
        return {
            "timer_text": self._format_seconds(remaining),
            "balance": balance,
            "conc_delta": conc_delta,
            "relax_delta": relax_delta,
            "headline": headline,
            "status": status,
            "muted": muted,
            "countdown_ratio": remaining / target_seconds,
        }

    def _update_gameplay_labels(self, snapshot=None):
        self._switch_game_widget()
        self._game_level_lbl.setText(self._controller.current_level.title)
        elapsed_seconds = self._current_level_elapsed()
        self._game_time_lbl.setText(self._format_seconds(elapsed_seconds))
        status = self._current_spec.instructions
        muted = False
        conc_delta = 0.0
        relax_delta = 0.0
        balance = 0.0
        phase_label = self._current_spec.card_title
        recommended_label = ""
        view_state = dict(getattr(self._controller, "view_state", {}) or {})
        if snapshot is not None:
            phase_label = snapshot.phase_label
            recommended_label = snapshot.recommended_label
            status = snapshot.blocked_reason or snapshot.control_hint
            muted = bool(snapshot.blocked_reason and not snapshot.direction)
            conc_delta = snapshot.conc_delta
            relax_delta = snapshot.relax_delta
            balance = snapshot.balance
            view_state = dict(snapshot.view_state or {})
        if self._current_game_id == "neuro_music_flow":
            concentration, relaxation = self._current_metric_pair()
            view_state["concentration"] = concentration
            view_state["relaxation"] = relaxation
        if self._current_game_id == "prosthetic_arm":
            view_state["arm_connected"] = self._arduino_arm.is_connected
            view_state["backend_mode"] = self._arm_backend_mode
            view_state["backend_status"] = self._arm_backend_status
            view_state["dominant_state"] = dominant_state_for_metrics(
                float(self._arm_live_metrics.get("attention", 0.0)),
                float(self._arm_live_metrics.get("relaxation", 0.0)),
            )
        view_state["balance_panel"] = self._build_gameplay_balance_panel(
            phase_label=phase_label,
            recommended_label=recommended_label,
            status=status,
            muted=muted,
            balance=balance,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            elapsed_seconds=elapsed_seconds,
        )
        self._apply_view_state(view_state)
        self._update_audio_mix(conc_delta, relax_delta, view_state)

    def _ensure_audio_assets(self):
        self._music_engine.ensure_assets()

    def _update_audio_mix(self, conc_delta: float, relax_delta: float, view_state: dict | None):
        if not self._current_spec.soundtrack_enabled:
            return
        band_powers = None
        if self._current_game_id == "neuro_music_flow" and self._stack.currentWidget() is self._gameplay_page:
            band_powers = self._latest_band_powers
        self._music_engine.update_mix(
            self._current_spec.music_profile,
            conc_delta,
            relax_delta,
            view_state or {},
            band_powers=band_powers,
        )

    def _stop_runtime_loops(self):
        self._calibration_timer.stop()
        self._gameplay_timer.stop()
        self._neuroflow_page.deactivate()
        self.stop_audio()

    def set_view_active(self, active: bool):
        self._view_active = bool(active)
        if not self._view_active:
            self._calibration_timer.stop()
            self._gameplay_timer.stop()
            self._neuroflow_page.deactivate()
            return
        if self._stack.currentWidget() is self._calibration_page and self._streaming_active:
            if not self._calibration_timer.isActive():
                self._calibration_timer.start()
        if self._stack.currentWidget() is self._gameplay_page and self._streaming_active:
            if not self._gameplay_timer.isActive():
                self._gameplay_timer.start()
        if self.is_neuroflow_active():
            self._neuroflow_page.activate()
            return
        self._neuroflow_page.deactivate()

    def is_neuroflow_active(self) -> bool:
        return bool(
            self._view_active
            and self._streaming_active
            and self._stack.currentWidget() is self._neuroflow_page
        )

    def _has_fresh_metrics(self):
        return self._current_metrics_fresh()

    def _has_artifacts(self):
        if self._current_game_id == "prosthetic_arm" and self._arm_backend_mode == "brainbit":
            return False
        return bool(
            self._latest_physio.get("nfbArtifacts", False)
            or self._latest_physio.get("cardioArtifacts", False)
        )

    def _current_level_elapsed(self):
        if not self._level_started_at:
            return 0
        return int(max(0, round(time.monotonic() - self._level_started_at)))

    def _format_seconds(self, total_seconds: int):
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def on_emotions(self, data: dict):
        self._latest_emotions = data or {}

    def on_productivity(self, data: dict):
        self._latest_productivity = data or {}
        self._last_productivity_t = time.monotonic()
        if self._owns_arm_runtime:
            self._capsule_arm_backend.ingest_productivity(data or {})
        self._refresh_live_labels()

    def on_cardio(self, data: dict):
        self._latest_cardio = data or {}

    def on_physio_states(self, data: dict):
        self._latest_physio = data or {}

    def on_connection_state(self, connected: bool, serial: str = "--"):
        self._latest_connection = {"connected": bool(connected), "serial": serial or "--"}
        if self.is_neuroflow_active():
            self._neuroflow_page.set_connection_state(bool(connected), serial or "--")
        self._refresh_live_labels()

    def on_resistance(self, data: dict):
        self._latest_resistances = data or {}
        if self.is_neuroflow_active():
            self._neuroflow_page.on_resistance(data or {})

    def on_eeg(self, eeg_timed_data):
        return

    def on_psd(self, psd_data):
        return

    def update_signal_snapshot(
        self,
        band_powers: dict,
        peak_freqs: dict,
        psd_timestamp: float | None = None,
    ):
        self._latest_band_powers = dict(band_powers or {})
        self._latest_peak_freqs = dict(peak_freqs or {})
        self._latest_psd_t = psd_timestamp
        if self.is_neuroflow_active():
            self._neuroflow_page.update_signal_snapshot(
                self._latest_band_powers,
                self._latest_peak_freqs,
                self._latest_psd_t,
            )

    def on_iapf_status(self, payload: dict):
        self._latest_iapf_status = payload or {
            "frequency": None,
            "source": "Not set",
            "status": "Not set",
            "applied": False,
        }
        if self.is_neuroflow_active():
            self._neuroflow_page.on_iapf_status(self._latest_iapf_status)

    def on_neuroflow_calibration_started(self):
        if self.is_neuroflow_active():
            self._neuroflow_page.on_calibration_started()

    def on_neuroflow_calibration_finished(self, success: bool, message: str = ""):
        if self._stack.currentWidget() is self._neuroflow_page:
            self._neuroflow_page.on_calibration_finished(success, message)

    def set_streaming_active(self, active: bool):
        self._streaming_active = bool(active)
        self._neuroflow_page.set_streaming_active(bool(active))
        if not self._streaming_active:
            self._calibration_timer.stop()
            self._gameplay_timer.stop()
        if not self.is_neuroflow_active():
            self._neuroflow_page.deactivate()

    def set_eeg_stream_metadata(
        self,
        sample_rate_hz: float | None = None,
        channel_names: list[str] | None = None,
    ):
        self._eeg_sample_rate_hz = sample_rate_hz
        self._eeg_channel_names = list(channel_names or [])

    def stop_audio(self):
        self._music_engine.stop()

    def stop_active_flow(self):
        self._stop_runtime_loops()
        if hasattr(self._controller, "reset_run"):
            self._controller.reset_run()
        self._show_catalog()

    def shutdown(self):
        if self._owns_arm_runtime:
            self._brainbit_arm_backend.shutdown()
            self._arduino_arm.disconnect_device()
        self._neuroflow_page.shutdown()
        self.stop_audio()

    def closeEvent(self, event):  # noqa: N802 - Qt API
        self.shutdown()
        super().closeEvent(event)
