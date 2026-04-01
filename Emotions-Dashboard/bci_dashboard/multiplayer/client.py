"""
MultiplayerClient – WebSocket guest running in a daemon thread.

Connects to a host server, sends local BCI metrics, and receives
game state for rendering.
"""
from __future__ import annotations

import asyncio
import logging
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
    decode_msg,
    encode_msg,
    lobby_from_dict,
)

log = logging.getLogger(__name__)


class MultiplayerClient(QObject):
    """WebSocket client that joins a host's multiplayer session."""

    # Qt signals
    connected = Signal()
    disconnected = Signal()
    lobby_updated = Signal(dict)
    calibration_sync = Signal(dict)       # {player_id, snapshot}
    game_started = Signal()
    game_state_received = Signal(dict)    # view_state
    game_over = Signal(dict)              # result
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws = None
        self._player_id: int | None = None
        self._running = False

    # ── Public API ────────────────────────────────────────────────
    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._running

    @property
    def player_id(self) -> int | None:
        return self._player_id

    def connect_to(self, host: str, port: int = DEFAULT_PORT,
                   player_name: str = "Player 2"):
        if self._running:
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(host, port, player_name),
            daemon=True,
            name="mp-client",
        )
        self._thread.start()

    def disconnect(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        self._loop = None
        self._ws = None

    def send_metrics(self, concentration: float, relaxation: float,
                     valid: bool, stale: bool):
        self._send(encode_msg(MSG_METRICS, {
            "concentration": concentration,
            "relaxation": relaxation,
            "valid": valid,
            "stale": stale,
        }))

    def send_calibration_sample(self, concentration: float, relaxation: float,
                                valid: bool):
        self._send(encode_msg(MSG_CALIBRATION_SAMPLE, {
            "concentration": concentration,
            "relaxation": relaxation,
            "valid": valid,
        }))

    def send_ready(self):
        self._send(encode_msg(MSG_READY, {}))

    # ── Private – event loop ──────────────────────────────────────
    def _run_loop(self, host: str, port: int, name: str):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect(host, port, name))
        except Exception as exc:
            if self._running:
                log.error("Client loop error: %s", exc)
                self.error_occurred.emit(str(exc))
        finally:
            self._running = False
            self.disconnected.emit()

    async def _connect(self, host: str, port: int, name: str):
        try:
            import websockets
        except ImportError:
            self.error_occurred.emit(
                "websockets package not installed.  Run: pip install websockets"
            )
            return

        uri = f"ws://{host}:{port}"
        try:
            async with websockets.connect(uri) as ws:
                self._ws = ws
                await ws.send(encode_msg(MSG_HELLO, {"name": name}))
                self.connected.emit()

                async for raw in ws:
                    if not self._running:
                        break
                    msg_type, payload = decode_msg(raw)
                    self._dispatch(msg_type, payload)
        except Exception as exc:
            if self._running:
                self.error_occurred.emit(f"Connection failed: {exc}")
        finally:
            self._ws = None

    def _dispatch(self, msg_type: str, payload: dict):
        if msg_type == MSG_WELCOME:
            self._player_id = payload.get("player_id")
            lobby_dict = payload.get("lobby", {})
            self.lobby_updated.emit(lobby_dict)

        elif msg_type == MSG_LOBBY_UPDATE:
            self.lobby_updated.emit(payload)

        elif msg_type == MSG_CALIBRATION_SYNC:
            self.calibration_sync.emit(payload)

        elif msg_type == MSG_GAME_START:
            self.game_started.emit()

        elif msg_type == MSG_GAME_STATE:
            self.game_state_received.emit(payload)

        elif msg_type == MSG_GAME_OVER:
            self.game_over.emit(payload)

        elif msg_type == MSG_PLAYER_LEFT:
            self.lobby_updated.emit(payload)

        elif msg_type == MSG_ERROR:
            self.error_occurred.emit(payload.get("message", "Unknown error"))

    # ── Helpers ───────────────────────────────────────────────────
    def _send(self, msg: str):
        if self._ws and self._loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self._safe_send(msg), self._loop
            )

    async def _safe_send(self, msg: str):
        try:
            if self._ws:
                await self._ws.send(msg)
        except Exception:
            pass
