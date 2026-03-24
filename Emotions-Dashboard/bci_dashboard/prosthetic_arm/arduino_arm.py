from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from prosthetic_arm.arm_state import STATE_TO_COMMAND

try:
    import serial
    import serial.tools.list_ports

    SERIAL_OK = True
except ImportError:
    serial = None
    SERIAL_OK = False


class ArduinoArmController(QObject):
    status_changed = Signal(str)
    connection_changed = Signal(bool)
    state_sent = Signal(str)

    def __init__(self, parent=None, *, baud_rate: int = 9600):
        super().__init__(parent)
        self._baud_rate = baud_rate
        self._serial = None
        self._last_cmd = None
        self._port = ""

    @property
    def is_connected(self) -> bool:
        return bool(self._serial and getattr(self._serial, "is_open", False))

    @property
    def port(self) -> str:
        return self._port

    def connect_device(self, port: str | None = None) -> bool:
        if not SERIAL_OK:
            self.status_changed.emit("pyserial is not installed. Simulation remains active.")
            self.connection_changed.emit(False)
            return False

        chosen_port = (port or "").strip() or self._auto_detect()
        if not chosen_port:
            self.status_changed.emit("No Arduino detected. Simulation remains active.")
            self.connection_changed.emit(False)
            return False

        try:
            self._serial = serial.Serial(chosen_port, self._baud_rate, timeout=1)
            time.sleep(1.5)
            self._port = chosen_port
            self._last_cmd = None
            self.status_changed.emit(f"Arduino connected on {chosen_port}.")
            self.connection_changed.emit(True)
            return True
        except Exception as exc:  # pragma: no cover - depends on local ports
            self._serial = None
            self._port = ""
            self.status_changed.emit(f"Arduino connection failed: {exc}")
            self.connection_changed.emit(False)
            return False

    def disconnect_device(self) -> None:
        if self._serial and getattr(self._serial, "is_open", False):
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._port = ""
        self._last_cmd = None
        self.status_changed.emit("Arduino disconnected. Simulation active.")
        self.connection_changed.emit(False)

    def send_state(self, state: str) -> bool:
        command = STATE_TO_COMMAND.get(state, STATE_TO_COMMAND["OPEN"])
        self.state_sent.emit(state)
        if not self.is_connected:
            return False
        if command == self._last_cmd:
            return True
        try:
            self._serial.write(command.encode("ascii"))
            self._last_cmd = command
            self.status_changed.emit(f"Arm command sent: {command}")
            return True
        except Exception as exc:  # pragma: no cover - depends on local ports
            self.status_changed.emit(f"Arm send failed: {exc}")
            return False

    def _auto_detect(self) -> str:
        if not SERIAL_OK:
            return ""
        keywords = ("arduino", "ch340", "usb serial", "usb-serial")
        for port in serial.tools.list_ports.comports():
            description = (port.description or "").lower()
            if any(keyword in description for keyword in keywords):
                return port.device
        return ""
