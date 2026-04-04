# Mini Militia–Inspired EEG Arena Shooter

This is a **separate game module** for your BCI project.
It is **inspired by** the core feel of Mini Militia: a 2D jetpack arena shooter with pickups, fast movement, and short matches.
It uses **original placeholder visuals and code structure**, so you can later skin it with your own art.

## What was matched from Mini Militia

From the current official game descriptions, the main loop is:
- 2D cartoon-style arena combat
- jetpack flight / rocket boots
- fast shooting with multiple weapons
- multiplayer / survival feel
- map exploration and pickups
- short, intense matches

Those points are reflected in this build as:
- side-view 2D arena
- jetpack energy system
- rifle / shotgun / sniper pickups
- AI bots for deathmatch feel
- health + energy + kill/death HUD
- fast respawn loop

## EEG control mapping used here

Because your headband is slower and noisier than touch controls, this version is **not a direct twin-stick clone**.
Instead it uses an EEG-friendly mapping:

- **Focus dominant** -> move / push right aggressively
- **Relax dominant** -> move / push left defensively
- **Steady balance** -> controlled hover with jetpack
- **Strong focus pulse** -> fire
- **Strong relaxation pulse** -> activate shield / recovery mode

This gives you both:
- the **Mini Militia combat feel**
- and a control method that is practical for EEG

## File structure idea for later dashboard integration

Recommended final structure inside your dashboard project:

```text
bci_dashboard/
  gui/
    training_games.py            # register Mini Militia inspired controller
    training_screen.py           # add game card + launch flow
    widgets/
      training_game_widgets.py   # add MiniMilitiaWidget
    games/
      mini_militia_controller.py # pure gameplay logic
      mini_militia_renderer.py   # drawing / view code
      mini_militia_models.py     # dataclasses: soldier, bullets, pickups
      mini_militia_bot_ai.py     # bot decisions
      mini_militia_bridge.py     # read focus/relaxation from live metrics
```

## Recommended controller design

### 1. EEG bridge layer
This layer receives live values from your dashboard/headband.
Expose only normalized values like:
- focus
- relaxation
- signal quality
- calibration ready
- optional blink or confidence values later

### 2. EEG interpreter layer
Convert raw values into game intents:
- move left
- move right
- hover
- fire pulse
- shield pulse

Keep debounce and cooldown here so the game layer stays clean.

### 3. Gameplay logic layer
Pure game state only:
- player state
- bot state
- bullets
- pickups
- collisions
- respawn logic
- scoring
- match timer

This layer should be independent from PySide6 drawing.

### 4. Widget / renderer layer
Only render:
- map
- players
- particles
- HUD
- focus and relax bars
- score panel

## Match rules in this prototype

- 3-minute deathmatch
- player vs 3 bots
- rifle default weapon
- shotgun / sniper pickups on the map
- heal pickups
- respawn after death
- score = kills
- winner = highest score when timer ends

## Physics model

- horizontal acceleration with damping
- gravity
- jetpack lift while energy is available
- platform landing
- camera follows player
- bullets use velocity + lifetime

## Why this is better for your project than copying the mobile game exactly

A direct copy of Mini Militia controls depends on:
- dual-stick aiming
- very fast manual taps
- exact mobile feel

That is not ideal for EEG.

This version keeps the recognizable gameplay pattern but adapts control so that:
- focus and relaxation both matter
- signal noise is tolerated better
- the player can still fight in a fast arena
- the game can be integrated into your BCI dashboard architecture

## Next integration step I recommend

1. Keep this file as a **standalone prototype** first.
2. Replace `DemoEEGBridge.read_metrics()` with your real focus/relaxation values.
3. Move the classes into your dashboard game modules.
4. Add a new training card in your Training Lab.
5. Add a result screen with score, survival time, accuracy, and calm-control stats.

## Good future upgrades

- add blink-based grenade throw
- add team deathmatch mode
- add 3 map themes
- add better AI pathing
- add recoil + knockback tuning
- add sound effects and adaptive soundtrack
- add focus/relax calibration page before match start
- add weapon ammo system
- add minimap and kill feed

## Run instructions

```bash
pip install pygame
python mini_militia_inspired_eeg_game.py
```

## Test controls

### EEG simulation mode
- `I` increase focus
- `K` decrease focus
- `O` increase relaxation
- `L` decrease relaxation
- `P` mark signal as connected
- `;` mark signal as demo/disconnected

### Keyboard fallback mode
- `TAB` switch between EEG and keyboard mode
- `A / D` move
- `W` or `SPACE` jetpack
- `F` fire
- `E` shield
- `R` restart
- `ESC` quit

