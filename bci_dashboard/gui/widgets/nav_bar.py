"""
NavBar – bottom navigation with Home / Monitoring / Training / Tracking tabs.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Signal


class NavBar(QWidget):
    """Emits *tab_selected(index)* when a tab is clicked."""

    tab_selected = Signal(int)

    TAB_LABELS = ["Home", "Monitoring", "Training", "Tracking"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        for idx, label in enumerate(self.TAB_LABELS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(self._style(False))
            btn.clicked.connect(lambda checked, i=idx: self._on_click(i))
            layout.addWidget(btn)
            self._buttons.append(btn)

        # Default: first tab active
        self._select(0)

    def _on_click(self, idx: int):
        self._select(idx)
        self.tab_selected.emit(idx)

    def _select(self, idx: int):
        for i, btn in enumerate(self._buttons):
            active = i == idx
            btn.setChecked(active)
            btn.setStyleSheet(self._style(active))

    def set_enabled_tabs(self, enabled: bool):
        """Enable / disable all tabs (e.g. disable during calibration)."""
        for btn in self._buttons:
            btn.setEnabled(enabled)

    @staticmethod
    def _style(active: bool) -> str:
        if active:
            return (
                "QPushButton { font-weight: bold; border: none; "
                "border-top: 2px solid #69F0AE; padding: 6px; }"
            )
        return "QPushButton { border: none; padding: 6px; color: #888; }"
