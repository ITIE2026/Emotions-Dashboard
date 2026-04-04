"""
NavBar – premium bottom navigation with animated sliding indicator.
Dark themed with icons matching the Mind Tracker BCI app.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QLinearGradient

from utils.config import BG_NAV, ACCENT_GREEN, ACCENT_CYAN, TEXT_SECONDARY


class _SlidingIndicator(QWidget):
    """A thin gradient bar that slides horizontally to the active tab."""

    def __init__(self, tab_count: int, parent=None):
        super().__init__(parent)
        self._tab_count = tab_count
        self._x_frac = 0.0
        self.setFixedHeight(3)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def get_pos(self) -> float:
        return self._x_frac

    def set_pos(self, v: float):
        self._x_frac = v
        self.update()

    pos_frac = Property(float, get_pos, set_pos)

    def paintEvent(self, event):
        if self._tab_count == 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        tab_w = self.width() / self._tab_count
        bar_w = max(40, int(tab_w * 0.55))
        tab_center = self._x_frac * (self._tab_count - 1) * tab_w + tab_w / 2
        x = int(tab_center - bar_w / 2)
        grad = QLinearGradient(x, 0, x + bar_w, 0)
        grad.setColorAt(0.0, QColor(ACCENT_GREEN))
        grad.setColorAt(1.0, QColor(ACCENT_CYAN))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(x, 0, bar_w, 3, 1.5, 1.5)
        painter.end()


class _TabButton(QWidget):
    """Single tab with icon + label stacked vertically."""
    clicked = Signal()

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 7, 4, 7)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignCenter)

        self._icon = QLabel(icon)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("font-size: 18px; background: transparent;")

        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("font-size: 10px; background: transparent; letter-spacing: 0.3px;")

        layout.addWidget(self._icon)
        layout.addWidget(self._label)
        self._active = False

    def set_active(self, active: bool):
        self._active = active
        if active:
            self._icon.setStyleSheet(f"font-size: 18px; color: {ACCENT_GREEN}; background: transparent;")
            self._label.setStyleSheet(
                f"font-size: 10px; color: {ACCENT_GREEN}; font-weight: bold; "
                f"background: transparent; letter-spacing: 0.5px;"
            )
        else:
            self._icon.setStyleSheet(f"font-size: 18px; color: {TEXT_SECONDARY}; background: transparent;")
            self._label.setStyleSheet(
                f"font-size: 10px; color: {TEXT_SECONDARY}; font-weight: normal; "
                f"background: transparent; letter-spacing: 0.3px;"
            )

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class NavBar(QWidget):
    """Emits *tab_selected(index)* when a tab is clicked."""

    tab_selected = Signal(int)
    gyro_mouse_toggled = Signal()  # emitted when gyro mouse button clicked

    # (icon_unicode, label) — 5 tabs covering all main sections
    _TABS = [
        ("\U0001F3E0", "Home"),         # 🏠
        ("\U0001F4CA", "Monitoring"),   # 📊
        ("\U0001F3AE", "Training"),     # 🎮
        ("\U0001F3C6", "Games"),        # 🏆
        ("\u2694\uFE0F", "Multiplayer"),# ⚔️
        ("\U0001F4C1", "Sessions"),     # 📁
        ("\U0001F3AC", "Media"),        # 🎬
        ("\U0001F4F8", "Instagram"),   # 📸
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[_TabButton] = []
        self._anim: QPropertyAnimation | None = None
        self.setStyleSheet(
            f"NavBar {{ background: {BG_NAV}; border-top: 1px solid #1A1E30; }}"
        )
        self.setFixedHeight(62)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sliding gradient indicator at top of nav
        self._indicator = _SlidingIndicator(len(self._TABS))
        outer.addWidget(self._indicator)

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.setSpacing(0)

        for idx, (icon, label) in enumerate(self._TABS):
            btn = _TabButton(icon, label)
            btn.clicked.connect(lambda i=idx: self._on_click(i))
            tabs_row.addWidget(btn, stretch=1)
            self._buttons.append(btn)

        # Gyro mouse toggle button (right side of nav bar)
        self._gyro_btn = _TabButton("\U0001F5B1", "Gyro")
        self._gyro_btn.clicked.connect(self._on_gyro_click)
        self._gyro_mouse_active = False
        tabs_row.addWidget(self._gyro_btn, stretch=1)

        outer.addLayout(tabs_row)
        self._select(0, animate=False)

    def _on_click(self, idx: int):
        self._select(idx, animate=True)
        self.tab_selected.emit(idx)

    def _select(self, idx: int, animate: bool = True):
        for i, btn in enumerate(self._buttons):
            btn.set_active(i == idx)

        target = idx / max(1, len(self._TABS) - 1)
        if animate:
            if self._anim:
                self._anim.stop()
            self._anim = QPropertyAnimation(self._indicator, b"pos_frac", self._indicator)
            self._anim.setStartValue(self._indicator.get_pos())
            self._anim.setEndValue(target)
            self._anim.setDuration(220)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start()
        else:
            self._indicator.set_pos(target)

    def set_active_tab(self, idx: int):
        """Programmatically switch tab (called from MainWindow when page changes)."""
        self._select(idx, animate=True)

    def set_enabled_tabs(self, enabled: bool):
        """Enable / disable all tabs (e.g. disable during calibration)."""
        for btn in self._buttons:
            btn.setEnabled(enabled)

    def _on_gyro_click(self):
        self.gyro_mouse_toggled.emit()

    def set_gyro_mouse_active(self, active: bool):
        """Update the gyro button appearance based on controller state."""
        self._gyro_mouse_active = active
        if active:
            self._gyro_btn._icon.setStyleSheet(
                f"font-size: 18px; color: {ACCENT_GREEN}; background: transparent;"
            )
            self._gyro_btn._label.setStyleSheet(
                f"font-size: 10px; color: {ACCENT_GREEN}; font-weight: bold; "
                f"background: transparent; letter-spacing: 0.5px;"
            )
            self._gyro_btn._label.setText("Gyro ON")
        else:
            self._gyro_btn._icon.setStyleSheet(
                f"font-size: 18px; color: {TEXT_SECONDARY}; background: transparent;"
            )
            self._gyro_btn._label.setStyleSheet(
                f"font-size: 10px; color: {TEXT_SECONDARY}; font-weight: normal; "
                f"background: transparent; letter-spacing: 0.3px;"
            )
            self._gyro_btn._label.setText("Gyro")
