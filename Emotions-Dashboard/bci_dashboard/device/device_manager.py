"""
DeviceManager – scan, connect, subscribe to device-level callbacks,
and expose Qt signals for the UI layer.
"""
import logging
import os
import sys
from PySide6.QtCore import QObject, QTimer, Signal

from utils.config import DEVICE_SEARCH_TIMEOUT_SEC, BIPOLAR_CHANNELS, CAPSULE_SDK_DIR
from utils.sdk_scalars import coerce_float, coerce_int, coerce_percent

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from DeviceType import DeviceType    # noqa: E402
from Device import Device            # noqa: E402


log = logging.getLogger(__name__)


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
    scan_error = Signal(str)             # emitted when BLE scan itself fails (e.g. Bluetooth disabled)

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._locator = bridge.locator
        self._locator.set_on_devices_list(self._on_devices_list)
        self._lib = bridge.lib
        self._device = None
        self._device_serial = None
        self._active_bipolar_mode = bool(BIPOLAR_CHANNELS)
        self._eeg_sample_rate = None
        self._eeg_channel_names = []
        self._scan_active = False
        self._requested_device_type = int(DeviceType.Band)
        self._scan_timeout = QTimer(self)
        self._scan_timeout.setSingleShot(True)
        self._scan_timeout.timeout.connect(self._on_scan_timeout)

    # ── Scanning ──────────────────────────────────────────────────────
    def scan_devices(self, device_type: int = DeviceType.Band, timeout_sec: int = DEVICE_SEARCH_TIMEOUT_SEC):
        """Start BLE scan using the shared app locator."""
        self._scan_active = False
        self._scan_timeout.stop()
        self._requested_device_type = int(device_type)
        self._scan_active = True
        self._scan_timeout.start(max(int(timeout_sec) + 3, 5) * 1000)
        try:
            scan_type = int(DeviceType.Any) if int(device_type) == int(DeviceType.Band) else int(device_type)
            self._locator.request_devices(scan_type, int(timeout_sec))
        except Exception as exc:
            self._scan_timeout.stop()
            self._scan_active = False
            self.scan_error.emit(_safe_str(exc) or "Bluetooth scan failed to start. Please try again.")

    def _on_devices_list(self, locator, device_info_list, fail_reason):
        if not self._scan_active:
            return

        results = []
        for i in range(len(device_info_list)):
            try:
                info = device_info_list[i]
                entry = (info.get_name(), info.get_serial(), int(info.get_type()))
            except OSError as exc:
                log.warning("Skipping invalid Bluetooth scan entry at index %s: %s", i, exc)
                continue
            except Exception as exc:
                log.warning("Failed to normalize Bluetooth scan entry at index %s: %s", i, exc)
                continue
            results.append(entry)

        requested_type = int(self._requested_device_type)
        if requested_type != int(DeviceType.Any):
            results = [item for item in results if int(item[2]) == requested_type]

        self._scan_active = False
        self._scan_timeout.stop()
        self.devices_found.emit(results)
        try:
            reason_val = coerce_int(fail_reason, default=0)
            if reason_val == 1:  # FailReason.BluetoothDisabled
                self.scan_error.emit(
                    "Bluetooth is disabled – please enable Bluetooth and try again"
                )
            elif reason_val == 2 and not results:  # FailReason.Unknown, no devices
                self.scan_error.emit("Device scan failed (unknown error)")
        except Exception:
            pass

    def _on_scan_timeout(self):
        if not self._scan_active:
            return
        self._scan_active = False
        self.scan_error.emit("Bluetooth scan timed out. Please try again.")


    # ── Connection ────────────────────────────────────────────────────
    def connect_device(self, serial: str, bipolar: bool = BIPOLAR_CHANNELS):
        """Create and connect to a device identified by *serial*."""
        # Release any existing Device before creating a new one.  Letting Python
        # GC do this non-deterministically while the DLL may still hold a
        # reference to the old C++ object causes use-after-free crashes.
        if self._device is not None:
            try:
                self._device.stop()
            except Exception:
                pass
            try:
                self._device.disconnect()
            except Exception:
                pass
            self._device = None
        self._device_serial = serial
        self._active_bipolar_mode = bool(bipolar)
        self._device = Device(self._locator, serial, self._lib)
        self._eeg_sample_rate = None
        self._eeg_channel_names = []

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
        self._refresh_eeg_metadata()

    def start_streaming(self) -> bool:
        if not self._device:
            return False
        try:
            self._refresh_eeg_metadata()
            self._device.start()
            return True
        except Exception as exc:
            msg = str(exc)
            if isinstance(exc, bytes):
                msg = exc.decode('utf-8', errors='replace')
            elif hasattr(exc, 'message') and isinstance(exc.message, bytes):
                msg = exc.message.decode('utf-8', errors='replace')
            self.error_occurred.emit(msg)
            return False

    def stop_streaming(self):
        if self._device:
            try:
                self._device.stop()
            except Exception:
                pass

    def disconnect(self):
        self._scan_active = False
        self._scan_timeout.stop()
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
                return coerce_percent(self._device.get_battery_charge(), default=-1)
            except Exception:
                return -1
        return -1

    @property
    def device(self):
        return self._device

    @property
    def device_serial(self):
        return self._device_serial

    @property
    def eeg_sample_rate(self) -> float | None:
        return self._eeg_sample_rate

    @property
    def eeg_channel_names(self) -> list[str]:
        return list(self._eeg_channel_names)

    @property
    def active_bipolar_mode(self) -> bool:
        return bool(self._active_bipolar_mode)

    @property
    def display_channel_names(self) -> list[str]:
        if self._eeg_channel_names:
            if self._active_bipolar_mode:
                preferred = {"O1-T3": 0, "O2-T4": 1}
            else:
                preferred = {"O1": 0, "T3": 1, "T4": 2, "O2": 3}
            return sorted(
                self._eeg_channel_names,
                key=lambda name: preferred.get(name, len(preferred) + self._eeg_channel_names.index(name)),
            )
        if self._active_bipolar_mode:
            return ["O1-T3", "O2-T4"]
        return ["O1", "T3", "T4", "O2"]

    # ── Capsule callbacks → Qt signals ────────────────────────────────
    def _on_conn(self, device, status):
        try:
            value = coerce_int(status, default=0)
            self.connection_changed.emit(int(value))
        except Exception as exc:
            self.error_occurred.emit(f"Connection status error: {exc}")

    def _on_resist(self, device, resistances):
        try:
            data = {}
            for i in range(len(resistances)):
                raw_name = resistances.get_channel_name(i)
                value = coerce_float(resistances.get_value(i), default=float("inf"))
                canonical_name = _normalize_resistance_channel_name(raw_name)
                if canonical_name:
                    data[canonical_name] = value
                if isinstance(raw_name, bytes):
                    raw_name = raw_name.decode("utf-8", errors="replace")
                if isinstance(raw_name, str):
                    raw_name = raw_name.strip()
                    if raw_name and raw_name not in data:
                        data[raw_name] = value
            self.resistance_updated.emit(data)
        except Exception as exc:
            self.error_occurred.emit(f"Resistance error: {exc}")

    def _on_battery(self, device, charge):
        try:
            value = coerce_percent(charge, default=None)
            if value is None:
                return
            self.battery_updated.emit(int(value))
        except Exception:
            pass

    def _on_mode(self, device, mode):
        try:
            value = coerce_int(mode, default=0)
            self.mode_changed.emit(int(value))
        except Exception:
            pass

    def _on_eeg(self, device, eeg_timed_data):
        try:
            if self._eeg_sample_rate is None or not self._eeg_channel_names:
                self._refresh_eeg_metadata()
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

    def _refresh_eeg_metadata(self):
        if not self._device:
            return
        try:
            sample_rate = coerce_float(self._device.get_eeg_sample_rate(), default=None)
            if sample_rate is not None and sample_rate > 0:
                self._eeg_sample_rate = float(sample_rate)
        except Exception:
            pass

        try:
            names = []
            channel_names = self._device.get_channel_names()
            for index in range(len(channel_names)):
                names.append(_normalize_eeg_channel_name(channel_names.get_name_by_index(index)))
            self._eeg_channel_names = [name for name in names if name]
        except Exception:
            pass


def _normalize_resistance_channel_name(name) -> str:
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")
    text = str(name or "").strip().upper().replace(" ", "")
    alias_map = {
        "01": "O1",
        "O1": "O1",
        "02": "O2",
        "O2": "O2",
        "T3": "T3",
        "T4": "T4",
    }
    if text in alias_map:
        return alias_map[text]
    if text.startswith("0") and len(text) == 2 and text[1].isdigit():
        candidate = f"O{text[1]}"
        if candidate in {"O1", "O2"}:
            return candidate
    return text


def _normalize_eeg_channel_name(name) -> str:
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")
    text = str(name or "").strip().upper().replace(" ", "")
    alias_map = {
        "O1": "O1",
        "O1-T3": "O1-T3",
        "O1T3": "O1-T3",
        "01-T3": "O1-T3",
        "T3": "T3",
        "T4": "T4",
        "O2": "O2",
        "O2-T4": "O2-T4",
        "O2T4": "O2-T4",
        "02-T4": "O2-T4",
    }
    if text in alias_map:
        return alias_map[text]
    return str(name or "").strip()


def _safe_str(value) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, Exception) and hasattr(value, "message"):
        return _safe_str(value.message)
    return str(value)
