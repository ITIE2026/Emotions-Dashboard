import os
import subprocess
import sys
import textwrap
import unittest


class MainStartupSmokeTests(unittest.TestCase):
    def test_main_py_starts_and_exits_cleanly_under_auto_quit_harness(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        main_path = os.path.join(root, "bci_dashboard", "main.py")
        script = textwrap.dedent(
            f"""
            import os
            import runpy
            import traceback

            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication, QMessageBox

            QMessageBox.critical = staticmethod(lambda *args, **kwargs: None)
            _orig_exec = QApplication.exec

            def _timed_exec(*args, **kwargs):
                app = QApplication.instance()
                if app is not None:
                    QTimer.singleShot(1200, app.quit)
                return _orig_exec()

            QApplication.exec = _timed_exec

            try:
                runpy.run_path({main_path!r}, run_name="__main__")
                print("MAIN_STARTUP_OK")
            except SystemExit as exc:
                print(f"MAIN_STARTUP_EXIT:{{exc.code!r}}")
            except Exception:
                traceback.print_exc()
                raise
            """
        )
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env.setdefault("PYTHONUNBUFFERED", "1")

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}",
        )
        self.assertIn("MAIN_STARTUP_EXIT:0", result.stdout)


if __name__ == "__main__":
    unittest.main()
