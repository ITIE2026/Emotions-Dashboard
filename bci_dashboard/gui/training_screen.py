"""
TrainingScreen - shared EEG training suite with multiple neurofeedback games.
"""
from __future__ import annotations

import math
import os
import tempfile
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
from gui.training_audio import AdaptiveMusicEngine
from gui.training_games import TRAINING_SPECS, active_training_specs
from gui.widgets.mind_maze_board import MindMazeBoard, MindMazeControlBar
from gui.widgets.training_game_widgets import (
    CalmCurrentWidget,
    FullRebootWidget,
    JumpBallWidget,
    NeuroRacerWidget,
    PatternRecallWidget,
    SpaceShooterWidget,
)
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
    SOUNDTRACKS = {
        "Central Park": {
            "description": "Wide, airy pads with a calm city-park pulse.",
            "colors": ("#235d4c", "#7ec28b"),
            "tone": (174.0, 208.0, 0.10),
        },
        "Kitten": {
            "description": "Soft warm chimes for the gentlest concentration game.",
            "colors": ("#65463b", "#e8d0be"),
            "tone": (232.0, 278.0, 0.08),
        },
        "Campfire": {
            "description": "Low amber drones with a slightly deeper breathing cadence.",
            "colors": ("#4a1d17", "#c87432"),
            "tone": (148.0, 192.0, 0.18),
        },
    }

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions: dict = {}
        self._latest_productivity: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}
        self._last_productivity_t = 0.0
        self._selected_soundtrack = "Kitten"
        self._level_started_at = 0.0
        self._audio_dir = os.path.join(tempfile.gettempdir(), "bci_training_audio")
        self._settings = QSettings("BCI Dashboard", "EEGTrainingSuite")
        self._game_specs = {spec.game_id: spec for spec in TRAINING_SPECS}
        self._active_specs = active_training_specs()
        self._current_game_id = "mind_maze"
        self._controller = self._game_specs[self._current_game_id].controller_factory()
        self._music_engine = AdaptiveMusicEngine(self, self._audio_dir, self.SOUNDTRACKS)

        self._calibration_timer = QTimer(self)
        self._calibration_timer.setInterval(250)
        self._calibration_timer.timeout.connect(self._tick_calibration)

        self._gameplay_timer = QTimer(self)
        self._gameplay_timer.setInterval(250)
        self._gameplay_timer.timeout.connect(self._tick_gameplay)

        self._build_ui()
        self._load_settings()
        self._ensure_audio_assets()
        self._refresh_soundtrack_cards()
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
        title = QLabel("Trainings")
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title)

        self._catalog_live_lbl = QLabel("Waiting for concentration and relaxation metrics.")
        self._catalog_live_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        layout.addWidget(self._catalog_live_lbl)

        section_order = [
            "Reduce stress and tension",
            "Improve concentration",
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
        heading = QLabel("Choose a soundtrack")
        heading.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        self._settings_copy_lbl = QLabel("")
        self._settings_copy_lbl.setWordWrap(True)
        self._settings_copy_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        card_layout.addWidget(heading)
        card_layout.addWidget(self._settings_copy_lbl)

        self._soundtrack_cards = []
        for name, spec in self.SOUNDTRACKS.items():
            option = SoundtrackCard(name, spec["description"], spec["colors"], self._select_soundtrack)
            self._soundtrack_cards.append(option)
            card_layout.addWidget(option)

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

        layout.addWidget(self._device_badge())
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
        self._full_reboot_widget = FullRebootWidget()
        self._space_shooter_widget = SpaceShooterWidget()
        self._jump_ball_widget = JumpBallWidget()
        self._neuro_racer_widget = NeuroRacerWidget()
        self._pattern_widget = PatternRecallWidget()
        self._game_widget_map = {
            "mind_maze": self._maze_board,
            "calm_current": self._current_widget,
            "full_reboot": self._full_reboot_widget,
            "space_shooter": self._space_shooter_widget,
            "jump_ball": self._jump_ball_widget,
            "neuro_racer": self._neuro_racer_widget,
            "pattern_recall": self._pattern_widget,
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

        cancel_btn = self._pill_button("Cancel", filled=False, wide=True)
        cancel_btn.clicked.connect(self._cancel_gameplay)
        layout.addWidget(cancel_btn)
        return page

    def _build_result_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        layout.setSpacing(18)

        layout.addWidget(self._device_badge())
        title = QLabel("Result")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 48px; font-weight: bold; color: #f8fafc;")
        self._result_score_lbl = QLabel("0%")
        self._result_score_lbl.setAlignment(Qt.AlignCenter)
        self._result_score_lbl.setStyleSheet("font-size: 58px; font-weight: bold; color: #f8fafc;")
        self._result_completion_lbl = QLabel("Training summary")
        self._result_completion_lbl.setAlignment(Qt.AlignCenter)
        self._result_completion_lbl.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        layout.addWidget(title)
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

    def _save_settings(self):
        self._settings.setValue("soundtrack", self._selected_soundtrack)
        self._show_detail(self._current_game_id)

    def _select_soundtrack(self, name: str):
        self._selected_soundtrack = name
        self._refresh_soundtrack_cards()

    def _refresh_soundtrack_cards(self):
        for card in getattr(self, "_soundtrack_cards", []):
            card.set_selected(card.name == self._selected_soundtrack)

    def _refresh_live_labels(self):
        concentration = float(self._latest_productivity.get("concentrationScore", 0.0))
        relaxation = float(self._latest_productivity.get("relaxationScore", 0.0))
        fresh = self._has_fresh_metrics()
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
        self._settings_subtitle_lbl.setText(self._current_spec.detail_title)
        self._settings_copy_lbl.setText(
            f"Select the adaptive soundtrack used during calibration and {self._current_spec.card_title} gameplay. "
            "The chosen preset is saved between runs, and its layers respond live to your EEG state."
        )
        self._stack.setCurrentWidget(self._settings_page)
        self._refresh_soundtrack_cards()

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

    def _begin_calibration_flow(self):
        if not self._has_fresh_metrics():
            self._refresh_live_labels()
            return
        self._controller.reset_run()
        self._controller.begin_calibration()
        self._calibration_title_lbl.setText(f"{self._current_spec.card_title} Calibration")
        self._calibration_subtitle_lbl.setText(self._current_spec.calibration_copy)
        self._update_calibration_ui(None)
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

    def _show_result(self, result):
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
        concentration = float(self._latest_productivity.get("concentrationScore", 0.0))
        relaxation = float(self._latest_productivity.get("relaxationScore", 0.0))
        valid = self._has_fresh_metrics() and not self._has_artifacts()
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
        concentration = float(self._latest_productivity.get("concentrationScore", 0.0))
        relaxation = float(self._latest_productivity.get("relaxationScore", 0.0))
        stale = not self._has_fresh_metrics()
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
        concentration = float(self._latest_productivity.get("concentrationScore", 0.0))
        relaxation = float(self._latest_productivity.get("relaxationScore", 0.0))
        if snapshot is None:
            self._calibration_counter_lbl.setText("00:05")
            self._calibration_value_lbl.setText("Ready delta: 0.0")
            self._calibration_status_lbl.setText("Collecting baseline samples...")
            self._calibration_bar.set_state(
                concentration - relaxation,
                0.0,
                0.0,
                "Relax to enter the ready zone",
                self._current_spec.calibration_copy,
                muted=not self._has_fresh_metrics(),
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
            muted=(not self._has_fresh_metrics() or self._has_artifacts()),
        )
        self._update_audio_mix(conc_delta, relax_delta, {"music_scene": "calibration", "serenity": 50.0, "restlessness": 18.0})

    def _switch_game_widget(self):
        self._game_views.setCurrentWidget(self._game_widget_map[self._current_game_id])

    def _apply_view_state(self, view_state: dict):
        widget = self._game_widget_map[self._current_game_id]
        if hasattr(widget, "set_view_state"):
            widget.set_view_state(view_state)
        else:
            widget.set_state(view_state)

    def _update_gameplay_labels(self, snapshot=None):
        self._switch_game_widget()
        self._game_level_lbl.setText(self._controller.current_level.title)
        self._game_time_lbl.setText(self._format_seconds(self._current_level_elapsed()))
        intent_label = "Hold steady"
        status = self._current_spec.instructions
        muted = False
        conc_delta = 0.0
        relax_delta = 0.0
        balance = 0.0
        view_state = getattr(self._controller, "view_state", {})
        if snapshot is not None:
            intent_label = (
                f"{snapshot.phase_label} • {snapshot.recommended_label}"
                if snapshot.recommended_label
                else snapshot.phase_label
            )
            status = snapshot.blocked_reason or snapshot.control_hint
            muted = bool(snapshot.blocked_reason and not snapshot.direction)
            conc_delta = snapshot.conc_delta
            relax_delta = snapshot.relax_delta
            balance = snapshot.balance
            view_state = snapshot.view_state
        self._apply_view_state(view_state)
        self._game_bar.set_state(balance, conc_delta, relax_delta, intent_label, status, muted)
        self._game_status_lbl.setText(status)
        self._update_audio_mix(conc_delta, relax_delta, view_state)

    def _ensure_audio_assets(self):
        self._music_engine.ensure_assets()

    def _update_audio_mix(self, conc_delta: float, relax_delta: float, view_state: dict | None):
        self._music_engine.update_mix(
            self._current_spec.music_profile,
            conc_delta,
            relax_delta,
            view_state or {},
        )

    def _stop_runtime_loops(self):
        self._calibration_timer.stop()
        self._gameplay_timer.stop()
        self.stop_audio()

    def _has_fresh_metrics(self):
        return (time.monotonic() - self._last_productivity_t) <= 2.0

    def _has_artifacts(self):
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
        self._refresh_live_labels()

    def on_cardio(self, data: dict):
        self._latest_cardio = data or {}

    def on_physio_states(self, data: dict):
        self._latest_physio = data or {}

    def stop_audio(self):
        self._music_engine.stop()
