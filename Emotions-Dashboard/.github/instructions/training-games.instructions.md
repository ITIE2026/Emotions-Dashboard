---
applyTo: "bci_dashboard/gui/training_games*.py"
description: "Use when editing training game controllers, adding new training games, or modifying game specs. Enforces the 5-step training game pattern and baseline validation."
---
# Training Game Rules

## Adding a New Game

Every training game requires all 5 steps — skipping any causes silent failures:

1. **Spec** — Add a `TrainingGameSpec` to `TRAINING_SPECS` in `training_games.py` with correct `section`, `game_id`, `enabled`, `immersive` flags
2. **Controller** — Subclass `BaseTrainingController` (or `ArcadeTrainingController` / `MemoryGameController`). Place in the matching module: `training_games_arcade.py`, `training_games_meditation.py`, or `training_games_memory.py`
3. **Widget** — Create an `_ImmersiveGameWidget` subclass in `gui/widgets/` (e.g., `my_game_widget.py`)
4. **Wire** — Add `game_id` → widget mapping in `training_screen.py` → `_game_widget_map`. If immersive, add to `IMMERSIVE_GAME_IDS`
5. **Test** — Add a test module in `tests/`

## Baseline Validation (Mandatory)

- Always use **delta-from-baseline**, never raw metric values
- Check `valid` and `stale` flags before acting on data
- Calibration: 20-sample baseline with 3 ready-streaks
- Pass game state via `view_state` dict → `widget.set_state()`

## Controller Hierarchy

- `BaseTrainingController` — base class in `training_games_base.py` (DIR_LABELS, thresholds)
- `ArcadeTrainingController` — arcade physics/loop games
- `MemoryGameController` — grid/pattern recall games

## Common Mistakes

- Using raw metric values instead of delta-from-baseline → metrics feel random
- Forgetting `_game_widget_map` entry → game launches but shows blank screen
- Missing `IMMERSIVE_GAME_IDS` entry for arcade games → wrong layout/sizing
- Adding a direction label not in `DIR_LABELS` → `KeyError` crash (known issue)
