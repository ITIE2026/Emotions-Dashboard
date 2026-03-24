"""
Isolated Bluetooth scan helper.

Runs Capsule BLE discovery inside a short-lived Qt event loop so the main app
stays alive even if the native scan path fails.
"""
from __future__ import annotations

import json
import logging
import os
import sys

from PySide6.QtCore import QCoreApplication, QObject, QTimer


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from utils.config import (  # noqa: E402
    CAPSULE_DLL_PATH,
    CAPSULE_SDK_DIR,
    CAPSULE_UPDATE_INTERVAL_MS,
    LOG_DIR,
)

if CAPSULE_SDK_DIR not in sys.path:
    sys.path.insert(0, CAPSULE_SDK_DIR)

from Capsule import Capsule  # noqa: E402
from DeviceLocator import DeviceLocator  # noqa: E402


HELPER_LOG_DIR = os.path.join(LOG_DIR, "scan_helper_runtime")
SCAN_LOG_PATH = os.path.join(HELPER_LOG_DIR, "scan_helper.log")


def _setup_logging() -> logging.Logger:
    os.makedirs(HELPER_LOG_DIR, exist_ok=True)
    logger = logging.getLogger("scan_helper")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    handler = logging.FileHandler(SCAN_LOG_PATH, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger


class ScanSession(QObject):
    def __init__(self, device_type: int, timeout_sec: int, logger: logging.Logger):
        super().__init__()
        self._device_type = int(device_type)
        self._timeout_sec = max(int(timeout_sec), 1)
        self._log = logger
        self._finished = False
        self._pump_logged = False

        self._capsule = None
        self._locator = None
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(max(int(CAPSULE_UPDATE_INTERVAL_MS), 100))
        self._pump_timer.timeout.connect(self._pump)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval((self._timeout_sec + 3) * 1000)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def start(self):
        self._log.info(
            "Starting Bluetooth scan helper: device_type=%s timeout=%ss",
            self._device_type,
            self._timeout_sec,
        )

        if not os.path.isfile(CAPSULE_DLL_PATH):
            self._finish_error(f"CapsuleClient.dll not found at {CAPSULE_DLL_PATH}")
            return

        try:
            self._capsule = Capsule(CAPSULE_DLL_PATH)
            lib = self._capsule.get_lib()
            self._locator = DeviceLocator(HELPER_LOG_DIR, lib)
            self._locator.set_on_devices_list(self._on_devices_list)
        except Exception as exc:
            self._log.exception("Failed to initialize scan helper")
            self._finish_error(str(exc))
            return

        self._timeout_timer.start()
        QTimer.singleShot(0, self._request_scan)

    def _request_scan(self):
        if self._finished or self._locator is None:
            return
        try:
            self._log.info("Requesting Bluetooth scan from Capsule locator")
            self._locator.request_devices(self._device_type, self._timeout_sec)
            self._log.info("Bluetooth scan request returned control to helper")
            QTimer.singleShot(250, self._start_pump)
        except Exception as exc:
            self._log.exception("Bluetooth scan request failed")
            self._finish_error(str(exc))

    def _start_pump(self):
        if self._finished or self._locator is None:
            return
        self._log.info(
            "Starting Bluetooth scan pump with %sms interval",
            self._pump_timer.interval(),
        )
        if not self._pump_timer.isActive():
            self._pump_timer.start()

    def _pump(self):
        if self._finished or self._locator is None:
            return
        if not self._pump_logged:
            self._pump_logged = True
            self._log.info("Bluetooth scan helper received first pump tick")
        try:
            self._locator.update()
        except BaseException as exc:  # pragma: no cover - native/runtime path
            self._log.exception("Bluetooth scan pump failed")
            self._finish_error(str(exc))

    def _on_timeout(self):
        self._log.warning("Bluetooth scan helper timed out")
        self._finish_error("Bluetooth scan timed out. Please try again.")

    def _on_devices_list(self, _locator, device_info_list, fail_reason):
        if self._finished:
            return

        try:
            devices = [
                (
                    info.get_name(),
                    info.get_serial(),
                    int(info.get_type()),
                )
                for info in device_info_list
            ]
        except Exception:
            self._log.exception("Failed to normalize scanned device list")
            devices = []

        try:
            reason = int(getattr(fail_reason, "value", fail_reason))
        except Exception:
            reason = 2

        self._log.info(
            "Bluetooth scan callback received: fail_reason=%s devices=%s",
            reason,
            len(devices),
        )

        if reason == 1:
            self._finish_error(
                "Bluetooth is disabled. Please enable Bluetooth and try again.",
                devices=devices,
            )
            return
        if reason == 2 and not devices:
            self._finish_error(
                "Bluetooth scan failed. Please try again.",
                devices=devices,
            )
            return
        self._finish_ok(devices)

    def _finish_ok(self, devices: list[tuple[str, str, int]]):
        self._log.info("Bluetooth scan helper finished successfully with %s devices", len(devices))
        self._finish({"status": "ok", "devices": devices})

    def _finish_error(self, message: str, *, devices: list | None = None):
        self._log.error("Bluetooth scan helper failed: %s", message)
        self._finish(
            {
                "status": "error",
                "error": message,
                "devices": devices or [],
            }
        )

    def _finish(self, payload: dict):
        if self._finished:
            return
        self._finished = True
        self._pump_timer.stop()
        self._timeout_timer.stop()
        try:
            sys.stdout.write(json.dumps(payload) + "\n")
            sys.stdout.flush()
        finally:
            QTimer.singleShot(0, QCoreApplication.instance().quit)


def main(argv: list[str]) -> int:
    logger = _setup_logging()

    try:
        device_type = int(argv[1]) if len(argv) > 1 else 0
    except (TypeError, ValueError):
        device_type = 0
    try:
        timeout_sec = int(argv[2]) if len(argv) > 2 else 15
    except (TypeError, ValueError):
        timeout_sec = 15

    app = QCoreApplication(argv)
    app.setApplicationName("bci-dashboard-scan-helper")

    session = ScanSession(device_type, timeout_sec, logger)
    QTimer.singleShot(0, session.start)

    try:
        return app.exec()
    except BaseException:  # pragma: no cover - defensive
        logger.exception("Scan helper event loop aborted")
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
