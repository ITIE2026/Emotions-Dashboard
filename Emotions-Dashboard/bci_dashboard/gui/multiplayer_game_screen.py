"""
MultiplayerGameScreen – orchestrates lobby → calibration → gameplay → result
for 2-player LAN games (Tug of War, Space Duel, Maze Race, Bubble Battle).
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.multiplayer_lobby import MultiplayerLobbyWidget
from gui.multiplayer_tug_of_war import MultiplayerTugOfWarController
from gui.multiplayer_space_duel import MultiplayerSpaceDuelController
from gui.multiplayer_maze_race import MultiplayerMazeRaceController
from gui.multiplayer_bubble_battle import MultiplayerBubbleBattleController
from gui.widgets.training_game_widgets import TugOfWarWidget, SpaceShooterWidget, BubbleBurstWidget
from gui.widgets.maze_race_widget import MazeRaceWidget
from multiplayer.client import MultiplayerClient
from multiplayer.protocol import DEFAULT_PORT
from multiplayer.server import MultiplayerServer
from utils.config import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BG_CARD,
    BG_PRIMARY,
    BORDER_SUBTLE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

log = logging.getLogger(__name__)

PAGE_LOBBY = 0
PAGE_CALIBRATION = 1
PAGE_GAMEPLAY = 2
PAGE_RESULT = 3

# Registry: game_id → (controller_factory, widget_factory)
MP_GAME_REGISTRY: dict[str, tuple] = {
    "mp_tug_of_war":    (MultiplayerTugOfWarController, TugOfWarWidget),
    "mp_space_duel":    (MultiplayerSpaceDuelController, SpaceShooterWidget),
    "mp_maze_race":     (MultiplayerMazeRaceController, MazeRaceWidget),
    "mp_bubble_battle": (MultiplayerBubbleBattleController, BubbleBurstWidget),
}

# Games that send per-player views (each player sees own board/ship)
_PER_PLAYER_VIEW_GAMES = {"mp_space_duel", "mp_bubble_battle"}


class MultiplayerGameScreen(QWidget):
    """Full-screen multiplayer game flow embedded in the main dashboard stack."""

    go_home = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._role: str | None = None  # "host" | "guest"
        self._game_id: str = "mp_tug_of_war"
        self._server: MultiplayerServer | None = None
        self._client: MultiplayerClient | None = None
        self._controller = None

        # Latest local BCI metrics
        self._latest_conc = 0.0
        self._latest_relax = 0.0
        self._latest_valid = False
        self._latest_stale = True
        self._has_artifacts = False
        self._streaming = False
        self._view_active = False

        self._calibration_timer = QTimer(self)
        self._calibration_timer.setInterval(250)
        self._calibration_timer.timeout.connect(self._tick_calibration)

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(200)
        self._metrics_timer.timeout.connect(self._send_metrics_tick)

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()

        # Page 0: Lobby
        self._lobby = MultiplayerLobbyWidget()
        self._lobby.host_requested.connect(self._on_host)
        self._lobby.join_requested.connect(self._on_join)
        self._lobby.cancel_requested.connect(self._on_cancel)
        self._lobby.start_game_requested.connect(self._on_start_requested)
        self._stack.addWidget(self._lobby)

        # Page 1: Calibration (side-by-side progress)
        self._cal_page = self._build_calibration_page()
        self._stack.addWidget(self._cal_page)

        # Page 2: Gameplay
        self._gameplay_page = self._build_gameplay_page()
        self._stack.addWidget(self._gameplay_page)

        # Page 3: Result
        self._result_page = self._build_result_page()
        self._stack.addWidget(self._result_page)

        root.addWidget(self._stack)

    def _build_calibration_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)
        lay.setContentsMargins(60, 40, 60, 40)

        title = QLabel("\U0001F9E0  Calibrating Both Players")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {ACCENT_GREEN}; "
            f"background: transparent;"
        )
        lay.addWidget(title)

        hint = QLabel("Relax and look at the screen. The baseline will be captured automatically.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY}; background: transparent;")
        lay.addWidget(hint)

        lay.addSpacing(24)

        # Player 1 progress
        row1 = QHBoxLayout()
        self._cal_p1_label = QLabel("Player 1")
        self._cal_p1_label.setStyleSheet(
            f"font-size: 14px; color: {ACCENT_GREEN}; font-weight: bold; background: transparent;"
        )
        self._cal_p1_bar = QProgressBar()
        self._cal_p1_bar.setRange(0, 100)
        self._cal_p1_bar.setValue(0)
        self._cal_p1_bar.setFixedHeight(12)
        self._cal_p1_bar.setFixedWidth(300)
        self._cal_p1_status = QLabel("")
        self._cal_p1_status.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;")
        row1.addStretch()
        row1.addWidget(self._cal_p1_label)
        row1.addWidget(self._cal_p1_bar)
        row1.addWidget(self._cal_p1_status)
        row1.addStretch()
        lay.addLayout(row1)

        # Player 2 progress
        row2 = QHBoxLayout()
        self._cal_p2_label = QLabel("Player 2")
        self._cal_p2_label.setStyleSheet(
            f"font-size: 14px; color: {ACCENT_CYAN}; font-weight: bold; background: transparent;"
        )
        self._cal_p2_bar = QProgressBar()
        self._cal_p2_bar.setRange(0, 100)
        self._cal_p2_bar.setValue(0)
        self._cal_p2_bar.setFixedHeight(12)
        self._cal_p2_bar.setFixedWidth(300)
        self._cal_p2_status = QLabel("")
        self._cal_p2_status.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY}; background: transparent;")
        row2.addStretch()
        row2.addWidget(self._cal_p2_label)
        row2.addWidget(self._cal_p2_bar)
        row2.addWidget(self._cal_p2_status)
        row2.addStretch()
        lay.addLayout(row2)

        lay.addStretch()
        return page

    def _build_gameplay_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Top bar with player names
        top_bar = QWidget()
        top_bar.setFixedHeight(40)
        top_bar.setStyleSheet(f"background: {BG_CARD};")
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(16, 0, 16, 0)
        self._gp_p1_lbl = QLabel("Player 1")
        self._gp_p1_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {ACCENT_GREEN}; background: transparent;"
        )
        self._gp_vs_lbl = QLabel("VS")
        self._gp_vs_lbl.setAlignment(Qt.AlignCenter)
        self._gp_vs_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {TEXT_SECONDARY}; background: transparent;"
        )
        self._gp_p2_lbl = QLabel("Player 2")
        self._gp_p2_lbl.setAlignment(Qt.AlignRight)
        self._gp_p2_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {ACCENT_CYAN}; background: transparent;"
        )
        tb_lay.addWidget(self._gp_p1_lbl)
        tb_lay.addStretch()
        tb_lay.addWidget(self._gp_vs_lbl)
        tb_lay.addStretch()
        tb_lay.addWidget(self._gp_p2_lbl)
        lay.addWidget(top_bar)

        # Container for the dynamic game widget
        self._game_container = QVBoxLayout()
        self._game_container.setContentsMargins(0, 0, 0, 0)
        self._game_widget: QWidget | None = None
        lay.addLayout(self._game_container, stretch=1)

        return page

    def _swap_game_widget(self):
        """Replace the game widget in the gameplay page based on self._game_id."""
        # Remove old widget
        if self._game_widget is not None:
            self._game_container.removeWidget(self._game_widget)
            self._game_widget.setParent(None)
            self._game_widget.deleteLater()
            self._game_widget = None

        # Create new widget from registry
        _, widget_cls = MP_GAME_REGISTRY.get(self._game_id, (None, TugOfWarWidget))
        self._game_widget = widget_cls()
        self._game_container.addWidget(self._game_widget)

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(20)
        lay.setContentsMargins(60, 60, 60, 60)

        self._result_title = QLabel("")
        self._result_title.setAlignment(Qt.AlignCenter)
        self._result_title.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {ACCENT_GREEN}; background: transparent;"
        )
        lay.addWidget(self._result_title)

        self._result_detail = QLabel("")
        self._result_detail.setAlignment(Qt.AlignCenter)
        self._result_detail.setWordWrap(True)
        self._result_detail.setStyleSheet(
            f"font-size: 15px; color: {TEXT_PRIMARY}; background: transparent;"
        )
        lay.addWidget(self._result_detail)

        lay.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._rematch_btn = QPushButton("\U0001F504  Rematch")
        self._rematch_btn.setProperty("class", "primary")
        self._rematch_btn.setFixedSize(160, 44)
        self._rematch_btn.setCursor(Qt.PointingHandCursor)
        self._rematch_btn.clicked.connect(self._on_rematch)
        btn_row.addWidget(self._rematch_btn)

        self._back_btn = QPushButton("\U0001F3E0  Back to Lobby")
        self._back_btn.setProperty("class", "secondary")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back_to_lobby)
        btn_row.addWidget(self._back_btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addStretch()
        return page

    # ── Public API (called by MainWindow / SignalDispatcher) ──────
    def on_productivity(self, data: dict):
        self._latest_conc = float(data.get("concentrationScore", 0.0) or 0.0)
        self._latest_relax = float(data.get("relaxationScore", 0.0) or 0.0)
        self._latest_stale = False
        self._latest_valid = True

    def on_physio_states(self, data: dict):
        artifacts = data.get("nfbArtifacts")
        self._has_artifacts = bool(artifacts) if artifacts is not None else False

    def set_streaming_active(self, active: bool):
        self._streaming = active

    def set_view_active(self, active: bool):
        self._view_active = active

    def stop_active_flow(self):
        self._stop_all()
        self._stack.setCurrentIndex(PAGE_LOBBY)
        self._lobby.reset()

    def shutdown(self):
        self._stop_all()

    # ── Host / Join handlers ──────────────────────────────────────
    def _on_host(self, name: str, game_id: str):
        self._role = "host"
        self._game_id = game_id

        ctrl_cls, _ = MP_GAME_REGISTRY.get(game_id, (MultiplayerTugOfWarController, TugOfWarWidget))
        self._controller = ctrl_cls(p1_name=name)

        self._swap_game_widget()

        self._server = MultiplayerServer(parent=self)
        self._server.set_controller(self._controller)
        self._server.server_started.connect(self._lobby.set_server_address)
        self._server.player_joined.connect(self._lobby.show_player_joined)
        self._server.player_joined.connect(self._on_guest_joined)
        self._server.player_left.connect(self._lobby.show_player_left)
        self._server.lobby_updated.connect(self._lobby.update_lobby)
        self._server.game_state_broadcast.connect(self._on_game_state)
        self._server.game_over.connect(self._on_game_over)
        self._server.error_occurred.connect(self._lobby.show_error)
        self._server.start(DEFAULT_PORT, host_name=name, game_id=game_id)

    def _on_join(self, host_ip: str, name: str, game_id: str):
        self._role = "guest"
        self._game_id = game_id

        self._swap_game_widget()

        self._client = MultiplayerClient(parent=self)
        self._client.connected.connect(self._lobby.set_connected_as_guest)
        self._client.lobby_updated.connect(self._lobby.update_lobby)
        self._client.calibration_sync.connect(self._on_calibration_sync_received)
        self._client.game_started.connect(self._on_game_started_as_guest)
        self._client.game_state_received.connect(self._on_game_state)
        self._client.game_over.connect(self._on_game_over)
        self._client.error_occurred.connect(self._lobby.show_error)
        self._client.disconnected.connect(lambda: self._lobby.show_error("Disconnected from host"))
        self._client.connect_to(host_ip, DEFAULT_PORT, player_name=name)

    def _on_cancel(self):
        self._stop_all()

    def _on_guest_joined(self, guest_name: str):
        """When guest joins, start calibration for both players."""
        self._start_calibration()

    def _on_start_requested(self):
        """Host clicked Start Match after both calibrated."""
        if self._server and self._role == "host":
            self._server.host_set_ready()
            self._start_gameplay()

    # ── Calibration ───────────────────────────────────────────────
    def _start_calibration(self):
        self._stack.setCurrentIndex(PAGE_CALIBRATION)
        self._cal_p1_bar.setValue(0)
        self._cal_p2_bar.setValue(0)
        self._cal_p1_status.setText("")
        self._cal_p2_status.setText("")
        self._calibration_timer.start()

    def _tick_calibration(self):
        """Feed local metrics as calibration sample (for host = player 0)."""
        if self._role == "host" and self._server and self._controller:
            valid = self._latest_valid and not self._has_artifacts and not self._latest_stale
            self._server.feed_host_calibration(
                self._latest_conc, self._latest_relax, valid
            )
        elif self._role == "guest" and self._client:
            valid = self._latest_valid and not self._has_artifacts and not self._latest_stale
            self._client.send_calibration_sample(
                self._latest_conc, self._latest_relax, valid
            )

    def _on_calibration_sync_received(self, data: dict):
        """Received from network – update both progress bars."""
        player_id = data.get("player_id", 0)
        snapshot = data.get("snapshot", {})
        progress = snapshot.get("progress", 0.0)
        complete = snapshot.get("complete", False)

        bar = self._cal_p1_bar if player_id == 0 else self._cal_p2_bar
        status_lbl = self._cal_p1_status if player_id == 0 else self._cal_p2_status

        bar.setValue(int(progress * 100))
        if complete:
            status_lbl.setText("\u2705 Ready")
            status_lbl.setStyleSheet(
                f"font-size: 12px; color: {ACCENT_GREEN}; background: transparent;"
            )
        else:
            status_lbl.setText(f"{int(progress * 100)}%")

    # ── Game start ────────────────────────────────────────────────
    def _on_game_started_as_guest(self):
        """Guest received GAME_START from server."""
        self._calibration_timer.stop()
        self._start_gameplay()

    def _start_gameplay(self):
        self._calibration_timer.stop()
        self._stack.setCurrentIndex(PAGE_GAMEPLAY)

        # Set player names on the top bar
        if self._controller:
            self._gp_p1_lbl.setText(getattr(self._controller, "_p1_name", "Player 1"))
            self._gp_p2_lbl.setText(getattr(self._controller, "_p2_name", "Player 2"))

        # Start sending metrics at regular intervals
        self._metrics_timer.start()

    def _send_metrics_tick(self):
        """Periodically send local metrics to server/client."""
        valid = self._latest_valid and not self._has_artifacts and not self._latest_stale
        if self._role == "host" and self._server:
            self._server.feed_host_metrics(
                self._latest_conc, self._latest_relax,
                valid, self._latest_stale,
            )
        elif self._role == "guest" and self._client:
            self._client.send_metrics(
                self._latest_conc, self._latest_relax,
                valid, self._latest_stale,
            )

    # ── Game state rendering ──────────────────────────────────────
    def _on_game_state(self, view_state: dict):
        """Update the game widget with networked game state."""
        # Per-player view games (Space Duel, Bubble Battle):
        # host sees player 0, guest sees player 1
        if self._game_id in _PER_PLAYER_VIEW_GAMES:
            player_views = view_state.get("player_views", {})
            my_key = "0" if self._role == "host" else "1"
            my_view = player_views.get(my_key, {})
            if self._game_widget and hasattr(self._game_widget, "set_state"):
                self._game_widget.set_state(my_view)
        else:
            # Shared-view games (Tug of War, Maze Race)
            if self._game_widget and hasattr(self._game_widget, "set_view_state"):
                self._game_widget.set_view_state(view_state)
            elif self._game_widget and hasattr(self._game_widget, "set_state"):
                self._game_widget.set_state(view_state)

        # Update player names from state
        p1 = view_state.get("player1_name", "")
        p2 = view_state.get("player2_name", "")
        if p1:
            self._gp_p1_lbl.setText(p1)
        if p2:
            self._gp_p2_lbl.setText(p2)

    # ── Game over ─────────────────────────────────────────────────
    def _on_game_over(self, result: dict):
        self._metrics_timer.stop()
        self._stack.setCurrentIndex(PAGE_RESULT)

        winner = result.get("winner", "draw")
        p1_score = result.get("player1_score", result.get("player_score", 0))
        p2_score = result.get("player2_score", result.get("system_score", 0))
        reason = result.get("reason", "")

        p1_name = getattr(self._controller, "_p1_name", "Player 1") if self._controller else "Player 1"
        p2_name = getattr(self._controller, "_p2_name", "Player 2") if self._controller else "Player 2"

        if winner == "draw":
            self._result_title.setText("\U0001F91D  It's a Draw!")
            self._result_title.setStyleSheet(
                f"font-size: 28px; font-weight: bold; color: {ACCENT_CYAN}; background: transparent;"
            )
        elif winner == "host" or winner == "player1":
            self._result_title.setText(f"\U0001F3C6  {p1_name} Wins!")
            self._result_title.setStyleSheet(
                f"font-size: 28px; font-weight: bold; color: {ACCENT_GREEN}; background: transparent;"
            )
        else:
            self._result_title.setText(f"\U0001F3C6  {p2_name} Wins!")
            self._result_title.setStyleSheet(
                f"font-size: 28px; font-weight: bold; color: {ACCENT_CYAN}; background: transparent;"
            )

        detail = f"Score: {p1_score} – {p2_score}"
        if reason:
            detail += f"\n{reason}"
        self._result_detail.setText(detail)

    # ── Rematch / Back ────────────────────────────────────────────
    def _on_rematch(self):
        if self._role == "host" and self._controller and self._game_id:
            ctrl_cls = MP_GAME_REGISTRY[self._game_id][0]
            p1 = getattr(self._controller, "_p1_name", "Player 1")
            p2 = getattr(self._controller, "_p2_name", "Player 2")
            self._controller = ctrl_cls(p1_name=p1, p2_name=p2)
            if self._server:
                self._server.set_controller(self._controller)
            self._start_calibration()
        elif self._role == "guest":
            self._start_calibration()

    def _on_back_to_lobby(self):
        self._stop_all()
        self._lobby.reset()
        self._stack.setCurrentIndex(PAGE_LOBBY)

    # ── Cleanup ───────────────────────────────────────────────────
    def _stop_all(self):
        self._calibration_timer.stop()
        self._metrics_timer.stop()
        if self._server:
            self._server.stop()
            self._server = None
        if self._client:
            self._client.disconnect()
            self._client = None
        self._controller = None
        self._role = None
        self._game_id = None
