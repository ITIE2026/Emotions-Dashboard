"""
TrainingScreen - mobile-inspired training catalog with Mind Maze gameplay.
"""
from __future__ import annotations

import math
import os
import struct
import tempfile
import time
import wave

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
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

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on local Qt multimedia install
    QSoundEffect = None

from gui.mind_maze_controller import MindMazeController
from gui.widgets.mind_maze_board import MindMazeBoard, MindMazeControlBar
from utils.config import ACCENT_GREEN, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY


CALIBRATION_READY_STREAK = 3


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
        title_lbl.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions: dict = {}
        self._latest_productivity: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}
        self._last_productivity_t = 0.0
        self._selected_soundtrack = "Kitten"
        self._level_started_at = 0.0
        self._audio_dir = os.path.join(tempfile.gettempdir(), "bci_mind_maze_audio")
        self._settings = QSettings("BCI Dashboard", "MindMaze")
        self._controller = MindMazeController()

        self._sound = None
        if QSoundEffect is not None:
            self._sound = QSoundEffect(self)
            self._sound.setLoopCount(int(QSoundEffect.Loop.Infinite.value))
            self._sound.setVolume(0.24)

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

        layout.addWidget(self._section_header("Reduce stress and tension"))
        layout.addWidget(
            TrainingCard(
                "Stress resistance",
                "Course training for stress resistance",
                "9 min",
                "A long-form guided training card shown for visual parity with the reference app.",
                "CALM",
                ("#364b6a", "#8699b7"),
                enabled=False,
            )
        )
        layout.addWidget(
            TrainingCard(
                "Relax reset",
                "A short training to relax and relieve stress",
                "6 min",
                "Preview card for future stress-reduction routines.",
                "RESET",
                ("#556b58", "#97c58e"),
                enabled=False,
            )
        )

        layout.addWidget(self._section_header("Relax before sleep"))
        layout.addWidget(
            TrainingCard(
                "Deep wind-down",
                "Full reboot",
                "25 min",
                "A quiet bedtime training preview, included so the desktop catalog mirrors the original app structure.",
                "SLEEP",
                ("#5f463d", "#c19d82"),
                enabled=False,
            )
        )

        layout.addWidget(self._section_header("Improve concentration"))
        layout.addWidget(
            TrainingCard(
                "Custom training",
                "Custom training",
                "25 min",
                "A future live-feedback training card. The layout is present, but the gameplay flow is not enabled in this pass.",
                "FOCUS",
                ("#43536a", "#8ea7c7"),
                enabled=False,
            )
        )
        layout.addWidget(
            TrainingCard(
                "Mind Maze",
                "A maze game for concentration",
                "10 min",
                "Navigate the maze by changing concentration and relaxation in real time. Concentrate to climb, relax to descend, and combine both states to unlock lateral movement.",
                "MAZE",
                ("#7b2d1d", "#db9054"),
                enabled=True,
                callback=self._show_detail,
            )
        )
        layout.addWidget(
            TrainingCard(
                "Skill builder",
                "Training for concentration",
                "10 min",
                "Another concentration card preview to keep the training page visually aligned with the screenshots.",
                "TRAIN",
                ("#6f5640", "#cfb38d"),
                enabled=False,
            )
        )
        layout.addWidget(
            TrainingCard(
                "Procedural memory",
                "Training skills",
                "25 min",
                "A future training card for memory-linked practice and habit routines.",
                "SKILL",
                ("#5b514a", "#bba18d"),
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
        hero = QLabel("MIND MAZE")
        hero.setAlignment(Qt.AlignCenter)
        hero.setFixedHeight(220)
        hero.setStyleSheet(
            "QLabel { border-radius: 36px; font-size: 44px; font-weight: bold; color: #fff8f0; "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7f2f1c, stop:1 #1d0a08); }"
        )
        layout.addWidget(hero)

        meta = QLabel("10 min   Live neurofeedback")
        meta.setStyleSheet(f"font-size: 14px; color: {ACCENT_GREEN};")
        layout.addWidget(meta)

        title = QLabel("A maze game for concentration")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 46px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title)

        body = QLabel(
            "Concentration training strengthens the ability to maintain focus on a single task while relaxing away distracting thoughts and external noise.\n\n"
            "Navigate the maze. Concentrate to move upward, relax to move downward, and combine the two states to unlock lateral movement."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 15px; color: {TEXT_SECONDARY};")
        layout.addWidget(body)
        layout.addWidget(self._section_header("Instruction"))
        instruction = QLabel(
            "Start calibration first. The game samples your concentration and relaxation baselines, then moves one maze tile every time you sustain a valid control state across two clean updates."
        )
        instruction.setWordWrap(True)
        instruction.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        layout.addWidget(instruction)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(12)
        self._detail_conc_lbl = self._metric_chip("Concentration", "0.0")
        self._detail_relax_lbl = self._metric_chip("Relaxation", "0.0")
        metrics_row.addWidget(self._detail_conc_lbl)
        metrics_row.addWidget(self._detail_relax_lbl)
        metrics_row.addStretch()
        layout.addLayout(metrics_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        settings_btn = self._pill_button("Settings", filled=False)
        settings_btn.clicked.connect(self._show_settings)
        start_btn = self._pill_button("Start", filled=True)
        start_btn.clicked.connect(self._begin_calibration_flow)
        self._detail_start_btn = start_btn
        back_btn = self._pill_button("Back", filled=False)
        back_btn.clicked.connect(self._show_catalog)
        buttons.addWidget(settings_btn)
        buttons.addWidget(start_btn)
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
        subtitle = QLabel("A maze game for concentration")
        subtitle.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: #121419; border: 1px solid {BORDER_SUBTLE}; border-radius: 34px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(18)
        heading = QLabel("Choose a soundtrack")
        heading.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        copy = QLabel(
            "Select the ambient soundtrack used during calibration and Mind Maze gameplay. The app keeps the chosen preset between runs."
        )
        copy.setWordWrap(True)
        copy.setStyleSheet(f"font-size: 14px; color: {TEXT_SECONDARY};")
        card_layout.addWidget(heading)
        card_layout.addWidget(copy)

        self._soundtrack_cards = []
        for name, spec in self.SOUNDTRACKS.items():
            option = SoundtrackCard(name, spec["description"], spec["colors"], self._select_soundtrack)
            self._soundtrack_cards.append(option)
            card_layout.addWidget(option)

        layout.addWidget(card)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        back_btn = self._pill_button("Back", filled=False)
        back_btn.clicked.connect(self._show_detail)
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
        title = QLabel("Calibration...")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #f8fafc;")
        subtitle = QLabel("Relax and hold the indicator in the ready zone to begin training.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: 16px; color: {TEXT_SECONDARY};")
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

        layout.addWidget(title)
        layout.addWidget(subtitle)
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

        self._maze_board = MindMazeBoard()
        self._maze_board.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._maze_board, stretch=1)

        self._game_bar = MindMazeControlBar()
        layout.addWidget(self._game_bar)
        self._game_status_lbl = QLabel("Concentrate to move upward, relax to move downward.")
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
        self._show_detail()

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
        if hasattr(self, "_catalog_live_lbl"):
            self._catalog_live_lbl.setText(live_text)
        if hasattr(self, "_detail_conc_lbl"):
            self._detail_conc_lbl.setText(f"Concentration: {concentration:.1f}")
        if hasattr(self, "_detail_relax_lbl"):
            self._detail_relax_lbl.setText(f"Relaxation: {relaxation:.1f}")
        if hasattr(self, "_detail_start_btn"):
            self._detail_start_btn.setEnabled(fresh)

    def _show_catalog(self):
        self._stop_runtime_loops()
        self._stack.setCurrentWidget(self._catalog_page)
        self._refresh_live_labels()

    def _show_detail(self):
        self._stop_runtime_loops()
        self._stack.setCurrentWidget(self._detail_page)
        self._refresh_live_labels()

    def _show_settings(self):
        self._stop_runtime_loops()
        self._stack.setCurrentWidget(self._settings_page)
        self._refresh_soundtrack_cards()

    def _begin_calibration_flow(self):
        if not self._has_fresh_metrics():
            self._refresh_live_labels()
            return
        self._controller.reset_run()
        self._controller.begin_calibration()
        self._update_calibration_ui(None)
        self._play_selected_track()
        self._stack.setCurrentWidget(self._calibration_page)
        self._calibration_timer.start()

    def _cancel_calibration(self):
        self._stop_runtime_loops()
        self._show_detail()

    def _cancel_gameplay(self):
        elapsed = self._current_level_elapsed()
        self._stop_runtime_loops()
        self._show_result(self._controller.finish_run(elapsed, aborted=True))

    def _show_result(self, result):
        self._result_score_lbl.setText(f"{result.final_score}%")
        self._result_completion_lbl.setText(
            f"{result.completion_pct}% complete   Total time {self._format_seconds(result.total_seconds)}"
        )
        for index, level_result in enumerate(result.level_results):
            name_lbl, score_lbl, time_lbl, target_lbl = self._result_cards[index]
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
                "Collecting baseline samples...",
                muted=not self._has_fresh_metrics(),
            )
            return

        if snapshot.conc_baseline is None:
            remaining_samples = max(0, snapshot.samples_needed - snapshot.sample_count)
            seconds_left = math.ceil(remaining_samples / 4)
        else:
            seconds_left = max(0, CALIBRATION_READY_STREAK - snapshot.ready_streak)
        self._calibration_counter_lbl.setText(f"00:{seconds_left:02d}")
        self._calibration_value_lbl.setText(f"Ready delta: {snapshot.ready_delta:+.1f}")
        self._calibration_status_lbl.setText(snapshot.status)
        conc_delta = concentration - snapshot.conc_baseline if snapshot.conc_baseline is not None else 0.0
        relax_delta = relaxation - snapshot.relax_baseline if snapshot.relax_baseline is not None else 0.0
        self._calibration_bar.set_state(
            concentration - relaxation,
            conc_delta,
            relax_delta,
            f"Ready hold {snapshot.ready_streak}/{CALIBRATION_READY_STREAK}",
            snapshot.status,
            muted=(not self._has_fresh_metrics() or self._has_artifacts()),
        )

    def _update_gameplay_labels(self, snapshot=None):
        level = self._controller.current_level
        self._game_level_lbl.setText(level.title)
        self._game_time_lbl.setText(self._format_seconds(self._current_level_elapsed()))
        message = ""
        status = "Concentrate to move upward, relax to move downward."
        intent_label = "Hold steady"
        muted = False
        conc_delta = 0.0
        relax_delta = 0.0
        balance = 0.0
        hint_direction = None
        if snapshot is not None:
            message = snapshot.blocked_reason
            if snapshot.level_completed:
                message = "Level cleared. Preparing the next maze."
            status = snapshot.blocked_reason or (
                snapshot.control_hint
            )
            intent_label = (
                f"{snapshot.phase_label} • {snapshot.recommended_label}"
                if snapshot.recommended_direction
                else snapshot.phase_label
            )
            muted = bool(snapshot.blocked_reason and not snapshot.direction)
            conc_delta = snapshot.conc_delta
            relax_delta = snapshot.relax_delta
            balance = snapshot.balance
            hint_direction = snapshot.recommended_direction
        self._maze_board.set_state(
            level,
            self._controller.player,
            self._controller.goal,
            message,
            hint_direction=hint_direction,
        )
        self._game_bar.set_state(balance, conc_delta, relax_delta, intent_label, status, muted)
        self._game_status_lbl.setText(
            status
            if snapshot is not None
            else "Concentrate to move upward, relax to move downward, and combine both states to shift across the maze."
        )

    def _ensure_audio_assets(self):
        os.makedirs(self._audio_dir, exist_ok=True)
        for name, spec in self.SOUNDTRACKS.items():
            path = self._soundtrack_path(name)
            if not os.path.exists(path):
                carrier, accent, depth = spec["tone"]
                self._write_tone(path, carrier, accent, depth)

    def _soundtrack_path(self, name: str):
        return os.path.join(self._audio_dir, f"{name.lower().replace(' ', '_')}.wav")

    def _write_tone(self, path: str, carrier: float, accent: float, depth: float):
        sample_rate = 22050
        duration = 4
        frames = bytearray()
        for index in range(sample_rate * duration):
            t = index / sample_rate
            envelope = 0.58 + 0.42 * math.sin(2 * math.pi * depth * t)
            sample = (
                0.34 * math.sin(2 * math.pi * carrier * t)
                + 0.18 * math.sin(2 * math.pi * accent * t)
                + 0.12 * math.sin(2 * math.pi * (carrier / 2.0) * t)
            ) * envelope
            sample = max(-1.0, min(1.0, sample))
            frames.extend(struct.pack("<h", int(sample * 32767)))
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(frames))

    def _play_selected_track(self):
        if self._sound is None:
            return
        path = self._soundtrack_path(self._selected_soundtrack)
        if not os.path.exists(path):
            return
        self._sound.stop()
        self._sound.setSource(QUrl.fromLocalFile(path))
        self._sound.play()

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
        if self._sound is not None:
            self._sound.stop()
