"""
Shared runtime for the in-app Phaseon page and prosthetic arm tooling.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QObject, Signal

from prosthetic_arm.arm_state import ArmStateEngine, dominant_state_for_metrics
from prosthetic_arm.arduino_arm import ArduinoArmController
from prosthetic_arm.brainbit_backend import BrainBitMetricAdapter
from prosthetic_arm.capsule_backend import CapsuleMetricAdapter


def _coerce_bool(value) -> bool:
    return bool(value)


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_key(key) -> str:
    return str(key or "").strip().lower().replace("_", "").replace("-", "")


def _normalize_channel_name(name: str) -> str:
    compact = str(name or "").strip().upper().replace(" ", "").replace("_", "").replace("/", "-")
    alias_map = {
        "01": "O1",
        "OT3": "O1-T3",
        "O1T3": "O1-T3",
        "T3O1": "O1-T3",
        "02": "O2",
        "OT4": "O2-T4",
        "O2T4": "O2-T4",
        "T4O2": "O2-T4",
    }
    return alias_map.get(compact, compact)


def _call_first(target, method_names: Sequence[str], *args):
    for name in method_names:
        method = getattr(target, name, None)
        if not callable(method):
            continue
        try:
            return method(*args)
        except TypeError:
            try:
                return method()
            except TypeError:
                continue
    return None


def _extract_named_numeric(payload, aliases: Sequence[str]) -> float | None:
    names = {_normalize_key(alias) for alias in aliases}
    matches: list[float] = []

    def visit(value, key_hint: str = ""):
        if isinstance(value, Mapping):
            for key, nested in value.items():
                visit(nested, str(key))
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for nested in value:
                visit(nested, key_hint)
            return
        if key_hint and _normalize_key(key_hint) in names:
            try:
                matches.append(float(value))
            except (TypeError, ValueError):
                return

    visit(payload)
    if not matches:
        return None
    return float(sum(matches) / len(matches))


def _metrics_from_payload(payload: Mapping | None) -> dict:
    payload = dict(payload or {})
    attention = _extract_named_numeric(
        payload,
        (
            "attention",
            "concentration",
            "concentrationscore",
            "focus",
            "productivityscore",
        ),
    )
    relaxation = _extract_named_numeric(
        payload,
        (
            "relaxation",
            "relaxationscore",
            "calm",
            "serenity",
        ),
    )
    attention = _coerce_float(attention, 0.0)
    relaxation = _coerce_float(relaxation, 0.0)
    dominant_state = payload.get("dominant_state")
    if not dominant_state:
        dominant_state = dominant_state_for_metrics(attention, relaxation)
    return {
        "attention": max(0.0, min(100.0, attention)),
        "relaxation": max(0.0, min(100.0, relaxation)),
        "dominant_state": str(dominant_state),
    }


class PhaseonRuntime(QObject):
    source_changed = Signal(str)
    state_changed = Signal(object)
    metrics_changed = Signal(object)
    resistance_changed = Signal(object)
    waves_changed = Signal(float, float)
    raw_eeg_changed = Signal(object)

    SOURCE_CAPSULE = "capsule"
    SOURCE_BRAINBIT = "brainbit"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_mode = self.SOURCE_CAPSULE
        self._capsule_backend = None
        self._brainbit_backend = None
        self._arduino_arm = None
        self._arm_state_engine = None

        self._capsule_metrics = {
            "attention": 0.0,
            "relaxation": 0.0,
            "dominant_state": "Balanced",
        }
        self._brainbit_metrics = dict(self._capsule_metrics)
        self._capsule_resistances: dict = {}
        self._brainbit_resistances: dict = {}
        self._capsule_raw: dict = {"channels": {}, "sample_rate_hz": 250.0, "channel_names": []}
        self._brainbit_raw: dict = {"channels": {}, "sample_rate_hz": 250.0, "channel_names": []}
        self._capsule_waves = (0.0, 0.0)
        self._brainbit_waves = (0.0, 0.0)

        self._state = {
            "source_mode": self._source_mode,
            "source_status": "Using live Capsule productivity metrics.",
            "capsule_connected": False,
            "brainbit_connected": False,
            "arduino_connected": False,
            "battery_pct": None,
            "serial": "",
            "session_id": "",
            "mode": "Idle",
            "arm_state": "OPEN",
            "dominant_state": "Balanced",
            "sample_rate_hz": 250.0,
            "channel_names": ["O1-T3", "O2-T4"],
        }

    @property
    def capsule_backend(self):
        if self._capsule_backend is None:
            self._capsule_backend = CapsuleMetricAdapter(self)
            self._capsule_backend.status_changed.connect(self._on_capsule_status)
            self._capsule_backend.connection_changed.connect(self._on_capsule_connection)
            self._capsule_backend.metrics_changed.connect(self._on_capsule_metrics)
        return self._capsule_backend

    @property
    def brainbit_backend(self):
        if self._brainbit_backend is None:
            self._brainbit_backend = BrainBitMetricAdapter(self)
            self._brainbit_backend.status_changed.connect(self._on_brainbit_status)
            self._brainbit_backend.connection_changed.connect(self._on_brainbit_connection)
            self._brainbit_backend.metrics_changed.connect(self._on_brainbit_metrics)
            self._brainbit_backend.resistance_changed.connect(self._on_brainbit_resistance)
            self._brainbit_backend.waves_changed.connect(self._on_brainbit_waves)
            self._brainbit_backend.raw_uv_changed.connect(self._on_brainbit_raw)
        return self._brainbit_backend

    @property
    def arduino_arm(self):
        if self._arduino_arm is None:
            self._arduino_arm = ArduinoArmController(self)
        return self._arduino_arm

    @property
    def arm_state_engine(self):
        if self._arm_state_engine is None:
            self._arm_state_engine = ArmStateEngine()
        return self._arm_state_engine

    def snapshot_state(self) -> dict:
        return dict(self._state)

    def snapshot_metrics(self) -> dict:
        return dict(self._current_metrics())

    def snapshot_resistances(self) -> dict:
        return dict(self._current_resistances())

    def snapshot_raw_payload(self) -> dict:
        return dict(self._current_raw_payload())

    def set_source_mode(self, mode: str):
        mode = str(mode or self.SOURCE_CAPSULE).strip().lower()
        if mode not in {self.SOURCE_CAPSULE, self.SOURCE_BRAINBIT}:
            mode = self.SOURCE_CAPSULE
        if mode == self._source_mode:
            return
        self._source_mode = mode
        self._state["source_mode"] = mode
        self._state["source_status"] = self._source_status_for(mode)
        self._state["dominant_state"] = self._current_metrics().get("dominant_state", "Balanced")
        self._emit_arm_state(self._current_metrics())
        self.source_changed.emit(mode)
        self.state_changed.emit(self.snapshot_state())
        self.metrics_changed.emit(self.snapshot_metrics())
        self.resistance_changed.emit(self.snapshot_resistances())
        alpha, beta = self._current_waves()
        self.waves_changed.emit(alpha, beta)
        self.raw_eeg_changed.emit(self.snapshot_raw_payload())

    def ingest_productivity(self, data: Mapping | None):
        self.capsule_backend.ingest_productivity(data or {})

    def ingest_band_powers(self, band_powers: Mapping | None):
        alpha = _extract_named_numeric(band_powers or {}, ("alpha",))
        beta = _extract_named_numeric(band_powers or {}, ("beta",))
        self._capsule_waves = (_coerce_float(alpha, 0.0), _coerce_float(beta, 0.0))
        if self._source_mode == self.SOURCE_CAPSULE:
            self.waves_changed.emit(*self._capsule_waves)

    def ingest_resistances(self, data: Mapping | None):
        self._capsule_resistances = dict(data or {})
        if self._source_mode == self.SOURCE_CAPSULE:
            self.resistance_changed.emit(dict(self._capsule_resistances))

    def ingest_eeg_packet(self, eeg_timed_data, *, sample_rate_hz: float | None = None, channel_names=None):
        payload = self._packet_to_payload(eeg_timed_data, sample_rate_hz=sample_rate_hz, channel_names=channel_names)
        if not payload["channels"]:
            return
        self._capsule_raw = payload
        self._state["sample_rate_hz"] = float(payload.get("sample_rate_hz") or self._state["sample_rate_hz"])
        self._state["channel_names"] = list(payload.get("channel_names") or self._state["channel_names"])
        if self._source_mode == self.SOURCE_CAPSULE:
            self.raw_eeg_changed.emit(dict(payload))

    def update_device_status(
        self,
        *,
        connected=None,
        serial=None,
        battery=None,
        mode=None,
        session_id=None,
        sample_rate_hz: float | None = None,
        channel_names=None,
    ):
        if connected is not None:
            self._state["capsule_connected"] = _coerce_bool(connected)
        if serial is not None:
            self._state["serial"] = str(serial or "")
        if battery is not None:
            self._state["battery_pct"] = None if battery in (-1, None, "") else int(battery)
        if mode is not None:
            self._state["mode"] = str(mode or "Idle")
        if session_id is not None:
            self._state["session_id"] = str(session_id or "")
        if sample_rate_hz:
            self._state["sample_rate_hz"] = float(sample_rate_hz)
        if channel_names:
            self._state["channel_names"] = [_normalize_channel_name(name) for name in channel_names]
        self._state["source_status"] = self._source_status_for(self._source_mode)
        self.state_changed.emit(self.snapshot_state())

    def toggle_brainbit_connection(self):
        backend = self.brainbit_backend
        if self._state["brainbit_connected"]:
            _call_first(
                backend,
                (
                    "disconnect_device",
                    "disconnect_sensor",
                    "disconnect",
                    "stop_stream",
                    "stop",
                ),
            )
            return
        _call_first(
            backend,
            (
                "connect_device",
                "connect_sensor",
                "connect",
                "start_stream",
                "start",
            ),
        )

    def toggle_arduino_connection(self, port: str | None = None):
        arm = self.arduino_arm
        if getattr(arm, "is_connected", False):
            _call_first(arm, ("disconnect_device", "disconnect"))
        else:
            _call_first(arm, ("connect_device", "connect"), port)
        self._state["arduino_connected"] = bool(getattr(arm, "is_connected", False))
        self.state_changed.emit(self.snapshot_state())

    def request_brainbit_iapf(self):
        _call_first(
            self.brainbit_backend,
            (
                "start_iapf",
                "request_iapf",
                "detect_iapf",
                "start_detect_iapf",
            ),
        )

    def request_brainbit_baseline(self):
        _call_first(
            self.brainbit_backend,
            (
                "start_baseline",
                "request_baseline",
                "start_baseline_calibration",
            ),
        )

    def shutdown(self):
        if self._brainbit_backend is not None:
            _call_first(
                self._brainbit_backend,
                ("shutdown", "disconnect_device", "disconnect_sensor", "disconnect"),
            )
        if self._arduino_arm is not None:
            _call_first(self._arduino_arm, ("disconnect_device", "disconnect"))

    def _on_capsule_status(self, text: str):
        if self._source_mode == self.SOURCE_CAPSULE:
            self._state["source_status"] = str(text or "")
            self.state_changed.emit(self.snapshot_state())

    def _on_capsule_connection(self, connected):
        self._state["capsule_connected"] = _coerce_bool(connected)
        if self._source_mode == self.SOURCE_CAPSULE:
            self._state["source_status"] = self._source_status_for(self.SOURCE_CAPSULE)
            self.state_changed.emit(self.snapshot_state())

    def _on_capsule_metrics(self, data):
        self._capsule_metrics = _metrics_from_payload(data)
        if self._source_mode == self.SOURCE_CAPSULE:
            self._emit_metrics(self._capsule_metrics)

    def _on_brainbit_status(self, text: str):
        if self._source_mode == self.SOURCE_BRAINBIT:
            self._state["source_status"] = str(text or "")
            self.state_changed.emit(self.snapshot_state())

    def _on_brainbit_connection(self, connected):
        self._state["brainbit_connected"] = _coerce_bool(connected)
        if self._source_mode == self.SOURCE_BRAINBIT:
            self._state["source_status"] = self._source_status_for(self.SOURCE_BRAINBIT)
            self.state_changed.emit(self.snapshot_state())

    def _on_brainbit_metrics(self, data):
        self._brainbit_metrics = _metrics_from_payload(data)
        if self._source_mode == self.SOURCE_BRAINBIT:
            self._emit_metrics(self._brainbit_metrics)

    def _on_brainbit_resistance(self, data):
        self._brainbit_resistances = dict(data or {})
        if self._source_mode == self.SOURCE_BRAINBIT:
            self.resistance_changed.emit(dict(self._brainbit_resistances))

    def _on_brainbit_waves(self, alpha, beta):
        self._brainbit_waves = (_coerce_float(alpha, 0.0), _coerce_float(beta, 0.0))
        if self._source_mode == self.SOURCE_BRAINBIT:
            self.waves_changed.emit(*self._brainbit_waves)

    def _on_brainbit_raw(self, data):
        self._brainbit_raw = self._normalize_raw_payload(data)
        if self._source_mode == self.SOURCE_BRAINBIT:
            self.raw_eeg_changed.emit(dict(self._brainbit_raw))

    def _emit_metrics(self, metrics: Mapping):
        metrics_payload = dict(metrics or {})
        self._state["dominant_state"] = str(metrics_payload.get("dominant_state", "Balanced"))
        self._emit_arm_state(metrics_payload)
        self.metrics_changed.emit(metrics_payload)
        self.state_changed.emit(self.snapshot_state())

    def _emit_arm_state(self, metrics: Mapping):
        attention = _coerce_float(metrics.get("attention"), 0.0)
        relaxation = _coerce_float(metrics.get("relaxation"), 0.0)
        if attention >= 50.0 and attention > relaxation:
            arm_state = "CLOSED"
        elif relaxation >= 50.0 and relaxation >= attention:
            arm_state = "OPEN"
        else:
            arm_state = "NEUTRAL"
        self._state["arm_state"] = arm_state
        arm = self._arduino_arm
        self._state["arduino_connected"] = bool(getattr(arm, "is_connected", False))
        if arm is not None:
            _call_first(
                arm,
                ("set_state", "apply_state", "send_state", "update_state"),
                arm_state,
            )

    def _current_metrics(self) -> dict:
        if self._source_mode == self.SOURCE_BRAINBIT:
            return self._brainbit_metrics
        return self._capsule_metrics

    def _current_resistances(self) -> dict:
        if self._source_mode == self.SOURCE_BRAINBIT:
            return self._brainbit_resistances
        return self._capsule_resistances

    def _current_waves(self) -> tuple[float, float]:
        if self._source_mode == self.SOURCE_BRAINBIT:
            return self._brainbit_waves
        return self._capsule_waves

    def _current_raw_payload(self) -> dict:
        if self._source_mode == self.SOURCE_BRAINBIT:
            return self._brainbit_raw
        return self._capsule_raw

    def _source_status_for(self, mode: str) -> str:
        if mode == self.SOURCE_BRAINBIT:
            return "BrainBit live mode ready." if self._state["brainbit_connected"] else "BrainBit standby."
        return "Using live Capsule productivity metrics." if self._state["capsule_connected"] else "Capsule standby."

    def _packet_to_payload(self, eeg_timed_data, *, sample_rate_hz: float | None = None, channel_names=None) -> dict:
        payload = {
            "channels": {},
            "sample_rate_hz": float(sample_rate_hz or self._state["sample_rate_hz"] or 250.0),
            "channel_names": [_normalize_channel_name(name) for name in (channel_names or self._state["channel_names"])],
        }
        if eeg_timed_data is None:
            return payload
        try:
            channel_count = int(eeg_timed_data.get_channels_count())
            sample_count = int(eeg_timed_data.get_samples_count())
        except Exception:
            return payload

        names = list(payload["channel_names"])
        if len(names) < channel_count:
            names.extend(f"CH{index + 1}" for index in range(len(names), channel_count))

        for channel_index in range(channel_count):
            series = []
            for sample_index in range(sample_count):
                try:
                    value = eeg_timed_data.get_raw_value(channel_index, sample_index)
                    series.append(float(value) * 1_000_000.0)
                except Exception:
                    continue
            if series:
                payload["channels"][names[channel_index]] = series
        payload["channel_names"] = names[:channel_count]
        return payload

    def _normalize_raw_payload(self, data) -> dict:
        payload = {
            "channels": {},
            "sample_rate_hz": float(self._state["sample_rate_hz"] or 250.0),
            "channel_names": list(self._state["channel_names"]),
        }
        if isinstance(data, Mapping):
            sample_rate = data.get("sample_rate_hz") or data.get("sample_rate") or payload["sample_rate_hz"]
            payload["sample_rate_hz"] = _coerce_float(sample_rate, payload["sample_rate_hz"])
            channels = data.get("channels")
            if isinstance(channels, Mapping):
                for name, samples in channels.items():
                    payload["channels"][_normalize_channel_name(name)] = [float(v) for v in samples]
                payload["channel_names"] = list(payload["channels"].keys())
                return payload
            direct = {}
            for name, samples in data.items():
                if isinstance(samples, Sequence) and not isinstance(samples, (str, bytes, bytearray)):
                    try:
                        direct[_normalize_channel_name(name)] = [float(v) for v in samples]
                    except (TypeError, ValueError):
                        continue
            if direct:
                payload["channels"] = direct
                payload["channel_names"] = list(direct.keys())
            return payload

        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            channels = {}
            names = list(payload["channel_names"])
            for index, samples in enumerate(data):
                if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes, bytearray)):
                    continue
                name = names[index] if index < len(names) else f"CH{index + 1}"
                try:
                    channels[_normalize_channel_name(name)] = [float(v) for v in samples]
                except (TypeError, ValueError):
                    continue
            payload["channels"] = channels
            payload["channel_names"] = list(channels.keys())
        return payload
