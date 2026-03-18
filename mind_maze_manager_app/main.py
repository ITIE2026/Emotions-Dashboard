"""
Manager-facing launcher for the live Mind Maze experience.

This launcher relies on the bundled `bci_dashboard` package, Capsule SDK files,
and PySide6. Ship this folder together with the dashboard package and its
runtime dependencies.
"""
from __future__ import annotations

import logging
import os
import sys
import traceback


APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
BCI_DIR = os.path.join(PROJECT_ROOT, "bci_dashboard")

if BCI_DIR not in sys.path:
    sys.path.insert(0, BCI_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui.main_window import MainWindow, PAGE_TRAINING  # noqa: E402
from utils.config import BG_PRIMARY, BG_CARD, BORDER_SUBTLE, TEXT_PRIMARY  # noqa: E402


def _setup_logging() -> None:
    log_dir = os.path.join(BCI_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(log_dir, "mind_maze_manager.log"), encoding="utf-8"),
        ],
    )


def _exception_hook(exc_type, exc_value, exc_tb) -> None:
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("Unhandled exception:\n%s", msg)
    QMessageBox.critical(None, "Mind Maze Error", str(exc_value))


def _focus_mind_maze(window: MainWindow) -> None:
    window._stack.setCurrentIndex(PAGE_TRAINING)
    window._training_screen._show_detail("mind_maze")


def main() -> int:
    _setup_logging()
    sys.excepthook = _exception_hook

    app = QApplication(sys.argv)
    app.setApplicationName("Mind Maze")
    app.setStyleSheet(
        f"""
        QMainWindow, QWidget {{
            background-color: {BG_PRIMARY};
            color: {TEXT_PRIMARY};
        }}
        QMessageBox {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
        }}
        """
    )

    window = MainWindow()
    window.setWindowTitle("Mind Maze")
    _focus_mind_maze(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
