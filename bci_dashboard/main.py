"""
BCI Dashboard – entry point.

Usage:
    python main.py
"""
import sys
import os
import logging
import traceback

# ── Ensure project root is on sys.path ────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt


def _setup_logging():
    log_dir = os.path.join(APP_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(log_dir, "dashboard.log"),
                encoding="utf-8",
            ),
        ],
    )


def _exception_hook(exc_type, exc_value, exc_tb):
    """Global exception handler – log and show a dialog."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("Unhandled exception:\n%s", msg)
    # CapsuleException stores bytes in .message; decode safely
    display = str(exc_value)
    if hasattr(exc_value, "message") and isinstance(exc_value.message, bytes):
        display = exc_value.message.decode("utf-8", errors="replace")
    elif isinstance(display, str) and display.startswith("b'") and display.endswith("'"):
        try:
            raw = display[2:-1].encode('raw_unicode_escape').decode('unicode_escape', errors='replace')
            display = raw
        except Exception:
            display = display[2:-1]
    # Silently ignore "Failed to launch Signal" – device already streaming
    if "Failed to launch Signal" in display:
        return
    QMessageBox.critical(None, "Error", display)


def main():
    _setup_logging()
    log = logging.getLogger("main")
    log.info("Starting BCI Dashboard")

    sys.excepthook = _exception_hook

    app = QApplication(sys.argv)

    # Import here so logging is already configured
    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()

    log.info("Entering event loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
