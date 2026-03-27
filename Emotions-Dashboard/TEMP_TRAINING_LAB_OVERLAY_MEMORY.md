# Temporary Training Lab Overlay Memory

Purpose: temporary recording-mode Training Lab overlay over dashboard.

## Summary

This note preserves the temporary Training Lab recording behavior so it can be re-implemented later even after the code is reverted.

The temporary feature was:

- Training Lab opens as a floating overlay over the main dashboard instead of replacing it.
- The full Training Lab flow stays inside the overlay:
  - catalog
  - detail
  - settings
  - calibration
  - gameplay
  - result
- Default placement is on the right side so the dashboard EEG graph area remains visible on the left for recording.
- The overlay is draggable, resizable, and collapsible to a one-line title bar.
- Collapse keeps the active Training Lab flow running.
- Close and `Home` stop the active Training Lab flow and hide the overlay.
- Switching to other full pages such as MEMS, Sessions, or Phaseon hides and stops the overlay so it remains a dashboard-recording-only tool.

## Main Implementation Decisions

- `main_window.py` owns the overlay and keeps the dashboard in the main stack.
- Training Lab menu entry points are routed into the overlay instead of switching the main stack to `PAGE_TRAINING`.
- The existing `TrainingScreen` instance is reused. Do not create a second Training Lab runtime.
- The overlay shell is implemented in `training_overlay_shell.py`.
- While the overlay is visible over the dashboard:
  - dashboard view remains active
  - Training Lab view also remains active
  - both dashboard metrics/graphs and Training Lab timers/gameplay continue updating at the same time
- This is temporary demo behavior only. It should stay isolated and easy to revert.

## Expected Overlay Behavior

- Opening Training Lab should first ensure the dashboard remains the visible base page.
- The overlay should appear over the dashboard with a header bar titled `Training Lab`.
- The header bar should include:
  - collapse/expand control
  - close control
- Dragging should work from the header only.
- Resizing should work from the lower-right corner.
- Collapsed state should show only the title bar.
- Expanded state should restore the previous larger size.
- The overlay should stay within the main window bounds.

## Revert / Reapply Guidance

- Revert removes the overlay code paths but keeps this note.
- Future reimplementation should follow this note as the source of truth for the temporary overlay behavior.
- Reapply should touch these files:
  - `bci_dashboard/gui/main_window.py`
  - `bci_dashboard/gui/training_overlay_shell.py`
  - `tests/test_training_overlay.py`

## Focused Verification Used During Working Version

Commands used when the temporary overlay was working:

```powershell
py -3 -m py_compile bci_dashboard\gui\training_overlay_shell.py bci_dashboard\gui\main_window.py tests\test_training_overlay.py
py -3 -m unittest tests.test_training_overlay tests.test_home_navigation
```

## Reimplementation Checklist

When reapplying later, confirm:

- Training Lab opens over the dashboard instead of replacing it.
- Dashboard remains visible behind the overlay.
- Dashboard and Training Lab both stay live while the overlay is open.
- Collapse does not stop calibration, gameplay, or audio.
- Close and `Home` stop the active Training Lab flow and hide the overlay.
- Switching to non-dashboard full pages hides/stops the overlay.
- Drag, resize, and collapse behavior still work.
