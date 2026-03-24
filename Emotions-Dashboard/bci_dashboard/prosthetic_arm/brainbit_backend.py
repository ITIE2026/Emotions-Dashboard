from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from prosthetic_arm.sources import MetricSourceAdapter, normalized_metrics

try:
    from em_st_artifacts.utils import lib_settings, support_classes
    from em_st_artifacts import emotional_math

    MATH_OK = True
except ImportError:
    lib_settings = None
    support_classes = None
    emotional_math = None
    MATH_OK = False

try:
    from neurosdk.cmn_types import SensorCommand, SensorFamily
    from neurosdk.scanner import Scanner

    SDK_OK = True
except Exception:
    SensorCommand = None
    SensorFamily = None
    Scanner = None
    SDK_OK = False


SCAN_TIMEOUT_SEC = 7
STABILIZE_DELAY_SEC = 3
WATCHDOG_SEC = 15
KEEPALIVE_MS = 200
EMIT_EVERY = 1


class BrainBitSensorWorker(QThread):
    status_changed = Signal(str)
    connection_changed = Signal(bool)
    packet_received = Signal(list)
    resistance_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._last_packet_t = 0.0

    def start_worker(self) -> None:
        if self.isRunning():
            return
        self._running = True
        self.start()

    def stop_worker(self) -> None:
        self._running = False
        self.quit()
        self.wait(5000)

    def _on_signal(self, sensor, data):
        if not self._running or not data:
            return
        self._last_packet_t = time.time()
        self.packet_received.emit(list(data))

    def _on_resistance(self, sensor, data):
        if not self._running:
            return
        self.resistance_changed.emit(
            {
                "O1": float(data.O1),
                "O2": float(data.O2),
                "T3": float(data.T3),
                "T4": float(data.T4),
            }
        )

    def run(self) -> None:
        self._running = True
        if not SDK_OK:
            self.status_changed.emit("NeuroSDK is unavailable.")
            return

        while self._running:
            self._run_session()
            if not self._running:
                break
            self.status_changed.emit("BrainBit reconnecting in 3s...")
            for _ in range(30):
                if not self._running:
                    break
                self.msleep(100)

    def _run_session(self) -> None:
        sensor = None
        scanner = None
        was_connected = False
        try:
            self.status_changed.emit("Scanning for BrainBit...")
            scanner = Scanner(
                [
                    SensorFamily.LEHeadband,
                    SensorFamily.LEBrainBit,
                    SensorFamily.LEBrainBit2,
                ]
            )
            scanner.start()
            waited_ms = 0
            while waited_ms < (SCAN_TIMEOUT_SEC * 1000):
                self.msleep(500)
                waited_ms += 500
                if not self._running:
                    scanner.stop()
                    return
                if scanner.sensors():
                    break
            scanner.stop()
            sensors = scanner.sensors()
            if not sensors:
                self.status_changed.emit("No BrainBit device found.")
                return

            sensor = scanner.create_sensor(sensors[0])
            sensor.signalDataReceived = self._on_signal
            sensor.resistDataReceived = self._on_resistance
            self.status_changed.emit(f"BrainBit connected: {sensors[0].Name}")
            self.connection_changed.emit(True)
            was_connected = True
            self.msleep(STABILIZE_DELAY_SEC * 1000)

            if sensor.is_supported_command(SensorCommand.StartSignalAndResist):
                sensor.exec_command(SensorCommand.StartSignalAndResist)
            else:
                sensor.exec_command(SensorCommand.StartResist)
                sensor.exec_command(SensorCommand.StartSignal)

            self._last_packet_t = time.time()
            while self._running:
                self.msleep(KEEPALIVE_MS)
                if (time.time() - self._last_packet_t) > WATCHDOG_SEC:
                    self.status_changed.emit("BrainBit watchdog triggered. Reconnecting...")
                    break
        except Exception as exc:  # pragma: no cover - depends on hardware
            self.status_changed.emit(f"BrainBit error: {exc}")
        finally:
            if sensor:
                try:
                    if sensor.is_supported_command(SensorCommand.StopSignalAndResist):
                        sensor.exec_command(SensorCommand.StopSignalAndResist)
                    else:
                        try:
                            sensor.exec_command(SensorCommand.StopSignal)
                        except Exception:
                            pass
                        try:
                            sensor.exec_command(SensorCommand.StopResist)
                        except Exception:
                            pass
                except Exception:
                    pass
            if was_connected:
                self.connection_changed.emit(False)


class BrainBitMathEngine(QObject):
    raw_uv_changed = Signal(list)
    waves_changed = Signal(float, float)
    metrics_changed = Signal(dict)
    calibration_progress_changed = Signal(int)
    calibration_mode_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._math = None
        self._packet_count = 0
        self._calibration_pct = 0
        self._calibrated = False
        self._running = False
        self._setup_math()

    def _setup_math(self) -> None:
        if not MATH_OK:
            self.status_changed.emit("em_st_artifacts is unavailable.")
            return
        try:
            math_settings = lib_settings.MathLibSetting(
                sampling_rate=250,
                process_win_freq=25,
                n_first_sec_skipped=4,
                fft_window=1000,
                bipolar_mode=True,
                channels_number=4,
                channel_for_analysis=0,
            )
            artifact_settings = lib_settings.ArtifactDetectSetting(
                art_bord=110,
                allowed_percent_artpoints=70,
                raw_betap_limit=800_000,
                global_artwin_sec=4,
                num_wins_for_quality_avg=125,
                hamming_win_spectrum=True,
                hanning_win_spectrum=False,
                total_pow_border=400_000_000,
                spect_art_by_totalp=True,
            )
            short_artifacts = lib_settings.ShortArtifactDetectSetting()
            mental_settings = lib_settings.MentalAndSpectralSetting(
                n_sec_for_averaging=2,
                n_sec_for_instant_estimation=4,
            )
            self._math = emotional_math.EmotionalMath(
                math_settings,
                artifact_settings,
                short_artifacts,
                mental_settings,
            )
            self._math.set_calibration_length(8)
            self._math.set_zero_spect_waves(True, 0, 1, 1, 1, 0)
            self._math.set_spect_normalization_by_bands_width(True)
            self._math.set_mental_estimation_mode(True)
            self.status_changed.emit("BrainBit math ready.")
        except Exception as exc:  # pragma: no cover - depends on native lib
            self._math = None
            self.status_changed.emit(f"BrainBit math setup failed: {exc}")

    @Slot()
    def reset(self) -> None:
        self._packet_count = 0
        self._calibration_pct = 0
        self._calibrated = False
        self._running = False
        self._setup_math()

    @Slot()
    def start_iapf(self) -> None:
        if not self._math:
            self.status_changed.emit("BrainBit math is unavailable.")
            return
        self._math.start_calibration()
        self._packet_count = 0
        self._calibration_pct = 0
        self._calibrated = False
        self._running = True
        self.calibration_mode_changed.emit("IAPF")
        self.status_changed.emit("BrainBit IAPF calibration started.")

    @Slot()
    def start_baseline(self) -> None:
        if not self._math:
            self.status_changed.emit("BrainBit math is unavailable.")
            return
        if not self._calibrated:
            self.status_changed.emit("Run IAPF before baseline calibration.")
            return
        self._math.start_calibration()
        self._packet_count = 0
        self._calibration_pct = 0
        self._running = True
        self.calibration_mode_changed.emit("Baseline")
        self.status_changed.emit("BrainBit baseline calibration started.")

    @Slot(list)
    def slot_packet(self, data: list) -> None:
        if not self._math or not data:
            return
        try:
            raw_uv = [(s.O1 * 1e6, s.O2 * 1e6, s.T3 * 1e6, s.T4 * 1e6) for s in data]
            bipolar = [support_classes.RawChannels(s.T3 - s.O1, s.T4 - s.O2) for s in data]
            self._math.push_data(bipolar)
            self._math.process_data_arr()
            self._packet_count += 1
            if self._packet_count % EMIT_EVERY != 0:
                return

            self.raw_uv_changed.emit(raw_uv)
            if not self._running:
                return

            calibration = int(self._math.get_calibration_percents())
            if calibration != self._calibration_pct:
                self._calibration_pct = calibration
                self.calibration_progress_changed.emit(calibration)
            if calibration < 100:
                return

            if not self._calibrated:
                self._calibrated = True
                self.calibration_mode_changed.emit("Running")
                self.status_changed.emit("BrainBit calibration complete.")

            spectra = self._math.read_spectral_data_percents_arr()
            if spectra:
                latest_spectrum = spectra[-1]
                self.waves_changed.emit(float(latest_spectrum.alpha * 100), float(latest_spectrum.beta * 100))

            mental = self._math.read_mental_data_arr()
            if mental:
                latest_mental = mental[-1]
                self.metrics_changed.emit(
                    normalized_metrics(
                        float(latest_mental.rel_attention),
                        float(latest_mental.rel_relaxation),
                    )
                )
        except Exception as exc:  # pragma: no cover - depends on native lib
            self.status_changed.emit(f"BrainBit processing error: {exc}")


class BrainBitMetricAdapter(MetricSourceAdapter):
    request_reset = Signal()
    request_iapf = Signal()
    request_baseline = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sensor_worker = BrainBitSensorWorker(self)
        self._math_engine = BrainBitMathEngine()
        self._math_thread = QThread(self)
        self._math_engine.moveToThread(self._math_thread)
        self._math_thread.start()

        self.request_reset.connect(self._math_engine.reset, Qt.QueuedConnection)
        self.request_iapf.connect(self._math_engine.start_iapf, Qt.QueuedConnection)
        self.request_baseline.connect(self._math_engine.start_baseline, Qt.QueuedConnection)

        self._sensor_worker.packet_received.connect(self._math_engine.slot_packet, Qt.QueuedConnection)
        self._sensor_worker.status_changed.connect(self.status_changed)
        self._sensor_worker.connection_changed.connect(self._on_connection_changed)
        self._sensor_worker.resistance_changed.connect(self.resistance_changed)

        self._math_engine.raw_uv_changed.connect(self.raw_uv_changed)
        self._math_engine.waves_changed.connect(self.waves_changed)
        self._math_engine.metrics_changed.connect(self.metrics_changed)
        self._math_engine.calibration_progress_changed.connect(self.calibration_progress_changed)
        self._math_engine.calibration_mode_changed.connect(self.calibration_mode_changed)
        self._math_engine.status_changed.connect(self.status_changed)

    def connect_device(self) -> bool:
        if not SDK_OK:
            self.status_changed.emit("NeuroSDK is unavailable. BrainBit mode disabled.")
            self._set_connected(False)
            return False
        if not MATH_OK:
            self.status_changed.emit("em_st_artifacts is unavailable. BrainBit mode disabled.")
            self._set_connected(False)
            return False
        self.status_changed.emit("BrainBit scan requested.")
        self._sensor_worker.start_worker()
        return True

    def disconnect_device(self) -> None:
        self._sensor_worker.stop_worker()
        self._set_connected(False, "BrainBit disconnected.")

    def start_iapf_calibration(self) -> None:
        self.request_iapf.emit()

    def start_baseline_calibration(self) -> None:
        self.request_baseline.emit()

    def shutdown(self) -> None:
        self.disconnect_device()
        self._math_thread.quit()
        self._math_thread.wait(3000)
        super().shutdown()

    @Slot(bool)
    def _on_connection_changed(self, connected: bool) -> None:
        self._set_connected(connected)
        if connected:
            self.request_reset.emit()
