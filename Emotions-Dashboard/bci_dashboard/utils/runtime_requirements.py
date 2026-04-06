from __future__ import annotations

import importlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


REQUIRED_GIT_BRANCH = "master"
SETUP_WINDOWS_COMMAND = r".\setup_windows.ps1"
RUN_DASHBOARD_COMMAND = r".\run_dashboard.ps1"
_WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


@dataclass(slots=True)
class InstagramRuntimeStatus:
    ready: bool
    issues: list[str]
    summary: str
    fix_command: str = SETUP_WINDOWS_COMMAND
    webview2_version: str | None = None


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_instagram_host_script_path() -> Path:
    return get_app_root() / "gui" / "_wv2_host.py"


def _host_script_exists() -> bool:
    return get_instagram_host_script_path().is_file()


def _module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except Exception:
        return False
    return True


def detect_current_branch(repo_root: Path | None = None) -> str | None:
    override = os.environ.get("BCI_DASHBOARD_TEST_BRANCH")
    if override:
        return override

    root = Path(repo_root) if repo_root is not None else get_repo_root()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None

    branch = (result.stdout or "").strip()
    return branch or None


def format_branch_requirement_error(current_branch: str | None) -> str:
    current = current_branch or "unknown"
    return (
        f"This dashboard is supported on the '{REQUIRED_GIT_BRANCH}' branch only. "
        f"Current branch: '{current}'. "
        f"Run: git checkout {REQUIRED_GIT_BRANCH} && git pull origin {REQUIRED_GIT_BRANCH}"
    )


def detect_webview2_runtime_version() -> str | None:
    override = os.environ.get("BCI_DASHBOARD_TEST_WEBVIEW2_VERSION")
    if override is not None:
        return override or None

    if os.name != "nt":
        return None

    try:
        import winreg
    except Exception:
        return None

    key_paths = [
        (winreg.HKEY_CURRENT_USER, fr"Software\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, fr"Software\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, fr"Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT_GUID}"),
    ]

    for hive, key_path in key_paths:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if isinstance(version, str):
            cleaned = version.strip()
            if cleaned and cleaned != "0.0.0.0":
                return cleaned
    return None


def get_instagram_runtime_status() -> InstagramRuntimeStatus:
    issues: list[str] = []

    if not _host_script_exists():
        issues.append(
            f"Instagram host script is missing: {get_instagram_host_script_path().name}."
        )

    if not _module_available("webview"):
        issues.append("pywebview is not installed in the repo virtual environment.")

    if not _module_available("pythonnet"):
        issues.append("pythonnet is not installed in the repo virtual environment.")

    webview2_version = detect_webview2_runtime_version()
    if not webview2_version:
        issues.append("Microsoft Edge WebView2 Runtime is missing.")

    if issues:
        return InstagramRuntimeStatus(
            ready=False,
            issues=issues,
            summary=(
                "Instagram is unavailable on this machine until setup completes. "
                f"Run {SETUP_WINDOWS_COMMAND} from the repo root."
            ),
            webview2_version=webview2_version,
        )

    return InstagramRuntimeStatus(
        ready=True,
        issues=[],
        summary=f"Instagram runtime ready (WebView2 {webview2_version}).",
        webview2_version=webview2_version,
    )
