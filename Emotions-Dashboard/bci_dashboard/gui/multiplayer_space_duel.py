"""
Multiplayer Space Duel – 2-player parallel space shooter.

Both players fly identical missions (same wave spawns).
Concentration moves ship RIGHT, relaxation moves LEFT,
steady state fires burst.  Winner = higher score after 3 waves.
"""
from __future__ import annotations

import time
from gui.eeg_game_base import (
    CALIBRATION_SAMPLES,
    READY_DELTA_THRESHOLD,
    READY_STREAK_TARGET,
    TrainingLevel,
)

# ── Thresholds (same as single-player arcade) ────────────────────
ARCADE_BALANCE_THRESHOLD = 0.8
ARCADE_DELTA_THRESHOLD = 0.15
ARCADE_STEADY_DEAD_ZONE = 0.35

CORRIDOR_WIDTH = 7
FIELD_HEIGHT = 120.0
SHIP_Y = 104.0
HULL_MAX = 4

# Wave spawns shared by both players: (slot, y_start, hp, drop_type, score)
WAVE_CONFIGS = [
    # --- Level 0 – 3 waves, wave_speed=6.4 ---
    {
        "wave_speed": 6.4,
        "star_thresholds": [280, 520, 760],
        "waves": [
            [(1, -4.0, 1, None, 60), (3, -18.0, 1, None, 60), (5, -32.0, 1, "repair", 70)],
            [(2, -8.0, 1, None, 70), (4, -20.0, 1, "weapon", 80), (2, -34.0, 1, None, 70), (4, -46.0, 1, None, 70)],
            [(1, -10.0, 2, None, 120), (3, -22.0, 1, None, 80), (5, -34.0, 2, None, 120)],
        ],
    },
]

INTENT_STREAK_NEEDED = 2


class _PlayerState:
    """All mutable per-player state for one space-shooter simulation."""

    def __init__(self):
        self.ship_slot: int = CORRIDOR_WIDTH // 2
        self.hull: int = HULL_MAX
        self.score: int = 0
        self.weapon_level: int = 1
        self.burst_ticks: int = 0
        self.streak: int = 0
        self.best_streak: int = 0
        self.shots_fired: int = 0
        self.destroyed: int = 0
        self.pickups_collected: int = 0
        self.hits_taken: int = 0

        self.enemies: list[dict] = []
        self.projectiles: list[dict] = []
        self.pickups: list[dict] = []
        self.explosions: list[dict] = []
        self.score_popups: list[dict] = []

        self.wave_index: int = 0
        self.wave_active: bool = False
        self.wave_spawned: bool = False
        self.overlay_kind: str | None = None
        self.overlay_title: str = ""
        self.overlay_subtitle: str = ""
        self.overlay_timer: int = 0
        self.finished: bool = False
        self.message: str = "Focus to move right, relax to move left, hold steady to fire."

        # Intent stabilisation
        self._intent_streak_label: str | None = None
        self._intent_streak_count: int = 0


class MultiplayerSpaceDuelController:
    """Authoritative controller for 2-player Space Duel.

    Runs two parallel space-shooter simulations with identical wave
    spawns.  The server ticks both and broadcasts per-player views.
    """

    def __init__(self, p1_name: str = "Player 1", p2_name: str = "Player 2"):
        self._p1_name = p1_name
        self._p2_name = p2_name
        self._config = WAVE_CONFIGS[0]
        self._wave_speed: float = self._config["wave_speed"]
        self._star_thresholds: list[int] = self._config["star_thresholds"]
        self._waves = self._config["waves"]
        self._started_at: float | None = None

        self._players = {0: _PlayerState(), 1: _PlayerState()}

        # Per-player calibration (same pattern as tug-of-war)
        self._cal = {
            0: {"samples": [], "baseline_conc": None, "baseline_relax": None,
                "ready_streak": 0, "complete": False},
            1: {"samples": [], "baseline_conc": None, "baseline_relax": None,
                "ready_streak": 0, "complete": False},
        }

    # ── Calibration ───────────────────────────────────────────────
    def add_calibration_sample_for(self, player_id: int, conc: float,
                                   relax: float, valid: bool) -> dict:
        cal = self._cal[player_id]
        if not valid:
            cal["ready_streak"] = 0
            return self._cal_snapshot(cal)

        if len(cal["samples"]) < CALIBRATION_SAMPLES:
            cal["samples"].append((conc, relax))

        if len(cal["samples"]) >= CALIBRATION_SAMPLES and cal["baseline_conc"] is None:
            cal["baseline_conc"] = sum(s[0] for s in cal["samples"]) / len(cal["samples"])
            cal["baseline_relax"] = sum(s[1] for s in cal["samples"]) / len(cal["samples"])

        if cal["baseline_conc"] is not None:
            ready_delta = (relax - cal["baseline_relax"]) - (conc - cal["baseline_conc"])
            if ready_delta >= READY_DELTA_THRESHOLD:
                cal["ready_streak"] += 1
            else:
                cal["ready_streak"] = 0
            cal["complete"] = cal["ready_streak"] >= READY_STREAK_TARGET

        return self._cal_snapshot(cal)

    @staticmethod
    def _cal_snapshot(cal: dict) -> dict:
        progress = min(1.0, len(cal["samples"]) / CALIBRATION_SAMPLES)
        return {
            "progress": progress,
            "sample_count": len(cal["samples"]),
            "samples_needed": CALIBRATION_SAMPLES,
            "complete": cal["complete"],
            "baseline_conc": cal["baseline_conc"],
            "baseline_relax": cal["baseline_relax"],
        }

    # ── Lifecycle ─────────────────────────────────────────────────
    def start_game(self):
        self._started_at = time.monotonic()
        for ps in self._players.values():
            self._spawn_wave(ps, 0)

    # ── Game tick ─────────────────────────────────────────────────
    def tick(self, p1_metrics: dict, p2_metrics: dict) -> dict:
        elapsed = time.monotonic() - (self._started_at or time.monotonic())

        self._tick_player(0, p1_metrics)
        self._tick_player(1, p2_metrics)

        p1_done = self._players[0].finished
        p2_done = self._players[1].finished
        run_completed = p1_done and p2_done

        winner = None
        if run_completed:
            s1 = self._players[0].score
            s2 = self._players[1].score
            if s1 > s2:
                winner = "player1"
            elif s2 > s1:
                winner = "player2"
            else:
                winner = "draw"

        return {
            "mode": "mp_space_duel",
            "player_views": {
                "0": self._view_state(0),
                "1": self._view_state(1),
            },
            "player1_name": self._p1_name,
            "player2_name": self._p2_name,
            "player1_score": self._players[0].score,
            "player2_score": self._players[1].score,
            "run_completed": run_completed,
            "winner": winner,
            "elapsed_seconds": round(elapsed, 1),
        }

    # ── Per-player tick ───────────────────────────────────────────
    def _tick_player(self, pid: int, metrics: dict):
        ps = self._players[pid]
        if ps.finished:
            return

        # Decay overlay timer
        if ps.overlay_timer > 0:
            ps.overlay_timer -= 1
            if ps.overlay_timer <= 0:
                ps.overlay_kind = None
                if ps.wave_index < len(self._waves):
                    self._spawn_wave(ps, ps.wave_index)
                else:
                    ps.finished = True
            return

        conc = metrics.get("concentration", 0.0)
        relax = metrics.get("relaxation", 0.0)
        valid = metrics.get("valid", False)
        stale = metrics.get("stale", False)

        base_c = self._cal[pid].get("baseline_conc") or 0.0
        base_r = self._cal[pid].get("baseline_relax") or 0.0
        conc_delta = conc - base_c
        relax_delta = relax - base_r

        # Determine intent
        intent = self._arcade_intent(conc_delta, relax_delta) if valid and not stale else None

        # Stabilise intent
        intent = self._stabilise_intent(ps, intent)

        # Apply intent
        if intent == "focus":
            ps.ship_slot = min(CORRIDOR_WIDTH - 1, ps.ship_slot + 1)
            ps.message = "Shifted into the right corridor."
        elif intent == "relax":
            ps.ship_slot = max(0, ps.ship_slot - 1)
            ps.message = "Drifted back toward the left."
        elif intent == "steady":
            ps.burst_ticks = max(ps.burst_ticks, 4)
            ps.message = "Burst cannons engaged."

        # Fire projectiles
        if ps.burst_ticks > 0:
            ps.burst_ticks -= 1
            self._fire(ps)

        # Advance entities
        self._advance_projectiles(ps)
        self._advance_enemies(ps)
        self._advance_pickups(ps)
        self._decay_effects(ps)

        # Check wave complete
        if ps.wave_spawned and not ps.enemies and ps.overlay_kind is None:
            ps.wave_index += 1
            if ps.wave_index >= len(self._waves):
                ps.overlay_kind = "level_complete"
                ps.overlay_title = "Mission Complete!"
                ps.overlay_subtitle = f"Score: {ps.score}"
                ps.overlay_timer = 8
            else:
                ps.overlay_kind = "wave_clear"
                ps.overlay_title = f"Wave {ps.wave_index} cleared!"
                ps.overlay_subtitle = f"Score: {ps.score}"
                ps.overlay_timer = 6

    @staticmethod
    def _arcade_intent(conc_delta: float, relax_delta: float) -> str | None:
        balance = conc_delta - relax_delta
        if balance >= ARCADE_BALANCE_THRESHOLD and conc_delta >= ARCADE_DELTA_THRESHOLD:
            return "focus"
        if balance <= -ARCADE_BALANCE_THRESHOLD and relax_delta >= ARCADE_DELTA_THRESHOLD:
            return "relax"
        if abs(balance) <= ARCADE_STEADY_DEAD_ZONE:
            return "steady"
        return None

    @staticmethod
    def _stabilise_intent(ps: _PlayerState, raw: str | None) -> str | None:
        if raw is None:
            ps._intent_streak_label = None
            ps._intent_streak_count = 0
            return None
        if raw == ps._intent_streak_label:
            ps._intent_streak_count += 1
        else:
            ps._intent_streak_label = raw
            ps._intent_streak_count = 1
        if ps._intent_streak_count >= INTENT_STREAK_NEEDED:
            ps._intent_streak_count = 0
            return raw
        return None

    # ── Spawning ──────────────────────────────────────────────────
    def _spawn_wave(self, ps: _PlayerState, wave_idx: int):
        ps.wave_spawned = True
        wave = self._waves[wave_idx]
        for slot, y, hp, drop, score in wave:
            speed = self._wave_speed + 0.35 * max(0, hp - 1)
            ps.enemies.append({
                "slot": slot, "y": y, "hp": hp, "max_hp": hp,
                "drop": drop, "score": score, "speed": speed,
            })

    # ── Projectiles ───────────────────────────────────────────────
    def _fire(self, ps: _PlayerState):
        ps.shots_fired += 1
        ps.projectiles.append({"slot": ps.ship_slot, "y": SHIP_Y - 6.0, "power": 1})
        if ps.weapon_level >= 2 and ps.ship_slot > 0:
            ps.projectiles.append({"slot": ps.ship_slot - 1, "y": SHIP_Y - 6.0, "power": 1})
        if ps.weapon_level >= 3 and ps.ship_slot < CORRIDOR_WIDTH - 1:
            ps.projectiles.append({"slot": ps.ship_slot + 1, "y": SHIP_Y - 6.0, "power": 1})

    def _advance_projectiles(self, ps: _PlayerState):
        survivors = []
        for proj in ps.projectiles:
            proj["y"] -= 15.0
            hit = None
            for enemy in ps.enemies:
                if enemy["slot"] == proj["slot"] and abs(enemy["y"] - proj["y"]) <= 8.0:
                    hit = enemy
                    break
            if hit is not None:
                hit["hp"] -= proj["power"]
                if hit["hp"] <= 0:
                    self._destroy_enemy(ps, hit)
                continue
            if proj["y"] > -10.0:
                survivors.append(proj)
        ps.projectiles = survivors

    def _destroy_enemy(self, ps: _PlayerState, enemy: dict):
        ps.score += enemy["score"]
        ps.destroyed += 1
        ps.streak += 1
        ps.best_streak = max(ps.best_streak, ps.streak)
        ps.explosions.append({"slot": enemy["slot"], "y": enemy["y"], "ticks": 6})
        ps.score_popups.append({
            "slot": enemy["slot"], "y": enemy["y"] - 4.0,
            "text": f"+{enemy['score']}", "ticks": 5,
        })
        if enemy.get("drop"):
            ps.pickups.append({
                "slot": enemy["slot"], "y": enemy["y"],
                "kind": enemy["drop"], "ticks": 40,
            })
        ps.enemies = [e for e in ps.enemies if e is not enemy]

    # ── Enemies ───────────────────────────────────────────────────
    def _advance_enemies(self, ps: _PlayerState):
        survivors = []
        for enemy in ps.enemies:
            enemy["y"] += enemy["speed"]
            if enemy["y"] >= SHIP_Y - 4.0 and enemy["slot"] == ps.ship_slot:
                ps.hull = max(0, ps.hull - 1)
                ps.hits_taken += 1
                ps.streak = 0
                ps.explosions.append({"slot": enemy["slot"], "y": SHIP_Y - 8.0, "ticks": 6})
                ps.message = "Incoming hit. Recover and clear the lane."
                if ps.hull <= 0:
                    ps.overlay_kind = "failure"
                    ps.overlay_title = "Hull Breached"
                    ps.overlay_subtitle = f"Final Score: {ps.score}"
                    ps.overlay_timer = 8
                    ps.finished = True
                continue
            if enemy["y"] <= FIELD_HEIGHT + 8.0:
                survivors.append(enemy)
        ps.enemies = survivors

    # ── Pickups ───────────────────────────────────────────────────
    def _advance_pickups(self, ps: _PlayerState):
        survivors = []
        for pickup in ps.pickups:
            pickup["y"] += 7.0
            pickup["ticks"] = max(0, pickup["ticks"] - 1)
            if pickup["slot"] == ps.ship_slot and abs(pickup["y"] - SHIP_Y) <= 9.0:
                self._collect_pickup(ps, pickup["kind"])
                continue
            if pickup["y"] <= FIELD_HEIGHT + 10.0 and pickup["ticks"] > 0:
                survivors.append(pickup)
        ps.pickups = survivors

    @staticmethod
    def _collect_pickup(ps: _PlayerState, kind: str):
        ps.pickups_collected += 1
        ps.score += 25
        ps.score_popups.append({
            "slot": ps.ship_slot, "y": SHIP_Y - 12.0, "text": "+25", "ticks": 5
        })
        if kind == "weapon":
            ps.weapon_level = min(3, ps.weapon_level + 1)
            ps.message = "Weapon upgrade collected."
        else:
            ps.hull = min(HULL_MAX, ps.hull + 1)
            ps.message = "Hull repair collected."

    # ── Effects decay ─────────────────────────────────────────────
    @staticmethod
    def _decay_effects(ps: _PlayerState):
        ps.explosions = [e for e in ps.explosions if (e.update(ticks=e["ticks"] - 1) or True) and e["ticks"] > 0]
        ps.score_popups = [p for p in ps.score_popups if (p.update(ticks=p["ticks"] - 1) or True) and p["ticks"] > 0]

    # ── View state ────────────────────────────────────────────────
    def _view_state(self, pid: int) -> dict:
        ps = self._players[pid]
        star_ceil = self._star_thresholds[-1] if self._star_thresholds else 1
        return {
            "mode": "space_shooter",
            "corridor_width": CORRIDOR_WIDTH,
            "field_height": FIELD_HEIGHT,
            "ship_slot": ps.ship_slot,
            "ship_y": SHIP_Y,
            "weapon_level": ps.weapon_level,
            "burst_ticks": ps.burst_ticks,
            "hull": ps.hull,
            "score": ps.score,
            "star_progress": min(1.0, ps.score / max(1, star_ceil)),
            "star_thresholds": self._star_thresholds,
            "streak": ps.streak,
            "best_streak": ps.best_streak,
            "shots_fired": ps.shots_fired,
            "destroyed": ps.destroyed,
            "pickups_collected": ps.pickups_collected,
            "wave_index": ps.wave_index,
            "wave_count": len(self._waves),
            "enemies": [dict(e) for e in ps.enemies],
            "projectiles": [dict(p) for p in ps.projectiles],
            "pickups": [dict(p) for p in ps.pickups],
            "explosions": [dict(e) for e in ps.explosions],
            "score_popups": [dict(s) for s in ps.score_popups],
            "overlay_kind": ps.overlay_kind,
            "overlay_title": ps.overlay_title,
            "overlay_subtitle": ps.overlay_subtitle,
            "overlay_timer": ps.overlay_timer,
            "menu_button_rect": [18, 18, 54, 42],
            "music_scene": "space_arcade",
            "music_bias": 0.0,
            "serenity": max(0.0, min(100.0, ps.hull * 22.0 + ps.streak * 3.5)),
            "restlessness": max(0.0, min(100.0, ps.hits_taken * 18.0)),
            "message": ps.message,
        }
