import os
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from calibration.calibration_manager import CalibrationManager  # noqa: E402
from device.device_manager import DeviceManager  # noqa: E402
from gui.dashboard_screen import DashboardScreen  # noqa: E402
from gui.main_window import MainWindow, PAGE_MEMS, PAGE_PHASEON  # noqa: E402
from gui.mems_screen import MemsScreen  # noqa: E402
from gui.training_screen import TrainingScreen  # noqa: E402
from gui.training_games import (  # noqa: E402
    BubbleBurstController,
    CalmCurrentController,
    CandyCascadeController,
    FullRebootController,
    JumpBallController,
    NeonDriftArenaController,
    NeuroRacerController,
    PatternRecallController,
    ProstheticArmController,
    SpaceShooterController,
    active_training_specs,
)
from gui.widgets.electrode_table import ElectrodeTable  # noqa: E402
from prosthetic_arm.arduino_arm import ArduinoArmController  # noqa: E402
from prosthetic_arm.capsule_backend import CapsuleMetricAdapter  # noqa: E402
from utils.sdk_scalars import coerce_float, coerce_int, coerce_percent  # noqa: E402
from utils.eeg_filter import EEGDisplayFilter  # noqa: E402

APP = QApplication.instance() or QApplication([])


class _FakeEEGTimedData:
    def __init__(self, channels, timestamps_ms, processed_channels=None):
        self._channels = channels
        self._timestamps_ms = timestamps_ms
        self._processed_channels = processed_channels

    def get_channels_count(self):
        return len(self._channels)

    def get_samples_count(self):
        return len(self._timestamps_ms)

    def get_timestamp(self, idx):
        return self._timestamps_ms[idx]

    def get_raw_value(self, ch_idx, sample_idx):
        return float(self._channels[ch_idx][sample_idx]) / 1_000_000.0

    def get_processed_value(self, ch_idx, sample_idx):
        if self._processed_channels is None:
            raise AttributeError("processed EEG unavailable")
        return float(self._processed_channels[ch_idx][sample_idx])


class _FakePSDData:
    def __init__(self, freqs, channel_powers):
        self._freqs = list(freqs)
        self._channel_powers = [list(channel) for channel in channel_powers]

    def get_frequencies_count(self):
        return len(self._freqs)

    def get_channels_count(self):
        return len(self._channel_powers)

    def get_frequency(self, idx):
        return float(self._freqs[idx])

    def get_psd(self, ch_idx, f_idx):
        return float(self._channel_powers[ch_idx][f_idx])


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)


class _DeviceManagerStub:
    def __init__(self, *args, **kwargs):
        self.connection_changed = _SignalStub()
        self.battery_updated = _SignalStub()
        self.resistance_updated = _SignalStub()
        self.mode_changed = _SignalStub()
        self.error_occurred = _SignalStub()
        self.psd_received = _SignalStub()
        self.eeg_received = _SignalStub()
        self.artifacts_received = _SignalStub()
        self.device = None
        self.device_serial = ""

    def stop_streaming(self):
        return None

    def start_streaming(self):
        return None

    def disconnect(self):
        return None

    def is_connected(self):
        return False


class _BridgeStub:
    def __init__(self, *args, **kwargs):
        self.lib = None

    def shutdown(self):
        return None


class _RecorderStub:
    def __init__(self, *args, **kwargs):
        self.file_path = ""
        self.session_id = "session-test"

    def start_session(self, *args, **kwargs):
        return None

    def stop_session(self):
        return None

    def update_calibration_info(self, *args, **kwargs):
        return None

    def record_mems_packet(self, *args, **kwargs):
        return None

    def record_resistances(self, *args, **kwargs):
        return None

    def record_emotions(self, *args, **kwargs):
        return None

    def record_productivity_metrics(self, *args, **kwargs):
        return None

    def record_productivity_indexes(self, *args, **kwargs):
        return None

    def record_ppg_packet(self, *args, **kwargs):
        return None

    def record_raw_eeg_packet(self, *args, **kwargs):
        return None

    def record_artifacts(self, *args, **kwargs):
        return None

    def log_metrics_row(self, *args, **kwargs):
        return None

    def record_cardio_metrics(self, *args, **kwargs):
        return None

    def record_rhythms(self, *args, **kwargs):
        return None

    def record_eeg_summary(self, *args, **kwargs):
        return None


class _SignalButtonStub:
    def __init__(self):
        self.clicked = _SignalStub()


class _ConnectionScreenStub(QWidget):
    selected_device_type_value = 0
    selected_device_type_label = "Headband"
    selected_write_options = {"raw_eeg": True}

    def __init__(self, *args, **kwargs):
        super().__init__()


class _CalibrationScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.cancel_button = _SignalButtonStub()

    def set_mode(self, *args, **kwargs):
        return None

    def set_result_text(self, *args, **kwargs):
        return None

    def set_stage(self, *args, **kwargs):
        return None

    def set_progress(self, *args, **kwargs):
        return None


class _DashboardScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.band_powers = {}
        self.peak_frequencies = {}
        self.ppg_metrics = {}

    def set_iapf_status(self, *args, **kwargs):
        return None

    def set_eeg_filter_enabled(self, *args, **kwargs):
        return None

    def set_streaming_active(self, *args, **kwargs):
        return None

    def set_session_info(self, *args, **kwargs):
        return None

    def set_battery(self, *args, **kwargs):
        return None

    def set_mode(self, *args, **kwargs):
        return None

    def on_resistance(self, *args, **kwargs):
        return None

    def on_emotions(self, *args, **kwargs):
        return None

    def on_productivity(self, *args, **kwargs):
        return None

    def on_cardio(self, *args, **kwargs):
        return None

    def on_ppg(self, *args, **kwargs):
        return None

    def on_physio_states(self, *args, **kwargs):
        return None

    def on_psd(self, *args, **kwargs):
        return None

    def on_eeg(self, *args, **kwargs):
        return None

    def on_artifacts(self, *args, **kwargs):
        return None

    def reset_session(self, *args, **kwargs):
        return None

    def set_session_file(self, *args, **kwargs):
        return None

    def stop_eeg_timer(self):
        return None


class _MemsScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.last_section = None

    def show_section(self, section_id):
        self.last_section = section_id

    def set_battery(self, *args, **kwargs):
        return None

    def set_mode(self, *args, **kwargs):
        return None

    def set_session_info(self, *args, **kwargs):
        return None

    def reset_session(self, *args, **kwargs):
        return None

    def set_streaming_active(self, *args, **kwargs):
        return None

    def on_band_powers(self, *args, **kwargs):
        return None

    def on_mems(self, *args, **kwargs):
        return None


class _TrainingScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def on_emotions(self, *args, **kwargs):
        return None

    def on_productivity(self, *args, **kwargs):
        return None

    def on_cardio(self, *args, **kwargs):
        return None

    def on_physio_states(self, *args, **kwargs):
        return None

    def shutdown(self):
        return None


class _SessionsScreenStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def refresh_list(self):
        return None


class _PhaseonScreenStub(QWidget):
    def __init__(self, runtime, *args, **kwargs):
        super().__init__()
        self.runtime = runtime


class _PhaseonRuntimeStub(QObject):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def snapshot_state(self):
        return {}

    def snapshot_metrics(self):
        return {}

    def snapshot_resistances(self):
        return {}

    def snapshot_raw_payload(self):
        return {"channels": {}}

    def update_device_status(self, *args, **kwargs):
        return None

    def ingest_resistances(self, *args, **kwargs):
        return None

    def ingest_productivity(self, *args, **kwargs):
        return None

    def ingest_band_powers(self, *args, **kwargs):
        return None

    def ingest_eeg_packet(self, *args, **kwargs):
        return None

    def shutdown(self):
        return None


class _SharedBackendStub(QObject):
    status_changed = Signal(str)
    connection_changed = Signal(bool)
    metrics_changed = Signal(object)
    resistance_changed = Signal(object)
    waves_changed = Signal(float, float)
    raw_uv_changed = Signal(object)
    calibration_mode_changed = Signal(str)
    calibration_progress_changed = Signal(float, str)

    def __init__(self):
        super().__init__()
        self.ingest_calls = 0
        self.shutdown_calls = 0
        self.is_connected = False

    def ingest_productivity(self, payload):
        self.ingest_calls += 1

    def shutdown(self):
        self.shutdown_calls += 1


class _SharedArduinoStub(QObject):
    connection_changed = Signal(bool)
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.disconnect_calls = 0

    def disconnect_device(self):
        self.disconnect_calls += 1


class _SharedRuntimeStub:
    def __init__(self):
        self.capsule_backend = _SharedBackendStub()
        self.brainbit_backend = _SharedBackendStub()
        self.arduino_arm = _SharedArduinoStub()
        self.arm_state_engine = object()


class _CalFakeProdHandler(QObject):
    baselines_updated = Signal(object)
    calibration_progress = Signal(float)

    def __init__(self):
        super().__init__()
        self.started = 0

    def start_baseline_calibration(self):
        self.started += 1

    def import_baselines(self, baselines):
        return None


class _CalFakePhyHandler(QObject):
    baselines_updated = Signal(object)
    calibration_progress = Signal(float)

    def __init__(self):
        super().__init__()
        self.started = 0

    def start_baseline_calibration(self):
        self.started += 1

    def import_baselines(self, baselines):
        return None


class _CalFakeCalibrator:
    def __init__(self, *args, **kwargs):
        self.finished_cb = None
        self.stage_cb = None
        self.failed = False

    def set_on_calibration_finished(self, callback):
        self.finished_cb = callback

    def set_on_calibration_stage_finished(self, callback):
        self.stage_cb = callback

    def calibrate_quick(self):
        return None

    def has_calibration_failed(self):
        return self.failed

    def import_alpha(self, nfb):
        return None


class _BridgeLite:
    locator = object()
    lib = object()


class _BatteryDevice:
    def __init__(self, battery_value):
        self._battery_value = battery_value

    def get_battery_charge(self):
        return self._battery_value


class _ChannelNamesPacket:
    def __init__(self, names):
        self._names = list(names)

    def __len__(self):
        return len(self._names)

    def get_name_by_index(self, index):
        return self._names[index]


class _MetadataDevice:
    def __init__(self, sample_rate, channel_names):
        self._sample_rate = sample_rate
        self._channel_names = _ChannelNamesPacket(channel_names)

    def get_eeg_sample_rate(self):
        return self._sample_rate

    def get_channel_names(self):
        return self._channel_names


class _ResistancePacket:
    def __init__(self, pairs):
        self._pairs = list(pairs)

    def __len__(self):
        return len(self._pairs)

    def get_channel_name(self, index):
        return self._pairs[index][0]

    def get_value(self, index):
        return self._pairs[index][1]


class TrainingGameControllerTests(unittest.TestCase):
    def _calibrate(self, controller):
        controller.begin_calibration()
        for _ in range(20):
            snapshot = controller.add_calibration_sample(50.0, 50.0, True)
        self.assertIsNotNone(snapshot.conc_baseline)
        self.assertIsNotNone(snapshot.relax_baseline)
        controller.start_game()

    def _set_bubble_board(self, controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=8):
        padded_rows = [list(row) for row in rows]
        while len(padded_rows) < controller.VISIBLE_ROWS:
            padded_rows.append([None for _ in range(len(rows[0]))])
        controller._board = padded_rows
        controller._columns = len(rows[0])
        palette = [current_bubble, next_bubble] + [cell for row in rows for cell in row if cell is not None]
        controller._palette = list(dict.fromkeys(palette))
        controller._current_bubble = current_bubble
        controller._next_bubble = next_bubble
        controller._aim_slot = aim_slot
        controller._shots_left = shots_left
        controller._score = 0
        controller._combo = 0
        controller._best_combo = 0
        controller._danger_steps = 0
        controller._ceiling_cursor = 0
        controller._spawn_cursor = 0
        controller._overlay_kind = None
        controller._overlay_title = ""
        controller._overlay_subtitle = ""
        controller._overlay_timer = 0
        controller._pending_outcome = None
        controller._launcher_zone_row = controller.VISIBLE_ROWS - 2
        controller._star_thresholds = [2000, 4000, 6000]
        controller._score_popups = []
        controller._message = ""
        controller._view_state = controller._bubble_view_state()

    def _set_cascade_board(self, controller, rows, blockers=None, specials=None):
        controller._grid_size = len(rows)
        controller._board = [cell for row in rows for cell in row]
        controller._blockers = set(blockers or set())
        controller._specials = dict(specials or {})
        controller._legal_swaps = controller._compute_legal_swaps(controller._board)
        controller._swap_index = 0
        controller._phase = "swap_select"
        controller._cascade_depth = 0
        controller._message = ""
        controller._view_state = controller._cascade_view_state()

    def _hold_arm_state(self, controller, attention, relaxation, repetitions, elapsed_seconds):
        snapshot = None
        for _ in range(repetitions):
            snapshot = controller.update_gameplay(
                attention,
                relaxation,
                valid=True,
                stale=False,
                elapsed_seconds=elapsed_seconds,
            )
        return snapshot

    def test_active_specs_include_arcade_games(self):
        active_ids = {spec.game_id for spec in active_training_specs()}
        self.assertTrue({"space_shooter", "jump_ball", "neuro_racer", "neon_drift_arena", "bubble_burst"}.issubset(active_ids))
        self.assertIn("full_reboot", active_ids)
        self.assertIn("candy_cascade", active_ids)
        self.assertIn("prosthetic_arm", active_ids)

    def test_calm_current_rewards_relaxation(self):
        controller = CalmCurrentController()
        self._calibrate(controller)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertEqual(snapshot.direction, "flow")
        self.assertGreater(controller.view_state["distance"], 0.0)

    def test_calm_current_artifacts_pause_progression(self):
        controller = CalmCurrentController()
        self._calibrate(controller)
        start_distance = controller.view_state["distance"]

        snapshot = controller.update_gameplay(49.0, 53.0, valid=False, stale=False, elapsed_seconds=1.0)
        self.assertIn("artifacts", snapshot.blocked_reason.lower())
        self.assertEqual(start_distance, controller.view_state["distance"])

    def test_full_reboot_relaxation_advances_sleep_stage(self):
        controller = FullRebootController()
        self._calibrate(controller)
        controller._calm_depth = controller._target_depth - 6.0

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=6.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=6.0)

        self.assertEqual(snapshot.direction, "flow")
        self.assertTrue(snapshot.level_completed)

    def test_full_reboot_stale_metrics_pause_progression(self):
        controller = FullRebootController()
        self._calibrate(controller)
        start_depth = controller.view_state["calm_depth"]

        snapshot = controller.update_gameplay(49.0, 52.0, valid=False, stale=True, elapsed_seconds=2.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_depth, controller.view_state["calm_depth"])

    def test_full_reboot_focus_spikes_raise_restlessness(self):
        controller = FullRebootController()
        self._calibrate(controller)
        start_restlessness = controller.view_state["restlessness"]

        controller.update_gameplay(53.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)
        snapshot = controller.update_gameplay(53.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertGreater(controller.view_state["restlessness"], start_restlessness)
        self.assertIn("soften", snapshot.control_hint.lower())

    def test_space_shooter_focus_and_relax_move_ship(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        start_slot = controller.view_state["ship_slot"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["ship_slot"], start_slot + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["ship_slot"], start_slot)

    def test_space_shooter_steady_burst_destroys_aligned_enemy(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._enemies = [
            {"slot": controller.view_state["ship_slot"], "y": 66.0, "hp": 1, "max_hp": 1, "drop": None, "score": 60, "speed": 0.0}
        ]
        controller._projectiles = []
        controller._view_state = controller._space_view_state()

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["destroyed"], 1)
        self.assertGreater(controller.view_state["burst_ticks"], 0)

    def test_space_shooter_pickups_modify_weapon_and_hull(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._weapon_level = 1
        controller._hull = 2
        controller._pickups = [
            {"slot": controller.view_state["ship_slot"], "y": 96.0, "kind": "weapon", "ticks": 4},
            {"slot": controller.view_state["ship_slot"], "y": 90.0, "kind": "repair", "ticks": 4},
        ]

        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(controller.view_state["weapon_level"], 2)
        self.assertEqual(controller.view_state["hull"], 3)

    def test_space_shooter_wave_clear_uses_overlay_before_progression(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        controller._enemies = []
        controller._projectiles = []
        controller._pickups = []
        controller._view_state = controller._space_view_state()

        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "wave_clear")

        for _ in range(5):
            snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["wave_index"], 1)

    def test_jump_ball_focus_clears_obstacle(self):
        controller = JumpBallController()
        self._calibrate(controller)
        controller._progress = 15.0

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertIn(snapshot.recommended_label, {"Jump charged", "Land clean", "Preserve the combo", "Hold rhythm"})
        self.assertGreaterEqual(controller.view_state["cleared"], 1)

    def test_neuro_racer_focus_and_relax_steer_between_lanes(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        start_lane = controller.view_state["lane"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["lane"], start_lane + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["lane"], start_lane)

    def test_neuro_racer_steady_nitro_consumes_charge_and_raises_speed(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._nitro = 50.0
        start_speed = controller.view_state["speed"]

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(snapshot.direction, "steady")
        self.assertGreater(controller.view_state["speed"], start_speed)
        self.assertLess(controller.view_state["nitro"], 50.0)

    def test_neuro_racer_collisions_reduce_stability_and_break_streaks(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._lane = 1
        controller._streak = 3
        controller._best_streak = 3
        controller._traffic = [{"lane": 1, "gap": 12.0, "speed": 56.0, "value": 45}]
        start_stability = controller.view_state["stability"]

        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertLess(controller.view_state["stability"], start_stability)
        self.assertEqual(controller.view_state["streak"], 0)
        self.assertEqual(controller.view_state["collisions"], 1)

    def test_neuro_racer_finish_overlay_before_progression(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        controller._distance = controller._finish_distance
        controller._view_state = controller._racer_view_state()

        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=8.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "finish")

        for _ in range(7):
            snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=8.0)

        self.assertTrue(snapshot.level_completed)
        self.assertEqual(controller.current_level_number, 2)

    def test_neon_drift_arena_focus_and_relax_shift_kart_between_lanes(self):
        controller = NeonDriftArenaController()
        self._calibrate(controller)
        start_lane = controller.view_state["kart_lane"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["kart_lane"], start_lane + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["kart_lane"], start_lane)

    def test_neon_drift_arena_steady_boost_consumes_charge(self):
        controller = NeonDriftArenaController()
        self._calibrate(controller)
        controller._boost_meter = 52.0
        start_progress = controller.view_state["track_progress"]

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(snapshot.direction, "boost")
        self.assertGreater(controller.view_state["track_progress"], start_progress)
        self.assertGreater(controller.view_state["boost_ticks"], 0)
        self.assertLess(controller.view_state["boost_meter"], 52.0)

    def test_neon_drift_arena_hazard_hit_resets_combo_and_drains_score(self):
        controller = NeonDriftArenaController()
        self._calibrate(controller)
        controller._lane = 2
        controller._drift_bias = 0.0
        controller._combo = 4
        controller._best_combo = 4
        controller._score = 180
        controller._items = [
            {
                "type": "hazard",
                "distance": 9.0,
                "lane": 2.0,
                "width": 0.9,
                "sway": 0.0,
                "penalty": 40,
                "resolved": False,
            }
        ]
        controller._view_state = controller._arena_view_state()

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=2.0)

        self.assertEqual(controller.view_state["hazard_hits"], 1)
        self.assertEqual(controller.view_state["combo"], 0)
        self.assertLess(controller.view_state["score"], 180)

    def test_neon_drift_arena_completion_uses_overlay_before_level_progression(self):
        controller = NeonDriftArenaController()
        self._calibrate(controller)
        controller._target_collectibles = 1
        controller._target_score = 20
        controller._items = [
            {
                "type": "tile",
                "distance": 8.0,
                "lane": float(controller._lane),
                "value": 28,
                "style": "violet",
                "sway": 0.0,
                "width": 0.62,
                "resolved": False,
            }
        ]
        controller._view_state = controller._arena_view_state()

        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "success")

        for _ in range(7):
            snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=3.0)

        self.assertTrue(snapshot.level_completed)
        self.assertEqual(controller.current_level_number, 2)

    def test_space_shooter_stale_metrics_pause_progression(self):
        controller = SpaceShooterController()
        self._calibrate(controller)
        start_enemies = [dict(enemy) for enemy in controller.view_state["enemies"]]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_enemies, controller.view_state["enemies"])

    def test_neuro_racer_stale_metrics_pause_progression(self):
        controller = NeuroRacerController()
        self._calibrate(controller)
        start_distance = controller.view_state["distance"]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_distance, controller.view_state["distance"])

    def test_bubble_burst_focus_and_relax_move_aim(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        start_slot = controller.view_state["aim_slot"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["aim_slot"], start_slot + 1)

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["aim_slot"], start_slot)

    def test_bubble_burst_steady_fire_consumes_shot_and_changes_board(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [[None, None, None, None, None, None] for _ in range(controller.VISIBLE_ROWS)]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=5)
        start_board = [list(row) for row in controller.view_state["board"]]

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["shots_left"], 4)
        self.assertNotEqual(start_board, controller.view_state["board"])

    def test_bubble_burst_pops_match_and_drops_floating_cluster(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [
            ["red", None, "red", None, None, None],
            [None, "green", "green", None, None, None],
            [None, "green", None, None, None, None],
        ]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=6)

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        top_rows = controller.view_state["board"][:3]
        self.assertEqual(controller.view_state["score"], 1800)
        self.assertTrue(all(cell is None for row in top_rows for cell in row))

    def test_bubble_burst_board_clear_uses_overlay_before_completion(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [
            ["red", None, "red", None, None, None],
            [None, None, None, None, None, None],
        ]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=4)

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["overlay_kind"], "board_clear")

        for _ in range(7):
            snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertTrue(snapshot.level_completed)

    def test_bubble_burst_stale_metrics_pause_progression(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        start_board = [list(row) for row in controller.view_state["board"]]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_board, controller.view_state["board"])

    def test_bubble_burst_shot_exhaustion_records_incomplete_level(self):
        controller = BubbleBurstController()
        self._calibrate(controller)
        rows = [
            [None, None, None, None, None, None],
            [None, None, None, None, None, None],
        ]
        self._set_bubble_board(controller, rows, current_bubble="red", next_bubble="green", aim_slot=1, shots_left=1)

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.direction, "fire")
        self.assertEqual(controller.view_state["overlay_kind"], "failure")

        for _ in range(7):
            snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        result = controller.finish_run(None, aborted=False)
        self.assertTrue(snapshot.run_completed)
        self.assertFalse(result.level_results[0].completed)

    def test_pattern_recall_preview_blocks_input(self):
        controller = PatternRecallController()
        self._calibrate(controller)

        snapshot = controller.update_gameplay(55.0, 48.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.phase, "preview")
        self.assertIn("preview", snapshot.control_hint.lower())

    def test_pattern_recall_chunk_retry_resets_only_current_chunk(self):
        controller = PatternRecallController()
        self._calibrate(controller)
        controller._preview_ticks = 0
        controller._selected_index = controller._sequence[0]
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=2.0)
        controller._selected_index = controller._sequence[1]
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        controller.update_gameplay(50.1, 50.0, valid=True, stale=False, elapsed_seconds=3.0)
        self.assertEqual(controller.view_state["confirmed_count"], 2)

        controller._selected_index = 6
        controller.update_gameplay(50.2, 50.1, valid=True, stale=False, elapsed_seconds=4.0)
        snapshot = controller.update_gameplay(50.2, 50.1, valid=True, stale=False, elapsed_seconds=4.0)

        self.assertEqual(snapshot.phase, "chunk_retry")
        self.assertEqual(controller.view_state["confirmed_count"], 2)

    def test_candy_cascade_focus_and_relax_cycle_legal_swaps(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        start_index = controller.view_state["swap_index"]

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)
        self.assertEqual(snapshot.direction, "right")
        self.assertEqual(controller.view_state["swap_index"], (start_index + 1) % controller.view_state["legal_move_count"])

        controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        snapshot = controller.update_gameplay(49.0, 52.0, valid=True, stale=False, elapsed_seconds=2.0)
        self.assertEqual(snapshot.direction, "left")
        self.assertEqual(controller.view_state["swap_index"], start_index)

    def test_candy_cascade_confirm_swap_clears_basic_match(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["berry", "berry", "lemon", "mint", "sky"],
            ["lemon", "mint", "berry", "peach", "sky"],
            ["peach", "berry", "mint", "sky", "lemon"],
            ["mint", "lemon", "sky", "berry", "peach"],
            ["sky", "peach", "lemon", "mint", "berry"],
        ]
        self._set_cascade_board(controller, rows)
        controller._swap_index = controller._legal_swaps.index((6, 7))

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertEqual(snapshot.direction, "confirm")
        self.assertGreater(controller.view_state["score"], 0)

    def test_candy_cascade_four_match_creates_single_striped_special(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["berry", "berry", "berry", "mint", "sky"],
            ["lemon", "mint", "sky", "berry", "peach"],
            ["peach", "lemon", "mint", "sky", "berry"],
            ["mint", "peach", "lemon", "berry", "sky"],
            ["sky", "berry", "peach", "lemon", "mint"],
        ]
        self._set_cascade_board(controller, rows)
        controller._swap_index = controller._legal_swaps.index((3, 8))

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertEqual(len(controller.view_state["special_cells"]), 1)
        self.assertEqual(controller.view_state["special_cells"][8], "row")

    def test_candy_cascade_striped_special_clears_row_and_blockers(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["sky", "peach", "mint", "lemon", "berry"],
            ["lemon", "berry", "berry", "berry", "sky"],
            ["peach", "mint", "lemon", "sky", "berry"],
            ["mint", "lemon", "sky", "berry", "peach"],
            ["berry", "sky", "peach", "mint", "lemon"],
        ]
        self._set_cascade_board(controller, rows, blockers={5, 6, 7, 8, 9}, specials={7: "row"})

        controller._resolve_board(8)
        controller._view_state = controller._cascade_view_state()

        self.assertEqual(controller.view_state["remaining_blockers"], 0)
        self.assertGreater(controller.view_state["score"], 0)

    def test_candy_cascade_level_completion_requires_zero_blockers(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        rows = [
            ["berry", "berry", "lemon", "mint", "sky"],
            ["lemon", "mint", "berry", "peach", "sky"],
            ["peach", "berry", "mint", "sky", "lemon"],
            ["mint", "lemon", "sky", "berry", "peach"],
            ["sky", "peach", "lemon", "mint", "berry"],
        ]
        self._set_cascade_board(controller, rows, blockers={24})
        controller._target_score = 20
        controller._score = 20
        controller._swap_index = controller._legal_swaps.index((6, 7))

        controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)
        snapshot = controller.update_gameplay(50.0, 50.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertFalse(snapshot.level_completed)
        self.assertEqual(controller.view_state["remaining_blockers"], 1)

    def test_candy_cascade_rebalances_when_no_legal_moves_exist(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        controller._legal_swaps = []

        controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=1.0)

        self.assertGreater(controller.view_state["legal_move_count"], 0)

    def test_candy_cascade_stale_metrics_pause_progression(self):
        controller = CandyCascadeController()
        self._calibrate(controller)
        start_board = list(controller.view_state["candies"])
        start_score = controller.view_state["score"]

        snapshot = controller.update_gameplay(52.0, 49.0, valid=False, stale=True, elapsed_seconds=1.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_board, controller.view_state["candies"])
        self.assertEqual(start_score, controller.view_state["score"])

    def test_prosthetic_arm_sequence_advances_and_completes_level(self):
        controller = ProstheticArmController()
        self._calibrate(controller)

        self._hold_arm_state(controller, 20.0, 58.0, 4, 2.0)
        self.assertEqual(controller.view_state["sequence_index"], 1)

        self._hold_arm_state(controller, 62.0, 24.0, 7, 8.0)
        self.assertEqual(controller.view_state["sequence_index"], 2)

        self._hold_arm_state(controller, 18.0, 60.0, 7, 14.0)
        snapshot = self._hold_arm_state(controller, 64.0, 22.0, 7, 20.0)

        self.assertTrue(snapshot.level_completed)
        self.assertGreaterEqual(controller.current_level_number, 2)

    def test_prosthetic_arm_stale_metrics_pause_sequence(self):
        controller = ProstheticArmController()
        self._calibrate(controller)
        start_index = controller.view_state["sequence_index"]

        snapshot = controller.update_gameplay(62.0, 24.0, valid=False, stale=True, elapsed_seconds=3.0)

        self.assertIn("stale", snapshot.blocked_reason.lower())
        self.assertEqual(start_index, controller.view_state["sequence_index"])

    def test_capsule_backend_normalizes_metrics_and_arduino_falls_back_without_serial(self):
        adapter = CapsuleMetricAdapter()
        captured = []
        adapter.metrics_changed.connect(captured.append)
        adapter.ingest_productivity({"concentrationScore": 54.0, "relaxationScore": 31.0})

        self.assertEqual(captured[-1]["dominant_state"], "Focused")

        with patch("prosthetic_arm.arduino_arm.SERIAL_OK", False):
            arm = ArduinoArmController()
            self.assertFalse(arm.connect_device("COM3"))

    def test_training_screen_injects_balance_panel_and_hides_shared_footer(self):
        with patch("gui.training_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            screen = TrainingScreen()
        try:
            screen._select_game("space_shooter")
            controller = screen._controller
            self._calibrate(controller)
            screen._level_started_at = time.monotonic() - 5.0

            snapshot = controller.update_gameplay(52.0, 49.0, valid=True, stale=False, elapsed_seconds=5.0)
            screen._update_gameplay_labels(snapshot)

            state = screen._space_shooter_widget._state
            self.assertIn("balance_panel", state)
            self.assertEqual(state["balance_panel"]["timer_text"], "00:47")
            self.assertIn("status", state["balance_panel"])
            self.assertTrue(screen._game_bar.isHidden())
            self.assertTrue(screen._game_status_lbl.isHidden())
            self.assertTrue(screen._game_time_lbl.isHidden())
        finally:
            screen.close()

    def test_training_screen_exposes_prosthetic_arm_flow_and_arm_lab(self):
        with patch("gui.training_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            screen = TrainingScreen()
        try:
            screen.on_productivity({"concentrationScore": 48.0, "relaxationScore": 34.0})
            screen._show_detail("prosthetic_arm")
            self.assertFalse(screen._detail_arm_lab_btn.isHidden())

            screen._show_arm_lab()
            self.assertIs(screen._stack.currentWidget(), screen._arm_lab_page)

            controller = screen._controller
            self._calibrate(controller)
            screen._level_started_at = time.monotonic() - 4.0
            snapshot = controller.update_gameplay(24.0, 58.0, valid=True, stale=False, elapsed_seconds=4.0)
            screen._update_gameplay_labels(snapshot)

            state = screen._prosthetic_arm_widget._state
            self.assertEqual(state["backend_mode"], "capsule")
            self.assertIn("target_state", state)
            self.assertIn("history", state)
        finally:
            screen.close()


class DashboardMemsFilteringTests(unittest.TestCase):
    def test_dashboard_no_longer_exposes_mems_panels(self):
        screen = DashboardScreen()
        try:
            self.assertEqual(screen._sections, {})
            self.assertFalse(hasattr(screen, "_accel_chart"))
            self.assertFalse(hasattr(screen, "_gyro_chart"))
            self.assertFalse(hasattr(screen, "_rhythms_pie"))
        finally:
            screen.close()

    def test_mems_screen_owns_accel_gyro_and_rhythms_sections(self):
        screen = MemsScreen()
        try:
            self.assertEqual(
                set(screen._sections.keys()),
                {"accelerometer", "gyroscope", "rhythms_diagram"},
            )
            screen.show_section("rhythms_diagram")
            APP.processEvents()
            self.assertTrue(screen._sections["rhythms_diagram"].is_expanded())
        finally:
            screen.close()

    def test_main_window_routes_mems_actions_to_dedicated_page(self):
        with patch("gui.main_window.CapsuleBridge", _BridgeStub), patch(
            "gui.main_window.DeviceManager", _DeviceManagerStub
        ), patch("gui.main_window.SessionRecorder", _RecorderStub), patch(
            "gui.main_window.ConnectionScreen", _ConnectionScreenStub
        ), patch(
            "gui.main_window.CalibrationScreen", _CalibrationScreenStub
        ), patch(
            "gui.main_window.DashboardScreen", _DashboardScreenStub
        ), patch(
            "gui.main_window.MemsScreen", _MemsScreenStub
        ), patch(
            "gui.main_window.TrainingScreen", _TrainingScreenStub
        ), patch(
            "gui.main_window.SessionsScreen", _SessionsScreenStub
        ), patch(
            "gui.main_window.QTimer.singleShot", side_effect=lambda _ms, fn: fn()
        ):
            window = MainWindow()
            try:
                menu_actions = {action.text(): action for action in window.menuBar().actions()}
                self.assertNotIn(
                    "Rhythms Diagram",
                    [action.text() for action in menu_actions["EEG"].menu().actions()],
                )
                self.assertIn(
                    "Rhythms Diagram",
                    [action.text() for action in menu_actions["MEMS"].menu().actions()],
                )
                window._show_mems("Rhythms Diagram")
                self.assertEqual(window._stack.currentIndex(), PAGE_MEMS)
                self.assertEqual(window._mems_screen.last_section, "rhythms_diagram")
            finally:
                window.close()

    def test_main_window_routes_phaseon_menu_to_in_app_page(self):
        with patch("gui.main_window.CapsuleBridge", _BridgeStub), patch(
            "gui.main_window.DeviceManager", _DeviceManagerStub
        ), patch("gui.main_window.SessionRecorder", _RecorderStub), patch(
            "gui.main_window.ConnectionScreen", _ConnectionScreenStub
        ), patch(
            "gui.main_window.CalibrationScreen", _CalibrationScreenStub
        ), patch(
            "gui.main_window.DashboardScreen", _DashboardScreenStub
        ), patch(
            "gui.main_window.MemsScreen", _MemsScreenStub
        ), patch(
            "gui.main_window.TrainingScreen", _TrainingScreenStub
        ), patch(
            "gui.main_window.SessionsScreen", _SessionsScreenStub
        ), patch(
            "gui.main_window.PhaseonScreen", _PhaseonScreenStub
        ), patch(
            "gui.main_window.PhaseonRuntime", _PhaseonRuntimeStub
        ):
            window = MainWindow()
            try:
                menu_actions = {action.text(): action for action in window.menuBar().actions()}
                self.assertIn("Phaseon", menu_actions)
                window._show_phaseon()
                self.assertEqual(window._stack.currentIndex(), PAGE_PHASEON)
                self.assertIsInstance(window._phaseon_screen, _PhaseonScreenStub)
            finally:
                window.close()

    def test_filter_object_reports_unavailable_when_mne_is_missing(self):
        filt = EEGDisplayFilter(loader=lambda: (None, None, RuntimeError("missing mne")))
        self.assertFalse(filt.available)
        self.assertEqual(filt.status_text(True), "Unavailable")

    def test_filter_object_uses_mne_style_backend_when_available(self):
        def fake_filter_data(data, **kwargs):
            return data * 0.5

        def fake_notch_filter(data, **kwargs):
            return data * 0.5

        filt = EEGDisplayFilter(loader=lambda: (fake_filter_data, fake_notch_filter, None))
        raw = np.linspace(-20.0, 20.0, 600)
        filtered = filt.apply(raw, sample_rate=250.0)
        self.assertTrue(filt.available)
        self.assertEqual(filt.status_text(True), "On")
        self.assertFalse(np.allclose(raw, filtered))

    def test_electrode_table_applies_filtered_visible_signal(self):
        table = ElectrodeTable()
        try:
            timestamps_ms = [index * 4 for index in range(500)]
            noisy = np.sin(np.linspace(0.0, 60.0, 500)) * 120.0
            packet = _FakeEEGTimedData([noisy, noisy * 0.5], timestamps_ms)

            table.add_eeg_data(packet)
            table.set_display_filter(False, lambda data, sample_rate=None: data)
            table.refresh()
            raw_avg = table._avg_uv["O1-T3"]

            table.set_display_filter(True, lambda data, sample_rate=None: np.zeros_like(data))
            table.refresh()
            filtered_avg = table._avg_uv["O1-T3"]

            self.assertGreater(raw_avg, filtered_avg)
            self.assertAlmostEqual(filtered_avg, 0.0, places=3)
        finally:
            table.close()

    def test_electrode_table_prefers_processed_signal_when_available(self):
        table = ElectrodeTable()
        try:
            timestamps_ms = [index * 4 for index in range(200)]
            raw = np.sin(np.linspace(0.0, 40.0, 200)) * 400.0
            processed = np.linspace(-25.0, 25.0, 200)
            packet = _FakeEEGTimedData(
                [raw, raw * 0.5],
                timestamps_ms,
                processed_channels=[processed, processed * 0.5],
            )

            table.add_eeg_data(packet)
            table.refresh()

            visible = np.asarray(table._display_buffers[0], dtype=float)
            self.assertTrue(np.allclose(visible[-10:], processed[-10:]))
        finally:
            table.close()

    def test_electrode_table_accepts_sample_rate_and_channel_labels(self):
        table = ElectrodeTable()
        try:
            table.set_sample_rate(256.0)
            table.set_channel_names(["O1T3", "O2-T4"])
            self.assertAlmostEqual(table._sample_rate_hz, 256.0)
            self.assertEqual(table._rows[0]["name_lbl"].text(), "O1-T3")
            self.assertEqual(table._rows[1]["name_lbl"].text(), "O2-T4")
        finally:
            table.close()

    def test_main_window_extract_eeg_snapshot_preserves_microvolt_values(self):
        timestamps_ms = [0.0, 4.0, 8.0, 12.0]
        raw = np.asarray([12.0, -18.0, 24.0, -9.0], dtype=float)
        processed = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=float)
        packet = _FakeEEGTimedData(
            [raw, raw * 0.5],
            timestamps_ms,
            processed_channels=[processed, processed * 0.5],
        )

        snapshot = MainWindow._extract_eeg_snapshot(packet)

        self.assertEqual(snapshot["timestampsMs"], timestamps_ms)
        self.assertEqual(snapshot["channels"][0], raw.tolist())
        self.assertEqual(snapshot["processed_channels"][0], processed.tolist())

    def test_main_window_extract_psd_snapshot_returns_average_and_summary(self):
        psd = _FakePSDData(
            [4.0, 6.0, 8.0, 10.0, 12.0, 18.0],
            [
                [1.0, 2.0, 6.0, 4.0, 2.0, 1.0],
                [1.0, 4.0, 8.0, 6.0, 4.0, 2.0],
            ],
        )

        snapshot = MainWindow._extract_psd_snapshot(psd)

        self.assertEqual(snapshot["freqs"], [4.0, 6.0, 8.0, 10.0, 12.0, 18.0])
        self.assertEqual(len(snapshot["avg_power"]), 6)
        self.assertIn("alpha", snapshot["band_powers"])
        self.assertIn("alpha_peak", snapshot["peak_frequencies"])
        self.assertAlmostEqual(snapshot["peak_frequencies"]["alpha_peak"], 8.0)

    def test_dashboard_psd_snapshot_path_uses_precomputed_summary(self):
        screen = DashboardScreen()
        try:
            screen.set_streaming_active(True)
            screen.set_view_active(True)
            snapshot = {
                "freqs": [4.0, 6.0, 8.0, 10.0, 12.0],
                "avg_power": [1.0, 2.0, 6.0, 4.0, 2.0],
                "band_powers": {"alpha": 10.0, "beta": 3.0, "theta": 2.0, "smr": 1.0},
                "peak_frequencies": {"alpha_peak": 8.0, "beta_peak": 18.0, "theta_peak": 6.0},
                "received_at": time.monotonic(),
            }

            with patch("gui.dashboard_screen.compute_band_powers", side_effect=AssertionError("should not recompute")), patch(
                "gui.dashboard_screen.compute_peak_frequencies",
                side_effect=AssertionError("should not recompute"),
            ):
                screen.on_psd_snapshot(snapshot)

            self.assertEqual(screen._latest_band_powers["alpha"], 10.0)
            self.assertEqual(screen._peak_labels["alpha_peak"].text(), "8.0 Hz")
        finally:
            screen.close()

    def test_electrode_table_accepts_preextracted_eeg_snapshot(self):
        table = ElectrodeTable()
        try:
            timestamps_ms = [index * 4.0 for index in range(200)]
            raw = np.sin(np.linspace(0.0, 20.0, 200)) * 80.0
            packet = _FakeEEGTimedData([raw, raw * 0.5], timestamps_ms)
            snapshot = MainWindow._extract_eeg_snapshot(packet)

            table.add_eeg_snapshot(snapshot)
            table.refresh()

            self.assertTrue(len(table._display_buffers[0]) > 0)
            self.assertGreater(table._avg_uv["O1-T3"], 0.0)
        finally:
            table.close()


class CalibrationStabilityTests(unittest.TestCase):
    def _build_manager(self):
        prod = _CalFakeProdHandler()
        phy = _CalFakePhyHandler()
        manager = CalibrationManager(object(), object(), prod, phy)
        return manager, prod, phy

    def test_scalar_helpers_normalize_ctypes_like_values(self):
        class _EnumLike:
            def __init__(self, value):
                self.value = value

        self.assertEqual(coerce_int(_EnumLike(7), default=-1), 7)
        self.assertEqual(coerce_int(b"\x02\x00\x00\x00", default=-1), 2)
        self.assertAlmostEqual(coerce_float("12.5", default=0.0), 12.5)
        self.assertEqual(coerce_percent(b"\x32\x00\x00\x00", default=-1), 50)
        self.assertEqual(coerce_percent(b"\x80\xf2\xaeI", default=-1), -1)

    def test_quick_calibration_emits_ready_then_finishes_after_background_baselines(self):
        manager, prod, phy = self._build_manager()
        stages = []
        progress = []
        ready = []
        completed = []
        manager.stage_changed.connect(lambda stage, text: stages.append((stage, text)))
        manager.progress_updated.connect(progress.append)
        manager.quick_ready.connect(ready.append)
        manager.calibration_complete.connect(completed.append)

        with patch("calibration.calibration_manager.Calibrator", _CalFakeCalibrator), patch(
            "calibration.calibration_manager.nfb_to_dict",
            return_value={
                "individualFrequency": 10.25,
                "individualPeakFrequency": 10.5,
                "lowerFrequency": 8.0,
                "upperFrequency": 12.0,
            },
        ), patch(
            "calibration.calibration_manager.prod_baselines_to_dict",
            return_value={"focus": 1.0},
        ), patch(
            "calibration.calibration_manager.phy_baselines_to_dict",
            return_value={"relaxation": 1.0},
        ), patch("calibration.calibration_manager.save_calibration"):
            manager.start_quick("SERIAL-1")
            self.assertEqual(stages[0][0], manager.STAGE_NFB)

            manager._on_nfb_finished(None, object())
            APP.processEvents()
            self.assertEqual(prod.started, 1)
            self.assertEqual(phy.started, 0)

            prod.baselines_updated.emit(object())
            APP.processEvents()
            self.assertEqual(phy.started, 1)

            phy.baselines_updated.emit(object())
            APP.processEvents()

        self.assertEqual([stage for stage, _ in stages], [1, 2, 3])
        self.assertTrue(all(left <= right for left, right in zip(progress, progress[1:])))
        self.assertAlmostEqual(progress[-1], 1.0)
        self.assertEqual(ready[-1]["mode"], manager.MODE_QUICK)
        self.assertTrue(ready[-1]["applied"])
        self.assertEqual(completed[-1]["mode"], manager.MODE_QUICK)
        self.assertTrue(completed[-1]["applied"])

    def test_detect_mode_finishes_after_nfb_only(self):
        manager, prod, phy = self._build_manager()
        completed = []
        manager.calibration_complete.connect(completed.append)

        with patch("calibration.calibration_manager.Calibrator", _CalFakeCalibrator), patch(
            "calibration.calibration_manager.nfb_to_dict",
            return_value={"individualFrequency": 9.75},
        ):
            manager.start_detect("SERIAL-2")
            manager._on_nfb_finished(None, object())

        self.assertEqual(prod.started, 0)
        self.assertEqual(phy.started, 0)
        self.assertEqual(completed[-1]["mode"], manager.MODE_DETECT)
        self.assertFalse(completed[-1]["applied"])

    def test_quick_calibration_survives_serialization_or_save_errors(self):
        manager, prod, phy = self._build_manager()
        completed = []
        failures = []
        manager.calibration_complete.connect(completed.append)
        manager.calibration_failed.connect(failures.append)

        with patch("calibration.calibration_manager.Calibrator", _CalFakeCalibrator), patch(
            "calibration.calibration_manager.nfb_to_dict",
            side_effect=ValueError("invalid literal for int() with base 10"),
        ), patch(
            "calibration.calibration_manager.prod_baselines_to_dict",
            side_effect=ValueError("bad prod baseline"),
        ), patch(
            "calibration.calibration_manager.phy_baselines_to_dict",
            side_effect=ValueError("bad phy baseline"),
        ), patch(
            "calibration.calibration_manager.save_calibration",
            side_effect=ValueError("save failed"),
        ):
            manager.start_quick("SERIAL-3")
            nfb = type(
                "NFB",
                (),
                {
                    "individualFrequency": 10.0,
                    "individualPeakFrequency": 10.5,
                    "lowerFrequency": 8.0,
                    "upperFrequency": 12.0,
                },
            )()
            manager._on_nfb_finished(None, nfb)
            prod.baselines_updated.emit(object())
            phy.baselines_updated.emit(object())

        self.assertFalse(failures)
        self.assertEqual(completed[-1]["mode"], manager.MODE_QUICK)
        self.assertTrue(completed[-1]["applied"])

    def test_quick_calibration_starts_followup_baselines_in_background(self):
        manager, prod, phy = self._build_manager()
        ready = []
        manager.quick_ready.connect(ready.append)

        with patch("calibration.calibration_manager.Calibrator", _CalFakeCalibrator), patch(
            "calibration.calibration_manager.nfb_to_dict",
            return_value={"individualFrequency": 10.0},
        ):
            manager.start_quick("SERIAL-4")
            manager._on_nfb_finished(None, object())
            APP.processEvents()
            self.assertEqual(len(ready), 1)
            self.assertEqual(prod.started, 1)
            self.assertEqual(phy.started, 0)

    def test_quick_calibration_ignores_late_baseline_callbacks_after_background_completion(self):
        manager, prod, phy = self._build_manager()
        completed = []
        manager.calibration_complete.connect(completed.append)

        with patch("calibration.calibration_manager.Calibrator", _CalFakeCalibrator), patch(
            "calibration.calibration_manager.nfb_to_dict",
            return_value={"individualFrequency": 10.0},
        ), patch(
            "calibration.calibration_manager.prod_baselines_to_dict",
            return_value={"focus": 1.0},
        ), patch(
            "calibration.calibration_manager.phy_baselines_to_dict",
            return_value={"relaxation": 1.0},
        ):
            manager.start_quick("SERIAL-5")
            manager._on_nfb_finished(None, object())
            APP.processEvents()
            prod.baselines_updated.emit(object())
            APP.processEvents()
            phy.baselines_updated.emit(object())
            APP.processEvents()
            prod.baselines_updated.emit(object())
            phy.baselines_updated.emit(object())

        self.assertEqual(len(completed), 1)

    def test_device_manager_battery_path_ignores_invalid_values(self):
        manager = DeviceManager(_BridgeLite())
        captured = []
        manager.battery_updated.connect(captured.append)

        manager._on_battery(None, b"\x32\x00\x00\x00")
        manager._on_battery(None, b"\x80\xf2\xaeI")

        self.assertEqual(captured, [50])

        manager._device = _BatteryDevice(b"\x32\x00\x00\x00")
        self.assertEqual(manager.get_battery(), 50)

        manager._device = _BatteryDevice(b"\x80\xf2\xaeI")
        self.assertEqual(manager.get_battery(), -1)

    def test_device_manager_refreshes_eeg_metadata(self):
        manager = DeviceManager(_BridgeLite())
        manager._device = _MetadataDevice(256.0, ["O1T3", "O2-T4"])

        manager._refresh_eeg_metadata()

        self.assertEqual(manager.eeg_sample_rate, 256.0)
        self.assertEqual(manager.eeg_channel_names, ["O1-T3", "O2-T4"])

    def test_o1_resistance_alias_maps_numeric_channel_name(self):
        manager = DeviceManager(_BridgeLite())
        captured = []
        manager.resistance_updated.connect(captured.append)

        packet = _ResistancePacket(
            [
                ("01", 650000.0),
                ("T3", 1273000.0),
                ("T4", 2214000.0),
                ("O2", 889000.0),
            ]
        )
        manager._on_resist(None, packet)

        self.assertEqual(captured[-1]["O1"], 650000.0)

        screen = DashboardScreen()
        try:
            screen.on_resistance(captured[-1])
            self.assertEqual(screen._resist_labels["O1"].text(), "O1: 650 kΩ")
        finally:
            screen.close()

    def test_training_screen_shared_runtime_skips_duplicate_arm_backend_shutdown(self):
        runtime = _SharedRuntimeStub()
        with patch("gui.training_screen.AdaptiveMusicEngine.ensure_assets", return_value=None):
            screen = TrainingScreen(runtime=runtime)
        try:
            screen.on_productivity({"concentrationScore": 54.0, "relaxationScore": 28.0})
            self.assertEqual(runtime.capsule_backend.ingest_calls, 0)

            screen.shutdown()
            self.assertEqual(runtime.brainbit_backend.shutdown_calls, 0)
            self.assertEqual(runtime.arduino_arm.disconnect_calls, 0)
        finally:
            screen.close()


if __name__ == "__main__":
    unittest.main()
