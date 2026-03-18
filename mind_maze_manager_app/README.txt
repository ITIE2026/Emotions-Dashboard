Mind Maze Manager App
=====================

What this is
------------
This is a launcher that opens the live Mind Maze flow directly. It uses the
real headband connection pipeline from this project.

What must be shipped together
-----------------------------
Copy these items together onto the manager's computer:

1. mind_maze_manager_app
2. bci_dashboard

The `bci_dashboard` folder must still contain:

- lib/CapsuleClient.dll
- capsule_sdk/

Python requirements
-------------------
Install these in Python 3.10:

- PySide6
- pyqtgraph
- numpy
- pandas

How to run
----------
Open PowerShell in the folder that contains both `mind_maze_manager_app` and
`bci_dashboard`, then run:

    py -3.10 mind_maze_manager_app\main.py

What the launcher does
----------------------
- Starts the existing dashboard backend
- Keeps the real headband scanning/connection flow
- Opens the Training screen directly
- Focuses the Mind Maze game first

Important note
--------------
This is not a true single-file app. Live headband support depends on the
Capsule DLL, the Python SDK wrappers, and the dashboard modules.
