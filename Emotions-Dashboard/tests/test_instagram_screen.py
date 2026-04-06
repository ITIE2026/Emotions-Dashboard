import os
import sys
import tempfile
import textwrap
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

import gui.instagram_screen as instagram_screen  # noqa: E402


APP = QApplication.instance() or QApplication([])


class _StubProcess:
    def __init__(self, initial_url: str, *args, **kwargs) -> None:
        self.initial_url = initial_url
        self.ready = True
        self.failed = False
        self.failure_reason = ""
        self.navigated_urls = []
        self.js_calls = []
        self.hide_called = False
        self.quit_called = False

    def navigate(self, url: str) -> None:
        self.navigated_urls.append(url)

    def run_js(self, code: str) -> None:
        self.js_calls.append(code)

    def configure_host(self, owner_hwnd: int) -> None:
        return None

    def move(self, x: int, y: int) -> None:
        return None

    def resize(self, w: int, h: int) -> None:
        return None

    def show(self) -> None:
        return None

    def hide(self) -> None:
        self.hide_called = True

    def quit(self) -> None:
        self.quit_called = True


class InstagramScreenTests(unittest.TestCase):
    def test_instagram_screen_prefers_reels_playback_host_when_runtime_ready(self):
        runtime_status = SimpleNamespace(
            ready=True,
            issues=[],
            summary="Instagram runtime ready",
            fix_command=r".\setup_windows.ps1",
        )
        with patch.object(instagram_screen, "get_instagram_runtime_status", return_value=runtime_status), patch.object(
            instagram_screen, "_Wv2Process", _StubProcess
        ):
            screen = instagram_screen.InstagramScreen()
            try:
                self.assertTrue(hasattr(screen, "_wv"))
                self.assertFalse(hasattr(screen, "_web_view"))
                self.assertIsInstance(screen._wv, _StubProcess)
            finally:
                screen.shutdown()
                screen.close()

    def test_instagram_screen_surfaces_runtime_diagnostic_in_placeholder(self):
        runtime_status = SimpleNamespace(
            ready=False,
            issues=[
                "pywebview is not installed in the repo virtual environment.",
                "Microsoft Edge WebView2 Runtime is missing.",
            ],
            summary="Instagram is unavailable on this machine until setup completes.",
            fix_command=r".\setup_windows.ps1",
        )
        with patch.object(instagram_screen, "get_instagram_runtime_status", return_value=runtime_status):
            screen = instagram_screen.InstagramScreen()
            try:
                self.assertFalse(hasattr(screen, "_wv"))
                placeholder = screen._placeholder.text()
                self.assertIn("Instagram is unavailable", placeholder)
                self.assertIn(r".\setup_windows.ps1", placeholder)
                self.assertIn("pywebview", placeholder)
                self.assertIn("WebView2", placeholder)
            finally:
                screen.close()


class Wv2ProcessTests(unittest.TestCase):
    @staticmethod
    def _wait_until(predicate, timeout: float = 2.0) -> bool:
        end_time = time.time() + timeout
        while time.time() < end_time:
            if predicate():
                return True
            time.sleep(0.05)
        return predicate()

    def test_wv2_process_times_out_and_includes_stderr(self):
        with tempfile.TemporaryDirectory() as tempdir:
            host_script = os.path.join(tempdir, "slow_host.py")
            with open(host_script, "w", encoding="utf-8") as handle:
                handle.write(
                    textwrap.dedent(
                        """
                        import sys
                        import time

                        sys.stderr.write("host started but never became ready\\n")
                        sys.stderr.flush()
                        time.sleep(30)
                        """
                    )
                )

            proc = instagram_screen._Wv2Process(
                "https://www.instagram.com/reels/",
                host_script=host_script,
                python_executable=sys.executable,
                storage_dir=tempdir,
                ready_timeout_sec=0.25,
            )
            try:
                self.assertTrue(
                    self._wait_until(lambda: getattr(proc, "failed", False), timeout=2.0),
                    "Timed-out host should be marked as failed",
                )
                self.assertIn("timed out", proc.failure_reason.lower())
                self.assertIn("host started but never became ready", proc.failure_reason)
            finally:
                proc.quit()

    def test_wv2_process_reports_non_zero_exit_and_stderr(self):
        with tempfile.TemporaryDirectory() as tempdir:
            host_script = os.path.join(tempdir, "crash_host.py")
            with open(host_script, "w", encoding="utf-8") as handle:
                handle.write(
                    textwrap.dedent(
                        """
                        import sys

                        sys.stderr.write("No module named webview\\n")
                        sys.stderr.flush()
                        raise SystemExit(3)
                        """
                    )
                )

            proc = instagram_screen._Wv2Process(
                "https://www.instagram.com/reels/",
                host_script=host_script,
                python_executable=sys.executable,
                storage_dir=tempdir,
                ready_timeout_sec=1.0,
            )
            try:
                self.assertTrue(
                    self._wait_until(lambda: getattr(proc, "failed", False), timeout=2.0),
                    "Crashed host should be marked as failed",
                )
                self.assertIn("exit code 3", proc.failure_reason.lower())
                self.assertIn("No module named webview", proc.failure_reason)
            finally:
                proc.quit()


if __name__ == "__main__":
    unittest.main()
