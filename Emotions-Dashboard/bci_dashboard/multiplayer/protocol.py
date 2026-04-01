"""
Multiplayer protocol – message types and JSON serialisation.

Every WebSocket frame is a JSON object with ``{"type": "<MSG_TYPE>", "payload": {...}}``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

# ── Message type constants ────────────────────────────────────────────
MSG_HELLO = "hello"
MSG_WELCOME = "welcome"
MSG_LOBBY_UPDATE = "lobby_update"
MSG_METRICS = "metrics"
MSG_CALIBRATION_SAMPLE = "calibration_sample"
MSG_CALIBRATION_SYNC = "calibration_sync"
MSG_READY = "ready"
MSG_GAME_START = "game_start"
MSG_GAME_STATE = "game_state"
MSG_GAME_OVER = "game_over"
MSG_PLAYER_LEFT = "player_left"
MSG_ERROR = "error"

DEFAULT_PORT = 7865


# ── Data classes ──────────────────────────────────────────────────────
@dataclass
class PlayerInfo:
    player_id: int
    name: str
    role: str  # "host" or "guest"
    ready: bool = False
    calibrated: bool = False
    calibration_progress: float = 0.0


@dataclass
class LobbyState:
    players: list[PlayerInfo] = field(default_factory=list)
    game_id: str = "mp_tug_of_war"
    status: str = "waiting"  # waiting | calibrating | playing | finished


# ── Encode / decode ──────────────────────────────────────────────────
def encode_msg(msg_type: str, payload: dict[str, Any] | None = None) -> str:
    return json.dumps({"type": msg_type, "payload": payload or {}})


def decode_msg(raw: str) -> tuple[str, dict[str, Any]]:
    obj = json.loads(raw)
    return obj["type"], obj.get("payload", {})


def lobby_to_dict(lobby: LobbyState) -> dict:
    return asdict(lobby)


def lobby_from_dict(d: dict) -> LobbyState:
    players = [PlayerInfo(**p) for p in d.get("players", [])]
    return LobbyState(
        players=players,
        game_id=d.get("game_id", "mp_tug_of_war"),
        status=d.get("status", "waiting"),
    )
