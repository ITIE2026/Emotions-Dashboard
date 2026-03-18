from __future__ import annotations

import os
import time

import pygame

from maze_game import MindMazeController, draw_mind_maze
from sensor_pipeline import SensorPipeline, SensorSnapshot


SCREEN_W = 1280
SCREEN_H = 800
FPS = 60
MANUAL_MOVE_COOLDOWN = 0.18

BG = (8, 11, 18)
PANEL = (16, 22, 32)
CARD = (20, 28, 42)
TEXT = (241, 245, 249)
MUTED = (148, 163, 184)
ACCENT = (87, 225, 171)
WARN = (251, 191, 36)
DANGER = (248, 113, 113)


def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_text_block(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    x: int,
    y: int,
    max_width: int,
    gap: int = 4,
) -> int:
    lines = _wrap_text(font, text, max_width)
    cursor_y = y
    for line in lines:
        rendered = font.render(line, True, color)
        surface.blit(rendered, (x, cursor_y))
        cursor_y += rendered.get_height() + gap
    return cursor_y


def _draw_metric_bar(
    surface: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    x: int,
    y: int,
    width: int,
    label: str,
    value: float,
    color: tuple[int, int, int],
) -> None:
    label_surface = fonts["small"].render(f"{label}  {value:0.1f}", True, TEXT)
    surface.blit(label_surface, (x, y))
    track = pygame.Rect(x, y + 24, width, 10)
    pygame.draw.rect(surface, (46, 59, 78), track, border_radius=6)
    fill = pygame.Rect(track.x, track.y, int(track.width * max(0.0, min(100.0, value)) / 100.0), track.height)
    pygame.draw.rect(surface, color, fill, border_radius=6)


def _build_balance_panel(
    headline: str,
    status: str,
    timer_text: str,
    countdown_ratio: float,
    balance: float,
    conc_delta: float,
    relax_delta: float,
    muted: bool,
) -> dict:
    return {
        "headline": headline,
        "status": status,
        "timer_text": timer_text,
        "countdown_ratio": countdown_ratio,
        "balance": balance,
        "conc_delta": conc_delta,
        "relax_delta": relax_delta,
        "muted": muted,
    }


def _format_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def _draw_sidebar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fonts: dict[str, pygame.font.Font],
    sensor: SensorSnapshot,
    app_phase: str,
    status_text: str,
    controls_text: str,
    demo_mode: bool,
) -> None:
    pygame.draw.rect(surface, PANEL, rect, border_radius=28)

    title = fonts["subhead"].render("Live State", True, TEXT)
    surface.blit(title, (rect.x + 24, rect.y + 20))

    status_color = DANGER if sensor.fallback_mode else ACCENT if sensor.live_calibration_complete else WARN
    status_chip = pygame.Rect(rect.x + 24, rect.y + 62, rect.width - 48, 34)
    pygame.draw.rect(surface, CARD, status_chip, border_radius=17)
    pygame.draw.rect(surface, status_color, status_chip, width=2, border_radius=17)
    chip_text = fonts["small"].render(sensor.mode.upper(), True, status_color)
    surface.blit(chip_text, (status_chip.x + 14, status_chip.y + 8))

    y = status_chip.bottom + 18
    y = _draw_text_block(surface, fonts["small"], f"Stage: {sensor.calibration_stage or app_phase}", MUTED, rect.x + 24, y, rect.width - 48)
    y += 4
    y = _draw_text_block(surface, fonts["small"], status_text, TEXT, rect.x + 24, y, rect.width - 48)
    y += 12

    if sensor.device_name:
        y = _draw_text_block(surface, fonts["small"], f"Device: {sensor.device_name}", MUTED, rect.x + 24, y, rect.width - 48)
    if sensor.device_serial:
        y = _draw_text_block(surface, fonts["small"], f"Serial: {sensor.device_serial}", MUTED, rect.x + 24, y, rect.width - 48)
    y += 14

    _draw_metric_bar(surface, fonts, rect.x + 24, y, rect.width - 48, "Concentration", sensor.concentration, (34, 197, 94))
    _draw_metric_bar(surface, fonts, rect.x + 24, y + 54, rect.width - 48, "Relaxation", sensor.relaxation, (96, 165, 250))
    _draw_metric_bar(surface, fonts, rect.x + 24, y + 108, rect.width - 48, "Productivity", sensor.productivity, (244, 114, 182))
    y += 166

    progress_box = pygame.Rect(rect.x + 24, y, rect.width - 48, 54)
    pygame.draw.rect(surface, CARD, progress_box, border_radius=18)
    pygame.draw.rect(surface, (66, 153, 225), progress_box, width=1, border_radius=18)
    progress_label = fonts["small"].render(f"Calibration progress  {sensor.progress * 100:0.0f}%", True, TEXT)
    surface.blit(progress_label, (progress_box.x + 12, progress_box.y + 10))
    progress_track = pygame.Rect(progress_box.x + 12, progress_box.y + 32, progress_box.width - 24, 10)
    pygame.draw.rect(surface, (51, 65, 85), progress_track, border_radius=6)
    progress_fill = pygame.Rect(progress_track.x, progress_track.y, int(progress_track.width * sensor.progress), progress_track.height)
    pygame.draw.rect(surface, status_color, progress_fill, border_radius=6)
    y = progress_box.bottom + 18

    artifact_text = "Artifacts detected" if sensor.has_artifacts else "Signal clean"
    artifact_color = DANGER if sensor.has_artifacts else ACCENT
    artifact_surface = fonts["small"].render(artifact_text, True, artifact_color)
    surface.blit(artifact_surface, (rect.x + 24, y))
    freshness_surface = fonts["small"].render("Metrics fresh" if sensor.fresh else "Waiting for fresh metrics", True, TEXT if sensor.fresh else WARN)
    surface.blit(freshness_surface, (rect.x + 24, y + 24))
    y += 60

    controls_title = fonts["small"].render("Controls", True, TEXT)
    surface.blit(controls_title, (rect.x + 24, y))
    y = _draw_text_block(surface, fonts["small"], controls_text, MUTED, rect.x + 24, y + 22, rect.width - 48)
    if demo_mode:
        y += 8
        demo_text = fonts["small"].render("Keyboard demo mode active", True, WARN)
        surface.blit(demo_text, (rect.x + 24, y))


def main() -> int:
    pygame.init()
    pygame.font.init()
    pygame.display.set_caption("EEG Mind Maze")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    fonts = {
        "title": pygame.font.SysFont("arial", 42, bold=True),
        "subhead": pygame.font.SysFont("arial", 28, bold=True),
        "body": pygame.font.SysFont("arial", 20),
        "small": pygame.font.SysFont("arial", 16),
        "timer": pygame.font.SysFont("arial", 24, bold=True),
    }

    pipeline = SensorPipeline()
    pipeline.start()
    controller = MindMazeController()

    app_phase = "pipeline_wait"
    demo_mode = False
    running = True
    level_started_at = 0.0
    manual_move_at = 0.0
    status_text = "Starting sensor pipeline..."
    final_result = None

    try:
        while running:
            sensor = pipeline.snapshot()
            now = time.monotonic()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif app_phase == "finished" and event.key == pygame.K_r:
                        controller.reset_run()
                        final_result = None
                        demo_mode = False
                        app_phase = "pipeline_wait"
                        status_text = "Restarting session..."
                    elif sensor.fallback_mode and app_phase == "pipeline_wait" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        demo_mode = True
                        controller.reset_run()
                        controller.bootstrap_demo_baseline()
                        controller.start_game()
                        level_started_at = now
                        app_phase = "playing"
                        status_text = "Keyboard demo mode active. Use arrow keys to navigate the maze."

            if app_phase == "pipeline_wait":
                status_text = sensor.status
                if sensor.live_calibration_complete and sensor.fresh and not sensor.fallback_mode:
                    controller.reset_run()
                    controller.begin_calibration()
                    app_phase = "game_calibration"
                    status_text = "Live metrics ready. Hold steady to unlock the Mind Maze."

            elif app_phase == "game_calibration":
                valid = sensor.fresh and not sensor.has_artifacts
                calibration = controller.add_calibration_sample(sensor.concentration, sensor.relaxation, valid)
                status_text = calibration.status
                if calibration.complete:
                    controller.start_game()
                    level_started_at = now
                    app_phase = "playing"
                    status_text = "Mind Maze started. Follow the direction hint with a stable signal."

            elif app_phase == "playing":
                elapsed = max(0.0, now - level_started_at)
                if demo_mode:
                    keys = pygame.key.get_pressed()
                    direction = None
                    if now - manual_move_at >= MANUAL_MOVE_COOLDOWN:
                        if keys[pygame.K_UP]:
                            direction = "up"
                        elif keys[pygame.K_RIGHT]:
                            direction = "right"
                        elif keys[pygame.K_DOWN]:
                            direction = "down"
                        elif keys[pygame.K_LEFT]:
                            direction = "left"
                        if direction:
                            snapshot = controller.manual_move(direction, elapsed)
                            manual_move_at = now
                            if snapshot.level_completed and not snapshot.run_completed:
                                level_started_at = now
                            if snapshot.run_completed:
                                final_result = controller.finish_run(None, False)
                                app_phase = "finished"
                                status_text = "Run complete. Press R to restart."
                    if app_phase == "playing":
                        phase_label = controller.movement_policy()[0]
                        status_text = f"Keyboard demo mode. Use arrow keys to move through the {phase_label} corridor."
                else:
                    snapshot = controller.update_gameplay(
                        sensor.concentration,
                        sensor.relaxation,
                        valid=(sensor.fresh and not sensor.has_artifacts),
                        stale=not sensor.fresh,
                        elapsed_seconds=elapsed,
                    )
                    status_text = snapshot.blocked_reason or snapshot.control_hint
                    if snapshot.level_completed and not snapshot.run_completed:
                        level_started_at = now
                    if snapshot.run_completed:
                        final_result = controller.finish_run(None, False)
                        app_phase = "finished"
                        status_text = "Run complete. Press R to restart."

            board_rect = pygame.Rect(24, 110, 820, 660)
            sidebar_rect = pygame.Rect(868, 110, 388, 660)
            screen.fill(BG)
            pygame.draw.rect(screen, (12, 18, 28), pygame.Rect(0, 0, SCREEN_W, 90))

            title_surface = fonts["title"].render("EEG Mind Maze", True, TEXT)
            screen.blit(title_surface, (24, 20))
            subtitle = "Standalone live headband app with automatic device discovery"
            subtitle_surface = fonts["small"].render(subtitle, True, MUTED)
            screen.blit(subtitle_surface, (26, 66))

            balance = sensor.concentration - sensor.relaxation
            panel = _build_balance_panel(
                headline="Mind Maze",
                status=status_text,
                timer_text=_format_seconds(max(0.0, time.monotonic() - level_started_at)) if app_phase == "playing" else "00:00",
                countdown_ratio=sensor.progress if app_phase == "pipeline_wait" else 0.0,
                balance=balance,
                conc_delta=sensor.concentration - (controller.conc_baseline or sensor.concentration),
                relax_delta=sensor.relaxation - (controller.relax_baseline or sensor.relaxation),
                muted=not sensor.fresh and not demo_mode,
            )
            view_state = dict(controller.view_state)
            view_state["balance_panel"] = panel
            draw_mind_maze(screen, board_rect, view_state, fonts)

            controls_text = (
                "ESC to quit. "
                "If no headband is found, press Enter to launch keyboard demo mode. "
                "In demo mode use arrow keys. Press R after finishing to restart."
            )
            _draw_sidebar(screen, sidebar_rect, fonts, sensor, app_phase, status_text, controls_text, demo_mode)

            if final_result is not None:
                result_box = pygame.Rect(270, 290, 500, 180)
                pygame.draw.rect(screen, CARD, result_box, border_radius=24)
                pygame.draw.rect(screen, ACCENT, result_box, width=2, border_radius=24)
                headline = fonts["subhead"].render("Run Complete", True, TEXT)
                screen.blit(headline, headline.get_rect(center=(result_box.centerx, result_box.y + 34)))
                summary = fonts["body"].render(
                    f"Score {final_result.final_score}%   Completion {final_result.completion_pct}%   Total {final_result.total_seconds}s",
                    True,
                    TEXT,
                )
                screen.blit(summary, summary.get_rect(center=(result_box.centerx, result_box.y + 86)))
                prompt = fonts["small"].render("Press R to restart or ESC to close", True, MUTED)
                screen.blit(prompt, prompt.get_rect(center=(result_box.centerx, result_box.y + 132)))

            pygame.display.flip()
            clock.tick(FPS)
    finally:
        pipeline.stop()
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
