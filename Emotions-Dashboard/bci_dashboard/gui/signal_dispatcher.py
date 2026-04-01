"""Signal subscription and data-routing mixin for MainWindow."""
from __future__ import annotations

import logging
import time

from PySide6.QtWidgets import QMessageBox

from calibration.calibration_manager import CalibrationManager
from classifiers.cardio_handler import CardioHandler
from classifiers.emotions_handler import EmotionsHandler
from classifiers.mems_handler import MemsHandler
from classifiers.physio_handler import PhysioHandler
from classifiers.productivity_handler import ProductivityHandler
from device.device_status_monitor import DeviceStatusMonitor
from gui.screen_router import PAGE_CONNECTION, PAGE_DASHBOARD, PAGE_MEMS, PAGE_MULTIPLAYER, PAGE_TRAINING

log = logging.getLogger(__name__)


def _safe_str(value) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, Exception) and hasattr(value, "message"):
        return _safe_str(value.message)
    return str(value)


class SignalDispatcherMixin:
    """Mixin that wires device/classifier signals to screens and graph history."""

    def _connect_device_signals(self):
        self._dm.connection_changed.connect(self._on_device_connected)
        self._dm.battery_updated.connect(self._on_battery_updated)
        self._dm.resistance_updated.connect(self._on_resistance_updated)
        self._dm.mode_changed.connect(self._on_mode_updated)
        self._dm.error_occurred.connect(self._on_error)

    def _on_battery_updated(self, pct: int):
        self._dash_screen.set_battery(pct)
        self._mems_screen.set_battery(pct)
        self._phaseon_runtime.update_device_status(battery=pct)

    def _on_resistance_updated(self, data: dict):
        self._latest_resistances = data or {}
        self._dash_screen.on_resistance(data)
        if self._training_screen.is_neuroflow_active():
            self._training_screen.on_resistance(data or {})
        self._phaseon_runtime.ingest_resistances(data)
        if self._session_active:
            self._recorder.record_resistances(data or {})

    def _on_mode_updated(self, mode: int):
        mode_map = {
            0: "Resistance",
            1: "Signal",
            2: "Signal+Resistance",
            3: "MEMS",
            4: "Stop MEMS",
            5: "PPG",
            6: "Stop PPG",
        }
        mode_str = mode_map.get(int(mode), "Unspecified")
        self._dash_screen.set_mode(mode_str)
        self._mems_screen.set_mode(mode_str)
        self._phaseon_runtime.update_device_status(mode=mode_str)

    def _on_device_connected(self, status: int):
        try:
            status = int(status)
        except (ValueError, TypeError):
            log.warning("Invalid connection status: %r", status)
            return

        if status == 1:
            log.info("Device connected - serial %s", self._dm.device_serial)
            self._disconnect_timer.stop()
            self._dash_screen.set_session_info(
                connected=True,
                serial=self._dm.device_serial or "",
            )
            self._training_screen.on_connection_state(
                connected=True,
                serial=self._dm.device_serial or "",
            )
            self._mems_screen.set_session_info(
                connected=True,
                serial=self._dm.device_serial or "",
            )
            self._dash_screen.set_eeg_stream_metadata(
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
            self._training_screen.set_eeg_stream_metadata(
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
            self._phaseon_runtime.update_device_status(
                connected=True,
                serial=self._dm.device_serial or "",
                sample_rate_hz=self._dm.eeg_sample_rate,
                channel_names=self._dm.display_channel_names,
            )
            self._refresh_battery_now()

            if not self._classifiers_created:
                self._create_classifiers()

            serial = self._dm.device_serial or ""
            if self._cal_mgr and serial and self._cal_mgr.can_import(serial):
                self._cal_mgr.import_saved(serial)
                self._load_saved_graph_references(serial)
            else:
                self._load_saved_graph_references("")
            if not self._session_active:
                self._safe_start_streaming()
                if self._streaming:
                    self._begin_session()
                else:
                    QMessageBox.warning(
                        self,
                        "Start Signal Failed",
                        "The device connected, but live streaming could not be started.",
                    )
        elif status == 0:
            log.info("Device disconnected signal - starting debounce timer")
            self._phaseon_runtime.update_device_status(connected=False)
            if not self._disconnect_timer.isActive():
                self._disconnect_timer.start()

    def _confirm_disconnected(self):
        if not self._dm.is_connected():
            log.info("Device confirmed disconnected")
            self._streaming = False
            self._dash_screen.set_session_info(connected=False)
            self._training_screen.on_connection_state(
                connected=False,
                serial=self._dm.device_serial or "",
            )
            self._mems_screen.set_session_info(connected=False)
            self._phaseon_runtime.update_device_status(connected=False, session_id="")
            self._dash_screen.set_streaming_active(False)
            self._mems_screen.set_streaming_active(False)
            self._stop_session()

    def _create_classifiers(self):
        dev = self._dm.device
        lib = self._bridge.lib
        if dev is None:
            return

        try:
            self._emotions_h = EmotionsHandler(dev, lib, parent=self)
            self._prod_h = ProductivityHandler(dev, lib, parent=self)
            self._cardio_h = CardioHandler(dev, lib, parent=self)
            self._physio_h = PhysioHandler(dev, lib, parent=self)
        except Exception as exc:
            log.error("Failed to create classifiers: %s", _safe_str(exc))
            return

        try:
            self._mems_h = MemsHandler(dev, lib, parent=self)
        except Exception as exc:
            self._mems_h = None
            log.warning("MEMS handler unavailable: %s", _safe_str(exc))

        self._classifiers_created = True
        self._cal_mgr = CalibrationManager(dev, lib, self._prod_h, self._physio_h, parent=self)
        self._status_mon = DeviceStatusMonitor(self._dm, parent=self)

        self._emotions_h.states_updated.connect(self._on_emotions)
        self._prod_h.metrics_updated.connect(self._on_productivity)
        self._prod_h.indexes_updated.connect(self._on_productivity_indexes)
        self._cardio_h.cardio_updated.connect(self._on_cardio)
        self._cardio_h.ppg_updated.connect(self._on_ppg)
        self._cardio_h.calibrated.connect(lambda: self._dash_screen.set_ppg_calibrated(True))
        self._physio_h.states_updated.connect(self._on_physio_states)
        if self._mems_h:
            self._mems_h.mems_updated.connect(self._on_mems)

        self._dm.psd_received.connect(self._on_psd)
        self._dm.eeg_received.connect(self._on_eeg)
        self._dm.artifacts_received.connect(self._on_artifacts)

        self._emotions_h.error_occurred.connect(self._on_error)

        self._cal_mgr.stage_changed.connect(self._cal_screen.set_stage)
        self._cal_mgr.progress_updated.connect(self._cal_screen.set_progress)
        self._cal_mgr.calibration_complete.connect(self._on_calibration_done)
        self._cal_mgr.calibration_failed.connect(self._on_calibration_failed)
        self._cal_mgr.iapf_updated.connect(self._on_iapf_updated)

        self._cal_screen.cancel_button.clicked.connect(self._cancel_calibration)

        self._status_mon.battery_polled.connect(self._on_battery_updated)
        self._status_mon.disconnection_detected.connect(self._on_disconnect_detected)
        self._status_mon.reconnection_failed.connect(self._on_reconnect_failed)
        self._status_mon.reconnection_succeeded.connect(self._on_reconnect_ok)

    def _on_emotions(self, data: dict):
        self._latest_emo = data or {}
        self._dash_screen.on_emotions(data)
        self._training_screen.on_emotions(data)
        youtube_screen = getattr(self, "_youtube_screen", None)
        if youtube_screen is not None and hasattr(youtube_screen, "on_emotions"):
            youtube_screen.on_emotions(data)
        gyro_mouse = getattr(self, "_gyro_mouse", None)
        if gyro_mouse is not None:
            gyro_mouse.on_emotions(data)
        aim_trainer = getattr(self, "_aim_trainer", None)
        if aim_trainer is not None:
            aim_trainer.on_emotions(data)
        brain_speller = getattr(self, "_brain_speller", None)
        if brain_speller is not None:
            brain_speller.on_emotions(data)
        music_dj = getattr(self, "_music_dj", None)
        if music_dj is not None:
            music_dj.on_emotions(data)
        focus_timer = getattr(self, "_focus_timer", None)
        if focus_timer is not None:
            focus_timer.on_emotions(data)
        neuro_art = getattr(self, "_neuro_art", None)
        if neuro_art is not None:
            neuro_art.on_emotions(data)
        neuro_journal = getattr(self, "_neuro_journal", None)
        if neuro_journal is not None:
            neuro_journal.on_emotions(data)
        if self.is_graph_active("cognitive_states"):
            self._refresh_metric_graph_window("cognitive_states")
        if self._session_active:
            self._recorder.record_emotions(self._latest_emo)

    def _on_productivity(self, data: dict):
        self._latest_prod = data or {}
        self._dash_screen.on_productivity(data)
        self._phaseon_runtime.ingest_productivity(data)
        self._training_screen.on_productivity(data)
        if hasattr(self, "_games_window"):
            self._games_window.on_productivity(data)
        if hasattr(self, "_multiplayer_screen"):
            self._multiplayer_screen.on_productivity(data)
        youtube_screen = getattr(self, "_youtube_screen", None)
        if youtube_screen is not None and hasattr(youtube_screen, "on_productivity"):
            youtube_screen.on_productivity(data)
        now = time.monotonic()
        self.append_graph_point("concentration_index", "concentrationScore", self._latest_prod.get("concentrationScore"), timestamp=now)
        self.append_graph_point("relaxation_index", "relaxationScore", self._latest_prod.get("relaxationScore"), timestamp=now)
        self.append_graph_point("fatigue_score", "fatigueScore", self._latest_prod.get("fatigueScore"), timestamp=now)
        self.append_graph_point("reverse_fatigue_score", "reverseFatigueScore", self._latest_prod.get("reverseFatigueScore"), timestamp=now)
        self.append_graph_point("alpha_gravity", "gravityScore", self._latest_prod.get("gravityScore"), timestamp=now)
        self.append_graph_point("productivity_score", "currentValue", self._latest_prod.get("currentValue"), timestamp=now)
        self.append_graph_point("accumulated_fatigue", "accumulatedFatigue", self._latest_prod.get("accumulatedFatigue"), timestamp=now)
        for graph_id in (
            "concentration_index",
            "relaxation_index",
            "fatigue_score",
            "reverse_fatigue_score",
            "alpha_gravity",
            "productivity_score",
            "accumulated_fatigue",
        ):
            self._refresh_metric_graph_window(graph_id)
        if self._session_active:
            self._recorder.record_productivity_metrics(self._latest_prod)

    def _on_productivity_indexes(self, data: dict):
        self._latest_indexes = data or {}
        self._dash_screen.on_indexes(data)
        self._update_graph_references_from_indexes(self._latest_indexes)
        self._append_eeg_quality_history(timestamp=time.monotonic())
        for graph_id in (
            "concentration_index",
            "relaxation_index",
            "fatigue_score",
            "reverse_fatigue_score",
            "alpha_gravity",
            "eeg_quality",
        ):
            self._refresh_metric_graph_window(graph_id)
        if self._session_active:
            self._recorder.record_productivity_indexes(self._latest_indexes)

    def _on_cardio(self, data: dict):
        self._latest_cardio = data or {}
        self._dash_screen.on_cardio(data)
        self._training_screen.on_cardio(data)

    def _on_ppg(self, ppg_timed_data):
        if not self._streaming:
            return
        self._dash_screen.on_ppg(ppg_timed_data)
        if self._session_active:
            self._recorder.record_ppg_packet(ppg_timed_data)

    def _on_physio_states(self, data: dict):
        self._latest_physio = data or {}
        self._dash_screen.on_physio_states(data)
        self._training_screen.on_physio_states(data)
        if hasattr(self, "_games_window"):
            self._games_window.on_physio_states(data)
        if hasattr(self, "_multiplayer_screen"):
            self._multiplayer_screen.on_physio_states(data)
        self._append_eeg_quality_history(timestamp=time.monotonic())
        self._refresh_metric_graph_window("eeg_quality")

    def _on_psd(self, psd_data):
        if not self._streaming:
            return
        raw = self._extract_psd_raw(psd_data)
        if raw is None:
            return
        self._psd_worker.submit(raw[0], raw[1])

    def _on_psd_computed(self, psd_snapshot: dict):
        self._latest_psd_t = float(psd_snapshot.get("received_at", time.monotonic()))
        self._latest_band_powers = dict(psd_snapshot.get("band_powers", {}))
        self._latest_peak_freqs = dict(psd_snapshot.get("peak_frequencies", {}))
        self.append_graph_point("frequency_peaks", "alpha_peak", self._latest_peak_freqs.get("alpha_peak"), timestamp=self._latest_psd_t)
        self.append_graph_point("frequency_peaks", "beta_peak", self._latest_peak_freqs.get("beta_peak"), timestamp=self._latest_psd_t)
        self.append_graph_point("frequency_peaks", "theta_peak", self._latest_peak_freqs.get("theta_peak"), timestamp=self._latest_psd_t)
        self._training_screen.update_signal_snapshot(
            self._latest_band_powers,
            self._latest_peak_freqs,
            self._latest_psd_t,
        )
        if hasattr(self, "_games_window"):
            self._games_window.update_signal_snapshot(
                self._latest_band_powers,
                self._latest_peak_freqs,
                self._latest_psd_t,
            )
        self._refresh_metric_graph_window("frequency_peaks")
        if self._stack.currentIndex() == PAGE_DASHBOARD:
            if hasattr(self._dash_screen, "on_psd_snapshot"):
                self._dash_screen.on_psd_snapshot(psd_snapshot)
            else:
                self._dash_screen.on_psd(psd_snapshot)
        if self._stack.currentIndex() == PAGE_MEMS:
            self._mems_screen.on_band_powers(self._latest_band_powers)

    def _on_eeg(self, eeg_timed_data):
        if not self._streaming:
            return
        dashboard_visible = self._stack.currentIndex() == PAGE_DASHBOARD
        if not dashboard_visible and not self._session_active:
            return
        eeg_snapshot = self._extract_eeg_snapshot(eeg_timed_data)
        if not eeg_snapshot:
            return
        if dashboard_visible:
            if hasattr(self._dash_screen, "on_eeg_snapshot"):
                self._dash_screen.on_eeg_snapshot(eeg_snapshot)
            else:
                self._dash_screen.on_eeg(eeg_timed_data)
        if self._session_active:
            if hasattr(self._recorder, "record_raw_eeg_snapshot"):
                self._recorder.record_raw_eeg_snapshot(eeg_snapshot)
            else:
                self._recorder.record_raw_eeg_packet(eeg_timed_data)

    def _on_artifacts(self, artifacts):
        if not self._streaming:
            return
        self._dash_screen.on_artifacts(artifacts)
        if self._session_active:
            self._recorder.record_artifacts(artifacts)

    def _on_mems(self, mems_timed_data):
        if not self._streaming:
            return
        if self._stack.currentIndex() == PAGE_MEMS:
            self._mems_screen.on_mems(mems_timed_data)
        if self._stack.currentIndex() == PAGE_TRAINING:
            self._training_screen.on_mems(mems_timed_data)
        if hasattr(self, "_games_window") and self._games_window.isVisible():
            self._games_window.on_mems(mems_timed_data)
        gyro_mouse = getattr(self, "_gyro_mouse", None)
        if gyro_mouse is not None:
            gyro_mouse.on_mems(mems_timed_data)
        aim_trainer = getattr(self, "_aim_trainer", None)
        if aim_trainer is not None:
            aim_trainer.on_mems(mems_timed_data)
        brain_speller = getattr(self, "_brain_speller", None)
        if brain_speller is not None:
            brain_speller.on_mems(mems_timed_data)
        music_dj = getattr(self, "_music_dj", None)
        if music_dj is not None:
            music_dj.on_mems(mems_timed_data)
        neuro_art = getattr(self, "_neuro_art", None)
        if neuro_art is not None:
            neuro_art.on_mems(mems_timed_data)
        if self._session_active:
            self._recorder.record_mems_packet(mems_timed_data)

    def _on_disconnect_detected(self):
        log.warning("Device disconnected - attempting to reconnect")
        self._dash_screen.set_session_info(connected=False)
        self._training_screen.on_connection_state(
            connected=False, serial=self._dm.device_serial or ""
        )
        self._mems_screen.set_session_info(connected=False)
        self._phaseon_runtime.update_device_status(connected=False)

    def _on_reconnect_failed(self):
        log.error("Reconnection failed after max attempts")
        QMessageBox.warning(
            self,
            "Disconnected",
            "Could not reconnect to the device.\nPlease check the hardware and try again.",
        )
        self._stop_session()
        self._stack.setCurrentIndex(PAGE_CONNECTION)

    def _on_reconnect_ok(self):
        log.info("Reconnected successfully")
        self._dash_screen.set_session_info(
            connected=True, serial=self._dm.device_serial or ""
        )
        self._training_screen.on_connection_state(
            connected=True, serial=self._dm.device_serial or ""
        )
        self._training_screen.set_eeg_stream_metadata(
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )
        self._mems_screen.set_session_info(
            connected=True, serial=self._dm.device_serial or ""
        )
        self._phaseon_runtime.update_device_status(
            connected=True,
            serial=self._dm.device_serial or "",
            sample_rate_hz=self._dm.eeg_sample_rate,
            channel_names=self._dm.display_channel_names,
        )

    def _on_error(self, msg):
        log.error("Error: %s", _safe_str(msg))
