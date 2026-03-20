"""
Session recorder that writes session bundles and optional CSV exports.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import time
import uuid
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from utils.config import (
    CSV_AGGREGATE_PER_MINUTE,
    CSV_COLUMNS,
    CSV_FLUSH_INTERVAL_SEC,
    SESSION_DIR,
    SESSION_FILE_NAMES,
    WRITE_OPTION_DEFAULTS,
    WRITE_OPTION_SPECS,
    WINDOW_TITLE,
)


log = logging.getLogger(__name__)


try:
    import h5py  # type: ignore
except Exception:
    h5py = None


WRITE_OPTION_LABELS = {key: label for key, label in WRITE_OPTION_SPECS}
CHANNEL_NAMES = {
    0: "O1-T3",
    1: "O2-T4",
    2: "T3",
    3: "O1",
    4: "O2",
    5: "T4",
}


def _utc_microseconds() -> int:
    return int(time.time() * 1_000_000)


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


class SessionRecorder:
    def __init__(self):
        self._started = False
        self._session_id: str | None = None
        self._session_dir: str | None = None
        self._json_path: str | None = None
        self._metrics_path: str | None = None
        self._h5_path: str | None = None
        self._csv_enabled = False
        self._write_options = dict(WRITE_OPTION_DEFAULTS)
        self._metadata: dict = {}
        self._minute_accum: dict[str, list[float]] = defaultdict(list)
        self._current_minute: str | None = None
        self._buffer: list[dict] = []
        self._last_flush = datetime.now()
        self._h5_file = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def session_dir(self) -> str | None:
        return self._session_dir

    @property
    def file_path(self) -> str | None:
        if self._csv_enabled and self._metrics_path:
            return self._metrics_path
        return self._session_dir

    def start_session(self, metadata: dict | None = None, write_options: dict | None = None):
        self.stop_session()

        self._session_id = str(uuid.uuid4())
        self._session_dir = os.path.join(SESSION_DIR, self._session_id)
        os.makedirs(self._session_dir, exist_ok=True)

        self._json_path = os.path.join(self._session_dir, SESSION_FILE_NAMES["json"])
        self._metrics_path = os.path.join(self._session_dir, SESSION_FILE_NAMES["metrics"])
        self._h5_path = os.path.join(self._session_dir, SESSION_FILE_NAMES["h5"])
        self._write_options = dict(WRITE_OPTION_DEFAULTS)
        self._write_options.update(write_options or {})
        self._csv_enabled = bool(self._write_options.get("export_to_csv", True))

        base_metadata = metadata or {}
        device_info = dict(base_metadata.get("deviceInfo", {}))
        session_info = dict(base_metadata.get("sessionInfo", {}))
        session_info.setdefault("capsuleSessionId", self._session_id)
        session_info["startUTCUnixTimestamp"] = _utc_microseconds()
        session_info["endUTCUnixTimestamp"] = None
        self._metadata = {
            "appInfo": {
                "clientVersion": base_metadata.get("clientVersion", WINDOW_TITLE),
                "operatingSystem": base_metadata.get("operatingSystem", platform.system()),
            },
            "sessionInfo": session_info,
            "deviceInfo": device_info,
            "writeOptions": {
                key: {
                    "label": WRITE_OPTION_LABELS[key],
                    "enabled": bool(self._write_options.get(key, False)),
                }
                for key in WRITE_OPTION_LABELS
            },
            "calibrationInfo": dict(base_metadata.get("calibrationInfo", {})),
            "storageInfo": {
                "h5Enabled": h5py is not None,
                "csvEnabled": self._csv_enabled,
            },
        }

        if self._csv_enabled:
            with open(self._metrics_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(",".join(CSV_COLUMNS) + "\n")

        self._buffer.clear()
        self._minute_accum = defaultdict(list)
        self._current_minute = None
        self._last_flush = datetime.now()
        self._started = True

        if h5py is not None:
            self._h5_file = h5py.File(self._h5_path, "w")
            self._h5_file.attrs["session_id"] = self._session_id
            self._h5_file.attrs["format"] = "json-record-stream"
        else:
            self._h5_file = None
            log.warning("h5py is not installed; session.h5 will not be written.")
            self._metadata["storageInfo"]["warning"] = "h5py unavailable"

        self._write_session_json()

    def stop_session(self):
        if not self._started:
            return

        self._flush_minute()
        self._flush_to_disk()
        if self._h5_file is not None:
            self._h5_file.close()
            self._h5_file = None

        self._metadata["sessionInfo"]["endUTCUnixTimestamp"] = _utc_microseconds()
        self._write_session_json()
        self._started = False

    def update_calibration_info(self, calibration_info: dict):
        if not calibration_info:
            return
        self._metadata.setdefault("calibrationInfo", {}).update(calibration_info)
        if self._started:
            self._write_session_json()

    def append_record(self, option_id: str, payload: dict):
        if not self._started or not bool(self._write_options.get(option_id, False)):
            return
        if self._h5_file is None:
            return

        label = WRITE_OPTION_LABELS.get(option_id, option_id)
        group = self._h5_file.require_group(label)
        if "records" not in group:
            dtype = h5py.string_dtype(encoding="utf-8")
            group.create_dataset("records", shape=(0,), maxshape=(None,), dtype=dtype)
        dataset = group["records"]
        dataset.resize((dataset.shape[0] + 1,))
        dataset[-1] = json.dumps(payload, default=_json_default)

    def log_metrics_row(
        self,
        emotions: dict | None = None,
        productivity: dict | None = None,
        cardio: dict | None = None,
        band_powers: dict | None = None,
        peak_freqs: dict | None = None,
    ):
        if not self._started or not self._csv_enabled:
            return

        now = datetime.now()
        e = emotions or {}
        p = productivity or {}
        c = cardio or {}
        bp = band_powers or {}
        pk = peak_freqs or {}

        row = {
            "time": now.strftime("%Y-%m-%d %H:%M"),
            "cognitive score": p.get("productivityScore", 0),
            "focus": e.get("focus", 0),
            "chill": e.get("chill", 0),
            "stress": e.get("stress", 0),
            "self-control": e.get("selfControl", 0),
            "anger": e.get("anger", 0),
            "relaxation index": p.get("relaxationScore", 0),
            "concentration index": p.get("concentrationScore", 0),
            "fatigue score": p.get("fatigueScore", 0),
            "reverse fatigue": p.get("reverseFatigueScore", 0),
            "alpha gravity": p.get("gravityScore", 0),
            "accumulated fatigue": p.get("accumulatedFatigue", 0),
            "heart rate": c.get("heartRate", 0),
            "stress index": c.get("stressIndex", p.get("stressIndex", 0)),
            "alpha rhythm": bp.get("alpha", 0),
            "beta rhythm": bp.get("beta", 0),
            "theta rhythm": bp.get("theta", 0),
            "smr rhythm": bp.get("smr", 0),
            "alpha peak hz": pk.get("alpha_peak", 0),
            "beta peak hz": pk.get("beta_peak", 0),
            "theta peak hz": pk.get("theta_peak", 0),
        }

        if CSV_AGGREGATE_PER_MINUTE:
            minute_key = row["time"]
            if self._current_minute is None:
                self._current_minute = minute_key
            if minute_key != self._current_minute:
                self._flush_minute()
                self._current_minute = minute_key
            for col in CSV_COLUMNS[1:]:
                self._minute_accum[col].append(float(row[col]))
        else:
            row["time"] = now.strftime("%Y-%m-%d %H:%M:%S")
            self._buffer.append(row)

        if (now - self._last_flush).total_seconds() >= CSV_FLUSH_INTERVAL_SEC:
            self._flush_to_disk()
            self._last_flush = now

    def record_emotions(self, data: dict):
        self.append_record("emotions", dict(data or {}))

    def record_productivity_metrics(self, data: dict):
        self.append_record("productivity", {"kind": "metrics", "payload": dict(data or {})})

    def record_productivity_indexes(self, data: dict):
        self.append_record("productivity", {"kind": "indexes", "payload": dict(data or {})})

    def record_cardio_metrics(self, data: dict):
        self.append_record("cardio_metrics", dict(data or {}))

    def record_resistances(self, data: dict):
        self.append_record("resistances", dict(data or {}))

    def record_rhythms(self, band_powers: dict):
        if not band_powers:
            return
        self.append_record("rhythms", {"timestamp": _utc_microseconds(), "bandPowers": dict(band_powers)})

    def record_eeg_summary(self, band_powers: dict, peak_freqs: dict, filter_enabled: bool, iapf_status: dict | None):
        summary = {
            "timestamp": _utc_microseconds(),
            "bandPowers": dict(band_powers or {}),
            "peakFrequencies": dict(peak_freqs or {}),
            "filterEnabled": bool(filter_enabled),
            "iapf": dict(iapf_status or {}),
        }
        self.append_record("eeg", summary)

    def record_ppg_packet(self, ppg_timed_data):
        record = {"timestamp": _utc_microseconds(), "values": [], "timestampsMs": []}
        try:
            for idx in range(len(ppg_timed_data)):
                record["values"].append(float(ppg_timed_data.get_value(idx)))
                record["timestampsMs"].append(float(ppg_timed_data.get_timestamp(idx)))
        except Exception:
            return
        self.append_record("ppg", record)

    def record_raw_eeg_packet(self, eeg_timed_data):
        try:
            n_channels = eeg_timed_data.get_channels_count()
            n_samples = eeg_timed_data.get_samples_count()
        except Exception:
            return
        if n_channels <= 0 or n_samples <= 0:
            return
        record = {"timestamp": _utc_microseconds(), "timestampsMs": [], "channels": {}}
        for sample_idx in range(n_samples):
            try:
                record["timestampsMs"].append(float(eeg_timed_data.get_timestamp(sample_idx)))
            except Exception:
                record["timestampsMs"].append(float(sample_idx))
        for ch_idx in range(n_channels):
            ch_name = CHANNEL_NAMES.get(ch_idx, f"channel_{ch_idx}")
            values = []
            for sample_idx in range(n_samples):
                try:
                    raw_value = float(eeg_timed_data.get_raw_value(ch_idx, sample_idx))
                except Exception:
                    raw_value = 0.0
                values.append(raw_value * 1_000_000.0)
            record["channels"][ch_name] = values
        self.append_record("raw_eeg", record)

    def record_artifacts(self, artifacts):
        try:
            count = artifacts.get_channels_count()
        except Exception:
            return
        payload = {
            "timestamp": _utc_microseconds(),
            "channels": {
                CHANNEL_NAMES.get(ch_idx, f"channel_{ch_idx}"): bool(
                    artifacts.get_artifacts_by_channel(ch_idx)
                )
                for ch_idx in range(count)
            },
        }
        self.append_record("eeg_artifacts", payload)

    def record_artifacts_snapshot(self, snapshot: dict):
        """Record a pre-extracted {ch_idx: bool} artifact snapshot (no DLL access)."""
        payload = {
            "timestamp": _utc_microseconds(),
            "channels": {
                CHANNEL_NAMES.get(ch_idx, f"channel_{ch_idx}"): val
                for ch_idx, val in snapshot.items()
            },
        }
        self.append_record("eeg_artifacts", payload)

    def record_ppg_snapshot(self, snapshot: dict):
        """Record a pre-extracted PPG packet snapshot (no DLL access)."""
        record = {
            "timestamp": _utc_microseconds(),
            "values": snapshot.get("values", []),
            "timestampsMs": snapshot.get("timestampsMs", []),
        }
        self.append_record("ppg", record)

    def record_raw_eeg_snapshot(self, snapshot: dict):
        """Record a pre-extracted EEG packet snapshot (no DLL access)."""
        record = {
            "timestamp": _utc_microseconds(),
            "timestampsMs": snapshot.get("timestampsMs", []),
            "channels": {
                CHANNEL_NAMES.get(ch_idx, f"channel_{ch_idx}"): values
                for ch_idx, values in snapshot.get("channels", {}).items()
            },
        }
        self.append_record("raw_eeg", record)

    def record_mems_snapshot(self, snapshot: dict):
        """Record a pre-extracted MEMS packet snapshot (no DLL access)."""
        record = {
            "timestamp": _utc_microseconds(),
            "samples": snapshot.get("samples", []),
        }
        self.append_record("mems", record)

    def record_mems_packet(self, mems_timed_data):
        record = {"timestamp": _utc_microseconds(), "samples": []}
        try:
            for idx in range(len(mems_timed_data)):
                accel = mems_timed_data.get_accelerometer(idx)
                gyro = mems_timed_data.get_gyroscope(idx)
                record["samples"].append(
                    {
                        "timestampMs": float(mems_timed_data.get_timestamp(idx)),
                        "accelerometer": {
                            "x": float(accel.x),
                            "y": float(accel.y),
                            "z": float(accel.z),
                        },
                        "gyroscope": {
                            "x": float(gyro.x),
                            "y": float(gyro.y),
                            "z": float(gyro.z),
                        },
                    }
                )
        except Exception:
            return
        self.append_record("mems", record)

    def record_baselines(self, payload: dict):
        self.append_record("productivity_baselines", dict(payload or {}))

    def _flush_minute(self):
        if not self._minute_accum or self._current_minute is None:
            return
        avg_row = {"time": self._current_minute}
        for col in CSV_COLUMNS[1:]:
            vals = self._minute_accum[col]
            avg_row[col] = round(sum(vals) / len(vals), 2) if vals else 0
        self._buffer.append(avg_row)
        self._minute_accum = defaultdict(list)

    def _flush_to_disk(self):
        if not self._buffer or not self._metrics_path:
            return
        df = pd.DataFrame(self._buffer, columns=CSV_COLUMNS)
        df.to_csv(
            self._metrics_path,
            mode="a",
            header=False,
            index=False,
            encoding="utf-8",
        )
        self._buffer.clear()

    def _write_session_json(self):
        if not self._json_path:
            return
        with open(self._json_path, "w", encoding="utf-8") as handle:
            json.dump(self._metadata, handle, indent=2)
