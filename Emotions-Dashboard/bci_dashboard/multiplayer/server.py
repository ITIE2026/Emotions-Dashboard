"""
MultiplayerServer – WebSocket host running in a daemon thread.

The hosting PC runs this server.  It accepts exactly one guest
connection, collects BCI metrics from both players, runs the
authoritative game controller, and broadcasts game state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from multiplayer.protocol import (
    DEFAULT_PORT,
    MSG_CALIBRATION_SAMPLE,
    MSG_CALIBRATION_SYNC,
    MSG_ERROR,
    MSG_GAME_OVER,
    MSG_GAME_START,
    MSG_GAME_STATE,
    MSG_HELLO,
    MSG_LOBBY_UPDATE,
    MSG_METRICS,
    MSG_PLAYER_LEFT,
    MSG_READY,
    MSG_WELCOME,
    LobbyState,
    PlayerInfo,
    encode_msg,
    decode_msg,
    lobby_to_dict,
)

log = logging.getLogger(__name__)


def _get_lan_ip() -> str:
    """Best-effort LAN IP (falls back to 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class MultiplayerServer(QObject):
    """Embedded WebSocket server for 2-player LAN games."""

    # Qt signals (thread-safe via queued connections)
    server_started = Signal(str)       # "ip:port"
    player_joined = Signal(str)        # player name
    player_left = Signal(str)          # player name
    lobby_updated = Signal(dict)       # LobbyState-as-dict
    game_state_broadcast = Signal(dict)  # view_state
    game_over = Signal(dict)           # result dict
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._port = DEFAULT_PORT
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server = None
        self._guest_ws = None
        self._lobby = LobbyState()
        self._host_metrics: dict[str, Any] = {}
        self._guest_metrics: dict[str, Any] = {}
        self._controller = None
        self._game_running = False
        self._host_ready = False
        self._guest_ready = False
        self._host_calibrated = False
        self._guest_calibrated = False

    # ── Public API ────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def lobby(self) -> LobbyState:
        return self._lobby

    def start(self, port: int = DEFAULT_PORT, host_name: str = "Player 1",
              game_id: str = "mp_tug_of_war"):
        if self.is_running:
            return
        self._port = port
        self._lobby = LobbyState(
            players=[PlayerInfo(player_id=0, name=host_name, role="host")],
            game_id=game_id,
            status="waiting",
        )
        self._host_ready = False
        self._guest_ready = False
        self._host_calibrated = False
        self._guest_calibrated = False
        self._game_running = False
        self._guest_ws = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="mp-server"
        )
        self._thread.start()

    def stop(self):
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        self._loop = None
        self._server = None
        self._guest_ws = None
        self._game_running = False

    def set_controller(self, controller):
        self._controller = controller

    # ── Host-side metric injection ────────────────────────────────
    def feed_host_metrics(self, concentration: float, relaxation: float,
                          valid: bool, stale: bool):
        self._host_metrics = {
            "concentration": concentration,
            "relaxation": relaxation,
            "valid": valid,
            "stale": stale,
        }

    def feed_host_calibration(self, concentration: float, relaxation: float,
                              valid: bool):
        if self._loop and self._controller:
            self._loop.call_soon_threadsafe(
                self._handle_calibration, 0, concentration, relaxation, valid
            )

    def host_set_ready(self):
        self._host_ready = True
        self._check_both_ready()

    # ── Private – event loop ──────────────────────────────────────
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:
            log.error("Server loop error: %s", exc)
            self.error_occurred.emit(str(exc))

    async def _serve(self):
        try:
            import websockets
            import websockets.asyncio.server as ws_server
        except ImportError:
            self.error_occurred.emit(
                "websockets package not installed.  Run: pip install websockets"
            )
            return

        lan_ip = _get_lan_ip()
        try:
            self._server = await ws_server.serve(
                self._on_connection, "0.0.0.0", self._port,
            )
        except OSError as exc:
            self.error_occurred.emit(f"Cannot bind port {self._port}: {exc}")
            return

        addr = f"{lan_ip}:{self._port}"
        log.info("Multiplayer server listening on %s", addr)
        self.server_started.emit(addr)
        self._emit_lobby()

        await asyncio.Future()  # run forever until loop.stop()

    # ── Connection handler ────────────────────────────────────────
    async def _on_connection(self, ws):
        if self._guest_ws is not None:
            await ws.send(encode_msg(MSG_ERROR, {"message": "Room is full"}))
            await ws.close()
            return

        self._guest_ws = ws
        guest_name = "Player 2"
        try:
            async for raw in ws:
                msg_type, payload = decode_msg(raw)

                if msg_type == MSG_HELLO:
                    guest_name = payload.get("name", "Player 2")
                    self._lobby.players = [
                        self._lobby.players[0],
                        PlayerInfo(player_id=1, name=guest_name, role="guest"),
                    ]
                    self._emit_lobby()
                    await ws.send(encode_msg(MSG_WELCOME, {
                        "player_id": 1,
                        "lobby": lobby_to_dict(self._lobby),
                    }))
                    self.player_joined.emit(guest_name)

                elif msg_type == MSG_METRICS:
                    self._guest_metrics = payload
                    if self._game_running:
                        self._tick_game()

                elif msg_type == MSG_CALIBRATION_SAMPLE:
                    self._handle_calibration(
                        1,
                        payload.get("concentration", 0.0),
                        payload.get("relaxation", 0.0),
                        payload.get("valid", False),
                    )

                elif msg_type == MSG_READY:
                    self._guest_ready = True
                    self._check_both_ready()

        except Exception as exc:
            log.warning("Guest disconnected: %s", exc)
        finally:
            self._guest_ws = None
            if len(self._lobby.players) > 1:
                left_name = self._lobby.players[1].name
                self._lobby.players = self._lobby.players[:1]
                self.player_left.emit(left_name)
            self._guest_ready = False
            self._guest_calibrated = False
            if self._game_running:
                self._game_running = False
                result = {"winner": "host", "reason": "Guest disconnected"}
                self.game_over.emit(result)
                self._broadcast_sync(encode_msg(MSG_GAME_OVER, result))
            self._lobby.status = "waiting"
            self._emit_lobby()

    # ── Calibration ───────────────────────────────────────────────
    def _handle_calibration(self, player_id: int, conc: float, relax: float,
                            valid: bool):
        if self._controller is None:
            return
        snapshot = self._controller.add_calibration_sample_for(
            player_id, conc, relax, valid
        )
        if player_id == 0:
            self._host_calibrated = snapshot.get("complete", False)
        else:
            self._guest_calibrated = snapshot.get("complete", False)

        # Update lobby player calibration progress
        if player_id < len(self._lobby.players):
            p = self._lobby.players[player_id]
            p.calibration_progress = snapshot.get("progress", 0.0)
            p.calibrated = snapshot.get("complete", False)

        sync_payload = {"player_id": player_id, "snapshot": snapshot}
        self._broadcast_sync(encode_msg(MSG_CALIBRATION_SYNC, sync_payload))
        self._emit_lobby()

    # ── Ready / start ─────────────────────────────────────────────
    def _check_both_ready(self):
        if self._host_ready and self._guest_ready:
            if self._host_calibrated and self._guest_calibrated:
                self._start_game()

    def _start_game(self):
        if self._controller:
            self._controller.start_game()
        self._game_running = True
        self._lobby.status = "playing"
        self._emit_lobby()
        self._broadcast_sync(encode_msg(MSG_GAME_START, {}))

    # ── Game tick ─────────────────────────────────────────────────
    def _tick_game(self):
        if not self._controller or not self._game_running:
            return
        view_state = self._controller.tick(self._host_metrics, self._guest_metrics)
        msg = encode_msg(MSG_GAME_STATE, view_state)
        self._broadcast_sync(msg)
        self.game_state_broadcast.emit(view_state)

        if view_state.get("run_completed"):
            self._game_running = False
            self._lobby.status = "finished"
            result = {
                "winner": view_state.get("winner", "draw"),
                "player1_score": view_state.get("player1_score", 0),
                "player2_score": view_state.get("player2_score", 0),
            }
            self.game_over.emit(result)
            self._broadcast_sync(encode_msg(MSG_GAME_OVER, result))
            self._emit_lobby()

    # ── Helpers ───────────────────────────────────────────────────
    def _broadcast_sync(self, msg: str):
        if self._guest_ws and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._safe_send(self._guest_ws, msg), self._loop
            )

    @staticmethod
    async def _safe_send(ws, msg: str):
        try:
            await ws.send(msg)
        except Exception:
            pass

    def _emit_lobby(self):
        self.lobby_updated.emit(lobby_to_dict(self._lobby))
