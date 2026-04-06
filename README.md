# BCI Dashboard Windows Setup

This repo ships the working Instagram/WebView2 build from the `master` branch.

## Supported flow

1. Clone the repo or pull the latest `master` branch.
2. From the repo root, run:

```powershell
.\setup_windows.ps1
```

3. Launch the dashboard with:

```powershell
.\run_dashboard.ps1
```

## Second-machine checklist

- Make sure your checkout is on `master`.
- Run `.\setup_windows.ps1` once to create or repair `.venv`, install Python dependencies, verify bundled Capsule assets, and ensure Microsoft Edge WebView2 is installed.
- Start the app with `.\run_dashboard.ps1` so it always uses the repo-managed virtual environment.

## If Instagram does not load

- Re-run `.\setup_windows.ps1`.
- If the setup script says WebView2 could not be installed automatically, install it manually from:
  - `https://go.microsoft.com/fwlink/p/?LinkId=2124703`
- Launch the app again with `.\run_dashboard.ps1`.
