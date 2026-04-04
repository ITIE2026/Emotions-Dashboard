from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Tuple

try:
    import pygame
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Pygame is required. Install it with: pip install pygame"
    ) from exc


WIDTH = 1440
HEIGHT = 900
FPS = 60
GRAVITY = 1200.0
WORLD_WIDTH = 2600
GROUND_Y = HEIGHT - 80


@dataclass
class EEGMetrics:
    focus: float = 40.0
    relaxation: float = 40.0
    signal_quality: float = 1.0
    connected: bool = False
    mode: str = "demo"


class DemoEEGBridge:
    """Small bridge that simulates live EEG values.

    Replace read_metrics() later with real values from your dashboard/headband.
    """

    def __init__(self) -> None:
        self.metrics = EEGMetrics(connected=False, mode="demo")
        self.t = 0.0
        self.target_focus = 46.0
        self.target_relax = 42.0

    def update_from_keyboard(self, dt: float, keys) -> None:
        # Manual test controls for EEG simulation.
        if keys[pygame.K_i]:
            self.target_focus = min(100.0, self.target_focus + 28.0 * dt)
        if keys[pygame.K_k]:
            self.target_focus = max(0.0, self.target_focus - 28.0 * dt)
        if keys[pygame.K_o]:
            self.target_relax = min(100.0, self.target_relax + 28.0 * dt)
        if keys[pygame.K_l]:
            self.target_relax = max(0.0, self.target_relax - 28.0 * dt)

        if keys[pygame.K_p]:
            self.metrics.connected = True
        if keys[pygame.K_SEMICOLON]:
            self.metrics.connected = False

    def read_metrics(self, dt: float) -> EEGMetrics:
        self.t += dt
        focus_noise = math.sin(self.t * 1.9) * 1.8 + random.uniform(-0.7, 0.7)
        relax_noise = math.cos(self.t * 1.5) * 1.5 + random.uniform(-0.7, 0.7)

        self.metrics.focus += (self.target_focus - self.metrics.focus) * min(1.0, dt * 4.2)
        self.metrics.relaxation += (self.target_relax - self.metrics.relaxation) * min(1.0, dt * 4.2)
        self.metrics.focus = max(0.0, min(100.0, self.metrics.focus + focus_noise))
        self.metrics.relaxation = max(0.0, min(100.0, self.metrics.relaxation + relax_noise))
        return self.metrics


@dataclass
class BrainIntent:
    horizontal: float = 0.0
    jetpack: bool = False
    fire: bool = False
    shield: bool = False
    steady: bool = False
    label: str = "neutral"


class EEGInterpreter:
    """Turns focus and relaxation into EEG-friendly gameplay controls.

    Mapping for this inspired game:
    - Focus dominant => push right/aggressive movement
    - Relax dominant => push left/defensive movement
    - Steady balance with enough combined intensity => hover / controlled jetpack
    - Strong focus spike => fire burst
    - Strong relaxation spike => temporary shield / faster recovery
    """

    def __init__(self) -> None:
        self.focus_baseline = 35.0
        self.relax_baseline = 35.0
        self.focus_history: List[float] = []
        self.relax_history: List[float] = []
        self.focus_pulse_cooldown = 0.0
        self.shield_cooldown = 0.0

    def update(self, metrics: EEGMetrics, dt: float) -> BrainIntent:
        self.focus_history.append(metrics.focus)
        self.relax_history.append(metrics.relaxation)
        if len(self.focus_history) > 45:
            self.focus_history.pop(0)
            self.relax_history.pop(0)

        if len(self.focus_history) >= 20:
            self.focus_baseline = sum(self.focus_history[-20:]) / 20.0
            self.relax_baseline = sum(self.relax_history[-20:]) / 20.0

        focus_delta = metrics.focus - self.focus_baseline
        relax_delta = metrics.relaxation - self.relax_baseline
        balance = focus_delta - relax_delta
        intensity = max(0.0, (abs(focus_delta) + abs(relax_delta)) / 40.0)
        steady = abs(balance) < 5.0 and metrics.focus > 42.0 and metrics.relaxation > 42.0

        intent = BrainIntent()
        intent.steady = steady
        intent.horizontal = max(-1.0, min(1.0, balance / 18.0))
        intent.jetpack = steady and intensity > 0.22
        intent.fire = False
        intent.shield = False

        if self.focus_pulse_cooldown > 0.0:
            self.focus_pulse_cooldown -= dt
        if self.shield_cooldown > 0.0:
            self.shield_cooldown -= dt

        if focus_delta > 9.0 and self.focus_pulse_cooldown <= 0.0:
            intent.fire = True
            self.focus_pulse_cooldown = 0.38

        if relax_delta > 10.0 and self.shield_cooldown <= 0.0:
            intent.shield = True
            self.shield_cooldown = 1.5

        if intent.fire:
            intent.label = "focus pulse"
        elif intent.shield:
            intent.label = "relax shield"
        elif intent.jetpack:
            intent.label = "steady hover"
        elif intent.horizontal > 0.25:
            intent.label = "push right"
        elif intent.horizontal < -0.25:
            intent.label = "push left"
        else:
            intent.label = "neutral"

        return intent


@dataclass
class Weapon:
    name: str
    bullet_speed: float
    damage: float
    cooldown: float
    spread_deg: float
    bullets_per_shot: int
    color: Tuple[int, int, int]


RIFLE = Weapon("Rifle", 900.0, 14.0, 0.18, 3.0, 1, (255, 220, 120))
SHOTGUN = Weapon("Shotgun", 820.0, 8.0, 0.55, 18.0, 5, (255, 170, 120))
SNIPER = Weapon("Sniper", 1350.0, 34.0, 0.85, 1.0, 1, (170, 255, 255))


@dataclass
class Platform:
    rect: pygame.Rect


@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    owner_id: int
    color: Tuple[int, int, int]
    life: float = 1.8

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0 and -100 <= self.x <= WORLD_WIDTH + 100 and -100 <= self.y <= HEIGHT + 100


@dataclass
class Pickup:
    x: float
    y: float
    kind: str
    active: bool = True
    bob: float = 0.0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 18), int(self.y - 18), 36, 36)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    radius: int
    color: Tuple[int, int, int]

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 180.0 * dt
        return self.ttl > 0


@dataclass
class Soldier:
    entity_id: int
    name: str
    x: float
    y: float
    color: Tuple[int, int, int]
    is_player: bool = False
    health: float = 100.0
    energy: float = 100.0
    vx: float = 0.0
    vy: float = 0.0
    facing: int = 1
    on_ground: bool = False
    shield_timer: float = 0.0
    weapon: Weapon = field(default_factory=lambda: RIFLE)
    fire_timer: float = 0.0
    respawn_timer: float = 0.0
    score: int = 0
    deaths: int = 0
    streak: int = 0
    target_x: float = 0.0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 16), int(self.y - 34), 32, 68)

    def alive(self) -> bool:
        return self.respawn_timer <= 0.0

    def apply_damage(self, dmg: float) -> bool:
        if self.shield_timer > 0.0:
            dmg *= 0.45
        self.health -= dmg
        return self.health <= 0.0

    def respawn(self, spawn: Tuple[float, float]) -> None:
        self.x, self.y = spawn
        self.health = 100.0
        self.energy = 100.0
        self.vx = 0.0
        self.vy = 0.0
        self.shield_timer = 0.0
        self.respawn_timer = 0.0
        self.on_ground = False
        self.weapon = RIFLE


class BotBrain:
    def __init__(self) -> None:
        self.decision_timer = 0.0
        self.move_dir = 0.0
        self.jetpack = False
        self.fire = False
        self.shield = False

    def think(self, bot: Soldier, enemies: List[Soldier], dt: float) -> BrainIntent:
        self.decision_timer -= dt
        live_enemies = [e for e in enemies if e.alive()]
        if not live_enemies:
            return BrainIntent()
        nearest = min(live_enemies, key=lambda e: abs(e.x - bot.x) + abs(e.y - bot.y))

        if self.decision_timer <= 0.0:
            dx = nearest.x - bot.x
            dy = nearest.y - bot.y
            self.move_dir = 1.0 if dx > 30 else -1.0 if dx < -30 else 0.0
            self.jetpack = dy < -90 and bot.energy > 20
            self.fire = abs(dx) < 520 and random.random() < 0.85
            self.shield = bot.health < 35 and random.random() < 0.35
            self.decision_timer = random.uniform(0.18, 0.42)

        return BrainIntent(
            horizontal=self.move_dir,
            jetpack=self.jetpack,
            fire=self.fire,
            shield=self.shield,
            label="bot",
        )


class MiniMilitiaInspiredEEGGame:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Mini Militia Inspired EEG Arena")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 22)
        self.small = pygame.font.SysFont("arial", 18)
        self.big = pygame.font.SysFont("arial", 38, bold=True)
        self.huge = pygame.font.SysFont("arial", 58, bold=True)

        self.eeg = DemoEEGBridge()
        self.interpreter = EEGInterpreter()
        self.use_eeg_controls = True
        self.camera_x = 0.0
        self.running = True
        self.match_time = 180.0
        self.last_player_intent = BrainIntent(label="boot")
        self.remaining = self.match_time
        self.winner_text = ""

        self.background_stars = [
            (random.randint(0, WORLD_WIDTH), random.randint(0, HEIGHT - 150), random.randint(1, 3))
            for _ in range(120)
        ]

        self.platforms = self._create_platforms()
        self.spawn_points = [(180, 240), (720, 220), (1260, 260), (1810, 200), (2320, 240)]
        self.pickups = [
            Pickup(660, 315, "shotgun"),
            Pickup(1310, 200, "sniper"),
            Pickup(2080, 160, "heal"),
            Pickup(930, 495, "heal"),
        ]

        self.player = Soldier(1, "You", 180, 240, (110, 220, 255), is_player=True)
        self.bots = [
            Soldier(2, "Bot Alpha", 750, 230, (255, 130, 130)),
            Soldier(3, "Bot Beta", 1320, 260, (255, 210, 110)),
            Soldier(4, "Bot Gamma", 1820, 210, (160, 255, 160)),
        ]
        self.bot_brains = {bot.entity_id: BotBrain() for bot in self.bots}

        self.bullets: List[Bullet] = []
        self.particles: List[Particle] = []

    def _create_platforms(self) -> List[Platform]:
        raw = [
            (0, GROUND_Y, WORLD_WIDTH, HEIGHT - GROUND_Y),
            (120, 520, 270, 22),
            (470, 360, 220, 20),
            (690, 540, 260, 20),
            (980, 410, 210, 20),
            (1220, 260, 230, 22),
            (1520, 560, 240, 22),
            (1760, 390, 230, 20),
            (2050, 230, 260, 20),
            (2280, 500, 210, 20),
        ]
        return [Platform(pygame.Rect(*p)) for p in raw]

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events(dt)
            self.update(dt)
            self.draw()
        pygame.quit()

    def handle_events(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        self.eeg.update_from_keyboard(dt, keys)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_TAB:
                    self.use_eeg_controls = not self.use_eeg_controls
                elif event.key == pygame.K_r:
                    self.__init__()
                    return

    def update(self, dt: float) -> None:
        if self.winner_text:
            return

        self.remaining = max(0.0, self.remaining - dt)
        metrics = self.eeg.read_metrics(dt)

        player_intent = self._player_intent(metrics, dt)
        self.last_player_intent = player_intent
        self._update_soldier(self.player, player_intent, dt)

        for bot in self.bots:
            if bot.respawn_timer > 0.0:
                bot.respawn_timer -= dt
                if bot.respawn_timer <= 0.0:
                    bot.respawn(random.choice(self.spawn_points))
                continue
            intent = self.bot_brains[bot.entity_id].think(bot, [self.player] + [b for b in self.bots if b.entity_id != bot.entity_id], dt)
            self._update_soldier(bot, intent, dt)

        self._update_bullets(dt)
        self._update_pickups(dt)
        self._update_particles(dt)
        self._update_camera(dt)

        if self.remaining <= 0.0:
            all_players = [self.player] + self.bots
            champion = max(all_players, key=lambda s: (s.score, -s.deaths))
            self.winner_text = f"Winner: {champion.name}"

    def _player_intent(self, metrics: EEGMetrics, dt: float) -> BrainIntent:
        keys = pygame.key.get_pressed()
        if not self.use_eeg_controls:
            horizontal = 0.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                horizontal -= 1.0
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                horizontal += 1.0
            return BrainIntent(
                horizontal=horizontal,
                jetpack=keys[pygame.K_w] or keys[pygame.K_UP] or keys[pygame.K_SPACE],
                fire=keys[pygame.K_f],
                shield=keys[pygame.K_e],
                label="keyboard",
            )
        return self.interpreter.update(metrics, dt)

    def _update_soldier(self, soldier: Soldier, intent: BrainIntent, dt: float) -> None:
        if soldier.respawn_timer > 0.0:
            return

        move_accel = 1100.0 if soldier.is_player else 980.0
        max_speed = 260.0 if soldier.is_player else 240.0
        air_control = 0.72 if not soldier.on_ground else 1.0

        soldier.fire_timer = max(0.0, soldier.fire_timer - dt)
        soldier.shield_timer = max(0.0, soldier.shield_timer - dt)

        soldier.vx += intent.horizontal * move_accel * air_control * dt
        soldier.vx *= 0.88 if soldier.on_ground else 0.96
        soldier.vx = max(-max_speed, min(max_speed, soldier.vx))

        if abs(intent.horizontal) > 0.15:
            soldier.facing = 1 if intent.horizontal > 0 else -1

        if intent.jetpack and soldier.energy > 2.5:
            soldier.vy -= 980.0 * dt
            soldier.energy = max(0.0, soldier.energy - 30.0 * dt)
            self._spawn_thruster(soldier)
        else:
            soldier.energy = min(100.0, soldier.energy + 22.0 * dt)

        if intent.shield and soldier.shield_timer <= 0.0:
            soldier.shield_timer = 1.0

        soldier.vy += GRAVITY * dt
        soldier.x += soldier.vx * dt
        soldier.y += soldier.vy * dt
        soldier.x = max(30.0, min(WORLD_WIDTH - 30.0, soldier.x))

        soldier.on_ground = False
        rect = soldier.rect()
        for platform in self.platforms:
            if rect.colliderect(platform.rect):
                prev_bottom = rect.bottom - int(soldier.vy * dt)
                if soldier.vy >= 0 and prev_bottom <= platform.rect.top + 12:
                    soldier.y = platform.rect.top - 34
                    soldier.vy = 0.0
                    soldier.on_ground = True
                    rect = soldier.rect()

        if soldier.y > HEIGHT + 160:
            self._kill(soldier, None)
            return

        if intent.fire and soldier.fire_timer <= 0.0:
            self._fire_weapon(soldier)
            soldier.fire_timer = soldier.weapon.cooldown

    def _fire_weapon(self, soldier: Soldier) -> None:
        enemies = [self.player] + self.bots
        targets = [e for e in enemies if e.entity_id != soldier.entity_id and e.alive()]
        if targets:
            target = min(targets, key=lambda e: abs(e.x - soldier.x) + abs(e.y - soldier.y))
            base_angle = math.atan2(target.y - soldier.y, target.x - soldier.x)
        else:
            base_angle = 0.0 if soldier.facing >= 0 else math.pi

        for _ in range(soldier.weapon.bullets_per_shot):
            spread = math.radians(random.uniform(-soldier.weapon.spread_deg, soldier.weapon.spread_deg))
            ang = base_angle + spread
            self.bullets.append(
                Bullet(
                    x=soldier.x + soldier.facing * 18,
                    y=soldier.y - 18,
                    vx=math.cos(ang) * soldier.weapon.bullet_speed,
                    vy=math.sin(ang) * soldier.weapon.bullet_speed,
                    damage=soldier.weapon.damage,
                    owner_id=soldier.entity_id,
                    color=soldier.weapon.color,
                )
            )
        for _ in range(7):
            self.particles.append(
                Particle(
                    x=soldier.x + soldier.facing * 18,
                    y=soldier.y - 18,
                    vx=random.uniform(-90, 90) + soldier.facing * 110,
                    vy=random.uniform(-80, 80),
                    ttl=random.uniform(0.1, 0.22),
                    radius=random.randint(2, 4),
                    color=soldier.weapon.color,
                )
            )

    def _spawn_thruster(self, soldier: Soldier) -> None:
        if random.random() < 0.45:
            self.particles.append(
                Particle(
                    x=soldier.x - soldier.facing * 10,
                    y=soldier.y + 10,
                    vx=random.uniform(-60, 60),
                    vy=random.uniform(140, 210),
                    ttl=random.uniform(0.15, 0.25),
                    radius=random.randint(2, 5),
                    color=(255, random.randint(150, 220), 80),
                )
            )

    def _update_bullets(self, dt: float) -> None:
        next_bullets: List[Bullet] = []
        soldiers = [self.player] + self.bots
        for bullet in self.bullets:
            if not bullet.update(dt):
                continue
            hit = False
            point = pygame.Rect(int(bullet.x - 2), int(bullet.y - 2), 4, 4)
            for platform in self.platforms[:-1]:
                if point.colliderect(platform.rect):
                    hit = True
                    break
            if hit:
                continue
            for soldier in soldiers:
                if soldier.entity_id == bullet.owner_id or not soldier.alive():
                    continue
                if soldier.rect().colliderect(point):
                    died = soldier.apply_damage(bullet.damage)
                    self._impact_particles(bullet.x, bullet.y, bullet.color)
                    if died:
                        killer = next((s for s in soldiers if s.entity_id == bullet.owner_id), None)
                        self._kill(soldier, killer)
                    hit = True
                    break
            if not hit:
                next_bullets.append(bullet)
        self.bullets = next_bullets

    def _kill(self, victim: Soldier, killer: Soldier | None) -> None:
        victim.respawn_timer = 2.4
        victim.deaths += 1
        victim.streak = 0
        for _ in range(18):
            self.particles.append(
                Particle(
                    x=victim.x,
                    y=victim.y - 16,
                    vx=random.uniform(-160, 160),
                    vy=random.uniform(-220, 60),
                    ttl=random.uniform(0.25, 0.7),
                    radius=random.randint(3, 6),
                    color=victim.color,
                )
            )
        if killer is not None and killer.entity_id != victim.entity_id:
            killer.score += 1
            killer.streak += 1
            killer.health = min(100.0, killer.health + 14.0)
            killer.energy = min(100.0, killer.energy + 24.0)
        victim.x = -200
        victim.y = -200
        victim.vx = 0.0
        victim.vy = 0.0

    def _impact_particles(self, x: float, y: float, color: Tuple[int, int, int]) -> None:
        for _ in range(8):
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=random.uniform(-120, 120),
                    vy=random.uniform(-120, 120),
                    ttl=random.uniform(0.12, 0.24),
                    radius=random.randint(2, 4),
                    color=color,
                )
            )

    def _update_pickups(self, dt: float) -> None:
        everyone = [self.player] + self.bots
        for pickup in self.pickups:
            if not pickup.active:
                continue
            pickup.bob += dt * 3.0
            rect = pickup.rect()
            for soldier in everyone:
                if soldier.alive() and soldier.rect().colliderect(rect):
                    if pickup.kind == "shotgun":
                        soldier.weapon = SHOTGUN
                    elif pickup.kind == "sniper":
                        soldier.weapon = SNIPER
                    elif pickup.kind == "heal":
                        soldier.health = min(100.0, soldier.health + 40.0)
                        soldier.energy = min(100.0, soldier.energy + 35.0)
                    pickup.active = False
                    break

    def _update_particles(self, dt: float) -> None:
        self.particles = [p for p in self.particles if p.update(dt)]

    def _update_camera(self, dt: float) -> None:
        target = self.player.x - WIDTH * 0.35
        target = max(0.0, min(WORLD_WIDTH - WIDTH, target))
        self.camera_x += (target - self.camera_x) * min(1.0, dt * 4.0)

    def draw(self) -> None:
        self._draw_background()
        self._draw_world()
        self._draw_hud()
        if self.winner_text:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 145))
            self.screen.blit(overlay, (0, 0))
            self._text(self.huge, self.winner_text, (WIDTH // 2, HEIGHT // 2 - 30), center=True)
            self._text(self.big, "Press R to restart or ESC to quit", (WIDTH // 2, HEIGHT // 2 + 34), center=True)
        pygame.display.flip()

    def _draw_background(self) -> None:
        for y in range(HEIGHT):
            c = int(25 + (y / HEIGHT) * 45)
            pygame.draw.line(self.screen, (18, 26, c), (0, y), (WIDTH, y))
        for sx, sy, size in self.background_stars:
            x = (sx - self.camera_x * 0.25) % WIDTH
            pygame.draw.circle(self.screen, (220, 230, 255), (int(x), sy), size)
        pygame.draw.circle(self.screen, (230, 240, 255), (1120, 150), 42)
        pygame.draw.circle(self.screen, (120, 150, 190), (1120, 150), 42, 2)

    def _draw_world(self) -> None:
        cam = self.camera_x
        for platform in self.platforms:
            rect = pygame.Rect(platform.rect.x - cam, platform.rect.y, platform.rect.w, platform.rect.h)
            color = (58, 66, 92) if platform.rect.y < GROUND_Y else (46, 52, 72)
            pygame.draw.rect(self.screen, color, rect, border_radius=12)
            pygame.draw.rect(self.screen, (98, 106, 138), rect, 2, border_radius=12)

        for pickup in self.pickups:
            if not pickup.active:
                continue
            y = pickup.y + math.sin(pickup.bob) * 6.0
            rect = pygame.Rect(int(pickup.x - cam - 18), int(y - 18), 36, 36)
            color = (255, 160, 120) if pickup.kind == "shotgun" else (160, 240, 255) if pickup.kind == "sniper" else (120, 255, 150)
            pygame.draw.rect(self.screen, color, rect, border_radius=10)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=10)
            label = "SG" if pickup.kind == "shotgun" else "SR" if pickup.kind == "sniper" else "+"
            self._text(self.small, label, rect.center, center=True)

        for bullet in self.bullets:
            pygame.draw.circle(self.screen, bullet.color, (int(bullet.x - cam), int(bullet.y)), 4)

        for particle in self.particles:
            alpha = max(60, min(255, int(255 * particle.ttl * 1.8)))
            surf = pygame.Surface((particle.radius * 2 + 2, particle.radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*particle.color, alpha), (particle.radius + 1, particle.radius + 1), particle.radius)
            self.screen.blit(surf, (particle.x - cam - particle.radius - 1, particle.y - particle.radius - 1))

        for soldier in [self.player] + self.bots:
            self._draw_soldier(soldier)

    def _draw_soldier(self, soldier: Soldier) -> None:
        if not soldier.alive():
            timer = max(0.0, soldier.respawn_timer)
            respawn = random.choice(self.spawn_points)
            if soldier.entity_id == self.player.entity_id:
                x = respawn[0] - self.camera_x
                y = respawn[1]
                self._text(self.small, f"Respawn in {timer:.1f}s", (x, y - 70), center=True)
            return

        cam = self.camera_x
        rx, ry = soldier.x - cam, soldier.y
        body = pygame.Rect(int(rx - 14), int(ry - 34), 28, 52)
        head_center = (int(rx), int(ry - 46))
        if soldier.shield_timer > 0.0:
            pygame.draw.circle(self.screen, (120, 220, 255), (int(rx), int(ry - 16)), 33, 2)
        pygame.draw.rect(self.screen, soldier.color, body, border_radius=10)
        pygame.draw.rect(self.screen, (20, 24, 40), body, 2, border_radius=10)
        pygame.draw.circle(self.screen, (238, 229, 214), head_center, 12)

        gun_end = (int(rx + soldier.facing * 24), int(ry - 18))
        pygame.draw.line(self.screen, (60, 60, 70), (int(rx), int(ry - 18)), gun_end, 5)
        pygame.draw.line(self.screen, (20, 24, 40), (int(rx), int(ry - 18)), gun_end, 1)

        self._bar(rx - 22, ry - 68, 44, 6, soldier.health / 100.0, (115, 255, 135), (65, 45, 45))
        self._bar(rx - 22, ry - 58, 44, 6, soldier.energy / 100.0, (120, 210, 255), (45, 55, 75))
        self._text(self.small, soldier.name, (rx, ry - 90), center=True)

    def _draw_hud(self) -> None:
        panel = pygame.Rect(20, 18, 420, 205)
        pygame.draw.rect(self.screen, (15, 20, 30), panel, border_radius=18)
        pygame.draw.rect(self.screen, (95, 110, 145), panel, 2, border_radius=18)

        metrics = self.eeg.metrics
        intent = self.last_player_intent if self.use_eeg_controls else BrainIntent(label="keyboard")
        mode = "EEG" if self.use_eeg_controls else "Keyboard"
        self._text(self.big, "EEG Arena Shooter", (38, 26))
        self._text(self.small, f"Control mode: {mode}   TAB switch", (38, 74))
        self._text(self.small, "I/K focus  O/L relax  P connect  ; disconnect", (38, 98))
        self._text(self.small, f"Brain intent: {intent.label}", (38, 122))

        self._text(self.small, f"Focus: {metrics.focus:5.1f}", (38, 150))
        self._bar(125, 154, 170, 10, metrics.focus / 100.0, (255, 205, 110), (46, 52, 70))
        self._text(self.small, f"Relax: {metrics.relaxation:5.1f}", (38, 176))
        self._bar(125, 180, 170, 10, metrics.relaxation / 100.0, (120, 230, 255), (46, 52, 70))
        self._text(self.small, f"Signal: {'OK' if metrics.connected else 'Demo'}", (312, 150))
        self._text(self.small, f"Weapon: {self.player.weapon.name}", (312, 176))

        scoreboard = pygame.Rect(WIDTH - 360, 18, 330, 180)
        pygame.draw.rect(self.screen, (15, 20, 30), scoreboard, border_radius=18)
        pygame.draw.rect(self.screen, (95, 110, 145), scoreboard, 2, border_radius=18)
        self._text(self.big, f"Time {int(self.remaining):03d}s", (WIDTH - 340, 28))
        y = 82
        ordered = sorted([self.player] + self.bots, key=lambda s: (s.score, -s.deaths), reverse=True)
        for soldier in ordered:
            self._text(self.small, f"{soldier.name:10}  K:{soldier.score:2d}  D:{soldier.deaths:2d}  Streak:{soldier.streak}", (WIDTH - 340, y))
            y += 28

        footer = pygame.Rect(20, HEIGHT - 64, WIDTH - 40, 44)
        pygame.draw.rect(self.screen, (12, 18, 26), footer, border_radius=14)
        pygame.draw.rect(self.screen, (72, 82, 112), footer, 2, border_radius=14)
        msg = (
            "Mini Militia-inspired: jetpack arena, pickups, bots, auto-aim, shield, EEG-adapted controls. "
            "Use this as a separate game module, then wire real focus/relaxation from your dashboard."
        )
        self._text(self.small, msg, (36, HEIGHT - 54))

    def _text(self, font, text: str, pos, center: bool = False) -> None:
        surf = font.render(text, True, (235, 240, 250))
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        self.screen.blit(surf, rect)

    def _bar(self, x: float, y: float, w: int, h: int, value: float, fg, bg) -> None:
        pygame.draw.rect(self.screen, bg, (x, y, w, h), border_radius=8)
        fill = max(0, min(w, int(w * max(0.0, min(1.0, value)))))
        if fill > 0:
            pygame.draw.rect(self.screen, fg, (x, y, fill, h), border_radius=8)
        pygame.draw.rect(self.screen, (255, 255, 255), (x, y, w, h), 1, border_radius=8)


if __name__ == "__main__":
    MiniMilitiaInspiredEEGGame().run()
