import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "bci_dashboard"


class QtStylesheetCompatibilityTests(unittest.TestCase):
    def test_app_sources_do_not_use_box_shadow(self):
        unsupported_uses = []

        for path in APP_ROOT.rglob("*"):
            if path.suffix.lower() not in {".py", ".qss"}:
                continue
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if "box-shadow" in text:
                unsupported_uses.append(os.path.relpath(path, ROOT))

        self.assertEqual(
            unsupported_uses,
            [],
            f"Qt stylesheets do not support box-shadow; found in: {unsupported_uses}",
        )


if __name__ == "__main__":
    unittest.main()
