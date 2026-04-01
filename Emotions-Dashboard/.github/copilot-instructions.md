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

`MainWindow` composes three mixins: `ScreenRouterMixin`, `SignalDispatcherMixin`, `GraphWindowManagerMixin`. Pages live in a `QStackedWidget` indexed by `PAGE_*` constants:

| Constant | Index | Screen |
|----------|-------|--------|
| `PAGE_CONNECTION` | 0 | BLE device discovery |
| `PAGE_CALIBRATION` | 1 | Baseline calibration |
| `PAGE_DASHBOARD` | 2 | Live metrics dashboard |
| `PAGE_MEMS` | 3 | Motion sensor view |
| `PAGE_TRAINING` | 4 | Training game launcher |
| `PAGE_SESSIONS` | 5 | Session history |
| `PAGE_PHASEON` | 6 | PhaseON runtime |
| `PAGE_YOUTUBE` | 7 | YouTube neurofeedback |
| `PAGE_MULTIPLAYER` | 8 | Multiplayer lobby |

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `capsule_sdk/` | Ctypes wrappers for Capsule C-library (Emotions, Productivity, Cardio, MEMS, PhysiologicalStates) |
| `classifiers/` | Metric handlers — bridge raw SDK callbacks to Qt signals with EMA smoothing |
| `gui/` | All screens, widgets, standalone windows, training games (~44 modules) |
| `gui/widgets/` | Reusable UI components — metric cards, EEG graphs, spectrum charts, game canvases (~20 modules) |
| `multiplayer/` | WebSocket protocol (JSON, port 7865), host-guest server/client |
| `device/` | Device manager, BLE discovery, Capsule bridge, device status monitor |
| `calibration/` | Calibration manager and persistent store |
| `storage/` | Async session recorder (threaded queue → JSON + H5 + CSV), CSV logger |
| `utils/` | Config constants, EEG filters, PSD worker, helpers, ui_effects, platform utils |
| `prosthetic_arm/` | Prosthetic arm control lab (ansible, state, backends) |
| `data/` | Static app data (neuroflow_apps.json) |
| `lib/` | Native DLLs (CapsuleClient.dll) |

### Standalone BCI Apps (gui/)

These screens run as standalone tools launched from the dashboard:

| Module | Purpose |
|--------|---------|
| `neuro_art_canvas.py` | EEG-driven art generation |
| `brain_speller.py` | P300-style BCI speller |
| `focus_timer.py` | Pomodoro-style focus timer |
| `bci_music_dj.py` | EEG-controlled music mixing |
| `bci_mouse_controller.py` | EEG-driven cursor control |
| `aim_trainer.py` | EEG targeting/aim trainer |
| `neuro_journal.py` | Neurofeedback session journal |
| `tracking_screen.py` | Metric tracking visualization |

## Conventions

### Metrics — Always Use Baselines

All EEG-driven game logic must use **delta-from-baseline**, never raw metric values. Validate with `valid` + `stale` checks before acting on data.

### Training Game Pattern

1. Define a `TrainingGameSpec` in `gui/training_games.py` → `TRAINING_SPECS` list
2. Subclass `BaseTrainingController` (or `ArcadeTrainingController` / `MemoryGameController`)
3. Create an `_ImmersiveGameWidget` subclass in `gui/widgets/training_game_widgets.py`
4. Wire game_id in `gui/training_screen.py` → `_game_widget_map`
5. Calibration: 20-sample baseline with 3 ready-streaks; view_state dict → `widget.set_state()`

**Game categories** (in `TRAINING_SPECS`):

| Category | Games |
|----------|-------|
| Meditation/Focus | calm_current, neuro_music_flow, neuroflow, mind_maze, prosthetic_arm, full_reboot |
| Arcade (immersive) | tug_of_war, space_shooter, jump_ball, bubble_burst, neon_vice, hill_climb_racer, gravity_drift, synapse_serpent, aero_zen, chrono_shift, neural_drive |
| Memory | pattern_recall, candy_cascade |

Immersive arcade games use `IMMERSIVE_GAME_IDS` set and get dedicated full-screen widgets. Each new arcade game gets a widget in `gui/widgets/` (e.g., `synapse_serpent_widget.py`).

**Controller hierarchy**: `BaseTrainingController` → `ArcadeTrainingController` (arcade physics/loop) or `MemoryGameController` (grid/pattern). Modules split across `training_games_base.py`, `training_games_arcade.py`, `training_games_meditation.py`, `training_games_memory.py`.

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
- 16+ test modules covering calibration, GUI, multiplayer games, training, audio, spectrum

### Multiplayer Protocol

JSON messages over WebSocket: `{"type": "MSG_*", "payload": {…}}`. Host is authoritative game controller; one guest per session. Dataclasses: `PlayerInfo`, `LobbyState`.

Message types: `MSG_HELLO`, `MSG_WELCOME`, `MSG_LOBBY_UPDATE`, `MSG_METRICS`, `MSG_CALIBRATION_SAMPLE`, `MSG_CALIBRATION_SYNC`, `MSG_READY`, `MSG_GAME_START`, `MSG_GAME_STATE`, `MSG_GAME_OVER`, `MSG_PLAYER_LEFT`, `MSG_ERROR`.

Multiplayer game screens: `multiplayer_tug_of_war.py`, `multiplayer_space_duel.py`, `multiplayer_bubble_battle.py`, `multiplayer_maze_race.py`.

## Known Issues

See [MANAGER_EEG_DASHBOARD_TECHNICAL_REVIEW.md](../MANAGER_EEG_DASHBOARD_TECHNICAL_REVIEW.md) for current status:
- Training gameplay crash (`KeyError` in DIR_LABELS)
- Physiological calibration timeouts
- Native BLE/device SDK errors
- `websockets` dependency in requirements.txt but missing from pyproject.toml

See [TEMP_TRAINING_LAB_OVERLAY_MEMORY.md](../TEMP_TRAINING_LAB_OVERLAY_MEMORY.md) for the experimental Training Lab overlay feature (temporary floating overlay for dashboard + training simultaneously).

## Pitfalls

- **PySide6 path limits on Windows**: Addons installed to `C:\p6`; `main.py` injects `QTWEBENGINEPROCESS_PATH` and `QTWEBENGINE_RESOURCES_PATH` env vars at boot.
- **Capsule SDK pointers**: Global ctypes pointers in `CapsulePointersImpl.py` — never garbage-collect while streaming.
- **Thread safety**: Session recorder uses a queue; never write to H5/CSV from the Qt main thread.
- **Device reconnection**: Max 10 attempts; baselines restore from `calibration_data/cal_<serial>.json`.
- **Dashboard screen migration**: Both `dashboard_screen_new.py` and `dashboard_screen_old.py` exist — new code should target the `_new` variant.
