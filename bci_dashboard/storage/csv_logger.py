"""
CSVLogger – continuous session data logger.

Supports:
  - Per-second raw logging
  - Per-minute aggregated logging (matches existing CSV format)
  - Periodic flush to prevent data loss
"""
import os
from datetime import datetime
from collections import defaultdict

import pandas as pd

from utils.config import SESSION_DIR, CSV_COLUMNS, CSV_FLUSH_INTERVAL_SEC, CSV_AGGREGATE_PER_MINUTE
from utils.helpers import timestamp_filename


class CSVLogger:
    """
    Call ``log_row()`` every second with the latest metric dicts.
    The logger handles aggregation and flushing automatically.
    """

    def __init__(self):
        self._file_path: str | None = None
        self._buffer: list[dict] = []
        self._minute_accum: dict[str, list[float]] = defaultdict(list)
        self._current_minute: str | None = None
        self._last_flush = datetime.now()
        self._started = False

    # ── Lifecycle ─────────────────────────────────────────────────────
    def start_session(self):
        fname = timestamp_filename() + ".csv"
        self._file_path = os.path.join(SESSION_DIR, fname)

        # Write header
        with open(self._file_path, "w", encoding="utf-8", newline="") as f:
            f.write(",".join(CSV_COLUMNS) + "\n")

        self._buffer.clear()
        self._minute_accum = defaultdict(list)
        self._current_minute = None
        self._last_flush = datetime.now()
        self._started = True

    def stop_session(self):
        if not self._started:
            return
        # Flush remaining minute aggregate
        self._flush_minute()
        self._flush_to_disk()
        self._started = False

    # ── Logging ───────────────────────────────────────────────────────
    def log_row(
        self,
        emotions: dict | None = None,
        productivity: dict | None = None,
        cardio: dict | None = None,
        band_powers: dict | None = None,
        peak_freqs: dict | None = None,
    ):
        if not self._started:
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
            "stress index": p.get("stressIndex", 0),
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
                # New minute → flush the previous minute
                self._flush_minute()
                self._current_minute = minute_key

            # Accumulate
            for col in CSV_COLUMNS[1:]:
                self._minute_accum[col].append(float(row[col]))
        else:
            row["time"] = now.strftime("%Y-%m-%d %H:%M:%S")
            self._buffer.append(row)

        # Periodic disk flush
        elapsed = (now - self._last_flush).total_seconds()
        if elapsed >= CSV_FLUSH_INTERVAL_SEC:
            self._flush_to_disk()
            self._last_flush = now

    # ── Internal ──────────────────────────────────────────────────────
    def _flush_minute(self):
        """Average accumulated values for the current minute and buffer."""
        if not self._minute_accum or self._current_minute is None:
            return
        avg_row = {"time": self._current_minute}
        for col in CSV_COLUMNS[1:]:
            vals = self._minute_accum[col]
            avg_row[col] = round(sum(vals) / len(vals), 2) if vals else 0
        self._buffer.append(avg_row)
        self._minute_accum = defaultdict(list)

    def _flush_to_disk(self):
        if not self._buffer or self._file_path is None:
            return
        df = pd.DataFrame(self._buffer, columns=CSV_COLUMNS)
        df.to_csv(
            self._file_path,
            mode="a",
            header=False,
            index=False,
            encoding="utf-8",
        )
        self._buffer.clear()

    @property
    def file_path(self) -> str | None:
        return self._file_path
