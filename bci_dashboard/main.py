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

    # ── Global dark stylesheet ────────────────────────────────────────
    from utils.config import (
        BG_PRIMARY, BG_CARD, BG_INPUT, BG_NAV, BORDER_SUBTLE,
        TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN,
    )

    app.setStyleSheet(f"""
        * {{
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }}
        QMainWindow, QWidget {{
            background-color: {BG_PRIMARY};
            color: {TEXT_PRIMARY};
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: {BG_PRIMARY};
            width: 6px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: #444;
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {BG_PRIMARY};
            height: 6px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: #444;
            border-radius: 3px;
            min-width: 20px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QGroupBox {{
            background: {BG_CARD};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 12px;
            padding: 14px 12px 10px 12px;
            margin-top: 8px;
            font-weight: bold;
            color: {TEXT_SECONDARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 4px;
            color: {TEXT_SECONDARY};
        }}
        QMessageBox {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
        }}
        QToolTip {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            padding: 4px;
        }}
        QSplitter::handle {{
            background: {BORDER_SUBTLE};
            width: 2px;
        }}
    """)

    # Import here so logging is already configured
    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()

    log.info("Entering event loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
