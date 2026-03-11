"""
TrainingScreen - neurofeedback-style practice mode.

Provides simple adaptive exercises and generated background tones that react
to the current emotion and productivity values.
"""
from __future__ import annotations

import math
import os
import random
import struct
import tempfile
import wave

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on local Qt multimedia install
    QSoundEffect = None

from gui.widgets.metric_card import MetricCard
from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_ORANGE,
    ACCENT_RED,
    BG_CARD,
    BG_PRIMARY,
    BORDER_SUBTLE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class TrainingScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest_emotions: dict = {}
        self._latest_productivity: dict = {}
        self._latest_cardio: dict = {}
        self._latest_physio: dict = {}

        self._calm_streak = 0
        self._focus_hits = 0
        self._focus_rounds = 0
        self._memory_score = 0
        self._memory_sequence: list[str] = []
        self._memory_input: list[str] = []
        self._active_track = ""
        self._audio_enabled = True
        self._audio_dir = os.path.join(tempfile.gettempdir(), "bci_training_audio")

        self._sound = None
        if QSoundEffect is not None:
            self._sound = QSoundEffect(self)
            # Some PySide6 builds expose Loop.Infinite but bind setLoopCount to int.
            self._sound.setLoopCount(int(QSoundEffect.Loop.Infinite.value))
            self._sound.setVolume(0.22)

        self._build_ui()
        self._ensure_audio_assets()
        self._prepare_focus_round()

        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._advance_training)
        self._tick.start()

    def _build_ui(self):
        self.setStyleSheet(f"background: {BG_PRIMARY};")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("Training Lab")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        subtitle = QLabel(
            "Live exercises adapt to focus, calmness, stress, self-control, and heart rate."
        )
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY}; padding-bottom: 6px;"
        )
        root.addWidget(title)
        root.addWidget(subtitle)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self._focus_card = MetricCard("Focus", "#B388FF")
        self._calm_card = MetricCard("Calmness", ACCENT_GREEN)
        self._stress_card = MetricCard("Stress", "#FF8A65")
        self._ctrl_card = MetricCard("Self-control", ACCENT_CYAN)
        for card in [
            self._focus_card,
            self._calm_card,
            self._stress_card,
            self._ctrl_card,
        ]:
            metrics.addWidget(card)
        root.addLayout(metrics)

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(10)
        top_grid.setVerticalSpacing(10)
        top_grid.addWidget(self._build_audio_panel(), 0, 0)
        top_grid.addWidget(self._build_breath_panel(), 0, 1)
        top_grid.addWidget(self._build_focus_panel(), 1, 0)
        top_grid.addWidget(self._build_memory_panel(), 1, 1)
        root.addLayout(top_grid)

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 14px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        header = QLabel(title)
        header.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY};"
        )
        layout.addWidget(header)
        return frame, layout

    def _build_audio_panel(self) -> QWidget:
        panel, layout = self._panel("Adaptive Brain Music")

        self._music_mode = QLabel("Mode: Waiting for live data")
        self._music_mode.setStyleSheet(
            f"font-size: 13px; color: {ACCENT_CYAN};"
        )
        self._music_reason = QLabel("Recommendation: connect signal to start audio coaching.")
        self._music_reason.setWordWrap(True)
        self._music_reason.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY};"
        )
        self._hr_status = QLabel("Heart rate: -- bpm")
        self._hr_status.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY};")

        controls = QHBoxLayout()
        self._audio_toggle = QPushButton("Pause Music")
        self._audio_toggle.clicked.connect(self._toggle_audio)
        self._audio_toggle.setCursor(Qt.PointingHandCursor)
        self._audio_toggle.setStyleSheet(self._button_style(ACCENT_CYAN))
        self._audio_toggle.setEnabled(self._sound is not None)
        controls.addWidget(self._audio_toggle)
        controls.addStretch()

        layout.addWidget(self._music_mode)
        layout.addWidget(self._music_reason)
        layout.addWidget(self._hr_status)
        if self._sound is None:
            warning = QLabel("Audio engine unavailable in this Qt build. Visual training still works.")
            warning.setWordWrap(True)
            warning.setStyleSheet(f"font-size: 11px; color: {ACCENT_RED};")
            layout.addWidget(warning)
        layout.addLayout(controls)
        layout.addStretch()
        return panel

    def _build_breath_panel(self) -> QWidget:
        panel, layout = self._panel("Calm Breath Game")

        copy = QLabel(
            "Hold calmness above 55 and stress below 40 to build a steady streak."
        )
        copy.setWordWrap(True)
        copy.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        self._breath_progress = QProgressBar()
        self._breath_progress.setRange(0, 30)
        self._breath_progress.setValue(0)
        self._breath_progress.setFormat("%v / %m sec")
        self._breath_progress.setStyleSheet(self._progress_style(ACCENT_GREEN))
        self._breath_status = QLabel("Status: waiting for stable calm state")
        self._breath_status.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY};")

        layout.addWidget(copy)
        layout.addWidget(self._breath_progress)
        layout.addWidget(self._breath_status)
        layout.addStretch()
        return panel

    def _build_focus_panel(self) -> QWidget:
        panel, layout = self._panel("Focus Match")

        copy = QLabel(
            "Tap the metric that is currently strongest. High focus and self-control increase score gain."
        )
        copy.setWordWrap(True)
        copy.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        self._focus_prompt = QLabel("Strongest state: --")
        self._focus_prompt.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {ACCENT_ORANGE};"
        )
        self._focus_score = QLabel("Score: 0 / 0")
        self._focus_score.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY};")

        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(8)
        btn_grid.setVerticalSpacing(8)
        self._focus_buttons = {}
        options = ["Focus", "Calmness", "Stress", "Self-control"]
        for index, label in enumerate(options):
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(self._button_style(ACCENT_ORANGE))
            button.clicked.connect(
                lambda checked=False, option=label: self._score_focus_round(option)
            )
            btn_grid.addWidget(button, index // 2, index % 2)
            self._focus_buttons[label] = button

        layout.addWidget(copy)
        layout.addWidget(self._focus_prompt)
        layout.addWidget(self._focus_score)
        layout.addLayout(btn_grid)
        layout.addStretch()
        return panel

    def _build_memory_panel(self) -> QWidget:
        panel, layout = self._panel("Memory Sequence")

        copy = QLabel(
            "Repeat the generated color sequence. Strong focus and calmness unlock longer patterns."
        )
        copy.setWordWrap(True)
        copy.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        self._memory_target = QLabel("Pattern: --")
        self._memory_target.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {ACCENT_GREEN};"
        )
        self._memory_status = QLabel("Press Start to generate a sequence")
        self._memory_status.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY};")
        self._memory_score_label = QLabel("Completed: 0")
        self._memory_score_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_PRIMARY};"
        )

        row = QHBoxLayout()
        self._memory_start = QPushButton("Start")
        self._memory_start.setCursor(Qt.PointingHandCursor)
        self._memory_start.setStyleSheet(self._button_style(ACCENT_GREEN))
        self._memory_start.clicked.connect(self._start_memory_round)
        row.addWidget(self._memory_start)

        self._memory_buttons = {}
        colors = [
            ("Blue", "#64B5F6"),
            ("Green", "#81C784"),
            ("Orange", "#FFB74D"),
            ("Red", "#E57373"),
        ]
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        for label, color in colors:
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(self._button_style(color))
            button.clicked.connect(
                lambda checked=False, value=label: self._memory_press(value)
            )
            self._memory_buttons[label] = button
            color_row.addWidget(button)

        layout.addWidget(copy)
        layout.addWidget(self._memory_target)
        layout.addWidget(self._memory_status)
        layout.addWidget(self._memory_score_label)
        layout.addLayout(row)
        layout.addLayout(color_row)
        layout.addStretch()
        return panel

    def _button_style(self, color: str) -> str:
        return (
            f"QPushButton {{ background: #20263f; color: {color}; border: 1px solid {color}; "
            f"border-radius: 8px; padding: 8px 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {color}; color: #10131f; }}"
        )

    def _progress_style(self, color: str) -> str:
        return (
            "QProgressBar { background: #10131f; color: #dfe6ff; border: 1px solid "
            f"{BORDER_SUBTLE}; border-radius: 6px; text-align: center; min-height: 20px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 5px; }}"
        )

    def _ensure_audio_assets(self):
        os.makedirs(self._audio_dir, exist_ok=True)
        tones = {
            "calm": (180.0, 222.0, 0.18),
            "focus": (220.0, 236.0, 0.22),
            "reset": (146.0, 196.0, 0.16),
        }
        for name, (carrier, accent, depth) in tones.items():
            path = os.path.join(self._audio_dir, f"{name}.wav")
            if not os.path.exists(path):
                self._write_tone(path, carrier, accent, depth)

    def _write_tone(self, path: str, carrier: float, accent: float, depth: float):
        sample_rate = 22050
        duration = 4
        frames = bytearray()
        for index in range(sample_rate * duration):
            t = index / sample_rate
            envelope = 0.55 + 0.45 * math.sin(2 * math.pi * depth * t)
            sample = (
                0.38 * math.sin(2 * math.pi * carrier * t)
                + 0.22 * math.sin(2 * math.pi * accent * t)
            ) * envelope
            clamped = max(-1.0, min(1.0, sample))
            frames.extend(struct.pack("<h", int(clamped * 32767)))
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(frames))

    def _advance_training(self):
        self._update_cards()
        self._update_breath_game()
        self._update_audio_mode()

    def _update_cards(self):
        emotions = self._latest_emotions
        self._focus_card.set_value(emotions.get("focus", 0))
        self._calm_card.set_value(emotions.get("chill", 0))
        self._stress_card.set_value(emotions.get("stress", 0))
        self._ctrl_card.set_value(emotions.get("selfControl", 0))

    def _update_breath_game(self):
        calm = float(self._latest_emotions.get("chill", 0))
        stress = float(self._latest_emotions.get("stress", 0))
        valid = not (
            self._latest_physio.get("nfbArtifacts", False)
            or self._latest_physio.get("cardioArtifacts", False)
        )

        if valid and calm >= 55 and stress <= 40:
            self._calm_streak = min(30, self._calm_streak + 1)
            self._breath_status.setText(
                f"Status: stable calm detected, keep breathing evenly ({self._calm_streak}s)"
            )
        else:
            self._calm_streak = max(0, self._calm_streak - 1)
            self._breath_status.setText(
                "Status: relax shoulders, slow exhale, and reduce motion artifacts"
            )
        self._breath_progress.setValue(self._calm_streak)

    def _update_audio_mode(self):
        focus = float(self._latest_emotions.get("focus", 0))
        calm = float(self._latest_emotions.get("chill", 0))
        stress = float(self._latest_emotions.get("stress", 0))
        self_ctrl = float(self._latest_emotions.get("selfControl", 0))
        hr = float(self._latest_cardio.get("heartRate", 0))
        concentration = float(self._latest_productivity.get("concentrationScore", 0))

        self._hr_status.setText(f"Heart rate: {hr:.1f} bpm")

        track = "reset"
        mode = "Reset / Recovery"
        reason = "Default recovery pulse helps settle the session."

        if stress >= 60 or hr >= 95:
            track = "calm"
            mode = "Calm Down"
            reason = "Stress or heart rate is elevated, so slower ambient pulses are selected."
        elif focus >= 60 and concentration >= 55 and self_ctrl >= 50:
            track = "focus"
            mode = "Deep Focus"
            reason = "Focus and concentration are stable, so sharper training pulses are selected."
        elif calm >= 55:
            track = "calm"
            mode = "Calm Stability"
            reason = "Calmness is strong, so low-pressure ambient tones reinforce the state."

        self._music_mode.setText(f"Mode: {mode}")
        self._music_reason.setText(f"Recommendation: {reason}")
        self._set_track(track)

    def _set_track(self, track: str):
        if not self._audio_enabled or self._active_track == track:
            if not self._audio_enabled and self._sound and self._sound.isPlaying():
                self._sound.stop()
            return
        path = os.path.join(self._audio_dir, f"{track}.wav")
        if not os.path.exists(path) or self._sound is None:
            return
        self._active_track = track
        self._sound.stop()
        self._sound.setSource(QUrl.fromLocalFile(path))
        self._sound.play()

    def _toggle_audio(self):
        self._audio_enabled = not self._audio_enabled
        if self._audio_enabled:
            self._audio_toggle.setText("Pause Music")
            self._active_track = ""
            self._update_audio_mode()
        else:
            self._audio_toggle.setText("Resume Music")
            if self._sound is not None:
                self._sound.stop()

    def _prepare_focus_round(self):
        values = {
            "Focus": float(self._latest_emotions.get("focus", 0)),
            "Calmness": float(self._latest_emotions.get("chill", 0)),
            "Stress": float(self._latest_emotions.get("stress", 0)),
            "Self-control": float(self._latest_emotions.get("selfControl", 0)),
        }
        self._focus_answer = max(values, key=values.get)
        self._focus_prompt.setText(f"Strongest state: {self._focus_answer}")
        self._focus_score.setText(f"Score: {self._focus_hits} / {self._focus_rounds}")

    def _score_focus_round(self, option: str):
        self._focus_rounds += 1
        if option == self._focus_answer:
            bonus_ready = (
                float(self._latest_emotions.get("focus", 0)) >= 60
                and float(self._latest_emotions.get("selfControl", 0)) >= 50
            )
            self._focus_hits += 2 if bonus_ready else 1
        self._prepare_focus_round()

    def _start_memory_round(self):
        level = 3
        if (
            float(self._latest_emotions.get("focus", 0)) >= 60
            and float(self._latest_emotions.get("chill", 0)) >= 50
        ):
            level = 5
        elif float(self._latest_emotions.get("focus", 0)) >= 45:
            level = 4
        palette = list(self._memory_buttons.keys())
        self._memory_sequence = [random.choice(palette) for _ in range(level)]
        self._memory_input = []
        self._memory_target.setText("Pattern: " + " - ".join(self._memory_sequence))
        self._memory_status.setText("Repeat the pattern using the color buttons")

    def _memory_press(self, value: str):
        if not self._memory_sequence:
            self._memory_status.setText("Press Start to generate a sequence")
            return
        self._memory_input.append(value)
        current_index = len(self._memory_input) - 1
        if self._memory_input[current_index] != self._memory_sequence[current_index]:
            self._memory_status.setText("Mismatch detected. Start a new round.")
            self._memory_input = []
            self._memory_sequence = []
            self._memory_target.setText("Pattern: --")
            return
        if len(self._memory_input) == len(self._memory_sequence):
            self._memory_score += 1
            self._memory_score_label.setText(f"Completed: {self._memory_score}")
            self._memory_status.setText("Correct. Start another round for a longer pattern.")
            self._memory_input = []
            self._memory_sequence = []
            self._memory_target.setText("Pattern: --")
        else:
            remaining = len(self._memory_sequence) - len(self._memory_input)
            self._memory_status.setText(f"Correct so far. {remaining} step(s) left.")

    def on_emotions(self, data: dict):
        self._latest_emotions = data or {}
        self._prepare_focus_round()

    def on_productivity(self, data: dict):
        self._latest_productivity = data or {}

    def on_cardio(self, data: dict):
        self._latest_cardio = data or {}

    def on_physio_states(self, data: dict):
        self._latest_physio = data or {}

    def stop_audio(self):
        if self._sound is not None:
            self._sound.stop()
