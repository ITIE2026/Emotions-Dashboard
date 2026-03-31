"""
GamesScreen – dedicated games section separated from Training Lab.

Manages its own catalog → detail → calibration → gameplay → result flow
for all arcade, puzzle, memory, and cognitive games.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QSettings, Qt, QTimer
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
from gui.training_audio import AdaptiveMusicEngine, TRAINING_AUDIO_ASSET_DIR
from gui.training_games import TRAINING_SPECS, active_game_specs
from gui.widgets.mind_maze_board import MindMazeBoard, MindMazeControlBar
from gui.widgets.training_game_widgets import (
    BubbleBurstWidget,
    CandyCascadeWidget,
    HillClimbRacerWidget,
    JumpBallWidget,
    NeonViceWidget,
    PatternRecallWidget,
    SpaceShooterWidget,
    TugOfWarWidget,
)
from gui.widgets.gravity_drift_widget import GravityDriftWidget
from gui.widgets.synapse_serpent_widget import SynapseSerpentWidget
from gui.widgets.aero_zen_widget import AeroZenWidget
from utils.config import ACCENT_GREEN, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


# ── Reusable card widgets (same look as Training Lab) ────────────────

class _GameCard(QFrame):
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        preview = QLabel(preview_label)
        preview.setAlignment(Qt.AlignCenter)
        preview.setFixedSize(230, 155)
        preview.setStyleSheet(
            "QLabel { border-radius: 18px; font-size: 20px; font-weight: bold; color: #f8fafc; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {colors[0]}, stop:0.6 {colors[1]}, stop:1 {colors[0]}); "
            f"border: 1px solid rgba(255,255,255,0.08); }}"
        )
        layout.addWidget(preview)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        eyebrow_lbl = QLabel(f"  {eyebrow}")
        eyebrow_lbl.setStyleSheet(
            f"font-size: 11px; color: {ACCENT_GREEN}; letter-spacing: 1px; "
            f"text-transform: uppercase; font-weight: bold;"
        )

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #F5F5F5; letter-spacing: 0.3px;"
        )

        status_text = duration if enabled else f"{duration}   \u2022  Coming soon"
        meta_lbl = QLabel(status_text)
        meta_lbl.setStyleSheet(
            f"font-size: 12px; color: {'#69F0AE' if enabled else TEXT_SECONDARY};"
        )

        description_lbl = QLabel(description)
        description_lbl.setWordWrap(True)
        description_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY}; line-height: 1.4;")

        text_col.addWidget(eyebrow_lbl)
        text_col.addWidget(title_lbl)
        text_col.addWidget(meta_lbl)
        text_col.addSpacing(4)
        text_col.addWidget(description_lbl)
        text_col.addStretch()
        layout.addLayout(text_col, stretch=1)

        border = "#2E3450" if enabled else "#1E2030"
        active_bg = "#0F1220"
        self.setStyleSheet(
            f"QFrame {{ background: {active_bg}; border: 1px solid {border}; border-radius: 22px; }}"
            f"QFrame:hover {{ background: #141826; border-color: {'#69F0AE' if enabled else border}; }}"
        )

    def mouseReleaseEvent(self, event):
        if self._enabled and self._callback and event.button() == Qt.LeftButton:
            self._callback()
        super().mouseReleaseEvent(event)


class _SoundtrackCard(QFrame):
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
                "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                "stop:0 #1A2E40, stop:1 #162535); "
                "border: 2px solid #69F0AE; border-radius: 22px; }"
            )
            self._state_lbl.setText("\u2713 Selected")
            self._state_lbl.setStyleSheet("font-size: 12px; color: #69F0AE; font-weight: bold;")
        else:
            self.setStyleSheet(
                f"QFrame {{ background: #0F1220; border: 1px solid {BORDER_SUBTLE}; border-radius: 22px; }}"
                f"QFrame:hover {{ background: #141826; border-color: #3A4060; }}"
            )
            self._state_lbl.setText("Tap to select")
            self._state_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._callback(self._name)
        super().mouseReleaseEvent(event)


# ── Main GamesScreen ─────────────────────────────────────────────────

class GamesScreen(QWidget):
    IMMERSIVE_GAME_IDS = {"tug_of_war", "space_shooter", "bubble_burst", "jump_ball", "neon_vice", "hill_climb_racer", "gravity_drift", "synapse_serpent", "aero_zen"}

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

    ALL_SOUNDTRACKS = {**SOUNDTRACKS}

    # Game section grouping for the catalog
    GAME_SECTIONS = [
        "Arcade neurofeedback",
        "Memory and cognitive control",
        "Improve concentration",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_productivity: dict = {}
        self._latest_physio: dict = {}
        self._last_productivity_t = 0.0
        self._latest_connection = {"connected": False, "serial": "--"}
        self._streaming_active = False
        self._view_active = False
        self._latest_band_powers: dict = {}
        self._selected_soundtrack = "Aurora Drift"
        self._level_started_at = 0.0
        self._audio_dir = TRAINING_AUDIO_ASSET_DIR
        self._settings = QSettings("BCI Dashboard", "GamesSection")
        self._game_specs = {spec.game_id: spec for spec in TRAINING_SPECS}
        self._active_specs = active_game_specs()
        self._current_game_id = "mind_maze"
        self._controller = self._game_specs[self._current_game_id].controller_factory()
        self._music_engine = AdaptiveMusicEngine(self, self._audio_dir, self.ALL_SOUNDTRACKS)

        self._calibration_timer = QTimer(self)
        self._calibration_timer.setInterval(250)
        self._calibration_timer.timeout.connect(self._tick_calibration)

        self._gameplay_timer = QTimer(self)
        self._gameplay_timer.setInterval(250)
        self._gameplay_timer.timeout.connect(self._tick_gameplay)

        self._build_ui()
        self._load_settings()
        self._ensure_audio_assets()
        self._rebuild_soundtrack_cards()
        self._refresh_live_labels()
        self._show_catalog()

    @property
    def _current_spec(self) -> TrainingGameSpec:
        return self._game_specs[self._current_game_id]

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet("background: #000000; color: #f8fafc;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._stack = QStackedWidget()
        self._catalog_page = self._build_catalog_page()
        self._detail_page = self._build_detail_page()
        self._settings_page = self._build_settings_page()
        self._calibration_page = self._build_calibration_page()
        self._gameplay_page = self._build_gameplay_page()
        self._result_page = self._build_result_page()
        for page in [
            self._catalog_page,
            self._detail_page,
            self._settings_page,
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
        title = QLabel("\U0001F3C6  Games")
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title)

        subtitle = QLabel(
            "All BCI-controlled games in one place. Pick a game, calibrate, and play."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        self._catalog_live_lbl = QLabel("Waiting for concentration and relaxation metrics.")
        self._catalog_live_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._catalog_live_lbl)

        for section in self.GAME_SECTIONS:
            cards = [spec for spec in self._active_specs if spec.section == section]
            if not cards:
                continue
            layout.addWidget(self._section_header(section))
            for spec in cards:
                layout.addWidget(
                    _GameCard(
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
        self._detail_hero = QLabel("GAME")
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
        back_btn = self._pill_button("Back", filled=False)
        back_btn.clicked.connect(self._show_catalog)
        buttons.addWidget(self._detail_settings_btn)
        buttons.addWidget(self._detail_start_btn)
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

        self._soundtrack_cards: list[_SoundtrackCard] = []
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
        self._tug_of_war_widget = TugOfWarWidget()
        self._space_shooter_widget = SpaceShooterWidget()
        self._jump_ball_widget = JumpBallWidget()
        self._bubble_burst_widget = BubbleBurstWidget()
        self._pattern_widget = PatternRecallWidget()
        self._candy_cascade_widget = CandyCascadeWidget()
        self._neon_vice_widget = NeonViceWidget()
        self._hill_climb_racer_widget = HillClimbRacerWidget()
        self._gravity_drift_widget = GravityDriftWidget()
        self._synapse_serpent_widget = SynapseSerpentWidget()
        self._aero_zen_widget = AeroZenWidget()

        self._tug_of_war_widget.set_menu_callback(self._cancel_gameplay)
        self._space_shooter_widget.set_menu_callback(self._cancel_gameplay)
        self._bubble_burst_widget.set_menu_callback(self._cancel_gameplay)
        self._bubble_burst_widget.set_swap_callback(self._swap_bubble_queue)
        self._neon_vice_widget.set_menu_callback(self._cancel_gameplay)
        self._hill_climb_racer_widget.set_menu_callback(self._cancel_gameplay)
        self._gravity_drift_widget.set_menu_callback(self._cancel_gameplay)
        self._synapse_serpent_widget.set_menu_callback(self._cancel_gameplay)
        self._aero_zen_widget.set_menu_callback(self._cancel_gameplay)

        self._game_widget_map = {
            "mind_maze": self._maze_board,
            "tug_of_war": self._tug_of_war_widget,
            "space_shooter": self._space_shooter_widget,
            "jump_ball": self._jump_ball_widget,
            "bubble_burst": self._bubble_burst_widget,
            "pattern_recall": self._pattern_widget,
            "candy_cascade": self._candy_cascade_widget,
            "neon_vice": self._neon_vice_widget,
            "hill_climb_racer": self._hill_climb_racer_widget,
            "gravity_drift": self._gravity_drift_widget,
            "synapse_serpent": self._synapse_serpent_widget,
            "aero_zen": self._aero_zen_widget,
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
        self._result_completion_lbl = QLabel("Game summary")
        self._result_completion_lbl.setAlignment(Qt.AlignCenter)
        self._result_completion_lbl.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._result_title_lbl)
        layout.addWidget(self._result_score_lbl)
        layout.addWidget(self._result_completion_lbl)

        self._result_cards: list[tuple] = []
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

    # ── Shared widgets ───────────────────────────────────────────────

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

    # ── Navigation ───────────────────────────────────────────────────

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
        self._detail_start_btn.setText("Start")

    # ── Calibration & Gameplay ───────────────────────────────────────

    def _current_metric_pair(self) -> tuple[float, float]:
        return (
            float(self._latest_productivity.get("concentrationScore", 0.0)),
            float(self._latest_productivity.get("relaxationScore", 0.0)),
        )

    def _current_metrics_fresh(self) -> bool:
        return (time.monotonic() - self._last_productivity_t) <= 2.0

    def _has_artifacts(self):
        return bool(
            self._latest_physio.get("nfbArtifacts", False)
            or self._latest_physio.get("cardioArtifacts", False)
        )

    def _begin_calibration_flow(self):
        if not self._current_metrics_fresh():
            self._refresh_live_labels()
            return
        self._controller.reset_run()
        self._controller.begin_calibration()
        self._calibration_title_lbl.setText(f"{self._current_spec.card_title} Calibration")
        self._calibration_subtitle_lbl.setText(self._current_spec.calibration_copy)
        self._update_calibration_ui(None)
        if self._current_spec.soundtrack_enabled:
            self._music_engine.start(self._selected_soundtrack)
        self._stack.setCurrentWidget(self._calibration_page)
        self._calibration_timer.start()

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
                concentration - relaxation, 0.0, 0.0,
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
            concentration - relaxation, conc_delta, relax_delta,
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

    def _show_result(self, result):
        self._result_title_lbl.setText("Result")
        self._result_score_lbl.setText(f"{result.final_score}%")
        self._result_completion_lbl.setText(
            f"{self._current_spec.card_title}   {result.completion_pct}% complete   "
            f"Total time {self._format_seconds(result.total_seconds)}"
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

    # ── Audio ────────────────────────────────────────────────────────

    def _ensure_audio_assets(self):
        self._music_engine.ensure_assets()

    def _update_audio_mix(self, conc_delta: float, relax_delta: float, view_state: dict | None):
        if not self._current_spec.soundtrack_enabled:
            return
        self._music_engine.update_mix(
            self._current_spec.music_profile,
            conc_delta,
            relax_delta,
            view_state or {},
        )

    def _load_settings(self):
        saved = self._settings.value("soundtrack", self._selected_soundtrack)
        if saved in self.SOUNDTRACKS:
            self._selected_soundtrack = saved

    def _save_settings(self):
        self._settings.setValue("soundtrack", self._selected_soundtrack)
        self._show_detail(self._current_game_id)

    def _rebuild_soundtrack_cards(self):
        while self._soundtrack_cards_layout.count():
            item = self._soundtrack_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._soundtrack_cards.clear()
        for name, info in self.SOUNDTRACKS.items():
            card = _SoundtrackCard(
                name, info["description"], info["colors"],
                callback=self._on_soundtrack_selected,
            )
            card.set_selected(name == self._selected_soundtrack)
            self._soundtrack_cards.append(card)
            self._soundtrack_cards_layout.addWidget(card)

    def _on_soundtrack_selected(self, name: str):
        self._selected_soundtrack = name
        for card in self._soundtrack_cards:
            card.set_selected(card.name == name)

    # ── Live label refresh ───────────────────────────────────────────

    def _refresh_live_labels(self):
        concentration, relaxation = self._current_metric_pair()
        fresh = self._current_metrics_fresh()
        live_text = (
            f"Live concentration {concentration:.1f}   Relaxation {relaxation:.1f}"
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
            else "Waiting for clean live metrics before the game can start."
        )

    # ── Runtime control ──────────────────────────────────────────────

    def _stop_runtime_loops(self):
        self._calibration_timer.stop()
        self._gameplay_timer.stop()
        self.stop_audio()

    def _current_level_elapsed(self):
        if not self._level_started_at:
            return 0
        return int(max(0, round(time.monotonic() - self._level_started_at)))

    def _format_seconds(self, total_seconds: int):
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    # ── Public API (called from MainWindow) ──────────────────────────

    def on_productivity(self, data: dict):
        self._latest_productivity = data or {}
        self._last_productivity_t = time.monotonic()
        self._refresh_live_labels()

    def on_physio_states(self, data: dict):
        self._latest_physio = data or {}

    def on_mems(self, mems_timed_data) -> None:
        if not hasattr(self, "_controller") or self._controller is None:
            return
        if not hasattr(self._controller, "update_mems"):
            return
        try:
            count = len(mems_timed_data)
            if count <= 0:
                return
            last = count - 1
            accel = mems_timed_data.get_accelerometer(last)
            gyro = mems_timed_data.get_gyroscope(last)
            self._controller.update_mems(
                accel.x, accel.y, accel.z,
                gyro.x, gyro.y, gyro.z,
            )
        except Exception:
            pass

    def update_signal_snapshot(
        self,
        band_powers: dict,
        peak_freqs: dict,
        psd_timestamp: float | None = None,
    ):
        self._latest_band_powers = dict(band_powers or {})

    def set_streaming_active(self, active: bool):
        self._streaming_active = bool(active)
        if not self._streaming_active:
            self._calibration_timer.stop()
            self._gameplay_timer.stop()

    def set_view_active(self, active: bool):
        self._view_active = bool(active)
        if not self._view_active:
            self._calibration_timer.stop()
            self._gameplay_timer.stop()
            return
        if self._stack.currentWidget() is self._calibration_page and self._streaming_active:
            if not self._calibration_timer.isActive():
                self._calibration_timer.start()
        if self._stack.currentWidget() is self._gameplay_page and self._streaming_active:
            if not self._gameplay_timer.isActive():
                self._gameplay_timer.start()

    def stop_audio(self):
        self._music_engine.stop()

    def stop_active_flow(self):
        self._stop_runtime_loops()
        if hasattr(self._controller, "reset_run"):
            self._controller.reset_run()
        self._show_catalog()

    def shutdown(self):
        self.stop_audio()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
