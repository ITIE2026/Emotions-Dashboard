"""
NavBar – bottom navigation with Home / Monitoring / Tracking tabs.
Dark themed with icons matching the Mind Tracker BCI app.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt

from utils.config import BG_NAV, ACCENT_GREEN, TEXT_SECONDARY, TEXT_DISABLED


class _TabButton(QWidget):
    """Single tab with icon (Unicode) + label stacked vertically."""
    clicked = Signal()

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self._icon = QLabel(icon)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("font-size: 20px;")

        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("font-size: 10px;")

        layout.addWidget(self._icon)
        layout.addWidget(self._label)
        self._active = False

    def set_active(self, active: bool):
        self._active = active
        color = ACCENT_GREEN if active else TEXT_SECONDARY
        self._icon.setStyleSheet(f"font-size: 20px; color: {color};")
        self._label.setStyleSheet(f"font-size: 10px; color: {color}; font-weight: {'bold' if active else 'normal'};")

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class NavBar(QWidget):
    """Emits *tab_selected(index)* when a tab is clicked."""

    tab_selected = Signal(int)

    # (icon_unicode, label)
    _TABS = [
        ("\U0001F3E0", "Home"),         # 🏠
        ("\U0001F4CA", "Monitoring"),    # 📊
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[_TabButton] = []
        self.setStyleSheet(f"background: {BG_NAV}; border-top: 1px solid #1E1E1E;")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for idx, (icon, label) in enumerate(self._TABS):
            btn = _TabButton(icon, label)
            btn.clicked.connect(lambda i=idx: self._on_click(i))
            layout.addWidget(btn, stretch=1)
            self._buttons.append(btn)

        # Default: first tab active
        self._select(0)

    def _on_click(self, idx: int):
        self._select(idx)
        self.tab_selected.emit(idx)

    def _select(self, idx: int):
        for i, btn in enumerate(self._buttons):
            btn.set_active(i == idx)

    def set_enabled_tabs(self, enabled: bool):
        """Enable / disable all tabs (e.g. disable during calibration)."""
        for btn in self._buttons:
            btn.setEnabled(enabled)
