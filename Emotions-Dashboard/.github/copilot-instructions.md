# Project Guidelines — BCI Emotions Dashboard

## Overview

Real-time neurofeedback desktop app built with **PySide6** and a **Neiry BCI headband** via the Capsule SDK (C-library bindings). Entry point: `bci_dashboard/main.py`. Python ≥ 3.10.

## Build and Test

```bash
# Install
pip install -r bci_dashboard/requirements.txt
# PySide6 addons go to C:\p6 (Windows MAX_PATH workaround — see main.py bootstrap)

# Run
cd bci_dashboard && python main.py

# Test
python -m pytest tests/ -v
```

## Architecture

### Signal Flow

```
Neiry Headband → Capsule C-DLL → capsule_sdk/ wrappers
  → classifiers/ (EMA-smoothed handlers) → Qt Signals
  → gui/ screens & widgets
```

### GUI — Screen Router Pattern

`MainWindow` composes three mixins: `ScreenRouterMixin`, `SignalDispatcherMixin`, `GraphWindowManagerMixin`. Pages live in a `QStackedWidget` indexed by `PAGE_*` constants (connection → calibration → dashboard → training → multiplayer → …).

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `capsule_sdk/` | Ctypes wrappers for Capsule C-library (Emotions, Productivity, Cardio, MEMS, PhysiologicalStates) |
| `classifiers/` | Metric handlers — bridge raw SDK callbacks to Qt signals with EMA smoothing |
| `gui/` | All screens, widgets, standalone windows, training games |
| `gui/widgets/` | Reusable UI components (metric cards, EEG graphs, spectrum charts, game canvases) |
| `multiplayer/` | WebSocket protocol (JSON, port 7865), host-guest server/client |
| `device/` | Device manager, BLE discovery, Capsule bridge |
| `calibration/` | Calibration manager and persistent store |
| `storage/` | Async session recorder (threaded queue → JSON + H5 + CSV) |
| `utils/` | Config constants, EEG filters, PSD worker, helpers |
| `prosthetic_arm/` | Prosthetic arm control lab |

## Conventions

### Metrics — Always Use Baselines

All EEG-driven game logic must use **delta-from-baseline**, never raw metric values. Validate with `valid` + `stale` checks before acting on data.

### Training Game Pattern

1. Define a `TrainingGameSpec` in `gui/training_games.py` → `TRAINING_SPECS` list
2. Subclass `BaseTrainingController` (or `ArcadeTrainingController` / `MemoryGameController`)
3. Create an `_ImmersiveGameWidget` subclass in `gui/widgets/training_game_widgets.py`
4. Wire game_id in `gui/training_screen.py` → `_game_widget_map`
5. Calibration: 20-sample baseline with 3 ready-streaks; view_state dict → `widget.set_state()`

### Constants & Colors

- All constants: `UPPER_SNAKE_CASE` in `utils/config.py`
- Color tokens prefixed by intent: `COLOR_*`, `BG_*`, `ACCENT_*`, `GLOW_*`, `BORDER_*`, `TEXT_*`
- Dark theme base: `#131624` (navy), cards: `#1B1F36`

### EEG Band Definitions

Delta 1–4 Hz · Theta 4–8 Hz · Alpha 8–12 Hz · SMR 12–15 Hz · Beta 15–30 Hz

### Testing

- Tests use `unittest.TestCase` with `unittest.mock`
- sys.path injection to resolve imports (ROOT / APP_ROOT)
- No linter config — follow existing code style

### Multiplayer Protocol

JSON messages over WebSocket: `{"type": "MSG_*", "payload": {…}}`. Host is authoritative game controller; one guest per session. Dataclasses: `PlayerInfo`, `LobbyState`.

## Known Issues

See [MANAGER_EEG_DASHBOARD_TECHNICAL_REVIEW.md](../MANAGER_EEG_DASHBOARD_TECHNICAL_REVIEW.md) for current status:
- Training gameplay crash (`KeyError` in DIR_LABELS)
- Physiological calibration timeouts
- Native BLE/device SDK errors

## Pitfalls

- **PySide6 path limits on Windows**: Addons installed to `C:\p6`; `main.py` injects `QTWEBENGINEPROCESS_PATH` and `QTWEBENGINE_RESOURCES_PATH` env vars at boot.
- **Capsule SDK pointers**: Global ctypes pointers in `CapsulePointersImpl.py` — never garbage-collect while streaming.
- **Thread safety**: Session recorder uses a queue; never write to H5/CSV from the Qt main thread.
- **Device reconnection**: Max 10 attempts; baselines restore from `calibration_data/cal_<serial>.json`.
