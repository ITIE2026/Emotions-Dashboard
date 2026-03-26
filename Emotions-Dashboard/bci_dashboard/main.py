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
        TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_GREEN, ACCENT_CYAN,
        ACCENT_RED,
    )

    app.setStyleSheet(f"""
        * {{
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }}
        QMainWindow, QWidget {{
            background-color: {BG_PRIMARY};
            color: {TEXT_PRIMARY};
        }}

        /* ── Scroll areas ── */
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: {BG_PRIMARY};
            width: 5px;
            border: none;
            border-radius: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: #3A3E5A;
            border-radius: 2px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #5A5E7A;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {BG_PRIMARY};
            height: 5px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: #3A3E5A;
            border-radius: 2px;
            min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #5A5E7A;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* ── Group boxes ── */
        QGroupBox {{
            background: {BG_CARD};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 14px;
            padding: 16px 14px 12px 14px;
            margin-top: 10px;
            font-weight: bold;
            color: {TEXT_SECONDARY};
            font-size: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 16px;
            padding: 0 6px;
            color: {TEXT_SECONDARY};
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        /* ── Buttons – primary ── */
        QPushButton[class="primary"] {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT_GREEN}, stop:1 {ACCENT_CYAN});
            color: #0A0A14;
            font-weight: bold;
            border: none;
            border-radius: 10px;
            padding: 10px 22px;
            font-size: 14px;
        }}
        QPushButton[class="primary"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_GREEN});
        }}
        QPushButton[class="primary"]:disabled {{
            background: #2A2E48;
            color: #555;
        }}

        /* ── Buttons – ghost/secondary ── */
        QPushButton[class="secondary"] {{
            background: transparent;
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 7px 16px;
            font-size: 13px;
        }}
        QPushButton[class="secondary"]:hover {{
            background: #242842;
            border-color: #4A4E6A;
        }}

        /* ── Combo boxes ── */
        QComboBox {{
            background: {BG_INPUT};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 7px 12px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
            selection-background-color: #2A2E48;
        }}
        QComboBox:focus {{
            border-color: {ACCENT_GREEN};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 6px;
            selection-background-color: #2A2E48;
            outline: none;
        }}

        /* ── Line edits / inputs ── */
        QLineEdit {{
            background: {BG_INPUT};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 7px 12px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {ACCENT_GREEN};
        }}

        /* ── List widgets ── */
        QListWidget {{
            background: {BG_INPUT};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 10px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 10px 14px;
            border-radius: 6px;
        }}
        QListWidget::item:selected {{
            background: #2A2E48;
            color: {TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background: #1E2238;
        }}

        /* ── Tab widget ── */
        QTabWidget::pane {{
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            background: {BG_CARD};
        }}
        QTabBar::tab {{
            background: transparent;
            color: {TEXT_SECONDARY};
            padding: 8px 18px;
            font-size: 12px;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:selected {{
            color: {ACCENT_GREEN};
            border-bottom: 2px solid {ACCENT_GREEN};
        }}
        QTabBar::tab:hover {{
            color: {TEXT_PRIMARY};
        }}

        /* ── Check boxes ── */
        QCheckBox {{
            color: {TEXT_PRIMARY};
            font-size: 13px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 4px;
            background: {BG_INPUT};
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT_GREEN};
            border-color: {ACCENT_GREEN};
            image: none;
        }}
        QCheckBox::indicator:hover {{
            border-color: {ACCENT_GREEN};
        }}

        /* ── Progress bars (global thin style) ── */
        QProgressBar {{
            background: #1E2238;
            border: none;
            border-radius: 3px;
            height: 5px;
        }}
        QProgressBar::chunk {{
            background: {ACCENT_GREEN};
            border-radius: 3px;
        }}

        /* ── Dialogs / message boxes ── */
        QMessageBox {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
        }}
        QDialog {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
        }}

        /* ── Tooltips ── */
        QToolTip {{
            background: #1E2238;
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            padding: 5px 8px;
            border-radius: 6px;
            font-size: 12px;
        }}

        /* ── Splitters ── */
        QSplitter::handle {{
            background: {BORDER_SUBTLE};
            width: 1px;
        }}
        QSplitter::handle:hover {{
            background: #4A4E6A;
        }}

        /* ── Spin boxes ── */
        QSpinBox, QDoubleSpinBox {{
            background: {BG_INPUT};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 6px 10px;
            color: {TEXT_PRIMARY};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {ACCENT_GREEN};
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
