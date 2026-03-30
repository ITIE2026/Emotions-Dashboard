# Manager-Facing Technical Review of the EEG Dashboard

Date: March 30, 2026  
Project: EEG / BCI Dashboard Application  
Primary codebase: `bci_dashboard`

## 1. Executive Summary

This application is a working real-time EEG dashboard with live device integration, calibration, metrics, training modules, sessions, and supporting runtime logic. The core system is functional on the current Windows developer setup, and the codebase already contains meaningful optimization work for live rendering, smoothing, buffering, and asynchronous recording.

However, the application is not yet ready for broad rollout across other PCs without setup work. There are confirmed runtime issues, including a training-game crash, repeated physiological calibration failures, and recurring native Bluetooth/device errors in SDK logs. The application also depends on Windows-specific components such as `CapsuleClient.dll`, `os.startfile`, and shell-based launch commands, which makes current portability limited.

Manager conclusion: the app is suitable for controlled demos and continued development on the current machine, and it may run on similar Windows PCs with manual setup, but it is not yet packaged or hardened enough for simple deployment to fresh systems or non-technical end users.

## 2. Current Debugging Findings

### Issue 1: Confirmed training gameplay crash

- Severity: Critical
- Status: Confirmed finding
- Root cause:
  - In `bci_dashboard/gui/training_games.py`, the `DIR_LABELS` map does not include `"storm"`.
  - The gameplay logic can set `direction = "storm"` and later index `DIR_LABELS[direction]`.
- Evidence:
  - `bci_dashboard/gui/training_games.py:23`
  - `bci_dashboard/gui/training_games.py:360`
  - `bci_dashboard/gui/training_games.py:406`
  - `bci_dashboard/logs/dashboard.log` contains repeated `KeyError: 'storm'`
- Impact:
  - This is a direct live runtime crash during training gameplay.
- Manager explanation:
  - One game state can produce a label that the UI label map does not know about, which causes the application to throw an exception and break the run.

### Issue 2: Physiological baseline calibration repeatedly times out

- Severity: High
- Status: Confirmed finding
- Root cause:
  - The calibration manager runs a staged quick-calibration flow and applies a hard timeout to baseline stages.
  - The physiological stage repeatedly times out and then fails after retry.
- Evidence:
  - `bci_dashboard/calibration/calibration_manager.py:67`
  - `bci_dashboard/calibration/calibration_manager.py:103`
  - `bci_dashboard/calibration/calibration_manager.py:453`
  - `bci_dashboard/calibration/calibration_manager.py:460`
  - `bci_dashboard/logs/dashboard.log` contains repeated:
    - `Calibration physiological baseline timed out; retrying`
    - `Calibration physiological baseline timed out after retry`
    - `Calibration failed: Physiological baseline calibration timed out. Please retry.`
- Impact:
  - Quick calibration is unreliable in real runs.
  - Training and manager demos can stall before the user reaches stable gameplay.
- Manager explanation:
  - The app’s final calibration stage does not complete reliably, so users can be blocked even when the rest of the app is working.

### Issue 3: NFB serialization fallback is active because of SDK value-shape problems

- Severity: Medium
- Status: Confirmed finding
- Root cause:
  - Some native values coming back from the SDK do not always convert cleanly to integers.
  - The calibration path already contains a safety fallback to avoid crashing.
- Evidence:
  - `bci_dashboard/calibration/calibration_manager.py:362`
  - `bci_dashboard/logs/dashboard.log` contains repeated warnings like:
    - `Falling back to safe NFB serialization: invalid literal for int() with base 10: b'...'`
- Impact:
  - The app survives, which is good.
  - But the warning indicates a still-unresolved integration mismatch between expected Python values and native SDK values.
- Manager explanation:
  - The team already added a protective fallback so the application does not crash, but the underlying data-conversion issue is still present.

### Issue 4: Native BLE/device initialization is unstable

- Severity: High
- Status: Confirmed finding
- Root cause:
  - The SDK/native layer is repeatedly failing to start scanning or to fully create the BLE device protocol.
- Evidence:
  - `bci_dashboard/logs/Logs/SDK.log` contains:
    - `Failed start BLE scanner. BLE adapter not found or disabled`
    - `Failed read characteristic value: Unreachable`
    - `Failed create Smart Band BLE Protocol: [Can not read Serial number]`
  - `bci_dashboard/logs/Logs/Device.log` contains:
    - `Failed to create BLEDevice: Can not read Serial number`
    - `Execute command 23 failed: Device error: [UNKNOWN]`
    - `Device is not connected!`
- Impact:
  - Device connection and stability are not yet fully reliable.
  - Another PC with slightly different Bluetooth conditions may behave worse.
- Manager explanation:
  - The app’s connection quality depends not only on the code, but also on the Bluetooth environment and the native SDK layer, which currently shows repeated failures in logs.

### Issue 5: Current environment is missing declared dependencies

- Severity: High
- Status: Confirmed finding
- Root cause:
  - The repo requirements include `pyserial` and `h5py`, but those modules are not currently importable on this machine.
- Evidence:
  - `bci_dashboard/requirements.txt`
  - Runtime environment check on this machine:
    - `PySide6: OK`
    - `pyqtgraph: OK`
    - `numpy: OK`
    - `pandas: OK`
    - `serial: FAIL`
    - `h5py: FAIL`
    - `mne: OK`
  - `bci_dashboard/storage/session_recorder.py:152`
  - `bci_dashboard/logs/dashboard.log` repeatedly logs:
    - `h5py is not installed; session.h5 will not be written.`
- Impact:
  - Session recording is partially degraded.
  - Prosthetic-arm serial features will not work unless `pyserial` is installed.
- Manager explanation:
  - Even on the current machine, the software environment is not fully aligned with the project requirements, which is a warning sign for deployment readiness.

### Issue 6: Core runtime has Windows-only assumptions

- Severity: High
- Status: Confirmed finding
- Root cause:
  - The app relies on Windows-native DLL and shell behaviors.
- Evidence:
  - `bci_dashboard/utils/config.py:10` uses `CapsuleClient.dll`
  - `bci_dashboard/device/capsule_bridge.py:47` raises if DLL is missing
  - `bci_dashboard/gui/dashboard_screen.py:779` uses `os.startfile`
  - `bci_dashboard/gui/sessions_screen.py:594` uses `os.startfile`
  - `bci_dashboard/gui/neuroflow_runtime.py:97` launches via `cmd /c start`
- Impact:
  - Current deployment is effectively Windows-only.
  - Linux and macOS are not ready for the main application path.
- Manager explanation:
  - The application can currently be treated as a Windows product only.

### Issue 7: Architecture is tightly coupled and harder to maintain

- Severity: Medium
- Status: Confirmed finding
- Root cause:
  - `MainWindow` owns device orchestration, calibration, routing, session recording, graph history, and page coordination.
  - `training_games.py` is a very large multi-controller module.
- Evidence:
  - `bci_dashboard/gui/main_window.py`
  - `bci_dashboard/gui/training_games.py`
- Impact:
  - Future debugging, onboarding, and feature changes are riskier and slower than they need to be.
- Manager explanation:
  - The app works, but too much logic lives in a few large modules, which makes long-term stability harder.

### Issue 8: Scan-helper architecture looks stale or partially unused

- Severity: Medium
- Status: Likely finding / inference
- Root cause:
  - The codebase still contains a helper-process scanning strategy and QProcess-related cleanup logic, but current scanning appears to use direct locator calls.
- Evidence:
  - `bci_dashboard/device/scan_helper.py`
  - `bci_dashboard/device/device_manager.py`
  - scan-helper runtime log directory exists but no active helper log files were found
- Impact:
  - This is more of a maintainability and correctness risk than an immediate crash.
- Manager explanation:
  - The code shows signs of multiple scanning approaches over time, which suggests cleanup is still needed.

### Issue 9: Legacy/duplicate UI files remain in the repo

- Severity: Low
- Status: Confirmed finding
- Root cause:
  - Historical screen variants such as `dashboard_screen_old.py` and `dashboard_screen_new.py` are still present.
- Evidence:
  - Static repo inspection and compile discovery
- Impact:
  - These are not proven live bugs, but they add confusion and maintenance overhead.
- Manager explanation:
  - There is some historical code still in the project that should be cleaned up before packaging or handoff.

### Open issues needing runtime verification

- Whether the UI-thread callback pump introduces visible lag under heavy live use
- Whether repeated calibration-start logging is duplicated user action or duplicate signal flow
- Whether reconnect fully restores all classifiers after a real disconnect
- Whether physiological timeout is mainly signal-quality related or stage-logic related

## 3. Performance Review

### Current performance behavior

The application is not using a crude busy loop. It is timer- and callback-driven:

- Capsule callback pump: `20 ms`
  - `bci_dashboard/device/capsule_bridge.py:58`
- Dashboard duration timer: `1000 ms`
  - `bci_dashboard/gui/dashboard_screen.py:140`
- Dashboard EEG refresh timer: `50 ms`
  - `bci_dashboard/gui/dashboard_screen.py:145`
- Dashboard PSD throttle: `0.08 s`
  - `bci_dashboard/gui/dashboard_screen.py:126`
- Training calibration timer: `250 ms`
  - `bci_dashboard/gui/training_screen.py:317`
- Training gameplay timer: `250 ms`
  - `bci_dashboard/gui/training_screen.py:321`
- Neuroflow simulation timer: `50 ms`
  - `bci_dashboard/gui/neuroflow_training_page.py`
- Neuroflow UI refresh timer: `100 ms`
  - `bci_dashboard/gui/neuroflow_training_page.py`
- Status/reconnect polling: `5000 ms`
  - `bci_dashboard/utils/config.py:62`

### Likely latency sources

**Confirmed findings**
- Main-thread risks exist because the native Capsule callback pump, PSD snapshot extraction, EEG snapshot extraction, and some page updates are coordinated from the main GUI runtime:
  - `bci_dashboard/gui/main_window.py:1284`
  - `bci_dashboard/gui/main_window.py:1310`
  - `bci_dashboard/gui/main_window.py:1464`
  - `bci_dashboard/gui/main_window.py:1495`
- Rendering overhead is partially controlled, but still present:
  - the electrode table stores up to `4000` samples per channel
  - redraws pyqtgraph plots
  - uses downsampling and clip-to-view
  - `bci_dashboard/gui/widgets/electrode_table.py:38`
  - `bci_dashboard/gui/widgets/electrode_table.py:611`
  - `bci_dashboard/gui/widgets/electrode_table.py:698`
- Training modules add periodic gameplay work and in some cases audio and richer visuals:
  - `bci_dashboard/gui/training_screen.py`

**Likely findings / inferences**
- If the dashboard, live EEG, PSD processing, and a game are all active together, the single-threaded UI path may become the main source of perceived lag.
- The native SDK callback pump being timer-driven on the Qt side is safe and simple, but it may become a bottleneck on slower PCs.

### Logging, buffering, and storage overhead

**Confirmed findings**
- Session writing is already moved off the UI path using a background recorder thread:
  - `bci_dashboard/gui/main_window.py:79`
  - `bci_dashboard/gui/main_window.py:86`
- Session data is buffered and flushed in batches:
  - `bci_dashboard/storage/session_recorder.py`
- PPG metrics are derived from rolling windows in pure helpers:
  - `bci_dashboard/gui/raw_metrics.py`

### Performance verdict

- Real-time suitability: Yes, for controlled Windows use on the current machine
- Confidence level: Moderate
- Why not higher:
  - critical native/device failures are still present
  - the most time-sensitive path still shares the GUI thread
  - there is no evidence yet from runtime profiling on slower or fresh machines

## 4. Existing Optimizations Identified

### Optimization 1: EMA smoothing in live metrics

- Location:
  - `bci_dashboard/classifiers/emotions_handler.py:25`
  - `bci_dashboard/classifiers/productivity_handler.py:29`
- What it does:
  - smooths incoming emotion and productivity values with exponential moving averages
- Why it helps:
  - reduces jitter in the dashboard and games
- Status:
  - useful and active
  - slightly increases responsiveness lag, but overall worthwhile

### Optimization 2: Dirty-flag and throttled dashboard updates

- Location:
  - `bci_dashboard/gui/dashboard_screen.py:126`
  - `bci_dashboard/gui/dashboard_screen.py:553`
  - `bci_dashboard/gui/dashboard_screen.py:786`
- What it does:
  - avoids redrawing on every incoming packet
  - throttles PSD work and only refreshes when data is marked dirty
- Why it helps:
  - reduces needless redraw cost
- Status:
  - effective and important

### Optimization 3: Async session recording

- Location:
  - `bci_dashboard/gui/main_window.py:79`
  - `bci_dashboard/gui/main_window.py:86`
- What it does:
  - records session data through a queue and a background thread
- Why it helps:
  - prevents recording IO from directly blocking live UI
- Status:
  - strong optimization already in place

### Optimization 4: Native-packet snapshot extraction before async handoff

- Location:
  - `bci_dashboard/gui/main_window.py:1464`
  - `bci_dashboard/gui/main_window.py:1495`
- What it does:
  - converts native/SDK packet objects into plain Python data before recording or forwarding
- Why it helps:
  - avoids lifetime/use-after-free issues with native objects
  - makes async recording safer
- Status:
  - important safety and stability optimization

### Optimization 5: Rolling raw-metric aggregation helpers

- Location:
  - `bci_dashboard/gui/raw_metrics.py`
- What it does:
  - centralizes band-history aggregation and PPG metric derivation
- Why it helps:
  - keeps calculations testable and avoids duplicated UI-side logic
- Status:
  - good structure improvement already present

### Optimization 6: Reconnect grace period and retry control

- Location:
  - `bci_dashboard/device/device_status_monitor.py`
- What it does:
  - waits for grace period, counts misses, retries on disconnect
- Why it helps:
  - avoids false disconnect reactions
- Status:
  - useful, but still limited by native BLE reliability

### Optimization 7: Plot downsampling and bounded EEG buffers

- Location:
  - `bci_dashboard/gui/widgets/electrode_table.py:38`
  - `bci_dashboard/gui/widgets/electrode_table.py:611`
  - `bci_dashboard/gui/widgets/electrode_table.py:698`
- What it does:
  - limits stored samples
  - downsamples plots to a smaller point set
  - clips rendering to view
- Why it helps:
  - lowers graph rendering overhead
- Status:
  - active and useful, but still on the GUI path

### Optimization 8: Calibration safety fallback

- Location:
  - `bci_dashboard/calibration/calibration_manager.py:362`
- What it does:
  - falls back to safer serialization when SDK values behave unexpectedly
- Why it helps:
  - keeps calibration from crashing
- Status:
  - good defensive improvement, but underlying issue remains unresolved

## 5. Improvements Already Done

Based on the current code and logs, several meaningful improvements appear to have already been implemented:

- safer session recording through async queue/thread handoff
- safer native-object handling through snapshot extraction
- dirty-flag and throttled dashboard refresh logic
- smoothing for noisy real-time metrics
- test coverage for dashboard metrics, spectrum widgets, Neuroflow, sessions, and calibration scenarios
- defensive calibration serialization fallback
- more robust reconnect behavior than a simple binary connected/disconnected flag
- graceful degradation when `h5py` is missing

These are real improvements, not cosmetic ones. The codebase is clearly past the earliest prototype stage. The remaining problem is that the app still has a few unresolved failures at exactly the points that matter most for demos and deployment: device reliability, calibration reliability, startup environment consistency, and packaging.

## 6. Future Optimization Plan

### 1. Critical

- Fix the confirmed `storm` gameplay crash in `training_games.py`
  - Expected benefit: removes a proven live crash
- Stabilize physiological baseline calibration with better diagnostics and less opaque timeout handling
  - Expected benefit: higher success rate in real sessions
- Add startup preflight checks for:
  - DLL presence
  - SDK importability
  - Python dependency availability
  - Bluetooth readiness
  - writable session/log directories
  - Expected benefit: much clearer deployment/startup behavior
- Resolve or simplify the BLE scanning architecture
  - Expected benefit: fewer device-discovery failures and less support complexity

### 2. High-value

- Move more non-UI work off the main thread where safe
  - especially PSD-heavy work and expensive snapshot creation
  - Expected benefit: better responsiveness under load
- Refactor `MainWindow` into smaller coordinating services
  - Expected benefit: easier debugging and lower regression risk
- Split `training_games.py` into smaller modules by game family
  - Expected benefit: easier maintenance and safer changes
- Make Neuroflow launch targets configurable instead of hard-coded
  - Expected benefit: more reliable app-launch behavior on other PCs

### 3. Medium-term

- Build a packaged Windows distribution
  - likely PyInstaller or similar
  - bundle runtime, assets, DLL, SDK wrappers
  - Expected benefit: easier execution on similar Windows PCs
- Add log rotation and support-bundle export
  - Expected benefit: easier field debugging
- Add explicit runtime profiling on:
  - dashboard only
  - dashboard + training
  - dashboard + recording
  - Expected benefit: real performance data for managers and QA

### 4. Optional

- Investigate true cross-platform support only after Windows packaging is stable
  - Expected benefit: future portability
  - Current priority: low

## 7. Cross-System Execution Assessment

### Overall answer to the manager question

“Will this application be able to run on other systems easily?”

Current answer: **Not easily yet.**

It can likely run on another similar Windows PC if the environment is carefully prepared, but it is not currently a plug-and-play product for fresh PCs.

### Can it run on other PCs now?

**Yes, under conditions**
- Windows PC
- correct Python version, currently observed as `Python 3.10.9`
- required packages installed
- local folder layout preserved
- `bci_dashboard/lib/CapsuleClient.dll` present
- `bci_dashboard/capsule_sdk` present
- Bluetooth adapter working and enabled
- hardware/device behavior similar to the current setup

**No, not easily on fresh systems**
- no packaged installer
- no root deployment guide
- current machine itself is missing two declared dependencies
- core runtime uses Windows-specific APIs

### Platform assumptions

**Confirmed findings**
- Windows DLL dependency:
  - `bci_dashboard/utils/config.py:10`
- Windows file-opening behavior:
  - `bci_dashboard/gui/dashboard_screen.py:779`
  - `bci_dashboard/gui/sessions_screen.py:594`
- Windows shell launching:
  - `bci_dashboard/gui/neuroflow_runtime.py:97`

### Python assumptions

**Confirmed findings**
- Current machine uses `Python 3.10.9`
- No formal top-level packaging metadata was found for the main app

### Native dependency assumptions

**Confirmed findings**
- `CapsuleClient.dll`
- SDK wrapper modules under `bci_dashboard/capsule_sdk`
- optional vendored `neurosdk` for prosthetic-arm/BrainBit-related paths

### Hardware and driver assumptions

**Confirmed findings**
- Bluetooth adapter is required for the main headband flow
- BLE instability is already visible in native logs
- optional Arduino serial connection is required for the prosthetic-arm path

### Folder structure assumptions

**Confirmed findings**
- paths are derived from local app folders
- the code repeatedly uses `sys.path.insert(...)` to make SDK and local modules importable
- this is workable for development, but weak for deployment

### Cross-platform conclusion

- Windows: partially viable with setup
- Linux: not ready
- macOS: not ready
- Cross-platform product claim: not supportable from current code state

## 8. Deployment and Packaging Recommendations

To make the application easier to run on other systems, the following are needed:

### Immediate packaging/setup steps

1. Pin and document the supported Python version
2. Ensure `requirements.txt` installs successfully on a clean Windows machine
3. Add startup checks that fail clearly if:
   - `CapsuleClient.dll` is missing
   - `capsule_sdk` is missing
   - `pyserial` or `h5py` are missing when needed
   - Bluetooth is unavailable
4. Provide one clear setup document at repo root
5. Validate startup on a second Windows PC

### Recommended Windows packaging path

1. Build a Windows executable bundle
2. Include:
   - Python runtime
   - `bci_dashboard`
   - `capsule_sdk`
   - `lib/CapsuleClient.dll`
   - assets, music, images
3. Add a post-start environment validation screen
4. Create a simple launch shortcut/start script

### For developers/testers

- create a reproducible `venv`-based setup
- add one command to verify environment health before first launch
- keep optional modules clearly marked as optional

## 9. Risks and Blockers

### Technical risks

- Critical: confirmed game crash
- High: unreliable physiological calibration
- High: native BLE/device creation failures
- High: undeclared environment drift between requirements and actual installed packages
- Medium: main-thread real-time coordination may become a performance bottleneck on weaker systems
- Medium: overly large orchestration modules increase change risk

### Architectural risks

- tightly coupled runtime ownership in `MainWindow`
- stale or duplicated discovery architecture
- large training controller file with inconsistent defensive coding

### Platform risks

- Windows-specific runtime path
- native DLL dependency
- Bluetooth/driver sensitivity
- optional serial and vendor-library dependencies

### Operational risks

- another PC may fail before user reaches dashboard due to environment mismatch
- native logs already show hardware/driver-level instability
- without packaging, deployment support burden stays high

## 10. Final Verdict

### Is the application ready for broader usage?

No, not yet.

### Is it ready only for the current machine?

Mostly yes. The current machine is the highest-confidence environment because it already contains the project layout, SDK files, and most of the working runtime context.

### Is it ready for similar Windows systems?

Partially, with manual setup and validation. It is not yet “easy to execute” in the manager’s sense.

### What must be fixed before rollout?

- fix the confirmed gameplay crash
- improve calibration reliability
- harden BLE/device startup and diagnostics
- align environment dependencies with actual runtime needs
- package the Windows runtime properly
- document startup/setup clearly

## Manager-Friendly Summary Paragraph

The EEG dashboard is already a real working application with live EEG integration, calibration, dashboards, games, and session recording, and it includes several real optimizations that make it usable on the current development system. But it is still not ready for simple rollout to other PCs because it depends on a Windows-specific native SDK setup, shows recurring Bluetooth/device and calibration failures in logs, and still has at least one confirmed runtime crash in gameplay. For now, it is best treated as a controlled Windows demo/development application rather than a finished portable product.

## Technical Engineering Summary Paragraph

The current runtime architecture is a Qt-driven, callback-and-timer-based BCI application centered on `MainWindow`, with native Capsule integration, classifier wrappers, throttled dashboard rendering, and asynchronous session recording. Existing optimizations are meaningful and include EMA smoothing, dirty-flag redraw control, pyqtgraph downsampling, async recording, and safer native snapshot extraction. The main engineering gaps are runtime stability at calibration/device boundaries, UI-thread ownership of key real-time paths, monolithic orchestration, inconsistent defensive handling across controllers, and lack of a reproducible packaging/deployment layer.

## Short Action Plan

1. Fix the `storm` gameplay crash immediately.
2. Add deeper diagnostics around physiological calibration timeout and reproduce it with a fresh live session.
3. Add startup preflight checks for DLLs, Python dependencies, Bluetooth, and writable directories.
4. Build and validate a packaged Windows version on a second PC before any wider rollout.
