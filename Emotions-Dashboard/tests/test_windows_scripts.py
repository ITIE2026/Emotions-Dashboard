import os
import subprocess
import sys
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETUP_SCRIPT = os.path.join(REPO_ROOT, "setup_windows.ps1")
RUN_SCRIPT = os.path.join(REPO_ROOT, "run_dashboard.ps1")


@unittest.skipUnless(sys.platform.startswith("win"), "Windows PowerShell scripts only")
class WindowsScriptTests(unittest.TestCase):
    def _run_powershell(self, script_path: str, *args: str, extra_env: dict | None = None):
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
                *args,
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_run_dashboard_dry_run_rejects_wrong_branch(self):
        result = self._run_powershell(
            RUN_SCRIPT,
            "-DryRun",
            extra_env={
                "BCI_DASHBOARD_TEST_BRANCH": "main",
                "BCI_DASHBOARD_TEST_WEBVIEW2_VERSION": "124.0.2478.80",
            },
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("master", combined)
        self.assertIn("main", combined)

    def test_run_dashboard_dry_run_succeeds_on_master(self):
        result = self._run_powershell(
            RUN_SCRIPT,
            "-DryRun",
            extra_env={
                "BCI_DASHBOARD_TEST_BRANCH": "master",
                "BCI_DASHBOARD_TEST_WEBVIEW2_VERSION": "124.0.2478.80",
            },
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN_DASHBOARD_READY", result.stdout)

    def test_setup_windows_check_only_succeeds_when_repo_is_ready(self):
        result = self._run_powershell(
            SETUP_SCRIPT,
            "-CheckOnly",
            extra_env={
                "BCI_DASHBOARD_TEST_BRANCH": "master",
                "BCI_DASHBOARD_TEST_WEBVIEW2_VERSION": "124.0.2478.80",
            },
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SETUP_WINDOWS_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
