"""Arcade game controllers (action-oriented neurofeedback games)."""
from __future__ import annotations

import math

from gui.eeg_game_base import GameplaySnapshot, TrainingLevel
from gui.training_games_base import (
    BaseTrainingController,
    DIR_LABELS,
    ARCADE_BALANCE_THRESHOLD,
    ARCADE_DELTA_THRESHOLD,
    ARCADE_STEADY_DEAD_ZONE,
)


class ArcadeTrainingController(BaseTrainingController):
    def _arcade_intent(self, conc_delta: float, relax_delta: float) -> str | None:
        balance = conc_delta - relax_delta
        if balance >= ARCADE_BALANCE_THRESHOLD and conc_delta >= ARCADE_DELTA_THRESHOLD:
            return "focus"
        if balance <= -ARCADE_BALANCE_THRESHOLD and relax_delta >= ARCADE_DELTA_THRESHOLD:
            return "relax"
        if abs(balance) <= ARCADE_STEADY_DEAD_ZONE:
            return "steady"
        return None

    def _arcade_snapshot(
        self,
        *,
        phase: str,
        phase_label: str,
        direction: str | None,
        blocked_reason: str,
        control_hint: str,
        conc_delta: float,
        relax_delta: float,
        moved: bool,
        level_completed: bool,
        run_completed: bool,
        recommended_label: str,
    ) -> GameplaySnapshot:
        balance = conc_delta - relax_delta
        return GameplaySnapshot(
            level_number=self.current_level_number,
            phase=phase,
            phase_label=phase_label,
            recommended_direction=direction,
            recommended_label=recommended_label,
            control_hint=blocked_reason or control_hint,
            direction=direction,
            direction_label=DIR_LABELS.get(direction, "Hold steady"),
            moved=moved,
            blocked_reason=blocked_reason,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            balance=balance,
            level_completed=level_completed,
            run_completed=run_completed,
            view_state=self._view_state,
        )


class TugOfWarController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Opening Pull", 75),
        TrainingLevel("System Pressure", 75),
        TrainingLevel("Boss Clash", 95),
    ]
    LEVEL_CONFIGS = [
        {"capture_target": 8, "velocity_decay": 0.80, "drive_scale": 0.028, "ai_base_pressure": 0.38, "ai_wave_pressure": 0.06, "wave_period": 9.0, "player_force_scale": 26.0, "relax_force_scale": 12.0, "pressure_level": 34.0},
        {"capture_target": 8, "velocity_decay": 0.78, "drive_scale": 0.031, "ai_base_pressure": 0.58, "ai_wave_pressure": 0.14, "wave_period": 7.0, "player_force_scale": 26.0, "relax_force_scale": 16.0, "pressure_level": 62.0},
        {"capture_target": 10, "velocity_decay": 0.74, "drive_scale": 0.034, "ai_base_pressure": 0.76, "ai_wave_pressure": 0.24, "wave_period": 5.5, "player_force_scale": 28.0, "relax_force_scale": 18.0, "pressure_level": 88.0},
    ]
    CAPTURE_THRESHOLD = 0.72

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.LEVEL_CONFIGS[self._level_index]
        self._capture_target = int(config["capture_target"])
        self._velocity_decay = float(config["velocity_decay"])
        self._drive_scale = float(config["drive_scale"])
        self._ai_base_pressure = float(config["ai_base_pressure"])
        self._ai_wave_pressure = float(config["ai_wave_pressure"])
        self._wave_period = float(config["wave_period"])
        self._player_force_scale = float(config["player_force_scale"])
        self._relax_force_scale = float(config["relax_force_scale"])
        self._pressure_level = float(config["pressure_level"])
        self._pressure_meter = self._pressure_level
        self._rope_position = 0.0
        self._rope_velocity = 0.0
        self._capture_streak = 0
        self._capture_owner: str | None = None
        self._player_score = 0.0
        self._system_score = 0.0
        self._player_force = 0.0
        self._system_force = 0.0
        self._advantage_side = "neutral"
        self._arena_energy = 38.0
        self._spark_intensity = 14.0
        self._rope_tension = 0.0
        self._message = self._target_message()
        self._view_state = self._tug_view_state()

    def update_gameplay(self, concentration: float, relaxation: float, valid: bool, stale: bool, elapsed_seconds: float) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        moved = False
        level_completed = False
        run_completed = False
        self._message = self._target_message()
        control_hint = self._target_hint()
        if stale:
            blocked_reason = "Metrics are stale. Tug of War paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Tug of War paused."
        else:
            ai_wave = self._ai_wave(elapsed_seconds)
            player_push = max(0.0, conc_delta) * self._player_force_scale
            system_push = ((self._ai_base_pressure + ai_wave) * 42.0) + (max(0.0, relax_delta) * self._relax_force_scale)
            self._player_force = max(0.0, min(100.0, player_push))
            self._system_force = max(0.0, min(100.0, system_push))
            tug_balance = max(-1.35, min(1.35, (self._system_force - self._player_force) / 100.0))
            self._pressure_meter = min(100.0, self._pressure_level + (ai_wave * 90.0))
            self._player_score += self._player_force * 0.085
            self._system_score += self._system_force * 0.085
            self._rope_velocity = (self._rope_velocity * self._velocity_decay) + (tug_balance * self._drive_scale)
            self._rope_position = max(-1.0, min(1.0, self._rope_position + self._rope_velocity))
            self._rope_tension = max(0.0, min(1.0, abs(self._rope_velocity) * 7.5 + abs(self._rope_position) * 0.35))
            self._arena_energy = max(22.0, min(100.0, 30.0 + (max(self._player_force, self._system_force) * 0.45) + (abs(self._rope_position) * 28.0)))
            self._spark_intensity = max(8.0, min(100.0, 10.0 + (self._rope_tension * 56.0) + ((self._capture_streak / max(1, self._capture_target)) * 18.0)))
            capture_owner = self._capture_owner_for_position()
            if capture_owner is not None:
                if capture_owner == self._capture_owner:
                    self._capture_streak += 1
                else:
                    self._capture_owner = capture_owner
                    self._capture_streak = 1
                self._message = f"{capture_owner.title()} side is capturing the rope."
            else:
                self._capture_owner = None
                self._capture_streak = max(0, self._capture_streak - 1)
            moved = abs(self._rope_velocity) > 0.001
            if self._capture_streak >= self._capture_target:
                if self._capture_owner == "player":
                    score = self._level_score(elapsed_seconds)
                    self._record_level_result(True, elapsed_seconds, score_override=score)
                    level_completed = True
                    run_completed = self._advance_level()
                    if not run_completed:
                        self._message = self._target_message()
                elif self._capture_owner == "system":
                    self._message = "The system overwhelmed the rope. This run ends here."
                    self._record_level_result(False, elapsed_seconds, score_override=0)
                    self._finished = True
                    run_completed = True
        self._advantage_side = self._current_advantage()
        self._view_state = self._tug_view_state(message=blocked_reason or self._message, conc_delta=conc_delta, relax_delta=relax_delta)
        direction = self._recommended_direction()
        recommended_label = {"player": "Player pull", "system": "System pressure"}.get(direction, "Hold center")
        return self._arcade_snapshot(phase="tug_of_war", phase_label=self.current_level.title, direction=direction, blocked_reason=blocked_reason, control_hint=control_hint, conc_delta=conc_delta, relax_delta=relax_delta, moved=moved, level_completed=level_completed, run_completed=run_completed, recommended_label=recommended_label)

    def _ai_wave(self, elapsed_seconds: float) -> float:
        if self._wave_period <= 0.0:
            return 0.0
        wave_phase = ((max(0.0, elapsed_seconds) / self._wave_period) * math.tau) - (math.pi / 2.0)
        return self._ai_wave_pressure * (0.5 + (0.5 * math.sin(wave_phase)))

    def _capture_owner_for_position(self) -> str | None:
        if self._rope_position <= -self.CAPTURE_THRESHOLD:
            return "player"
        if self._rope_position >= self.CAPTURE_THRESHOLD:
            return "system"
        return None

    def _recommended_direction(self) -> str | None:
        if self._player_force >= self._system_force + 6.0:
            return "player"
        if self._system_force >= self._player_force + 6.0:
            return "system"
        return None

    def _current_advantage(self) -> str:
        if self._capture_owner is not None:
            return self._capture_owner
        if self._rope_position <= -0.12:
            return "player"
        if self._rope_position >= 0.12:
            return "system"
        return "neutral"

    def _target_message(self) -> str:
        if self._level_index == 0:
            return "Concentrate to pull the knot into the Player zone before the system settles in."
        if self._level_index == 1:
            return "System pressure is rising. Hold concentration or the AI will drag the rope away."
        return "Boss Clash is active. Stay focused through every surge or the system takes the zone."

    def _target_hint(self) -> str:
        if self._level_index == 0:
            return "Concentration helps you pull. Relaxation gives the system a counter-pull."
        if self._level_index == 1:
            return "The system now applies stronger base pressure. Any relaxation gives it even more ground."
        return "Boss surges keep pushing from the system side. Stay concentrated to survive the wave windows."

    def _level_score(self, elapsed_seconds: float) -> float:
        elapsed_penalty = max(0.0, float(elapsed_seconds) - float(self.current_level.target_seconds))
        capture_bonus = (self._capture_streak / max(1.0, float(self._capture_target))) * 12.0
        duel_bonus = min(18.0, self._player_score / 10.0)
        tension_bonus = self._arena_energy * 0.18
        return 52.0 + capture_bonus + duel_bonus + tension_bonus - elapsed_penalty

    def _tug_view_state(self, *, message: str = "", conc_delta: float = 0.0, relax_delta: float = 0.0) -> dict:
        return {
            "mode": "tug_of_war",
            "headline": self.current_level.title,
            "rope_position": self._rope_position,
            "rope_tension": self._rope_tension,
            "player_force": self._player_force,
            "system_force": self._system_force,
            "player_score": int(round(self._player_score)),
            "system_score": int(round(self._system_score)),
            "capture_progress": min(1.0, self._capture_streak / max(1.0, float(self._capture_target))),
            "advantage_side": self._advantage_side,
            "pressure_level": self._pressure_meter,
            "arena_energy": self._arena_energy,
            "spark_intensity": self._spark_intensity,
            "music_scene": "arcade",
            "music_bias": max(-1.0, min(1.0, (self._system_force - self._player_force) / 100.0)),
            "message": message or self._message,
        }


class SpaceShooterController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Sector 1", 52),
        TrainingLevel("Sector 2", 62),
        TrainingLevel("Sector 3", 72),
    ]
    CONFIGS = [
        {
            "star_thresholds": [280, 520, 760],
            "wave_speed": 6.4,
            "waves": [
                [(1, -4.0, 1, None, 60), (3, -18.0, 1, None, 60), (5, -32.0, 1, "repair", 70)],
                [(2, -8.0, 1, None, 70), (4, -20.0, 1, "weapon", 80), (2, -34.0, 1, None, 70), (4, -46.0, 1, None, 70)],
                [(1, -10.0, 2, None, 120), (3, -22.0, 1, None, 80), (5, -34.0, 2, None, 120)],
            ],
        },
        {
            "star_thresholds": [360, 640, 920],
            "wave_speed": 7.2,
            "waves": [
                [(0, -6.0, 1, None, 70), (3, -20.0, 1, None, 70), (6, -34.0, 1, None, 70), (3, -48.0, 2, "weapon", 120)],
                [(1, -8.0, 1, None, 80), (2, -18.0, 1, None, 80), (4, -28.0, 1, None, 80), (5, -38.0, 1, "repair", 90), (3, -54.0, 2, None, 130)],
                [(2, -10.0, 2, None, 140), (3, -26.0, 3, None, 180), (4, -42.0, 2, None, 140)],
            ],
        },
        {
            "star_thresholds": [440, 760, 1080],
            "wave_speed": 8.0,
            "waves": [
                [(1, -4.0, 1, None, 80), (3, -16.0, 1, None, 80), (5, -28.0, 1, None, 80), (3, -40.0, 2, None, 130)],
                [(0, -8.0, 1, None, 90), (2, -20.0, 2, None, 120), (4, -32.0, 2, "weapon", 120), (6, -44.0, 1, None, 90)],
                [(1, -10.0, 2, None, 140), (3, -24.0, 3, "repair", 200), (5, -38.0, 2, None, 140), (3, -56.0, 3, None, 220)],
            ],
        },
    ]
    FIELD_WIDTH = 7
    FIELD_HEIGHT = 120.0
    SHIP_Y = 104.0

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._star_thresholds = list(config["star_thresholds"])
        self._wave_speed = float(config["wave_speed"])
        self._wave_scripts = config["waves"]
        self._wave_index = 0
        self._wave_count = len(self._wave_scripts)
        self._ship_slot = self.FIELD_WIDTH // 2
        self._weapon_level = 1
        self._burst_ticks = 0
        self._hull = 4
        self._score = 0
        self._score_popups: list[dict] = []
        self._shots_fired = 0
        self._destroyed = 0
        self._pickups_collected = 0
        self._hits_taken = 0
        self._wave_score = 0
        self._streak = 0
        self._best_streak = 0
        self._overlay_kind: str | None = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_timer = 0
        self._pending_outcome: str | None = None
        self._message = "Glide the ship, keep the burst ready, and clear every wave."
        self._enemies: list[dict] = []
        self._projectiles: list[dict] = []
        self._pickups: list[dict] = []
        self._explosions: list[dict] = []
        self._spawn_wave(self._wave_index)
        self._view_state = self._space_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = "Concentrate to drift right, relax to drift left, and hold steady to trigger a burst volley."

        if self._overlay_kind is not None:
            level_completed, run_completed = self._tick_overlay(elapsed_seconds)
        elif stale:
            blocked_reason = "Metrics are stale. Space Shooter paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Space Shooter paused."
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                if self._stabilize_intent(intent):
                    self._ship_slot = min(self.FIELD_WIDTH - 1, self._ship_slot + 1)
                    self._message = "Shifted into the right corridor."
                    action = "right"
                    moved = True
            elif intent == "relax":
                if self._stabilize_intent(intent):
                    self._ship_slot = max(0, self._ship_slot - 1)
                    self._message = "Drifted back toward the left."
                    action = "left"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    self._burst_ticks = max(self._burst_ticks, 4)
                    self._message = "Burst cannons engaged."
                    action = "fire"
                    moved = True
            else:
                self._stabilize_intent(None)

            self._spawn_auto_fire()
            self._advance_projectiles()
            self._advance_pickups()
            self._advance_enemies()
            self._tick_effects()
            if self._hull <= 0 and self._overlay_kind is None:
                self._start_failure_overlay("Hull breached before the next wave.")
            elif not self._enemies and self._overlay_kind is None:
                self._start_wave_overlay()

        self._view_state = self._space_view_state(message=blocked_reason, music_bias=relax_delta - conc_delta)
        recommended_label = self._space_recommendation(action)
        return self._arcade_snapshot(
            phase="space_shooter",
            phase_label="Space Shooter",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _spawn_wave(self, wave_index: int) -> None:
        self._enemies = []
        for slot, y_pos, hp, drop, score in self._wave_scripts[wave_index]:
            self._enemies.append(
                {
                    "slot": slot,
                    "y": y_pos,
                    "hp": hp,
                    "max_hp": hp,
                    "drop": drop,
                    "score": score,
                    "speed": self._wave_speed + (0.35 * max(0, hp - 1)),
                }
            )
        self._projectiles = []
        self._pickups = []
        self._explosions = []
        self._wave_score = 0

    def _tick_overlay(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._tick_effects()
        if self._overlay_timer > 0:
            self._overlay_timer -= 1
        if self._overlay_timer > 0:
            return False, False

        outcome = self._pending_outcome
        self._overlay_kind = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._pending_outcome = None
        if outcome == "wave":
            self._wave_index += 1
            self._message = f"Wave {self._wave_index + 1} incoming."
            self._spawn_wave(self._wave_index)
            return False, False
        if outcome == "failure":
            self._record_level_result(False, elapsed_seconds, score_override=0)
            self._finished = True
            return False, True
        if outcome == "level_complete":
            time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
            score = (
                46
                + min(32.0, self._score / 28.0)
                + (self._hull * 6.0)
                + min(16.0, self._best_streak * 2.0)
                - (self._hits_taken * 5.0)
                - time_penalty
            )
            self._record_level_result(True, elapsed_seconds, score_override=score)
            level_completed = True
            run_completed = self._advance_level()
            return level_completed, run_completed
        return False, False

    def _spawn_auto_fire(self) -> None:
        slots = {self._ship_slot}
        if self._weapon_level >= 2:
            slots.add(max(0, self._ship_slot - 1))
        if self._weapon_level >= 3:
            slots.add(min(self.FIELD_WIDTH - 1, self._ship_slot + 1))
        if self._burst_ticks > 0:
            slots.add(max(0, self._ship_slot - 1))
            slots.add(min(self.FIELD_WIDTH - 1, self._ship_slot + 1))
            power = 2
            self._burst_ticks -= 1
        else:
            power = 1
        for slot in sorted(slots):
            self._projectiles.append({"slot": slot, "y": self.SHIP_Y - 10.0, "power": power})
            self._shots_fired += 1

    def _advance_projectiles(self) -> None:
        survivors = []
        for projectile in self._projectiles:
            projectile["y"] -= 15.0
            target = None
            for enemy in self._enemies:
                if enemy["slot"] == projectile["slot"] and abs(enemy["y"] - projectile["y"]) <= 8.0:
                    target = enemy
                    break
            if target is not None:
                target["hp"] -= projectile["power"]
                if target["hp"] <= 0:
                    self._destroy_enemy(target)
                continue
            if projectile["y"] > -10.0:
                survivors.append(projectile)
        self._projectiles = survivors

    def _destroy_enemy(self, enemy: dict) -> None:
        if enemy not in self._enemies:
            return
        self._enemies.remove(enemy)
        self._destroyed += 1
        self._wave_score += int(enemy["score"])
        self._score += int(enemy["score"])
        self._streak += 1
        self._best_streak = max(self._best_streak, self._streak)
        self._explosions.append({"slot": enemy["slot"], "y": enemy["y"], "ticks": 5})
        self._score_popups.append({"slot": enemy["slot"], "y": enemy["y"], "text": f"+{int(enemy['score'])}", "ticks": 6})
        if enemy["drop"] is not None:
            self._pickups.append({"slot": enemy["slot"], "y": enemy["y"], "kind": enemy["drop"], "ticks": 18})

    def _advance_pickups(self) -> None:
        survivors = []
        for pickup in self._pickups:
            pickup["y"] += 7.0
            pickup["ticks"] = max(0, pickup["ticks"] - 1)
            if pickup["slot"] == self._ship_slot and abs(pickup["y"] - self.SHIP_Y) <= 9.0:
                self._collect_pickup(pickup["kind"])
                continue
            if pickup["y"] <= self.FIELD_HEIGHT + 10.0 and pickup["ticks"] > 0:
                survivors.append(pickup)
        self._pickups = survivors

    def _collect_pickup(self, kind: str) -> None:
        self._pickups_collected += 1
        self._score += 25
        self._score_popups.append({"slot": self._ship_slot, "y": self.SHIP_Y - 12.0, "text": "+25", "ticks": 5})
        if kind == "weapon":
            self._weapon_level = min(3, self._weapon_level + 1)
            self._message = "Weapon upgrade collected."
        else:
            self._hull = min(4, self._hull + 1)
            self._message = "Hull repair collected."

    def _advance_enemies(self) -> None:
        survivors = []
        for enemy in self._enemies:
            enemy["y"] += enemy["speed"]
            if enemy["y"] >= self.SHIP_Y - 4.0:
                if enemy["slot"] == self._ship_slot:
                    self._hull = max(0, self._hull - 1)
                    self._hits_taken += 1
                    self._streak = 0
                    self._explosions.append({"slot": enemy["slot"], "y": self.SHIP_Y - 8.0, "ticks": 6})
                    self._message = "Incoming hit. Recover and clear the lane."
                    continue
                if enemy["y"] <= self.FIELD_HEIGHT + 10.0:
                    continue
            if enemy["y"] <= self.FIELD_HEIGHT + 8.0:
                survivors.append(enemy)
        self._enemies = survivors

    def _tick_effects(self) -> None:
        for group_name in ("_explosions", "_score_popups"):
            trimmed = []
            for item in getattr(self, group_name):
                updated = dict(item)
                updated["ticks"] = max(0, int(updated.get("ticks", 0)) - 1)
                updated["y"] = float(updated.get("y", 0.0)) - 1.5
                if updated["ticks"] > 0:
                    trimmed.append(updated)
            setattr(self, group_name, trimmed)

    def _start_wave_overlay(self) -> None:
        if self._wave_index < self._wave_count - 1:
            self._overlay_kind = "wave_clear"
            self._overlay_title = f"Wave {self._wave_index + 1} cleared"
            self._overlay_subtitle = "Next formation sliding in."
            self._overlay_timer = 5
            self._pending_outcome = "wave"
            self._message = self._overlay_title
            return
        self._overlay_kind = "level_complete"
        self._overlay_title = "Sector cleared"
        self._overlay_subtitle = "Star corridor secured."
        self._overlay_timer = 7
        self._pending_outcome = "level_complete"
        self._message = self._overlay_title

    def _start_failure_overlay(self, subtitle: str) -> None:
        self._overlay_kind = "failure"
        self._overlay_title = "Ship down"
        self._overlay_subtitle = subtitle
        self._overlay_timer = 7
        self._pending_outcome = "failure"
        self._message = subtitle

    def _space_recommendation(self, action: str | None) -> str:
        if action == "right":
            return "Slide right"
        if action == "left":
            return "Slide left"
        if action == "fire":
            return "Burst volley"
        for enemy in self._enemies:
            lane_diff = enemy["slot"] - self._ship_slot
            if abs(lane_diff) <= 1:
                if lane_diff > 0:
                    return "Track the right flank"
                if lane_diff < 0:
                    return "Drift left for cover"
                return "Hold steady to burst"
        return "Read the next wave"

    def _space_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        star_ceiling = max(1.0, float(self._star_thresholds[-1]))
        return {
            "mode": "space_shooter",
            "corridor_width": self.FIELD_WIDTH,
            "field_height": self.FIELD_HEIGHT,
            "ship_slot": self._ship_slot,
            "ship_y": self.SHIP_Y,
            "weapon_level": self._weapon_level,
            "burst_ticks": self._burst_ticks,
            "hull": self._hull,
            "score": self._score,
            "star_progress": max(0.0, min(1.0, self._score / star_ceiling)),
            "star_thresholds": list(self._star_thresholds),
            "streak": self._streak,
            "best_streak": self._best_streak,
            "shots_fired": self._shots_fired,
            "destroyed": self._destroyed,
            "pickups_collected": self._pickups_collected,
            "wave_index": self._wave_index,
            "wave_count": self._wave_count,
            "enemies": [dict(enemy) for enemy in self._enemies],
            "projectiles": [dict(projectile) for projectile in self._projectiles],
            "pickups": [dict(pickup) for pickup in self._pickups],
            "explosions": [dict(explosion) for explosion in self._explosions],
            "score_popups": [dict(popup) for popup in self._score_popups],
            "overlay_kind": self._overlay_kind,
            "overlay_title": self._overlay_title,
            "overlay_subtitle": self._overlay_subtitle,
            "overlay_timer": self._overlay_timer,
            "menu_button_rect": [18, 18, 54, 42],
            "music_scene": "space_arcade",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 56.0 + (self._hull * 8.0) + (self._best_streak * 2.0))),
            "restlessness": max(0.0, min(100.0, 22.0 + (self._hits_taken * 16.0))),
            "message": message or self._message,
        }


# ── Dino Runner constants (gyroscope) ──────────────────────────────
_DINO_GYRO_DEAD_ZONE = 0.05
_DINO_GYRO_EMA_ALPHA = 0.25
_DINO_JUMP_TILT_THRESHOLD = 0.18   # accel-X tilt to trigger jump (head nod up)
_DINO_DUCK_TILT_THRESHOLD = -0.15  # negative accel-X tilt = head nod down → duck
_DINO_JUMP_VELOCITY = 14.0
_DINO_GRAVITY = 1.4
_DINO_GROUND_Y = 0.0


class JumpBallController(ArcadeTrainingController):
    """
    Chrome Dino-style side-scrolling runner controlled by BCI signals.

    Controls
    --------
    * **Focus (concentration)** -> run forward (scroll speed increases)
    * **Relaxation** -> run in reverse / slow down
    * **Gyroscope tilt up** -> jump over cacti
    * **Gyroscope tilt down** -> duck under pterodactyls
    """

    LEVELS = [
        TrainingLevel("Desert", 45),
        TrainingLevel("Canyon", 55),
        TrainingLevel("Volcano", 65),
    ]

    LEVEL_CONFIGS = [
        {"base_speed": 3.0, "spawn_interval": 2.5, "ptero_chance": 0.0, "speed_cap": 6.0},
        {"base_speed": 4.5, "spawn_interval": 1.8, "ptero_chance": 0.25, "speed_cap": 8.5},
        {"base_speed": 6.0, "spawn_interval": 1.2, "ptero_chance": 0.40, "speed_cap": 11.0},
    ]

    OBSTACLE_TEMPLATES = [
        {"kind": "cactus_small", "width": 18.0, "height": 34.0, "fly_y": 0.0},
        {"kind": "cactus_large", "width": 24.0, "height": 48.0, "fly_y": 0.0},
        {"kind": "cactus_group", "width": 42.0, "height": 38.0, "fly_y": 0.0},
        {"kind": "pterodactyl", "width": 36.0, "height": 28.0, "fly_y": 40.0},
    ]

    def __init__(self):
        super().__init__(self.LEVELS)
        # gyroscope state
        self._gyro_tilt_y = 0.0  # smoothed forward/back head tilt (accel X)
        self._gyro_zero_y = 0.0
        self._gyro_samples: list[float] = []
        self._gyro_calibrated = False

    # -- MEMS input (called by TrainingScreen before update_gameplay) --

    def update_mems(self, accel_x: float, accel_y: float, accel_z: float,
                    gyro_x: float, gyro_y: float, gyro_z: float) -> None:
        raw_y = accel_x  # forward/back tilt from accel X

        if not self._gyro_calibrated:
            self._gyro_samples.append(raw_y)
            if len(self._gyro_samples) >= 60:
                self._gyro_zero_y = sum(self._gyro_samples) / len(self._gyro_samples)
                self._gyro_calibrated = True
            return

        adj_y = raw_y - self._gyro_zero_y
        if abs(adj_y) < _DINO_GYRO_DEAD_ZONE:
            adj_y = 0.0
        self._gyro_tilt_y += _DINO_GYRO_EMA_ALPHA * (adj_y - self._gyro_tilt_y)

    # -- lifecycle --

    def _reset_level_state(self) -> None:
        cfg = self.LEVEL_CONFIGS[self._level_index]
        self._base_speed: float = cfg["base_speed"]
        self._spawn_interval: float = cfg["spawn_interval"]
        self._ptero_chance: float = cfg["ptero_chance"]
        self._speed_cap: float = cfg["speed_cap"]

        self._scroll_speed: float = self._base_speed
        self._distance: float = 0.0
        self._dino_y: float = _DINO_GROUND_Y
        self._dino_vy: float = 0.0
        self._dino_on_ground: bool = True
        self._dino_ducking: bool = False
        self._jump_requested: bool = False
        self._duck_requested: bool = False
        self._stun_ticks: int = 0
        self._spawn_timer: float = self._spawn_interval
        self._obstacle_counter: int = 0
        self._obstacles: list[dict] = []
        self._combo: int = 0
        self._best_combo: int = 0
        self._cleared: int = 0
        self._misses: int = 0
        self._score: int = 0
        self._view_state = self._dino_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = (
            "Focus to run forward, relax to slow down, tilt head up to jump over cacti, tilt down to duck."
        )

        # Read gyroscope intent
        jump_tilt = self._gyro_tilt_y >= _DINO_JUMP_TILT_THRESHOLD
        duck_tilt = self._gyro_tilt_y <= _DINO_DUCK_TILT_THRESHOLD
        if jump_tilt:
            self._jump_requested = True
        if duck_tilt:
            self._duck_requested = True

        if stale:
            blocked_reason = "Metrics are stale. Runner paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Runner paused."
        elif self._stun_ticks > 0:
            self._stun_ticks -= 1
            blocked_reason = "Stunned!"
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)

            # Scroll speed from EEG intent
            if intent == "focus":
                speed_mult = 1.0 + min(0.6, conc_delta * 0.03)
                self._scroll_speed = min(self._speed_cap, self._base_speed * speed_mult)
                if self._stabilize_intent(intent):
                    action = "run"
                    moved = True
            elif intent == "relax":
                speed_mult = -0.5 * (1.0 + min(0.4, relax_delta * 0.02))
                self._scroll_speed = self._base_speed * speed_mult
                if self._stabilize_intent(intent):
                    action = "reverse"
                    moved = True
            elif intent == "steady":
                self._scroll_speed = self._base_speed * 0.8
                if self._stabilize_intent(intent):
                    action = "steady"
                    moved = True
            else:
                self._stabilize_intent(None)
                self._scroll_speed = self._base_speed * 0.4

            # Jump physics
            if self._jump_requested and self._dino_on_ground:
                self._dino_vy = _DINO_JUMP_VELOCITY
                self._dino_on_ground = False
                self._dino_ducking = False
                action = "jump"
                moved = True
            self._jump_requested = False

            # Duck
            self._dino_ducking = self._duck_requested and self._dino_on_ground
            self._duck_requested = False

            # Gravity
            if not self._dino_on_ground:
                self._dino_y += self._dino_vy
                self._dino_vy -= _DINO_GRAVITY
                if self._dino_y <= _DINO_GROUND_Y:
                    self._dino_y = _DINO_GROUND_Y
                    self._dino_vy = 0.0
                    self._dino_on_ground = True

            # Distance and spawning
            scroll_step = abs(self._scroll_speed)
            self._distance += scroll_step
            self._score = int(self._distance * 0.1) + self._cleared * 10 + self._best_combo * 5

            # Spawn obstacles
            self._spawn_timer -= scroll_step * 0.04
            if self._spawn_timer <= 0.0:
                self._spawn_obstacle()
                self._spawn_timer = self._spawn_interval

            # Move obstacles
            for obs in self._obstacles:
                obs["x"] -= self._scroll_speed

            # Collision detection
            self._resolve_collisions()

            # Remove off-screen obstacles (passed to the left)
            before = len(self._obstacles)
            self._obstacles = [o for o in self._obstacles if o["x"] > -60.0]
            newly_cleared = before - len(self._obstacles)
            if newly_cleared > 0:
                self._cleared += newly_cleared
                self._combo += newly_cleared
                self._best_combo = max(self._best_combo, self._combo)

            # Level completion by timer
            if elapsed_seconds >= self.current_level.target_seconds:
                combo_bonus = min(20.0, self._best_combo * 2.5)
                miss_penalty = self._misses * 6.0
                score = 48 + self._distance * 0.08 + combo_bonus - miss_penalty
                self._record_level_result(True, elapsed_seconds, score_override=score)
                level_completed = True
                run_completed = self._advance_level()

        day_night = (self._distance % 1000.0) / 1000.0
        if day_night > 0.5:
            day_night = 1.0 - day_night
        day_night *= 2.0  # 0->1->0 cycle

        self._view_state = self._dino_view_state(message=blocked_reason, music_bias=relax_delta - conc_delta,
                                                  day_night=day_night)
        recommended_label = self._dino_recommendation(action)
        return self._arcade_snapshot(
            phase="jump_ball",
            phase_label="Dino Runner",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _spawn_obstacle(self) -> None:
        import random
        if random.random() < self._ptero_chance:
            template = self.OBSTACLE_TEMPLATES[3]  # pterodactyl
        else:
            template = random.choice(self.OBSTACLE_TEMPLATES[:3])  # cactus variants
        self._obstacle_counter += 1
        self._obstacles.append({
            "id": self._obstacle_counter,
            "x": 800.0,  # spawn off-screen right
            "width": template["width"],
            "height": template["height"],
            "kind": template["kind"],
            "fly_y": template["fly_y"],
        })

    def _resolve_collisions(self) -> None:
        dino_x = 80.0
        dino_w = 36.0
        dino_h = 20.0 if self._dino_ducking else 44.0
        dino_bottom = self._dino_y
        dino_top = dino_bottom + dino_h

        for obs in self._obstacles:
            if obs.get("hit"):
                continue
            obs_left = obs["x"]
            obs_right = obs_left + obs["width"]
            obs_bottom = obs["fly_y"]
            obs_top = obs_bottom + obs["height"]

            # AABB overlap check
            if (dino_x + dino_w > obs_left and dino_x < obs_right
                    and dino_top > obs_bottom and dino_bottom < obs_top):
                obs["hit"] = True
                self._misses += 1
                self._combo = 0
                self._stun_ticks = 3

    def _dino_recommendation(self, action: str | None) -> str:
        if action == "jump":
            return "Jump!"
        if action == "run":
            return "Stay focused"
        if action == "reverse":
            return "Slowing down"
        if action == "steady":
            return "Nice combo!"
        # Look ahead for incoming obstacles
        for obs in sorted(self._obstacles, key=lambda o: o["x"]):
            if obs.get("hit"):
                continue
            if obs["x"] < 200.0:
                if obs["fly_y"] > 0:
                    return "Duck!"
                if self._dino_on_ground:
                    return "Jump now!"
                return "Hold air"
            break
        return "Keep running"

    def _dino_view_state(self, message: str = "", music_bias: float = 0.0,
                         day_night: float = 0.0) -> dict:
        return {
            "mode": "jump_ball",
            "dino_y": self._dino_y,
            "dino_on_ground": self._dino_on_ground,
            "dino_ducking": self._dino_ducking,
            "scroll_speed": self._scroll_speed,
            "distance": self._distance,
            "score": self._score,
            "combo": self._combo,
            "best_combo": self._best_combo,
            "cleared": self._cleared,
            "misses": self._misses,
            "day_night": day_night,
            "obstacles": [
                {"x": o["x"], "width": o["width"], "height": o["height"],
                 "kind": o["kind"], "fly_y": o["fly_y"]}
                for o in self._obstacles if not o.get("hit")
            ],
            "music_scene": "dino_run",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 58.0 + (self._best_combo * 4.0) - (self._misses * 10.0))),
            "restlessness": max(0.0, min(100.0, 18.0 + (self._misses * 12.0))),
            "message": message,
        }


class BubbleBurstController(ArcadeTrainingController):
    LEVELS = [
        TrainingLevel("Wave 1", 60),
        TrainingLevel("Wave 2", 75),
        TrainingLevel("Wave 3", 90),
    ]
    CONFIGS = [
        {
            "columns": 6,
            "palette": ["red", "green"],
            "shots_left": 20,
            "star_thresholds": [2200, 3800, 5400],
            "layout": [".GGGG.", "GGRRGG", ".RRRR.", "R.GG.R", ".G..G."],
        },
        {
            "columns": 7,
            "palette": ["red", "green", "yellow"],
            "shots_left": 18,
            "star_thresholds": [3200, 5100, 7200],
            "layout": [".GGYGG.", "GGRRRGG", ".RRYRR.", "R.GYG.R", ".GGYGG.", "..Y.Y.."],
        },
        {
            "columns": 8,
            "palette": ["red", "green", "yellow", "blue"],
            "shots_left": 17,
            "star_thresholds": [4200, 6600, 9200],
            "layout": [".GGYYGG.", "GGRRRRGG", ".RYYBBR.", "RRGBBGRR", ".GYYBBG.", "..G..G.."],
        },
    ]
    TOKEN_MAP = {".": None, "R": "red", "G": "green", "Y": "yellow", "B": "blue"}
    VISIBLE_ROWS = 10

    def __init__(self):
        super().__init__(self.LEVELS)

    def _reset_level_state(self) -> None:
        config = self.CONFIGS[self._level_index]
        self._columns = config["columns"]
        self._palette = list(config["palette"])
        self._shots_left = int(config["shots_left"])
        self._star_thresholds = list(config["star_thresholds"])
        self._layout = list(config["layout"])
        self._board: list[list[str | None]] = [
            [None for _ in range(self._columns)] for _ in range(self.VISIBLE_ROWS)
        ]
        self._spawn_cursor = 0
        self._ceiling_cursor = self._level_index * 5
        self._danger_steps = 0
        self._score = 0
        self._combo = 0
        self._best_combo = 0
        self._score_popups: list[dict] = []
        self._aim_slot = self._columns // 2
        self._overlay_kind: str | None = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._overlay_timer = 0
        self._pending_outcome: str | None = None
        self._launcher_zone_row = self.VISIBLE_ROWS - 2
        self._message = "Clear the whole cluster before the launcher gets crowded."
        self._seed_board()
        self._current_bubble = self._next_spawn()
        self._next_bubble = self._next_spawn()
        self._view_state = self._bubble_view_state()

    def update_gameplay(
        self,
        concentration: float,
        relaxation: float,
        valid: bool,
        stale: bool,
        elapsed_seconds: float,
    ) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked_reason = ""
        action = None
        moved = False
        level_completed = False
        run_completed = False
        control_hint = "Concentrate to nudge the aim right, relax to nudge it left, and hold steady to fire."

        if self._overlay_kind is not None:
            level_completed, run_completed = self._tick_overlay(elapsed_seconds)
        elif stale:
            blocked_reason = "Metrics are stale. Bubble Burst paused."
        elif not valid:
            blocked_reason = "Artifacts detected. Bubble Burst paused."
        else:
            self._tick_score_popups()
            intent = self._arcade_intent(conc_delta, relax_delta)
            if intent == "focus":
                if self._stabilize_intent(intent):
                    self._aim_slot = min(self._columns - 1, self._aim_slot + 1)
                    self._message = "Aim shifted right."
                    action = "right"
                    moved = True
            elif intent == "relax":
                if self._stabilize_intent(intent):
                    self._aim_slot = max(0, self._aim_slot - 1)
                    self._message = "Aim shifted left."
                    action = "left"
                    moved = True
            elif intent == "steady":
                if self._stabilize_intent(intent):
                    action = "fire"
                    moved = True
                    level_completed, run_completed = self._fire_bubble(elapsed_seconds)
            else:
                self._stabilize_intent(None)

        message = blocked_reason or self._message
        self._view_state = self._bubble_view_state(
            message=message,
            music_bias=relax_delta - conc_delta,
        )
        recommended_label = self._bubble_recommendation(action)
        return self._arcade_snapshot(
            phase="bubble_burst",
            phase_label="Bubble Burst",
            direction=action,
            blocked_reason=blocked_reason,
            control_hint=control_hint,
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_completed,
            run_completed=run_completed,
            recommended_label=recommended_label,
        )

    def _seed_board(self) -> None:
        for row_index, row_pattern in enumerate(self._layout):
            for col_index, char in enumerate(row_pattern):
                self._board[row_index][col_index] = self.TOKEN_MAP[char]

    def _next_spawn(self) -> str:
        color = self._palette[(self._spawn_cursor + self._level_index) % len(self._palette)]
        self._spawn_cursor += 1
        return color

    def _fire_bubble(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._shots_left = max(0, self._shots_left - 1)
        placed = self._place_current_bubble()
        if placed is None:
            self._message = "No landing slot. The ceiling drops."
            self._drop_ceiling_row()
            self._cycle_bubble_queue()
            if self._launcher_zone_reached():
                self._start_failure_overlay("Bubbles reached the launcher.")
                return False, False
            if self._shots_left == 0:
                self._start_failure_overlay("Out of shots before the board cleared.")
                return False, False
            return False, False

        row, col = placed
        popped_cells = self._resolve_burst(row, col)
        self._cycle_bubble_queue()

        if popped_cells:
            self._combo += 1
            self._best_combo = max(self._best_combo, self._combo)
            burst_score = (len(popped_cells) * 300) + max(0, (self._combo - 1) * 90)
            self._score += burst_score
            self._score_popups.append(
                {"row": row, "col": col, "text": str(burst_score), "ticks": 7}
            )
            self._message = f"Burst {len(popped_cells)} bubbles."
        else:
            self._combo = 0
            self._message = "No match. The ceiling drops."
            self._drop_ceiling_row()
            if self._launcher_zone_reached():
                self._start_failure_overlay("Bubbles reached the launcher.")
                return False, False

        if self._board_empty():
            self._start_success_overlay()
            return False, False
        if self._shots_left == 0:
            self._start_failure_overlay("Out of shots before the board cleared.")
            return False, False
        return False, False

    def _place_current_bubble(self) -> tuple[int, int] | None:
        for col in self._column_scan_order(self._aim_slot):
            row = self._landing_row(col)
            if row is not None:
                self._board[row][col] = self._current_bubble
                return row, col
        return None

    def _column_scan_order(self, center: int) -> list[int]:
        order = [center]
        for distance in range(1, self._columns):
            left = center - distance
            right = center + distance
            if left >= 0:
                order.append(left)
            if right < self._columns:
                order.append(right)
        return order

    def _landing_row(self, col: int) -> int | None:
        for row in range(self.VISIBLE_ROWS):
            if self._board[row][col] is None:
                return row
        return None

    def _resolve_burst(self, row: int, col: int) -> set[tuple[int, int]]:
        cluster = self._color_cluster(row, col)
        if len(cluster) < 3:
            return set()

        removed = set(cluster)
        self._clear_cells(cluster)
        floating = self._floating_cells()
        if floating:
            removed.update(floating)
            self._clear_cells(floating)
        return removed

    def _color_cluster(self, row: int, col: int) -> set[tuple[int, int]]:
        color = self._board[row][col]
        if color is None:
            return set()
        cluster = set()
        stack = [(row, col)]
        while stack:
            cell = stack.pop()
            if cell in cluster:
                continue
            r, c = cell
            if self._board[r][c] != color:
                continue
            cluster.add(cell)
            for neighbor in self._neighbors(r, c):
                if neighbor not in cluster:
                    stack.append(neighbor)
        return cluster

    def _floating_cells(self) -> set[tuple[int, int]]:
        anchored = set()
        stack = [(0, col) for col in range(self._columns) if self._board[0][col] is not None]
        while stack:
            cell = stack.pop()
            if cell in anchored:
                continue
            anchored.add(cell)
            r, c = cell
            for neighbor in self._neighbors(r, c):
                nr, nc = neighbor
                if self._board[nr][nc] is not None and neighbor not in anchored:
                    stack.append(neighbor)

        floating = set()
        for row in range(self.VISIBLE_ROWS):
            for col in range(self._columns):
                if self._board[row][col] is not None and (row, col) not in anchored:
                    floating.add((row, col))
        return floating

    def _neighbors(self, row: int, col: int) -> list[tuple[int, int]]:
        if row % 2 == 0:
            offsets = [(0, -1), (0, 1), (-1, -1), (-1, 0), (1, -1), (1, 0)]
        else:
            offsets = [(0, -1), (0, 1), (-1, 0), (-1, 1), (1, 0), (1, 1)]

        neighbors = []
        for row_delta, col_delta in offsets:
            next_row = row + row_delta
            next_col = col + col_delta
            if 0 <= next_row < self.VISIBLE_ROWS and 0 <= next_col < self._columns:
                neighbors.append((next_row, next_col))
        return neighbors

    def _clear_cells(self, cells: set[tuple[int, int]]) -> None:
        for row, col in cells:
            self._board[row][col] = None

    def _cycle_bubble_queue(self) -> None:
        self._current_bubble = self._next_bubble
        self._next_bubble = self._next_spawn()

    def _drop_ceiling_row(self) -> None:
        self._danger_steps += 1
        new_row = [
            (
                None
                if self._columns >= 7 and ((self._ceiling_cursor + col) % 5 == 0)
                else self._palette[(self._ceiling_cursor + col + self._level_index) % len(self._palette)]
            )
            for col in range(self._columns)
        ]
        self._ceiling_cursor += 1
        self._board = [new_row] + [row[:] for row in self._board[:-1]]

    def _board_empty(self) -> bool:
        return all(cell is None for row in self._board for cell in row)

    def _launcher_zone_reached(self) -> bool:
        for row in range(self._launcher_zone_row, self.VISIBLE_ROWS):
            if any(cell is not None for cell in self._board[row]):
                return True
        return False

    def _tick_score_popups(self) -> None:
        trimmed = []
        for popup in self._score_popups:
            updated = dict(popup)
            updated["ticks"] = max(0, int(updated.get("ticks", 0)) - 1)
            updated["row"] = max(0.0, float(updated.get("row", 0.0)) - 0.12)
            if updated["ticks"] > 0:
                trimmed.append(updated)
        self._score_popups = trimmed

    def swap_bubbles(self) -> bool:
        if self._overlay_kind is not None:
            return False
        self._current_bubble, self._next_bubble = self._next_bubble, self._current_bubble
        self._message = "Bubble queue swapped."
        self._view_state = self._bubble_view_state()
        return True

    def _start_success_overlay(self) -> None:
        self._overlay_kind = "board_clear"
        self._overlay_title = "You popped all bubbles"
        self._overlay_subtitle = "Level completed!"
        self._overlay_timer = 7
        self._pending_outcome = "level_complete"
        self._message = self._overlay_title

    def _start_failure_overlay(self, subtitle: str) -> None:
        self._overlay_kind = "failure"
        self._overlay_title = "Bubble run over"
        self._overlay_subtitle = subtitle
        self._overlay_timer = 7
        self._pending_outcome = "failure"
        self._message = subtitle

    def _tick_overlay(self, elapsed_seconds: float) -> tuple[bool, bool]:
        self._tick_score_popups()
        if self._overlay_timer > 0:
            self._overlay_timer -= 1
        if self._overlay_timer > 0:
            return False, False

        outcome = self._pending_outcome
        self._overlay_kind = None
        self._overlay_title = ""
        self._overlay_subtitle = ""
        self._pending_outcome = None
        if outcome == "failure":
            self._record_level_result(False, elapsed_seconds, score_override=0)
            self._finished = True
            return False, True
        if outcome == "level_complete":
            time_penalty = max(0, elapsed_seconds - self.current_level.target_seconds)
            score = (
                50
                + min(34.0, self._score / 180.0)
                + min(12.0, self._shots_left * 1.2)
                + min(12.0, self._best_combo * 2.0)
                - time_penalty
            )
            self._record_level_result(True, elapsed_seconds, score_override=score)
            level_completed = True
            run_completed = self._advance_level()
            return level_completed, run_completed
        return False, False

    def _bubble_recommendation(self, action: str | None) -> str:
        if action == "right":
            return "Track right"
        if action == "left":
            return "Track left"
        if action == "fire":
            return "Burst cluster"
        if self._nearest_reachable_match() == self._current_bubble:
            return "Build the center cluster"
        return "Stabilize the shot"

    def _nearest_reachable_match(self) -> str | None:
        for col in self._column_scan_order(self._aim_slot):
            row = self._landing_row(col)
            if row is None:
                continue
            for neighbor in self._neighbors(row, col):
                nr, nc = neighbor
                if self._board[nr][nc] is not None:
                    return self._board[nr][nc]
        return None

    def _bubble_view_state(self, message: str = "", music_bias: float = 0.0) -> dict:
        return {
            "mode": "bubble_burst",
            "columns": self._columns,
            "visible_rows": self.VISIBLE_ROWS,
            "board": [list(row) for row in self._board],
            "aim_slot": self._aim_slot,
            "current_bubble": self._current_bubble,
            "next_bubble": self._next_bubble,
            "shots_left": self._shots_left,
            "score": self._score,
            "combo": self._combo,
            "best_combo": self._best_combo,
            "danger_steps": self._danger_steps,
            "launcher_zone_row": self._launcher_zone_row,
            "score_popups": [dict(popup) for popup in self._score_popups],
            "swap_enabled": self._overlay_kind is None,
            "star_progress": max(0.0, min(1.0, self._score / max(1, self._star_thresholds[-1]))),
            "star_thresholds": list(self._star_thresholds),
            "overlay_kind": self._overlay_kind,
            "overlay_title": self._overlay_title,
            "overlay_subtitle": self._overlay_subtitle,
            "overlay_timer": self._overlay_timer,
            "menu_button_rect": [18, 18, 54, 42],
            "swap_button_rect": [0, 0, 0, 0],
            "music_scene": "bubble_arcade",
            "music_bias": music_bias,
            "serenity": max(0.0, min(100.0, 60.0 + (self._shots_left * 1.5) + (self._best_combo * 4.0))),
            "restlessness": max(0.0, min(100.0, 16.0 + (self._danger_steps * 12.0))),
            "message": message or self._message,
        }


# ---------------------------------------------------------------------------
# Neon Vice -- top-down arena shooter (gyro aim / focus fire / relax shield)
# ---------------------------------------------------------------------------
_NV_GYRO_DEAD_ZONE = 0.05
_NV_GYRO_EMA_ALPHA = 0.25
_NV_AIM_SENSITIVITY = 4.5          # tilt -> degrees/tick
_NV_FIRE_FOCUS_THRESHOLD = 0.15    # conc_delta above baseline to auto-fire
_NV_WALK_SPEED_BASE = 1.8          # px/tick at moderate focus
_NV_SPRINT_MULTIPLIER = 2.4
_NV_BULLET_SPEED = 10.0
_NV_BULLET_LIFETIME = 55           # ticks before bullet despawns
_NV_FIRE_COOLDOWN = 6              # ticks between shots
_NV_ENEMY_BASE_SPEED = 0.55
_NV_PLAYER_RADIUS = 12.0
_NV_ENEMY_RADIUS = 10.0
_NV_BULLET_RADIUS = 4.0
_NV_PLAYER_MAX_HP = 3
_NV_ARENA_W = 900.0
_NV_ARENA_H = 600.0
_NV_SHIELD_SUSTAIN_NEEDED = 6      # ticks of relax intent to activate shield
_NV_DAMAGE_INVULN = 20             # ticks of invulnerability after taking a hit


class NeonViceController(ArcadeTrainingController):
    """Top-down arena shooter -- Hotline Miami meets Vice City.

    Controls
    --------
    * Gyroscope (head tilt left/right) -> aim direction (360 degrees)
    * High focus -> sprint in aim direction **and** auto-fire bullets
    * Moderate focus -> walk in aim direction
    * Relaxation -> slow down + activate shield (absorbs 1 hit)
    """

    LEVELS = [
        TrainingLevel("Neon Streets", 50),
        TrainingLevel("Vice District", 60),
        TrainingLevel("Kingpin Tower", 70),
    ]

    LEVEL_CONFIGS = [
        {"enemies_per_wave": 4, "wave_count": 3, "speed_scale": 1.0,
         "heavy_chance": 0.0, "runner_chance": 0.1, "spawn_delay": 12},
        {"enemies_per_wave": 5, "wave_count": 4, "speed_scale": 1.25,
         "heavy_chance": 0.15, "runner_chance": 0.25, "spawn_delay": 10},
        {"enemies_per_wave": 6, "wave_count": 5, "speed_scale": 1.5,
         "heavy_chance": 0.25, "runner_chance": 0.35, "spawn_delay": 8},
    ]

    def __init__(self) -> None:
        super().__init__(self.LEVELS)
        self._gyro_tilt = 0.0
        self._gyro_zero: float | None = None
        self._gyro_samples: list[float] = []
        self._gyro_calibrated = False

    # -- MEMS / gyroscope -------------------------------------------------

    def update_mems(self, accel_x, accel_y, accel_z,
                    gyro_x, gyro_y, gyro_z) -> None:
        raw = accel_y  # left/right head tilt
        if not self._gyro_calibrated:
            self._gyro_samples.append(raw)
            if len(self._gyro_samples) >= 60:
                self._gyro_zero = sum(self._gyro_samples) / len(self._gyro_samples)
                self._gyro_calibrated = True
            return
        adj = raw - (self._gyro_zero or 0.0)
        if abs(adj) < _NV_GYRO_DEAD_ZONE:
            adj = 0.0
        self._gyro_tilt += _NV_GYRO_EMA_ALPHA * (adj - self._gyro_tilt)

    # -- level state ------------------------------------------------------

    def _reset_level_state(self) -> None:
        cfg = self.LEVEL_CONFIGS[self._level_index] if self._level_index < len(self.LEVEL_CONFIGS) else self.LEVEL_CONFIGS[-1]
        self._speed_scale = cfg["speed_scale"]
        self._enemies_per_wave = cfg["enemies_per_wave"]
        self._wave_count = cfg["wave_count"]
        self._heavy_chance = cfg["heavy_chance"]
        self._runner_chance = cfg["runner_chance"]
        self._spawn_delay = cfg["spawn_delay"]

        self._player_x = _NV_ARENA_W / 2
        self._player_y = _NV_ARENA_H / 2
        self._aim_angle = 0.0          # degrees, 0 = right
        self._health = _NV_PLAYER_MAX_HP
        self._shield_active = False
        self._shield_sustain = 0
        self._invuln_ticks = 0

        self._bullets: list[dict] = []
        self._enemies: list[dict] = []
        self._particles: list[dict] = []
        self._fire_cooldown = 0

        self._wave_number = 0
        self._wave_spawned = False
        self._spawn_timer = 0
        self._score = 0
        self._combo = 0
        self._best_combo = 0
        self._kills = 0
        self._tick = 0

        self._overlay_kind: str | None = None
        self._overlay_ticks = 0
        self._message = ""
        self._view_state = {"mode": "neon_vice"}

    # -- gameplay loop ----------------------------------------------------

    def update_gameplay(self, concentration, relaxation, valid, stale,
                        elapsed_seconds) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked = ""
        moved = False
        level_done = False
        run_done = False
        self._tick += 1

        # ---- overlay transitions ------------------------------------
        if self._overlay_kind is not None:
            self._overlay_ticks += 1
            if self._overlay_ticks >= 40:
                score_pct = min(100, int(self._score / max(1, self._wave_count * self._enemies_per_wave) * 8))
                if self._overlay_kind == "success":
                    self._record_level_result(True, elapsed_seconds, score_override=score_pct)
                else:
                    self._record_level_result(False, elapsed_seconds, score_override=max(10, score_pct // 2))
                level_done = True
                run_done = self._advance_level()
                self._overlay_kind = None
                self._overlay_ticks = 0

        elif stale:
            blocked = "Signal unavailable -- hold the headband steady"
        elif not valid:
            blocked = "Artifacts detected -- relax your jaw and forehead"
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)

            # ---- aim ------------------------------------------------
            self._aim_angle += self._gyro_tilt * _NV_AIM_SENSITIVITY
            self._aim_angle %= 360.0

            # ---- movement -------------------------------------------
            rad = math.radians(self._aim_angle)
            dx = math.cos(rad)
            dy = math.sin(rad)

            if intent == "focus":
                speed = _NV_WALK_SPEED_BASE * _NV_SPRINT_MULTIPLIER
            elif intent == "relax":
                speed = _NV_WALK_SPEED_BASE * 0.25
            else:
                speed = _NV_WALK_SPEED_BASE

            self._player_x += dx * speed
            self._player_y += dy * speed
            self._player_x = max(_NV_PLAYER_RADIUS, min(_NV_ARENA_W - _NV_PLAYER_RADIUS, self._player_x))
            self._player_y = max(_NV_PLAYER_RADIUS, min(_NV_ARENA_H - _NV_PLAYER_RADIUS, self._player_y))
            moved = speed > 0.5

            # ---- fire -----------------------------------------------
            if self._fire_cooldown > 0:
                self._fire_cooldown -= 1
            if intent == "focus" and conc_delta > _NV_FIRE_FOCUS_THRESHOLD and self._fire_cooldown <= 0:
                self._bullets.append({
                    "x": self._player_x + dx * (_NV_PLAYER_RADIUS + 4),
                    "y": self._player_y + dy * (_NV_PLAYER_RADIUS + 4),
                    "dx": dx * _NV_BULLET_SPEED,
                    "dy": dy * _NV_BULLET_SPEED,
                    "life": _NV_BULLET_LIFETIME,
                })
                self._fire_cooldown = _NV_FIRE_COOLDOWN

            # ---- shield (relax) -------------------------------------
            if intent == "relax":
                self._shield_sustain += 1
                if self._shield_sustain >= _NV_SHIELD_SUSTAIN_NEEDED:
                    self._shield_active = True
            else:
                self._shield_sustain = max(0, self._shield_sustain - 2)
                if self._shield_sustain <= 0:
                    self._shield_active = False

            # ---- invulnerability timer ------------------------------
            if self._invuln_ticks > 0:
                self._invuln_ticks -= 1

            # ---- update bullets -------------------------------------
            self._update_bullets()

            # ---- wave spawning --------------------------------------
            if not self._enemies and not self._wave_spawned:
                self._spawn_timer += 1
                if self._spawn_timer >= self._spawn_delay:
                    self._spawn_wave()
                    self._spawn_timer = 0

            # ---- update enemies -------------------------------------
            self._update_enemies()

            # ---- collisions: bullet -> enemy -------------------------
            self._resolve_hits()

            # ---- collisions: enemy -> player -------------------------
            self._check_player_damage()

            # ---- wave / level completion ----------------------------
            if not self._enemies and self._wave_spawned:
                if self._wave_number >= self._wave_count:
                    self._overlay_kind = "success"
                    self._overlay_ticks = 0
                else:
                    self._wave_spawned = False
                    self._spawn_timer = 0

            # ---- death check ----------------------------------------
            if self._health <= 0 and self._overlay_kind is None:
                self._overlay_kind = "fail"
                self._overlay_ticks = 0

            # ---- time limit -----------------------------------------
            if elapsed_seconds >= self.current_level.target_seconds and self._overlay_kind is None:
                if self._wave_number >= self._wave_count and not self._enemies:
                    self._overlay_kind = "success"
                else:
                    self._overlay_kind = "timeout"
                self._overlay_ticks = 0

        # ---- particles ----------------------------------------------
        self._update_particles()

        # ---- build view state ---------------------------------------
        self._view_state = self._nv_view_state(blocked, conc_delta, relax_delta)

        return self._arcade_snapshot(
            phase="neon_vice",
            phase_label=self.current_level.title,
            direction=self._nv_direction(),
            blocked_reason=blocked,
            control_hint="Tilt to aim / Focus to fire / Relax for shield",
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_done,
            run_completed=run_done,
            recommended_label=self._nv_recommendation(),
        )

    # -- internal helpers -------------------------------------------------

    def _spawn_wave(self) -> None:
        import random
        self._wave_number += 1
        self._wave_spawned = True
        for _ in range(self._enemies_per_wave):
            edge = random.randint(0, 3)
            if edge == 0:
                ex, ey = random.uniform(20, _NV_ARENA_W - 20), 0.0
            elif edge == 1:
                ex, ey = random.uniform(20, _NV_ARENA_W - 20), _NV_ARENA_H
            elif edge == 2:
                ex, ey = 0.0, random.uniform(20, _NV_ARENA_H - 20)
            else:
                ex, ey = _NV_ARENA_W, random.uniform(20, _NV_ARENA_H - 20)
            roll = random.random()
            if roll < self._heavy_chance:
                kind, hp, spd = "heavy", 2, 0.35
            elif roll < self._heavy_chance + self._runner_chance:
                kind, hp, spd = "runner", 1, 1.2
            else:
                kind, hp, spd = "thug", 1, 0.7
            self._enemies.append({
                "x": ex, "y": ey, "hp": hp, "kind": kind,
                "speed": spd * _NV_ENEMY_BASE_SPEED * self._speed_scale,
            })

    def _update_bullets(self) -> None:
        alive = []
        for b in self._bullets:
            b["x"] += b["dx"]
            b["y"] += b["dy"]
            b["life"] -= 1
            if b["life"] > 0 and 0 <= b["x"] <= _NV_ARENA_W and 0 <= b["y"] <= _NV_ARENA_H:
                alive.append(b)
        self._bullets = alive

    def _update_enemies(self) -> None:
        for e in self._enemies:
            dx = self._player_x - e["x"]
            dy = self._player_y - e["y"]
            dist = math.hypot(dx, dy)
            if dist > 1.0:
                e["x"] += (dx / dist) * e["speed"]
                e["y"] += (dy / dist) * e["speed"]

    def _resolve_hits(self) -> None:
        import random
        remaining_bullets = []
        for b in self._bullets:
            hit = False
            for e in self._enemies:
                if e["hp"] <= 0:
                    continue
                d = math.hypot(b["x"] - e["x"], b["y"] - e["y"])
                if d < _NV_BULLET_RADIUS + _NV_ENEMY_RADIUS:
                    e["hp"] -= 1
                    hit = True
                    if e["hp"] <= 0:
                        self._kills += 1
                        self._combo += 1
                        self._best_combo = max(self._best_combo, self._combo)
                        pts = 100 + (self._combo - 1) * 25
                        self._score += pts
                        for _ in range(6):
                            self._particles.append({
                                "x": e["x"], "y": e["y"],
                                "dx": random.uniform(-3, 3),
                                "dy": random.uniform(-3, 3),
                                "life": random.randint(8, 18),
                                "color": "pink" if e["kind"] == "thug" else "orange",
                            })
                    break
            if not hit:
                remaining_bullets.append(b)
        self._bullets = remaining_bullets
        self._enemies = [e for e in self._enemies if e["hp"] > 0]

    def _check_player_damage(self) -> None:
        if self._invuln_ticks > 0:
            return
        for e in self._enemies:
            d = math.hypot(self._player_x - e["x"], self._player_y - e["y"])
            if d < _NV_PLAYER_RADIUS + _NV_ENEMY_RADIUS:
                if self._shield_active:
                    self._shield_active = False
                    self._shield_sustain = 0
                    self._invuln_ticks = _NV_DAMAGE_INVULN
                else:
                    self._health -= 1
                    self._combo = 0
                    self._invuln_ticks = _NV_DAMAGE_INVULN
                break

    def _update_particles(self) -> None:
        alive = []
        for p in self._particles:
            p["x"] += p["dx"]
            p["y"] += p["dy"]
            p["life"] -= 1
            if p["life"] > 0:
                alive.append(p)
        self._particles = alive

    def _nv_direction(self) -> str | None:
        if self._shield_active:
            return "shield"
        if self._fire_cooldown == _NV_FIRE_COOLDOWN:
            return "fire"
        if self._health <= 1:
            return "shield"
        return "focus"

    def _nv_recommendation(self) -> str:
        if self._overlay_kind == "success":
            return "Level clear!"
        if self._overlay_kind == "fail":
            return "Game over"
        if self._overlay_kind == "timeout":
            return "Time up"
        if self._health <= 1:
            return "Find cover!"
        if self._shield_active:
            return "Shield up!"
        if self._combo >= 3:
            return f"x{self._combo} Combo!"
        if self._fire_cooldown == _NV_FIRE_COOLDOWN:
            return "Fire!"
        return "Stay focused"

    def _nv_view_state(self, blocked: str, conc_delta: float, relax_delta: float) -> dict:
        return {
            "mode": "neon_vice",
            "player_x": self._player_x,
            "player_y": self._player_y,
            "aim_angle": self._aim_angle,
            "health": self._health,
            "shield_active": self._shield_active,
            "bullets": [{"x": b["x"], "y": b["y"]} for b in self._bullets],
            "enemies": [{"x": e["x"], "y": e["y"], "kind": e["kind"], "hp": e["hp"]} for e in self._enemies],
            "particles": list(self._particles),
            "score": self._score,
            "combo": self._combo,
            "best_combo": self._best_combo,
            "kills": self._kills,
            "wave_number": self._wave_number,
            "wave_count": self._wave_count,
            "tick": self._tick,
            "overlay_kind": self._overlay_kind,
            "level_title": self.current_level.title,
            "headline": self.current_level.title,
            "blocked": blocked,
            "conc_delta": conc_delta,
            "relax_delta": relax_delta,
            "arena_w": _NV_ARENA_W,
            "arena_h": _NV_ARENA_H,
            "serenity": max(0.0, min(100.0, 50.0 + relax_delta * 5.0)),
            "restlessness": max(0.0, min(100.0, 50.0 + conc_delta * 5.0)),
            "music_scene": "neon_vice",
            "music_bias": max(-1.0, min(1.0, (conc_delta - relax_delta) / 3.0)),
            "message": self._message,
        }


# ---------------------------------------------------------------------------
# Hill Climb Racer -- side-scrolling physics racer (focus gas / relax brake / gyro tilt)
# ---------------------------------------------------------------------------
_HC_GYRO_DEAD_ZONE = 0.05
_HC_GYRO_EMA_ALPHA = 0.25
_HC_TILT_SENSITIVITY = 3.0         # degrees per tick from head tilt
_HC_MAX_TILT = 60.0                # max car rotation degrees
_HC_GRAVITY = 0.35                 # downward acceleration
_HC_GAS_ACCEL = 0.18               # focus -> forward acceleration
_HC_BRAKE_DECEL = 0.25             # relax -> braking strength
_HC_DRAG = 0.985                   # velocity drag each tick
_HC_MAX_SPEED = 6.0                # max horizontal speed
_HC_FUEL_MAX = 100.0
_HC_FUEL_DRAIN = 0.12              # fuel consumed per tick while moving
_HC_FUEL_REFILL = 25.0             # fuel gained from canister
_HC_COIN_VALUE = 50                # points per coin
_HC_FLIP_BONUS = 200               # points for a full flip
_HC_AIR_BONUS_RATE = 2             # points per tick in air
_HC_CAR_W = 48.0
_HC_CAR_H = 24.0
_HC_ROAD_Y_BASE = 400.0            # base ground Y in logical coords
_HC_VIEW_W = 900.0                 # logical viewport width
_HC_VIEW_H = 500.0                 # logical viewport height
_HC_HILL_SEG_W = 60.0              # width of each terrain segment
_HC_PICKUP_RADIUS = 22.0           # collection radius for coins/fuel


class HillClimbRacerController(ArcadeTrainingController):
    """Side-scrolling physics racer -- Hill Climb Racing meets BCI.

    Controls
    --------
    * Focus (concentration) -> Gas pedal -- accelerate forward
    * Relaxation -> Brake -- slow down
    * Gyroscope (head tilt) -> Tilt car in mid-air to land safely
    * Steady state -> Coast at current speed
    """

    LEVELS = [
        TrainingLevel("Countryside", 60),
        TrainingLevel("Desert Canyon", 70),
        TrainingLevel("Arctic Ridge", 80),
    ]

    LEVEL_CONFIGS = [
        {"hill_intensity": 0.6, "fuel_freq": 8, "coin_freq": 5, "speed_scale": 1.0,
         "target_distance": 2500},
        {"hill_intensity": 0.85, "fuel_freq": 10, "coin_freq": 6, "speed_scale": 1.15,
         "target_distance": 3200},
        {"hill_intensity": 1.1, "fuel_freq": 12, "coin_freq": 7, "speed_scale": 1.3,
         "target_distance": 4000},
    ]

    def __init__(self) -> None:
        super().__init__(self.LEVELS)
        self._gyro_tilt = 0.0
        self._gyro_zero: float | None = None
        self._gyro_samples: list[float] = []
        self._gyro_calibrated = False

    # -- MEMS / gyroscope -------------------------------------------------

    def update_mems(self, accel_x, accel_y, accel_z,
                    gyro_x, gyro_y, gyro_z) -> None:
        raw = accel_y
        if not self._gyro_calibrated:
            self._gyro_samples.append(raw)
            if len(self._gyro_samples) >= 60:
                self._gyro_zero = sum(self._gyro_samples) / len(self._gyro_samples)
                self._gyro_calibrated = True
            return
        adj = raw - (self._gyro_zero or 0.0)
        if abs(adj) < _HC_GYRO_DEAD_ZONE:
            adj = 0.0
        self._gyro_tilt += _HC_GYRO_EMA_ALPHA * (adj - self._gyro_tilt)

    # -- level state ------------------------------------------------------

    def _reset_level_state(self) -> None:
        import random
        cfg = self.LEVEL_CONFIGS[self._level_index] if self._level_index < len(self.LEVEL_CONFIGS) else self.LEVEL_CONFIGS[-1]
        self._hill_intensity = cfg["hill_intensity"]
        self._fuel_freq = cfg["fuel_freq"]
        self._coin_freq = cfg["coin_freq"]
        self._speed_scale = cfg["speed_scale"]
        self._target_distance = cfg["target_distance"]

        self._car_x = 120.0          # screen-space X (stays roughly fixed)
        self._world_x = 0.0          # world distance traveled
        self._car_vx = 0.0           # horizontal velocity
        self._car_vy = 0.0           # vertical velocity
        self._car_angle = 0.0        # rotation degrees
        self._on_ground = True
        self._air_ticks = 0
        self._total_rotation = 0.0   # tracks rotation for flip detection
        self._flips = 0

        self._fuel = _HC_FUEL_MAX
        self._coins = 0
        self._score = 0
        self._distance = 0.0
        self._best_distance = 0.0
        self._tick = 0

        # Generate terrain as list of ground heights per segment
        self._terrain: list[float] = []
        self._generate_terrain(200, random)

        # Pickups: list of {world_x, kind, collected}
        self._pickups: list[dict] = []
        self._generate_pickups(random)

        self._overlay_kind: str | None = None
        self._overlay_ticks = 0
        self._message = ""
        self._view_state = {"mode": "hill_climb_racer"}

    def _generate_terrain(self, num_segments: int, rng) -> None:
        """Create a hilly terrain using simple sine-wave composition."""
        self._terrain = []
        for i in range(num_segments):
            base = _HC_ROAD_Y_BASE
            x_pos = i * _HC_HILL_SEG_W
            # Layer multiple sine waves for natural hills
            h1 = math.sin(x_pos * 0.008) * 60 * self._hill_intensity
            h2 = math.sin(x_pos * 0.015 + 1.5) * 35 * self._hill_intensity
            h3 = math.sin(x_pos * 0.003 + 3.0) * 80 * self._hill_intensity
            self._terrain.append(base - h1 - h2 - h3)

    def _generate_pickups(self, rng) -> None:
        """Place fuel canisters and coins along the terrain."""
        self._pickups = []
        for i in range(len(self._terrain)):
            wx = i * _HC_HILL_SEG_W
            if i > 3 and i % self._fuel_freq == 0:
                self._pickups.append({"world_x": wx, "y_offset": -40.0,
                                      "kind": "fuel", "collected": False})
            if i > 2 and i % self._coin_freq == 0:
                self._pickups.append({"world_x": wx, "y_offset": -35.0,
                                      "kind": "coin", "collected": False})

    def _ground_height_at(self, world_x: float) -> float:
        """Interpolate terrain height at a world X position."""
        seg = world_x / _HC_HILL_SEG_W
        idx = int(seg)
        frac = seg - idx
        if idx < 0:
            return self._terrain[0] if self._terrain else _HC_ROAD_Y_BASE
        if idx >= len(self._terrain) - 1:
            return self._terrain[-1] if self._terrain else _HC_ROAD_Y_BASE
        return self._terrain[idx] * (1 - frac) + self._terrain[idx + 1] * frac

    def _slope_angle_at(self, world_x: float) -> float:
        """Get the slope angle in degrees at a world X position."""
        seg = int(world_x / _HC_HILL_SEG_W)
        if seg < 0 or seg >= len(self._terrain) - 1:
            return 0.0
        dy = self._terrain[seg + 1] - self._terrain[seg]
        return math.degrees(math.atan2(dy, _HC_HILL_SEG_W))

    # -- gameplay loop ----------------------------------------------------

    def update_gameplay(self, concentration, relaxation, valid, stale,
                        elapsed_seconds) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked = ""
        moved = False
        level_done = False
        run_done = False
        self._tick += 1

        if self._overlay_kind is not None:
            self._overlay_ticks += 1
            if self._overlay_ticks >= 40:
                pct = min(100, int(self._distance / max(1, self._target_distance) * 100))
                if self._overlay_kind == "success":
                    self._record_level_result(True, elapsed_seconds, score_override=pct)
                else:
                    self._record_level_result(False, elapsed_seconds, score_override=max(10, pct // 2))
                level_done = True
                run_done = self._advance_level()
                self._overlay_kind = None
                self._overlay_ticks = 0

        elif stale:
            blocked = "Signal unavailable -- hold the headband steady"
        elif not valid:
            blocked = "Artifacts detected -- relax your jaw and forehead"
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            ground_y = self._ground_height_at(self._world_x)
            car_y = ground_y  # simplified -- car follows terrain when on ground

            # ---- gas / brake ----------------------------------------
            if intent == "focus" and self._fuel > 0:
                self._car_vx += _HC_GAS_ACCEL * self._speed_scale
                self._fuel -= _HC_FUEL_DRAIN
                moved = True
            elif intent == "relax":
                self._car_vx -= _HC_BRAKE_DECEL
                if self._car_vx < 0:
                    self._car_vx = 0.0

            # ---- drag -----------------------------------------------
            self._car_vx *= _HC_DRAG
            if self._car_vx > _HC_MAX_SPEED * self._speed_scale:
                self._car_vx = _HC_MAX_SPEED * self._speed_scale

            # ---- world movement -------------------------------------
            self._world_x += self._car_vx
            self._distance = self._world_x
            self._best_distance = max(self._best_distance, self._distance)

            # ---- terrain following / air detection -------------------
            new_ground = self._ground_height_at(self._world_x)
            slope = self._slope_angle_at(self._world_x)

            # Check if car is in the air (going over a hill crest)
            prev_ground = self._ground_height_at(self._world_x - self._car_vx)
            if self._on_ground and new_ground > prev_ground + 3.0 and self._car_vx > 1.5:
                self._on_ground = False
                self._car_vy = -self._car_vx * 0.3  # launch upward
                self._air_ticks = 0
                self._total_rotation = 0.0

            if not self._on_ground:
                # Air physics -- gyro controls rotation
                self._car_angle += self._gyro_tilt * _HC_TILT_SENSITIVITY
                self._car_angle = max(-_HC_MAX_TILT, min(_HC_MAX_TILT, self._car_angle))
                self._total_rotation += abs(self._gyro_tilt * _HC_TILT_SENSITIVITY)
                self._car_vy += _HC_GRAVITY
                self._air_ticks += 1
                self._score += _HC_AIR_BONUS_RATE

                # Check landing
                if self._car_vy > 0:  # falling
                    if car_y + self._car_vy >= new_ground:
                        self._on_ground = True
                        self._car_vy = 0.0
                        # Check if landed safely (not too tilted)
                        if abs(self._car_angle) > 50:
                            # Crash! -- flip too extreme
                            self._overlay_kind = "crash"
                            self._overlay_ticks = 0
                        else:
                            # Check for flip bonus
                            if self._total_rotation > 300:
                                self._flips += 1
                                self._score += _HC_FLIP_BONUS
                            self._car_angle = slope  # align to slope
            else:
                self._car_angle = slope

            # ---- pickup collection ----------------------------------
            for p in self._pickups:
                if p["collected"]:
                    continue
                dx = abs(p["world_x"] - self._world_x)
                if dx < _HC_PICKUP_RADIUS:
                    p["collected"] = True
                    if p["kind"] == "fuel":
                        self._fuel = min(_HC_FUEL_MAX, self._fuel + _HC_FUEL_REFILL)
                    elif p["kind"] == "coin":
                        self._coins += 1
                        self._score += _HC_COIN_VALUE

            # ---- fuel empty -----------------------------------------
            if self._fuel <= 0 and self._car_vx < 0.1 and self._overlay_kind is None:
                self._overlay_kind = "fuel"
                self._overlay_ticks = 0

            # ---- level completion -----------------------------------
            if self._distance >= self._target_distance and self._overlay_kind is None:
                self._overlay_kind = "success"
                self._overlay_ticks = 0

            # ---- time limit -----------------------------------------
            if elapsed_seconds >= self.current_level.target_seconds and self._overlay_kind is None:
                if self._distance >= self._target_distance:
                    self._overlay_kind = "success"
                else:
                    self._overlay_kind = "timeout"
                self._overlay_ticks = 0

        self._view_state = self._hc_view_state(blocked, conc_delta, relax_delta)

        return self._arcade_snapshot(
            phase="hill_climb_racer",
            phase_label=self.current_level.title,
            direction=self._hc_direction(),
            blocked_reason=blocked,
            control_hint="Focus to gas / Relax to brake / Tilt to balance",
            conc_delta=conc_delta,
            relax_delta=relax_delta,
            moved=moved,
            level_completed=level_done,
            run_completed=run_done,
            recommended_label=self._hc_recommendation(),
        )

    # -- helpers ----------------------------------------------------------

    def _hc_direction(self) -> str:
        if self._fuel <= 15:
            return "fuel"
        if not self._on_ground:
            return "balance"
        if self._car_vx > _HC_MAX_SPEED * 0.7:
            return "fast"
        return "focus"

    def _hc_recommendation(self) -> str:
        if self._overlay_kind == "success":
            return "Level clear!"
        if self._overlay_kind == "crash":
            return "You crashed!"
        if self._overlay_kind == "fuel":
            return "Out of fuel!"
        if self._overlay_kind == "timeout":
            return "Time up"
        if self._fuel <= 15:
            return "Low fuel!"
        if not self._on_ground:
            return "Balance the car!"
        if self._car_vx < 0.5:
            return "Focus to accelerate"
        if self._flips > 0 and self._air_ticks > 0:
            return f"Nice flip! x{self._flips}"
        return "Keep driving!"

    def _hc_view_state(self, blocked: str, conc_delta: float, relax_delta: float) -> dict:
        # Build visible terrain segments centered on car position
        vis_start = int(self._world_x / _HC_HILL_SEG_W) - 2
        vis_end = vis_start + int(_HC_VIEW_W / _HC_HILL_SEG_W) + 4
        terrain_vis = []
        for i in range(max(0, vis_start), min(len(self._terrain), vis_end)):
            terrain_vis.append({
                "world_x": i * _HC_HILL_SEG_W,
                "y": self._terrain[i],
            })

        # Visible pickups
        vis_pickups = []
        for p in self._pickups:
            if not p["collected"] and abs(p["world_x"] - self._world_x) < _HC_VIEW_W:
                vis_pickups.append(p)

        return {
            "mode": "hill_climb_racer",
            "world_x": self._world_x,
            "car_x": self._car_x,
            "car_angle": self._car_angle,
            "car_vx": self._car_vx,
            "on_ground": self._on_ground,
            "air_ticks": self._air_ticks,
            "fuel": self._fuel,
            "coins": self._coins,
            "score": self._score,
            "distance": self._distance,
            "target_distance": self._target_distance,
            "best_distance": self._best_distance,
            "flips": self._flips,
            "terrain": terrain_vis,
            "pickups": vis_pickups,
            "tick": self._tick,
            "overlay_kind": self._overlay_kind,
            "level_title": self.current_level.title,
            "headline": self.current_level.title,
            "blocked": blocked,
            "conc_delta": conc_delta,
            "relax_delta": relax_delta,
            "view_w": _HC_VIEW_W,
            "view_h": _HC_VIEW_H,
            "serenity": max(0.0, min(100.0, 50.0 + relax_delta * 5.0)),
            "restlessness": max(0.0, min(100.0, 50.0 + conc_delta * 5.0)),
            "music_scene": "hill_climb",
            "music_bias": max(-1.0, min(1.0, (conc_delta - relax_delta) / 3.0)),
            "message": self._message,
        }


# ═══════════════════════════════════════════════════════════════════════
#  GRAVITY DRIFT – Neon tunnel flyer (gyro steer + focus/relax powers)
# ═══════════════════════════════════════════════════════════════════════

_GD_GYRO_DEAD_ZONE = 0.04
_GD_GYRO_EMA = 0.30


class GravityDriftController(ArcadeTrainingController):
    """Pilot an orb through a neon tunnel. Gyro steers, focus = speed/shield,
    relax = bullet-time to navigate tight gaps."""

    LEVELS = [
        TrainingLevel("Neon Gate", 55),
        TrainingLevel("Plasma Corridor", 65),
        TrainingLevel("Void Run", 80),
    ]
    LEVEL_CONFIGS = [
        {"base_speed": 2.5, "gap_min": 0.45, "gap_shrink": 0.02, "obstacle_interval": 1.8},
        {"base_speed": 3.5, "gap_min": 0.35, "gap_shrink": 0.025, "obstacle_interval": 1.4},
        {"base_speed": 4.5, "gap_min": 0.25, "gap_shrink": 0.03, "obstacle_interval": 1.0},
    ]

    def __init__(self) -> None:
        super().__init__(self.LEVELS)
        self._gyro_x = 0.0
        self._gyro_y = 0.0
        self._gyro_zero_x = 0.0
        self._gyro_zero_y = 0.0
        self._gyro_samples: list[tuple[float, float]] = []
        self._gyro_calibrated = False

    def update_mems(self, accel_x: float, accel_y: float, accel_z: float,
                    gyro_x: float, gyro_y: float, gyro_z: float) -> None:
        raw_x, raw_y = accel_y, accel_x
        if not self._gyro_calibrated:
            self._gyro_samples.append((raw_x, raw_y))
            if len(self._gyro_samples) >= 60:
                self._gyro_zero_x = sum(s[0] for s in self._gyro_samples) / len(self._gyro_samples)
                self._gyro_zero_y = sum(s[1] for s in self._gyro_samples) / len(self._gyro_samples)
                self._gyro_calibrated = True
            return
        ax = raw_x - self._gyro_zero_x
        ay = raw_y - self._gyro_zero_y
        if abs(ax) < _GD_GYRO_DEAD_ZONE:
            ax = 0.0
        if abs(ay) < _GD_GYRO_DEAD_ZONE:
            ay = 0.0
        self._gyro_x += _GD_GYRO_EMA * (ax - self._gyro_x)
        self._gyro_y += _GD_GYRO_EMA * (ay - self._gyro_y)

    def _reset_level_state(self) -> None:
        cfg = self.LEVEL_CONFIGS[self._level_index]
        self._base_speed: float = cfg["base_speed"]
        self._gap_min: float = cfg["gap_min"]
        self._gap_shrink: float = cfg["gap_shrink"]
        self._obstacle_interval: float = cfg["obstacle_interval"]
        self._orb_x: float = 0.5
        self._orb_y: float = 0.5
        self._speed: float = self._base_speed
        self._shield_active: bool = False
        self._bullet_time: bool = False
        self._score: int = 0
        self._distance: float = 0.0
        self._hull: int = 4
        self._obstacles: list[dict] = []
        self._particles: list[dict] = []
        self._spawn_timer: float = 0.0
        self._tick: int = 0
        self._message = ""

    def update_gameplay(self, concentration: float, relaxation: float,
                        valid: bool, stale: bool, elapsed_seconds: float) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked = ""
        moved = False
        level_completed = False
        run_completed = False

        if stale:
            blocked = "Waiting for signal…"
        elif not valid:
            blocked = "Artifacts detected – paused"
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)
            self._orb_x = max(0.05, min(0.95, self._orb_x + self._gyro_x * 0.08))
            self._orb_y = max(0.10, min(0.90, self._orb_y + self._gyro_y * 0.06))
            moved = abs(self._gyro_x) > _GD_GYRO_DEAD_ZONE or abs(self._gyro_y) > _GD_GYRO_DEAD_ZONE

            self._shield_active = False
            self._bullet_time = False
            speed_mult = 1.0
            if intent == "focus":
                speed_mult = 1.6
                self._shield_active = True
            elif intent == "relax":
                speed_mult = 0.4
                self._bullet_time = True

            self._speed = self._base_speed * speed_mult
            dt = 0.25
            self._distance += self._speed * dt
            self._spawn_timer += dt

            if self._spawn_timer >= self._obstacle_interval:
                self._spawn_timer = 0.0
                gap_center = 0.15 + (hash(int(self._distance * 100)) % 70) / 100.0
                gap_width = max(self._gap_min, 0.55 - self._gap_shrink * len(self._obstacles))
                self._obstacles.append({
                    "y": -0.05, "gap_center": gap_center, "gap_width": gap_width,
                    "color_shift": (hash(int(self._distance * 37)) % 360),
                })

            survived = []
            for obs in self._obstacles:
                obs["y"] += self._speed * dt * 0.018
                if obs["y"] > 1.15:
                    self._score += 10 + int(speed_mult * 5)
                    continue
                if 0.80 < obs["y"] < 0.95:
                    gc, gw = obs["gap_center"], obs["gap_width"]
                    if self._orb_x < gc - gw / 2 or self._orb_x > gc + gw / 2:
                        if not self._shield_active:
                            self._hull -= 1
                            self._message = "Impact!"
                            self._particles.extend([
                                {"x": self._orb_x, "y": self._orb_y, "dx": (i - 4) * 0.02,
                                 "dy": -0.03 + i * 0.005, "life": 12}
                                for i in range(8)
                            ])
                            if self._hull <= 0:
                                run_completed = True
                        else:
                            self._score += 25
                            self._message = "Shielded!"
                        obs["y"] = 1.2
                survived.append(obs)
            self._obstacles = survived

            alive_p = []
            for p in self._particles:
                p["x"] += p["dx"]
                p["y"] += p["dy"]
                p["life"] -= 1
                if p["life"] > 0:
                    alive_p.append(p)
            self._particles = alive_p

            target_dist = self.current_level.target_seconds * self._base_speed * 0.8
            if self._distance >= target_dist and not run_completed:
                level_completed = True
                self._record_level_result(True, elapsed_seconds)
                run_completed = self._advance_level()

            self._tick += 1

        self._view_state = {
            "mode": "gravity_drift",
            "orb_x": self._orb_x, "orb_y": self._orb_y,
            "speed": self._speed, "shield": self._shield_active,
            "bullet_time": self._bullet_time,
            "score": self._score, "hull": self._hull,
            "distance": self._distance,
            "obstacles": list(self._obstacles),
            "particles": list(self._particles),
            "tick": self._tick,
            "message": self._message if not blocked else blocked,
            "level_title": self.current_level.title,
            "headline": self.current_level.title,
            "blocked": blocked,
            "conc_delta": conc_delta,
            "relax_delta": relax_delta,
            "serenity": max(0.0, min(100.0, 50.0 + relax_delta * 5.0)),
            "restlessness": max(0.0, min(100.0, 50.0 + conc_delta * 5.0)),
            "music_scene": "gravity_drift",
            "music_bias": max(-1.0, min(1.0, (conc_delta - relax_delta) / 3.0)),
        }

        action = "focus" if self._shield_active else ("relax" if self._bullet_time else None)
        return self._arcade_snapshot(
            phase="gravity_drift", phase_label="Gravity Drift",
            direction=action, blocked_reason=blocked,
            control_hint="Tilt head to steer • Focus for shield • Relax for slow-motion",
            conc_delta=conc_delta, relax_delta=relax_delta,
            moved=moved, level_completed=level_completed, run_completed=run_completed,
            recommended_label="Steer through gaps",
        )


# ═══════════════════════════════════════════════════════════════════════
#  SYNAPSE SERPENT – Brain-controlled snake (gyro tilts board, focus/relax powers)
# ═══════════════════════════════════════════════════════════════════════

_SS_GRID = 20
_SS_CELL = 30.0


class SynapseSerpentController(ArcadeTrainingController):
    """Snake on a tiltable neural circuit board. Gyro tilts the board causing
    the snake to slide. Focus = grow + points. Relax = phase-shift (pass through tail)."""

    LEVELS = [
        TrainingLevel("Cortex", 60),
        TrainingLevel("Thalamus", 70),
        TrainingLevel("Brainstem", 85),
    ]
    LEVEL_CONFIGS = [
        {"food_value": 10, "slide_speed": 1.0, "phase_duration": 12},
        {"food_value": 15, "slide_speed": 1.3, "phase_duration": 10},
        {"food_value": 20, "slide_speed": 1.6, "phase_duration": 8},
    ]

    def __init__(self) -> None:
        super().__init__(self.LEVELS)
        self._gyro_x = 0.0
        self._gyro_y = 0.0
        self._gyro_zero_x = 0.0
        self._gyro_zero_y = 0.0
        self._gyro_samples: list[tuple[float, float]] = []
        self._gyro_calibrated = False

    def update_mems(self, accel_x: float, accel_y: float, accel_z: float,
                    gyro_x: float, gyro_y: float, gyro_z: float) -> None:
        raw_x, raw_y = accel_y, accel_x
        if not self._gyro_calibrated:
            self._gyro_samples.append((raw_x, raw_y))
            if len(self._gyro_samples) >= 60:
                self._gyro_zero_x = sum(s[0] for s in self._gyro_samples) / len(self._gyro_samples)
                self._gyro_zero_y = sum(s[1] for s in self._gyro_samples) / len(self._gyro_samples)
                self._gyro_calibrated = True
            return
        ax = raw_x - self._gyro_zero_x
        ay = raw_y - self._gyro_zero_y
        if abs(ax) < _GD_GYRO_DEAD_ZONE:
            ax = 0.0
        if abs(ay) < _GD_GYRO_DEAD_ZONE:
            ay = 0.0
        self._gyro_x += _GD_GYRO_EMA * (ax - self._gyro_x)
        self._gyro_y += _GD_GYRO_EMA * (ay - self._gyro_y)

    def _reset_level_state(self) -> None:
        cfg = self.LEVEL_CONFIGS[self._level_index]
        self._food_value: int = cfg["food_value"]
        self._slide_speed: float = cfg["slide_speed"]
        self._max_phase: int = cfg["phase_duration"]
        mid = _SS_GRID // 2
        self._snake: list[tuple[int, int]] = [(mid, mid), (mid - 1, mid), (mid - 2, mid)]
        self._direction: tuple[int, int] = (1, 0)
        self._food: tuple[int, int] = self._place_food()
        self._score: int = 0
        self._phase_shift: bool = False
        self._phase_ticks: int = 0
        self._combo: int = 0
        self._synapses: list[dict] = []
        self._tick: int = 0
        self._alive: bool = True
        self._message = ""

    def _place_food(self) -> tuple[int, int]:
        import random as _rng
        for _ in range(200):
            x = _rng.randint(1, _SS_GRID - 2)
            y = _rng.randint(1, _SS_GRID - 2)
            if (x, y) not in self._snake:
                return (x, y)
        return (1, 1)

    def update_gameplay(self, concentration: float, relaxation: float,
                        valid: bool, stale: bool, elapsed_seconds: float) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked = ""
        moved = False
        level_completed = False
        run_completed = False

        if stale:
            blocked = "Waiting for signal…"
        elif not valid:
            blocked = "Artifacts – serpent frozen"
        elif not self._alive:
            blocked = "Game over"
            run_completed = True
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)

            threshold = 0.08 * self._slide_speed
            if abs(self._gyro_x) > abs(self._gyro_y):
                if self._gyro_x > threshold:
                    new_dir = (1, 0)
                elif self._gyro_x < -threshold:
                    new_dir = (-1, 0)
                else:
                    new_dir = self._direction
            else:
                if self._gyro_y > threshold:
                    new_dir = (0, 1)
                elif self._gyro_y < -threshold:
                    new_dir = (0, -1)
                else:
                    new_dir = self._direction

            if (new_dir[0] + self._direction[0], new_dir[1] + self._direction[1]) != (0, 0):
                self._direction = new_dir

            head = self._snake[0]
            nx = (head[0] + self._direction[0]) % _SS_GRID
            ny = (head[1] + self._direction[1]) % _SS_GRID
            moved = True

            if (nx, ny) in self._snake[1:] and not self._phase_shift:
                self._alive = False
                self._message = "Collision!"
                run_completed = True
            else:
                self._snake.insert(0, (nx, ny))
                if (nx, ny) == self._food:
                    self._score += self._food_value + self._combo * 5
                    self._combo += 1
                    self._food = self._place_food()
                    self._synapses.append({"x": nx, "y": ny, "life": 15})
                else:
                    self._snake.pop()

            if intent == "relax" and not self._phase_shift:
                self._phase_shift = True
                self._phase_ticks = self._max_phase
            if self._phase_shift:
                self._phase_ticks -= 1
                if self._phase_ticks <= 0:
                    self._phase_shift = False

            if intent == "focus":
                self._score += 2

            self._synapses = [s for s in self._synapses if (s.__setitem__("life", s["life"] - 1) or s["life"] > 0)]  # noqa: E501

            self._tick += 1
            target_ticks = self.current_level.target_seconds * 4
            if self._tick >= target_ticks and self._alive:
                level_completed = True
                self._record_level_result(True, elapsed_seconds)
                run_completed = self._advance_level()

        self._view_state = {
            "mode": "synapse_serpent",
            "grid": _SS_GRID, "cell": _SS_CELL,
            "snake": list(self._snake), "food": self._food,
            "direction": self._direction,
            "score": self._score, "combo": self._combo,
            "phase_shift": self._phase_shift, "phase_ticks": self._phase_ticks,
            "synapses": [dict(s) for s in self._synapses],
            "alive": self._alive, "tick": self._tick,
            "message": self._message if not blocked else blocked,
            "level_title": self.current_level.title,
            "headline": self.current_level.title,
            "blocked": blocked,
            "conc_delta": conc_delta,
            "relax_delta": relax_delta,
            "serenity": max(0.0, min(100.0, 50.0 + relax_delta * 5.0)),
            "restlessness": max(0.0, min(100.0, 50.0 + conc_delta * 5.0)),
            "music_scene": "synapse_serpent",
            "music_bias": max(-1.0, min(1.0, (conc_delta - relax_delta) / 3.0)),
        }

        action = "relax" if self._phase_shift else ("focus" if conc_delta > relax_delta else None)
        return self._arcade_snapshot(
            phase="synapse_serpent", phase_label="Synapse Serpent",
            direction=action, blocked_reason=blocked,
            control_hint="Tilt to steer • Focus for points • Relax to phase-shift",
            conc_delta=conc_delta, relax_delta=relax_delta,
            moved=moved, level_completed=level_completed, run_completed=run_completed,
            recommended_label="Navigate the neural network",
        )


# ═══════════════════════════════════════════════════════════════════════
#  AERO ZEN – Minimalist crane flyer (gyro altitude + focus/relax weather)
# ═══════════════════════════════════════════════════════════════════════

_AZ_GYRO_DEAD_ZONE = 0.04
_AZ_GYRO_EMA = 0.28


class AeroZenController(ArcadeTrainingController):
    """Fly a paper crane through a parallax landscape. Gyro Y controls altitude.
    Focus = wind burst, relaxation = thermal updraft + sky clears."""

    LEVELS = [
        TrainingLevel("Morning Mist", 50),
        TrainingLevel("Mountain Pass", 60),
        TrainingLevel("Sky Temple", 75),
    ]
    LEVEL_CONFIGS = [
        {"wind_strength": 0.8, "obstacle_rate": 2.2, "storm_threshold": 0.65},
        {"wind_strength": 1.2, "obstacle_rate": 1.6, "storm_threshold": 0.50},
        {"wind_strength": 1.6, "obstacle_rate": 1.1, "storm_threshold": 0.40},
    ]

    def __init__(self) -> None:
        super().__init__(self.LEVELS)
        self._gyro_y = 0.0
        self._gyro_zero_y = 0.0
        self._gyro_samples: list[float] = []
        self._gyro_calibrated = False

    def update_mems(self, accel_x: float, accel_y: float, accel_z: float,
                    gyro_x: float, gyro_y: float, gyro_z: float) -> None:
        raw_y = accel_x
        if not self._gyro_calibrated:
            self._gyro_samples.append(raw_y)
            if len(self._gyro_samples) >= 60:
                self._gyro_zero_y = sum(self._gyro_samples) / len(self._gyro_samples)
                self._gyro_calibrated = True
            return
        adj = raw_y - self._gyro_zero_y
        if abs(adj) < _AZ_GYRO_DEAD_ZONE:
            adj = 0.0
        self._gyro_y += _AZ_GYRO_EMA * (adj - self._gyro_y)

    def _reset_level_state(self) -> None:
        cfg = self.LEVEL_CONFIGS[self._level_index]
        self._wind_strength: float = cfg["wind_strength"]
        self._obstacle_rate: float = cfg["obstacle_rate"]
        self._storm_threshold: float = cfg["storm_threshold"]
        self._crane_y: float = 0.5
        self._crane_vy: float = 0.0
        self._scroll_x: float = 0.0
        self._score: int = 0
        self._zen_score: float = 0.0
        self._zen_streak: float = 0.0
        self._sky_serenity: float = 0.5
        self._obstacles: list[dict] = []
        self._zen_gates: list[dict] = []
        self._blossoms: list[dict] = []
        self._mountains: list[dict] = self._gen_mountains()
        self._spawn_timer: float = 0.0
        self._hull: int = 3
        self._tick: int = 0
        self._message = ""
        self._color_saturation: float = 0.1

    def _gen_mountains(self) -> list[dict]:
        return [
            {"x": i * 0.15, "height": 0.2 + (hash(i * 79 + self._level_index) % 30) / 100.0,
             "width": 0.12 + (hash(i * 41) % 8) / 100.0}
            for i in range(12)
        ]

    def update_gameplay(self, concentration: float, relaxation: float,
                        valid: bool, stale: bool, elapsed_seconds: float) -> GameplaySnapshot:
        conc_delta = concentration - (self._conc_baseline or 0.0)
        relax_delta = relaxation - (self._relax_baseline or 0.0)
        blocked = ""
        moved = False
        level_completed = False
        run_completed = False

        if stale:
            blocked = "Waiting for signal…"
        elif not valid:
            blocked = "Artifacts – gliding…"
        else:
            intent = self._arcade_intent(conc_delta, relax_delta)

            self._crane_vy += self._gyro_y * 0.015
            self._crane_vy *= 0.92

            if intent == "relax":
                self._crane_vy -= 0.008
                self._sky_serenity = min(1.0, self._sky_serenity + 0.015)
                self._zen_streak += 0.25
                self._color_saturation = min(1.0, self._color_saturation + 0.008)
                if self._tick % 8 == 0:
                    self._blossoms.append({
                        "x": 1.05, "y": 0.2 + (self._tick * 17 % 60) / 100.0,
                        "drift": -0.008, "life": 40,
                    })
            elif intent == "focus":
                self._scroll_x += self._wind_strength * 0.02
                self._score += 3
                self._sky_serenity = max(0.0, self._sky_serenity - 0.005)
                self._zen_streak = 0.0
            else:
                self._sky_serenity = max(0.3, self._sky_serenity - 0.003)
                self._zen_streak = max(0.0, self._zen_streak - 0.1)

            self._crane_y = max(0.05, min(0.95, self._crane_y + self._crane_vy))
            moved = abs(self._gyro_y) > _AZ_GYRO_DEAD_ZONE

            if self._zen_streak > 4.0:
                self._zen_score += 0.5

            self._scroll_x += 0.005 + (self._sky_serenity * 0.003)
            self._spawn_timer += 0.25

            if self._spawn_timer >= self._obstacle_rate:
                self._spawn_timer = 0.0
                if self._sky_serenity < self._storm_threshold:
                    cloud_y = 0.15 + (hash(int(self._scroll_x * 100)) % 60) / 100.0
                    self._obstacles.append({
                        "x": 1.1, "y": cloud_y, "width": 0.12, "height": 0.08, "kind": "storm",
                    })
                else:
                    gate_y = 0.2 + (hash(int(self._scroll_x * 77)) % 50) / 100.0
                    self._zen_gates.append({"x": 1.1, "y": gate_y, "collected": False})

            alive_obs = []
            for obs in self._obstacles:
                obs["x"] -= 0.012
                if obs["x"] < -0.15:
                    continue
                if (abs(obs["x"] - 0.15) < obs["width"] / 2 and
                        abs(obs["y"] - self._crane_y) < obs["height"] / 2):
                    self._hull -= 1
                    self._message = "Storm hit!"
                    if self._hull <= 0:
                        run_completed = True
                    obs["x"] = -0.2
                alive_obs.append(obs)
            self._obstacles = alive_obs

            alive_gates = []
            for g in self._zen_gates:
                g["x"] -= 0.010
                if g["x"] < -0.1:
                    continue
                if not g["collected"] and abs(g["x"] - 0.15) < 0.04 and abs(g["y"] - self._crane_y) < 0.06:
                    g["collected"] = True
                    self._score += 30
                    self._zen_score += 2.0
                alive_gates.append(g)
            self._zen_gates = alive_gates

            alive_b = []
            for b in self._blossoms:
                b["x"] += b["drift"]
                b["y"] += math.sin(b["life"] * 0.3) * 0.003
                b["life"] -= 1
                if b["life"] > 0 and b["x"] > -0.05:
                    alive_b.append(b)
            self._blossoms = alive_b

            self._tick += 1
            target_ticks = self.current_level.target_seconds * 4
            if self._tick >= target_ticks and not run_completed:
                level_completed = True
                self._record_level_result(True, elapsed_seconds)
                run_completed = self._advance_level()

        self._view_state = {
            "mode": "aero_zen",
            "crane_y": self._crane_y, "crane_vy": self._crane_vy,
            "scroll_x": self._scroll_x,
            "score": self._score, "zen_score": self._zen_score,
            "zen_streak": self._zen_streak,
            "sky_serenity": self._sky_serenity,
            "color_saturation": self._color_saturation,
            "hull": self._hull,
            "obstacles": list(self._obstacles),
            "zen_gates": list(self._zen_gates),
            "blossoms": list(self._blossoms),
            "mountains": list(self._mountains),
            "tick": self._tick, "message": self._message if not blocked else blocked,
            "level_title": self.current_level.title,
            "headline": self.current_level.title,
            "blocked": blocked,
            "conc_delta": conc_delta,
            "relax_delta": relax_delta,
            "serenity": max(0.0, min(100.0, 50.0 + relax_delta * 5.0)),
            "restlessness": max(0.0, min(100.0, 50.0 + conc_delta * 5.0)),
            "music_scene": "aero_zen",
            "music_bias": max(-1.0, min(1.0, (conc_delta - relax_delta) / 3.0)),
        }

        action = "relax" if self._zen_streak > 2 else ("focus" if conc_delta > 0.15 else None)
        return self._arcade_snapshot(
            phase="aero_zen", phase_label="Aero Zen",
            direction=action, blocked_reason=blocked,
            control_hint="Tilt to fly • Relax for lift & clear skies • Focus for wind burst",
            conc_delta=conc_delta, relax_delta=relax_delta,
            moved=moved, level_completed=level_completed, run_completed=run_completed,
            recommended_label="Find your zen altitude",
        )
