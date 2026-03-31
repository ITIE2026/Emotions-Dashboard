"""Screen routing and navigation mixin for MainWindow."""
from __future__ import annotations

from PySide6.QtCore import QTimer

PAGE_CONNECTION = 0
PAGE_CALIBRATION = 1
PAGE_DASHBOARD = 2
PAGE_MEMS = 3
PAGE_TRAINING = 4
PAGE_SESSIONS = 5
PAGE_PHASEON = 6
PAGE_YOUTUBE = 7


class ScreenRouterMixin:
    """Mixin that manages page switching, nav-bar sync, and live-view activity."""

    def _show_dashboard(self, section: str = ""):
        self._stack.setCurrentIndex(PAGE_DASHBOARD)
        section_map = {
            "Rhythms Diagram": "rhythms_diagram",
        }
        section_id = section_map.get(section)
        if section_id:
            QTimer.singleShot(0, lambda sid=section_id: self._dash_screen.show_section(sid))

    def _show_mems(self, section: str = ""):
        self._stack.setCurrentIndex(PAGE_MEMS)
        section_map = {
            "Rhythms Diagram": "rhythms_diagram",
            "Accelerometer": "accelerometer",
            "Accelerometer Tab": "accelerometer",
            "Gyroscope": "gyroscope",
            "Gyroscope Tab": "gyroscope",
        }
        section_id = section_map.get(section)
        if section_id:
            QTimer.singleShot(0, lambda sid=section_id: self._mems_screen.show_section(sid))

    def _show_phaseon(self):
        self._stack.setCurrentIndex(PAGE_PHASEON)

    def _on_nav_tab_selected(self, tab_idx: int):
        """Map NavBar tab index (0-4) to stack page."""
        mapping = {
            0: PAGE_CONNECTION,
            1: PAGE_DASHBOARD,
            2: PAGE_TRAINING,
            3: PAGE_SESSIONS,
            4: PAGE_YOUTUBE,
        }
        page = mapping.get(tab_idx, PAGE_CONNECTION)
        if page == PAGE_TRAINING and self._stack.currentIndex() == PAGE_TRAINING:
            return  # already there
        self._stack.setCurrentIndex(page)

    def _sync_nav_bar(self, page_index: int):
        """Keep NavBar indicator in sync when page changes programmatically."""
        reverse_map = {
            PAGE_CONNECTION: 0,
            PAGE_CALIBRATION: 0,   # calibration belongs to Home flow
            PAGE_DASHBOARD: 1,
            PAGE_MEMS: 1,          # MEMS is part of Monitoring
            PAGE_TRAINING: 2,
            PAGE_SESSIONS: 3,
            PAGE_PHASEON: 2,       # PhaseON is a training mode
            PAGE_YOUTUBE: 4,       # Media tab
        }
        tab = reverse_map.get(page_index, 0)
        self._nav_bar.set_active_tab(tab)

    def _go_home(self):
        current_index = self._stack.currentIndex()
        if current_index == PAGE_DASHBOARD:
            return
        if current_index == PAGE_TRAINING:
            self._training_screen.stop_active_flow()
            self._stack.setCurrentIndex(PAGE_DASHBOARD)
            return
        if current_index == PAGE_CALIBRATION:
            self._calibration_return_page = PAGE_DASHBOARD
            self._cancel_calibration()
            return
        self._stack.setCurrentIndex(PAGE_DASHBOARD)

    def _update_live_view_activity(self, index: int):
        dashboard_active = index == PAGE_DASHBOARD
        mems_active = index == PAGE_MEMS
        training_active = index == PAGE_TRAINING
        self._dash_screen.set_view_active(dashboard_active)
        if hasattr(self._mems_screen, "set_view_active"):
            self._mems_screen.set_view_active(mems_active)
        if hasattr(self._training_screen, "set_view_active"):
            self._training_screen.set_view_active(training_active)
