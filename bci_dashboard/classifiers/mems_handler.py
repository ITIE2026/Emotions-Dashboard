"""
MemsHandler – wraps the Capsule MEMS stream.

Emits raw MEMS timed-data updates for accelerometer and gyroscope charts.
"""
import sys

from PySide6.QtCore import QObject, Signal

from utils.config import CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from MEMS import MEMS  # noqa: E402


class MemsHandler(QObject):
    """Create **after** Device, **before** device.start()."""

    mems_updated = Signal(object)

    def __init__(self, device, lib, parent=None):
        super().__init__(parent)
        self._mems = MEMS(device, lib)
        self._mems.set_on_update(self._on_update)

    def _on_update(self, mems_obj, mems_timed_data):
        try:
            self.mems_updated.emit(mems_timed_data)
        except Exception:
            pass
