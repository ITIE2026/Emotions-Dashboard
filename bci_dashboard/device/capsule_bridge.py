"""
CapsuleBridge – singleton loader for the CapsuleClient DLL.

Owns the Capsule + DeviceLocator lifecycle and drives the
single-threaded callback pump via a QTimer.
"""
import sys
import os
from PySide6.QtCore import QObject, QTimer, Signal

from utils.config import (
    CAPSULE_DLL_PATH,
    CAPSULE_SDK_DIR,
    LOG_DIR,
    CAPSULE_UPDATE_INTERVAL_MS,
)

# Make capsule_sdk importable by the SDK wrappers (they use bare imports)
if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Capsule import Capsule                   # noqa: E402
from DeviceLocator import DeviceLocator       # noqa: E402
from DeviceType import DeviceType             # noqa: E402


class CapsuleBridge(QObject):
    """Manages DLL, DeviceLocator and the update-pump timer."""

    error_occurred = Signal(str)

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        if hasattr(self, "_initialised"):
            return
        super().__init__(parent)
        self._initialised = True

        # ── Load DLL ──────────────────────────────────────────────────
        if not os.path.isfile(CAPSULE_DLL_PATH):
            raise FileNotFoundError(
                f"CapsuleClient.dll not found at {CAPSULE_DLL_PATH}"
            )

        self._capsule = Capsule(CAPSULE_DLL_PATH)
        self._lib = self._capsule.get_lib()

        # ── Create DeviceLocator ──────────────────────────────────────
        self._locator = DeviceLocator(LOG_DIR, self._lib)

        # ── Pump timer ────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(CAPSULE_UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._pump)
        self._timer.start()

    # ── Public API ────────────────────────────────────────────────────
    @property
    def lib(self):
        return self._lib

    @property
    def locator(self) -> DeviceLocator:
        return self._locator

    def version(self) -> str:
        return self._capsule.get_version()

    def shutdown(self):
        """Stop the pump and release resources."""
        self._timer.stop()

    # ── Private ───────────────────────────────────────────────────────
    def _pump(self):
        """Called every CAPSULE_UPDATE_INTERVAL_MS to drive callbacks."""
        try:
            self._locator.update()
        except Exception as exc:
            self.error_occurred.emit(str(exc))
