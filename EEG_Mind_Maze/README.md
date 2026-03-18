# EEG Mind Maze

Standalone Mind Maze app with live Capsule headband support.

## What is included

- `main.py` - the only file the user needs to run
- `sensor_pipeline.py` - standalone device discovery, connection, calibration, and live metric flow
- `maze_game.py` - Mind Maze rules and rendering
- `CapsuleClient.dll` - local Capsule runtime
- `capsule_sdk/` - local Capsule Python wrappers

## How it works

1. Scans for the first compatible band automatically.
2. Connects and starts the Capsule stream.
3. Runs quick closed-eyes calibration.
4. Runs productivity and physiological baseline calibration.
5. Waits for fresh concentration and relaxation metrics.
6. Starts Mind Maze.

## Run

Use Python 3.10 on Windows:

```powershell
cd EEG_Mind_Maze
py -3.10 -m pip install -r requirements.txt
py -3.10 main.py
```

## Demo fallback

If no headband is found, the app stays open and offers keyboard demo mode.

- `Enter` or `Space` starts demo mode
- Arrow keys move through the maze
- `R` restarts after a run finishes
- `Esc` closes the app
