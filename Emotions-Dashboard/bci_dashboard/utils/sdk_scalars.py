"""
Helpers for normalizing Capsule SDK scalar values into Python numbers.
"""
from __future__ import annotations

import ast
from typing import Any


def _unwrap_value(value: Any) -> Any:
    if hasattr(value, "value"):
        try:
            return value.value
        except Exception:
            pass
    return value


def _literal_bytes(value: str):
    text = (value or "").strip()
    if not (text.startswith("b'") or text.startswith('b"')):
        return None
    try:
        raw = ast.literal_eval(text)
    except Exception:
        return None
    return raw if isinstance(raw, (bytes, bytearray)) else None


def _coerce_text_number(text: str, cast, default):
    cleaned = (text or "").strip().strip("\x00")
    if not cleaned:
        return default
    try:
        return cast(cleaned)
    except Exception:
        literal = _literal_bytes(cleaned)
        if literal is None:
            return default
        return _coerce_from_bytes(literal, cast, default)


def _coerce_from_bytes(raw: bytes | bytearray, cast, default):
    if raw is None:
        return default
    payload = bytes(raw)
    if not payload:
        return default
    if len(payload) >= 4:
        try:
            return cast(int.from_bytes(payload[:4], byteorder="little", signed=True))
        except Exception:
            pass
    try:
        return _coerce_text_number(payload.strip(b"\x00").decode("utf-8", errors="ignore"), cast, default)
    except Exception:
        return default


def coerce_scalar(value: Any, cast=float, default=None):
    """
    Normalize SDK values in this order:
    native numeric -> .value -> 4-byte little-endian bytes -> numeric string -> default.
    """
    value = _unwrap_value(value)
    if value is None:
        return default
    if isinstance(value, bool):
        return cast(int(value))
    if isinstance(value, (int, float)):
        try:
            return cast(value)
        except Exception:
            return default
    if isinstance(value, (bytes, bytearray)):
        return _coerce_from_bytes(value, cast, default)
    if isinstance(value, str):
        return _coerce_text_number(value, cast, default)
    return default


def coerce_int(value: Any, default=None):
    return coerce_scalar(value, cast=int, default=default)


def coerce_float(value: Any, default=None):
    return coerce_scalar(value, cast=float, default=default)


def coerce_percent(value: Any, default=None):
    pct = coerce_int(value, default=default)
    if pct is None:
        return default
    if 0 <= int(pct) <= 100:
        return int(pct)
    return default
