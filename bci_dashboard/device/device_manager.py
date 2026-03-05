"""
DeviceManager – scan, connect, subscribe to device-level callbacks,
and expose Qt signals for the UI layer.
"""
import sys
from PySide6.QtCore import QObject, Signal

from utils.config import DEVICE_SEARCH_TIMEOUT_SEC, BIPOLAR_CHANNELS, CAPSULE_SDK_DIR

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from DeviceType import DeviceType    # noqa: E402
from Device import Device            # noqa: E402


class DeviceManager(QObject):
    """Wraps Capsule Device discovery + connection with Qt signals."""

    # ── Signals ───────────────────────────────────────────────────────
    devices_found = Signal(list)          # [(name, serial, type), ...]
    connection_changed = Signal(int)      # Device_Connection_Status value
    resistance_updated = Signal(dict)     # {channel_name: value_ohms}
    battery_updated = Signal(int)         # 0-100
    mode_changed = Signal(int)            # Device_Mode value
    eeg_received = Signal(object)         # EEGTimedData
    psd_received = Signal(object)         # PSDData
    artifacts_received = Signal(object)   # EEGArtifacts
    error_occurred = Signal(str)

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._locator = bridge.locator
        self._lib = bridge.lib
        self._device = None
        self._device_serial = None

    # ── Scanning ──────────────────────────────────────────────────────
    def scan_devices(self, timeout_sec: int = DEVICE_SEARCH_TIMEOUT_SEC):
        """Start BLE scan. Results arrive via *devices_found* signal."""
        self._locator.set_on_devices_list(self._on_devices_list)
        self._locator.request_devices(DeviceType.Band, timeout_sec)

    def _on_devices_list(self, locator, device_info_list, fail_reason):
        results = []
        for i in range(len(device_info_list)):
            info = device_info_list[i]
            results.append((info.get_name(), info.get_serial(), info.get_type()))
        self.devices_found.emit(results)

    # ── Connection ────────────────────────────────────────────────────
    def connect_device(self, serial: str, bipolar: bool = BIPOLAR_CHANNELS):
        """Create and connect to a device identified by *serial*."""
        self._device_serial = serial
        self._device = Device(self._locator, serial, self._lib)

        # Register callbacks BEFORE start
        self._device.set_on_connection_status_changed(self._on_conn)
        self._device.set_on_resistances(self._on_resist)
        self._device.set_on_battery_charge_changed(self._on_battery)
        self._device.set_on_mode_changed(self._on_mode)
        self._device.set_on_eeg(self._on_eeg)
        self._device.set_on_psd(self._on_psd)
        self._device.set_on_eeg_artifacts(self._on_artifacts)
        self._device.set_on_error(self._on_error)

        self._device.connect(bipolar)

    def start_streaming(self):
        if self._device:
            try:
                self._device.start()
            except Exception as exc:
                msg = str(exc)
                if isinstance(exc, bytes):
                    msg = exc.decode('utf-8', errors='replace')
                elif hasattr(exc, 'message') and isinstance(exc.message, bytes):
                    msg = exc.message.decode('utf-8', errors='replace')
                self.error_occurred.emit(msg)

    def stop_streaming(self):
        if self._device:
            try:
                self._device.stop()
            except Exception:
                pass

    def disconnect(self):
        if self._device:
            try:
                self._device.stop()
            except Exception:
                pass
            try:
                self._device.disconnect()
            except Exception:
                pass

    def is_connected(self) -> bool:
        if self._device:
            try:
                return self._device.is_connected()
            except Exception:
                return False
        return False

    def get_battery(self) -> int:
        if self._device:
            try:
                return self._device.get_battery_charge()
            except Exception:
                return -1
        return -1

    @property
    def device(self):
        return self._device

    @property
    def device_serial(self):
        return self._device_serial

    # ── Capsule callbacks → Qt signals ────────────────────────────────
    def _on_conn(self, device, status):
        try:
            v = status
            if isinstance(v, bytes):
                import struct
                try:
                    v = struct.unpack('<i', v[:4])[0]
                except Exception:
                    v = 0
            self.connection_changed.emit(int(v))
        except Exception as exc:
            self.error_occurred.emit(f"Connection status error: {exc}")

    def _on_resist(self, device, resistances):
        try:
            data = {}
            for i in range(len(resistances)):
                name = resistances.get_channel_name(i)
                value = resistances.get_value(i)
                data[name] = value
            self.resistance_updated.emit(data)
        except Exception as exc:
            self.error_occurred.emit(f"Resistance error: {exc}")

    def _on_battery(self, device, charge):
        try:
            v = charge
            if isinstance(v, bytes):
                import struct
                try:
                    v = struct.unpack('<i', v[:4])[0]
                except Exception:
                    v = -1
            self.battery_updated.emit(int(v))
        except Exception:
            pass

    def _on_mode(self, device, mode):
        try:
            v = mode
            if isinstance(v, bytes):
                import struct
                try:
                    v = struct.unpack('<i', v[:4])[0]
                except Exception:
                    v = 0
            self.mode_changed.emit(int(v))
        except Exception:
            pass

    def _on_eeg(self, device, eeg_timed_data):
        try:
            self.eeg_received.emit(eeg_timed_data)
        except Exception:
            pass

    def _on_psd(self, device, psd_data):
        try:
            self.psd_received.emit(psd_data)
        except Exception:
            pass

    def _on_artifacts(self, device, artifacts):
        try:
            self.artifacts_received.emit(artifacts)
        except Exception:
            pass

    def _on_error(self, device, error_msg):
        # error_msg arrives as str(bytes) from ctypes — clean it up
        msg = error_msg
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', errors='replace')
        elif isinstance(msg, str) and msg.startswith("b'"):
            try:
                msg = msg[2:-1]
            except Exception:
                pass
        self.error_occurred.emit(msg)
