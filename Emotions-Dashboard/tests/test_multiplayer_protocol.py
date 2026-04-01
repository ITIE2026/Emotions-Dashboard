import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from multiplayer.protocol import (  # noqa: E402
    MSG_HELLO,
    MSG_METRICS,
    MSG_GAME_STATE,
    DEFAULT_PORT,
    PlayerInfo,
    LobbyState,
    encode_msg,
    decode_msg,
    lobby_to_dict,
    lobby_from_dict,
)


class TestEncodeDecodeMsgRoundTrip(unittest.TestCase):
    """encode_msg → decode_msg should preserve type and payload."""

    def test_simple_message(self):
        raw = encode_msg(MSG_HELLO, {"name": "Alice"})
        msg_type, payload = decode_msg(raw)
        self.assertEqual(msg_type, MSG_HELLO)
        self.assertEqual(payload["name"], "Alice")

    def test_empty_payload(self):
        raw = encode_msg(MSG_METRICS)
        msg_type, payload = decode_msg(raw)
        self.assertEqual(msg_type, MSG_METRICS)
        self.assertEqual(payload, {})

    def test_nested_payload(self):
        data = {"state": {"rope_position": 0.35, "scores": [10, 20]}}
        raw = encode_msg(MSG_GAME_STATE, data)
        msg_type, payload = decode_msg(raw)
        self.assertEqual(msg_type, MSG_GAME_STATE)
        self.assertAlmostEqual(payload["state"]["rope_position"], 0.35)
        self.assertEqual(payload["state"]["scores"], [10, 20])


class TestLobbyStateSerialization(unittest.TestCase):
    """LobbyState → dict → LobbyState round-trip."""

    def _make_lobby(self):
        return LobbyState(
            players=[
                PlayerInfo(0, "Host", "host", ready=True, calibrated=True,
                           calibration_progress=1.0),
                PlayerInfo(1, "Guest", "guest", ready=False, calibrated=False,
                           calibration_progress=0.4),
            ],
            game_id="mp_tug_of_war",
            status="calibrating",
        )

    def test_round_trip(self):
        lobby = self._make_lobby()
        d = lobby_to_dict(lobby)
        restored = lobby_from_dict(d)

        self.assertEqual(len(restored.players), 2)
        self.assertEqual(restored.players[0].name, "Host")
        self.assertTrue(restored.players[0].ready)
        self.assertEqual(restored.players[1].name, "Guest")
        self.assertAlmostEqual(restored.players[1].calibration_progress, 0.4)
        self.assertEqual(restored.status, "calibrating")

    def test_empty_dict_defaults(self):
        restored = lobby_from_dict({})
        self.assertEqual(restored.players, [])
        self.assertEqual(restored.game_id, "mp_tug_of_war")
        self.assertEqual(restored.status, "waiting")


class TestDefaultPort(unittest.TestCase):
    def test_port_is_integer(self):
        self.assertIsInstance(DEFAULT_PORT, int)
        self.assertGreater(DEFAULT_PORT, 1024)


if __name__ == "__main__":
    unittest.main()
