import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from utils.runtime_requirements import (  # noqa: E402
    REQUIRED_GIT_BRANCH,
    format_branch_requirement_error,
    get_instagram_runtime_status,
)


class RuntimeRequirementsTests(unittest.TestCase):
    def test_get_instagram_runtime_status_reports_all_missing_prereqs(self):
        with (
            patch("utils.runtime_requirements._host_script_exists", return_value=False),
            patch("utils.runtime_requirements._module_available", side_effect=lambda name: False),
            patch("utils.runtime_requirements.detect_webview2_runtime_version", return_value=None),
        ):
            status = get_instagram_runtime_status()

        self.assertFalse(status.ready)
        self.assertIn("_wv2_host.py", "\n".join(status.issues))
        self.assertIn("pywebview", "\n".join(status.issues))
        self.assertIn("pythonnet", "\n".join(status.issues))
        self.assertIn("WebView2", "\n".join(status.issues))
        self.assertIn(r".\setup_windows.ps1", status.summary)

    def test_get_instagram_runtime_status_is_ready_when_everything_exists(self):
        with (
            patch("utils.runtime_requirements._host_script_exists", return_value=True),
            patch("utils.runtime_requirements._module_available", return_value=True),
            patch("utils.runtime_requirements.detect_webview2_runtime_version", return_value="124.0.2478.80"),
        ):
            status = get_instagram_runtime_status()

        self.assertTrue(status.ready)
        self.assertEqual(status.issues, [])
        self.assertIn("ready", status.summary.lower())

    def test_format_branch_requirement_error_mentions_supported_branch(self):
        message = format_branch_requirement_error("main")
        self.assertIn(REQUIRED_GIT_BRANCH, message)
        self.assertIn("main", message)
        self.assertIn("git checkout", message)


if __name__ == "__main__":
    unittest.main()
