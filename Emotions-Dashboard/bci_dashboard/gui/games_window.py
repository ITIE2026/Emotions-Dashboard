"""
GamesWindow – fully standalone QMainWindow for the Games section.

Launches as an independent top-level window with its own title bar,
completely separate from the main BCI Dashboard stack. Receives live
EEG data forwarded from MainWindow but otherwise runs independently.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

from gui.games_screen import GamesScreen


class GamesWindow(QMainWindow):
    """A separate top-level window that hosts the Games section."""

    def __init__(self):
        # No parent → truly independent OS-level window
        super().__init__(None, Qt.Window)
        self.setWindowTitle("\U0001F3C6  Games — BCI Neurofeedback")
        self.setMinimumSize(1100, 720)
        self.resize(1400, 900)

        # Dark background on the window frame itself
        self.setStyleSheet("QMainWindow { background: #000000; }")

        self._screen = GamesScreen(self)
        self.setCentralWidget(self._screen)

    # ── Window lifecycle → drive GamesScreen view_active ────────────

    def showEvent(self, event):
        self._screen.set_view_active(True)
        super().showEvent(event)

    def hideEvent(self, event):
        self._screen.set_view_active(False)
        super().hideEvent(event)

    def closeEvent(self, event):
        # Hide instead of destroy so the window can be re-opened
        self._screen.stop_active_flow()
        self.hide()
        event.ignore()

    # ── Public API forwarded to inner GamesScreen ────────────────────

    def on_productivity(self, data: dict):
        self._screen.on_productivity(data)

    def on_physio_states(self, data: dict):
        self._screen.on_physio_states(data)

    def on_mems(self, mems_timed_data) -> None:
        self._screen.on_mems(mems_timed_data)

    def update_signal_snapshot(
        self,
        band_powers: dict,
        peak_freqs: dict,
        psd_timestamp: float | None = None,
    ):
        self._screen.update_signal_snapshot(band_powers, peak_freqs, psd_timestamp)

    def set_streaming_active(self, active: bool):
        self._screen.set_streaming_active(active)

    def stop_active_flow(self):
        self._screen.stop_active_flow()

    def shutdown(self):
        self._screen.shutdown()
        self.destroy()
