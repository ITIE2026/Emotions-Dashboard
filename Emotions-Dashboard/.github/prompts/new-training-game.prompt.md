---
description: "Scaffold a complete new EEG training game — spec, controller, widget, wiring, and test"
agent: "agent"
argument-hint: "game name and type (arcade/meditation/memory)"
---
Create a new training game for the BCI Emotions Dashboard.

## Input

The user will provide:
- **Game name** (e.g., "Plasma Pulse")
- **Game type**: arcade, meditation, or memory
- **Primary metric**: which EEG metric drives the game (e.g., focus, relaxation, cognitive_load)
- **Brief gameplay concept**

## Steps

Follow the [training game pattern](.github/instructions/training-games.instructions.md) — all 5 steps are mandatory:

### 1. Spec — `bci_dashboard/gui/training_games.py`
Add a `TrainingGameSpec` to the `TRAINING_SPECS` list with:
- `game_id` (snake_case), `label`, `desc`, `section`, `icon` (emoji)
- `controller_cls` pointing to the new controller
- `enabled=True`, `immersive=True` for arcade games

### 2. Controller — `bci_dashboard/gui/training_games_{type}.py`
Subclass the appropriate base:
- Arcade → `ArcadeTrainingController` in `training_games_arcade.py`
- Meditation → subclass in `training_games_meditation.py`
- Memory → `MemoryGameController` in `training_games_memory.py`

Must implement:
- `_on_metric_update()` using **delta-from-baseline** (never raw values)
- `_build_view_state()` returning a dict for the widget
- Proper `valid` + `stale` checks

### 3. Widget — `bci_dashboard/gui/widgets/{game_id}_widget.py`
Create an `_ImmersiveGameWidget` subclass with:
- `set_state(state: dict)` method
- QPainter-based rendering
- Dark theme colors from `utils/config.py` (BG_PRIMARY, ACCENT_*, etc.)

### 4. Wire — `bci_dashboard/gui/training_screen.py`
- Add to `_game_widget_map`
- If arcade/immersive: add to `IMMERSIVE_GAME_IDS`
- Import the widget class

### 5. Test — `tests/test_{game_id}.py`
- `unittest.TestCase` with `unittest.mock`
- Test controller metric handling with baseline validation
- Test widget `set_state()` with mock state dict
- Test spec is present in `TRAINING_SPECS`

## Output

Create all 5 files/modifications and confirm each step is complete.
