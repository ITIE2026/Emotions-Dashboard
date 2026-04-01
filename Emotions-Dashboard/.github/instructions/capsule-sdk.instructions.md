---
applyTo: "bci_dashboard/capsule_sdk/**"
description: "Use when editing Capsule SDK ctypes wrappers, device bindings, or C-library integration code. Covers pointer safety, threading, and callback rules."
---
# Capsule SDK Rules

## Pointer Lifetime

Global ctypes pointers live in `CapsulePointersImpl.py`. These are raw C pointers to SDK state — **never let them be garbage-collected** while streaming is active. Do not reassign, shadow, or wrap them in temporary variables that go out of scope.

## Thread Safety

- SDK callbacks fire on background threads
- Never update Qt widgets directly from callbacks — emit a Qt signal instead
- The classifier layer (`classifiers/`) bridges callbacks → Qt signals with EMA smoothing

## Callback Data

- Emotion/Productivity/Cardio callbacks deliver real-time metrics
- Always validate `valid` flag before using values
- Stale data (no update for >2s) should be treated as invalid

## C-DLL Path

`lib/CapsuleClient.dll` — path configured via `CAPSULE_DLL_PATH` in `utils/config.py`. The DLL is loaded once at startup via `ctypes.CDLL`. Do not attempt to reload or unload.

## Adding New Wrappers

Follow the existing pattern: one module per SDK domain (e.g., `Emotions.py`, `Cardio.py`). Each exposes:
- A setup function that registers callbacks via ctypes function pointers
- Type definitions matching the C header structs
- No business logic — that belongs in `classifiers/`
