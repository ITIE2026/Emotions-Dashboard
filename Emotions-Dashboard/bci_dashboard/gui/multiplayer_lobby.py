"""
MultiplayerLobbyWidget – Host / Join UI for 2-player LAN games.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BG_CARD,
    BG_INPUT,
    BG_PRIMARY,
    BORDER_SUBTLE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

log = logging.getLogger(__name__)


# Game catalogue for selector cards
MP_GAMES = [
    {"id": "mp_tug_of_war",     "icon": "\U0001F4AA", "title": "Tug of War",
     "desc": "Pull the rope with concentration. 1-v-1 direct duel."},
    {"id": "mp_space_duel",     "icon": "\U0001F680", "title": "Space Duel",
     "desc": "Fly identical missions. Highest score wins."},
    {"id": "mp_maze_race",      "icon": "\U0001F9E9", "title": "Maze Race",
     "desc": "Race through the same maze. First to the goal wins."},
    {"id": "mp_bubble_battle",  "icon": "\U0001FAE7", "title": "Bubble Battle",
     "desc": "Pop bubbles on your board. Combos dump garbage on opponent."},
]


class MultiplayerLobbyWidget(QWidget):
    """Host or Join a multiplayer session on LAN."""

    host_requested = Signal(str, str)        # player_name, game_id
    join_requested = Signal(str, str, str)   # host_ip, player_name, game_id
    cancel_requested = Signal()
    start_game_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode: str | None = None   # "host" | "join" | None
        self._selected_game: str = MP_GAMES[0]["id"]
        self._game_cards: list[QWidget] = []
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)
        root.setSpacing(24)
        root.setContentsMargins(60, 40, 60, 40)

        # Title
        title = QLabel("\u2694\uFE0F  Multiplayer Arena")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {ACCENT_GREEN}; "
            f"background: transparent;"
        )
        root.addWidget(title)

        subtitle = QLabel("Each player needs their own headband connected to their own PC")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 13px; color: {TEXT_SECONDARY}; background: transparent;"
        )
        root.addWidget(subtitle)

        root.addSpacing(12)

        # ── Game selector cards ───────────────────────────────────
        game_row = QHBoxLayout()
        game_row.setSpacing(12)
        game_row.addStretch()
        for info in MP_GAMES:
            card = self._make_game_card(info)
            game_row.addWidget(card)
        game_row.addStretch()
        root.addLayout(game_row)
        # Highlight default selection
        self._highlight_selected_game()

        root.addSpacing(12)

        # ── Name input ────────────────────────────────────────────
        name_row = QHBoxLayout()
        name_lbl = QLabel("Your name:")
        name_lbl.setStyleSheet(
            f"font-size: 13px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._name_input = QLineEdit("Player")
        self._name_input.setMaxLength(20)
        self._name_input.setFixedWidth(200)
        name_row.addStretch()
        name_row.addWidget(name_lbl)
        name_row.addWidget(self._name_input)
        name_row.addStretch()
        root.addLayout(name_row)

        root.addSpacing(8)

        # ── Host / Join buttons ───────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.addStretch()

        self._host_btn = QPushButton("\U0001F3E0  Host Game")
        self._host_btn.setProperty("class", "primary")
        self._host_btn.setFixedSize(200, 48)
        self._host_btn.setCursor(Qt.PointingHandCursor)
        self._host_btn.clicked.connect(self._on_host_click)
        btn_row.addWidget(self._host_btn)

        self._join_btn = QPushButton("\U0001F517  Join Game")
        self._join_btn.setProperty("class", "primary")
        self._join_btn.setFixedSize(200, 48)
        self._join_btn.setCursor(Qt.PointingHandCursor)
        self._join_btn.clicked.connect(self._on_join_click)
        btn_row.addWidget(self._join_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addSpacing(8)

        # ── Join: IP input (hidden initially) ─────────────────────
        self._ip_row = QWidget()
        ip_layout = QHBoxLayout(self._ip_row)
        ip_layout.setContentsMargins(0, 0, 0, 0)
        ip_lbl = QLabel("Host IP:")
        ip_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent;")
        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("e.g. 192.168.1.42")
        self._ip_input.setFixedWidth(200)
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setProperty("class", "primary")
        self._connect_btn.setCursor(Qt.PointingHandCursor)
        self._connect_btn.clicked.connect(self._on_connect_click)
        ip_layout.addStretch()
        ip_layout.addWidget(ip_lbl)
        ip_layout.addWidget(self._ip_input)
        ip_layout.addWidget(self._connect_btn)
        ip_layout.addStretch()
        self._ip_row.hide()
        root.addWidget(self._ip_row)

        # ── Status area ───────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"font-size: 14px; color: {ACCENT_CYAN}; background: transparent;"
        )
        root.addWidget(self._status_lbl)

        # ── Player cards ──────────────────────────────────────────
        players_row = QHBoxLayout()
        players_row.setSpacing(20)
        players_row.addStretch()

        self._p1_card = self._make_player_card("Player 1", ACCENT_GREEN)
        self._p2_card = self._make_player_card("Waiting...", TEXT_SECONDARY)
        players_row.addWidget(self._p1_card["widget"])
        players_row.addWidget(self._p2_card["widget"])

        players_row.addStretch()
        root.addLayout(players_row)

        # ── Bottom buttons ────────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        self._cancel_btn = QPushButton("Leave")
        self._cancel_btn.setProperty("class", "secondary")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.hide()
        bottom_row.addWidget(self._cancel_btn)

        self._start_btn = QPushButton("\u25B6  Start Match")
        self._start_btn.setProperty("class", "primary")
        self._start_btn.setFixedSize(180, 44)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self.start_game_requested.emit)
        self._start_btn.setEnabled(False)
        self._start_btn.hide()
        bottom_row.addWidget(self._start_btn)

        bottom_row.addStretch()
        root.addLayout(bottom_row)

        root.addStretch()

    # ── Game card builder ─────────────────────────────────────────
    def _make_game_card(self, info: dict) -> QWidget:
        card = QWidget()
        card.setFixedSize(160, 90)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("game_id", info["id"])
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        title_lbl = QLabel(f"{info['icon']}  {info['title']}")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(title_lbl)

        desc_lbl = QLabel(info["desc"])
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"font-size: 10px; color: {TEXT_SECONDARY}; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(desc_lbl)

        card.mousePressEvent = lambda ev, gid=info["id"]: self._on_game_card_click(gid)
        self._game_cards.append(card)
        return card

    def _on_game_card_click(self, game_id: str):
        self._selected_game = game_id
        self._highlight_selected_game()

    def _highlight_selected_game(self):
        for card in self._game_cards:
            gid = card.property("game_id")
            if gid == self._selected_game:
                card.setStyleSheet(
                    f"background: {BG_CARD}; border: 2px solid {ACCENT_GREEN}; "
                    f"border-radius: 12px;"
                )
            else:
                card.setStyleSheet(
                    f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; "
                    f"border-radius: 12px;"
                )

    # ── Player card builder ───────────────────────────────────────
    @staticmethod
    def _make_player_card(name: str, color: str) -> dict:
        card = QWidget()
        card.setFixedSize(200, 120)
        card.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; "
            f"border-radius: 14px;"
        )
        lay = QVBoxLayout(card)
        lay.setAlignment(Qt.AlignCenter)

        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {color}; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(name_lbl)

        status_lbl = QLabel("")
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(status_lbl)

        card.hide()
        return {"widget": card, "name": name_lbl, "status": status_lbl}

    # ── Handlers ──────────────────────────────────────────────────
    def _on_host_click(self):
        self._mode = "host"
        name = self._name_input.text().strip() or "Player 1"
        self._host_btn.hide()
        self._join_btn.hide()
        self._cancel_btn.show()
        self._start_btn.show()
        self._p1_card["widget"].show()
        self._p2_card["widget"].show()
        self._p1_card["name"].setText(name)
        self._p1_card["name"].setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ACCENT_GREEN}; "
            f"background: transparent; border: none;"
        )
        self._p1_card["status"].setText("Host (you)")
        self._status_lbl.setText("Starting server...")
        self.host_requested.emit(name, self._selected_game)

    def _on_join_click(self):
        self._mode = "join"
        self._host_btn.hide()
        self._join_btn.hide()
        self._ip_row.show()
        self._cancel_btn.show()
        self._status_lbl.setText("Enter the host's IP address to connect")

    def _on_connect_click(self):
        ip = self._ip_input.text().strip()
        if not ip:
            self._status_lbl.setText("Please enter an IP address")
            return
        name = self._name_input.text().strip() or "Player 2"
        self._status_lbl.setText(f"Connecting to {ip}...")
        self._connect_btn.setEnabled(False)
        self.join_requested.emit(ip, name, self._selected_game)

    def _on_cancel(self):
        self.cancel_requested.emit()
        self.reset()

    # ── Public update methods ─────────────────────────────────────
    def set_server_address(self, addr: str):
        self._status_lbl.setText(
            f"Hosting on  <b>{addr}</b><br>"
            f"Share this IP with your opponent to connect"
        )

    def set_connected_as_guest(self):
        self._ip_row.hide()
        self._p1_card["widget"].show()
        self._p2_card["widget"].show()
        self._status_lbl.setText("Connected! Waiting for host to start...")

    def update_lobby(self, lobby: dict):
        players = lobby.get("players", [])
        if len(players) >= 1:
            p1 = players[0]
            self._p1_card["name"].setText(p1.get("name", "Player 1"))
            cal_pct = int(p1.get("calibration_progress", 0) * 100)
            status = "Ready" if p1.get("calibrated") else f"Calibrating... {cal_pct}%"
            if not p1.get("calibrated") and cal_pct == 0:
                status = "Host" if p1.get("role") == "host" else "Connected"
            self._p1_card["status"].setText(status)

        if len(players) >= 2:
            p2 = players[1]
            self._p2_card["name"].setText(p2.get("name", "Player 2"))
            self._p2_card["name"].setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {ACCENT_CYAN}; "
                f"background: transparent; border: none;"
            )
            cal_pct = int(p2.get("calibration_progress", 0) * 100)
            status = "Ready" if p2.get("calibrated") else f"Calibrating... {cal_pct}%"
            if not p2.get("calibrated") and cal_pct == 0:
                status = "Connected"
            self._p2_card["status"].setText(status)

            both_calibrated = players[0].get("calibrated") and players[1].get("calibrated")
            if self._mode == "host":
                self._start_btn.setEnabled(both_calibrated)
                if both_calibrated:
                    self._status_lbl.setText("Both players calibrated — ready to start!")
        else:
            self._p2_card["name"].setText("Waiting for opponent...")
            self._p2_card["name"].setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {TEXT_SECONDARY}; "
                f"background: transparent; border: none;"
            )
            self._p2_card["status"].setText("")

    def show_error(self, msg: str):
        self._status_lbl.setText(f'<span style="color:{ACCENT_RED}">{msg}</span>')
        self._connect_btn.setEnabled(True)

    def show_player_joined(self, name: str):
        self._status_lbl.setText(
            f'<b>{name}</b> joined! Calibrating...'
        )

    def show_player_left(self, name: str):
        self._status_lbl.setText(
            f'<span style="color:{ACCENT_RED}">{name} left the game</span>'
        )
        self._start_btn.setEnabled(False)

    def reset(self):
        self._mode = None
        self._host_btn.show()
        self._join_btn.show()
        self._ip_row.hide()
        self._cancel_btn.hide()
        self._start_btn.hide()
        self._start_btn.setEnabled(False)
        self._p1_card["widget"].hide()
        self._p2_card["widget"].hide()
        self._status_lbl.setText("")
        self._connect_btn.setEnabled(True)
        self._ip_input.clear()
        self._selected_game = MP_GAMES[0]["id"]
        self._highlight_selected_game()
