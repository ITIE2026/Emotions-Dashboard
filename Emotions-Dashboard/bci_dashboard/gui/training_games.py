"""Registry and concrete controllers for EEG training games.

Controller implementations live in sub-modules:
  training_games_base        – BaseTrainingController, constants
  training_games_meditation  – CalmCurrent, FullReboot, NeuroMusicFlow, ProstheticArm
  training_games_arcade      – TugOfWar, SpaceShooter, JumpBall, BubbleBurst, NeonVice, HillClimbRacer
  training_games_memory      – PatternRecall, CandyCascade

This file re-exports every public name for backward compatibility and
keeps the TRAINING_SPECS registry + active_training_specs() helper.
"""
from __future__ import annotations

from gui.eeg_game_base import TrainingGameSpec

from gui.training_games_base import (  # noqa: F401
    BaseTrainingController,
    DIR_LABELS,
    MEMORY_MOVE_BALANCE_THRESHOLD,
    MEMORY_MOVE_DELTA_THRESHOLD,
    MEMORY_CONFIRM_DEAD_ZONE,
    ARCADE_BALANCE_THRESHOLD,
    ARCADE_DELTA_THRESHOLD,
    ARCADE_STEADY_DEAD_ZONE,
    NeuroflowPlaceholderController,
)
from gui.training_games_meditation import (  # noqa: F401
    CalmCurrentController,
    FullRebootController,
    NeuroMusicFlowController,
    ProstheticArmController,
)
from gui.training_games_arcade import (  # noqa: F401
    ArcadeTrainingController,
    TugOfWarController,
    SpaceShooterController,
    JumpBallController,
    BubbleBurstController,
    NeonViceController,
    HillClimbRacerController,
    GravityDriftController,
    SynapseSerpentController,
    AeroZenController,
    ChronoShiftController,
    NeuralDriveController,
)
from gui.training_games_memory import (  # noqa: F401
    MemoryGameController,
    PatternRecallController,
    CandyCascadeController,
)
from gui.mind_maze_controller import MindMazeController  # noqa: F401


TRAINING_SPECS: list[TrainingGameSpec] = [
    TrainingGameSpec(
        game_id="calm_current",
        section="Reduce stress and tension",
        eyebrow="Calm river",
        card_title="Calm Current",
        detail_title="A river game for relaxation",
        duration="8 min",
        description="Ease the current by staying relaxed and let the lantern drift through calmer water.",
        detail_body=(
            "Calm Current trains relaxation control by turning clean, steady calmness into forward momentum. "
            "Spikes in concentration make the river choppy, so the strongest runs come from sustained relaxed control."
        ),
        instructions=(
            "During gameplay, relax to deepen the current and increase flow. Strong concentration spikes increase "
            "turbulence and slow the lantern down."
        ),
        calibration_copy="Relax and settle into a smooth baseline before the river begins to move.",
        preview_label="RIVER",
        colors=("#1d4f53", "#7fd8b3"),
        enabled=True,
        controller_factory=CalmCurrentController,
        widget_kind="calm_current",
        music_profile="calm",
    ),
    TrainingGameSpec(
        game_id="neuro_music_flow",
        section="Reduce stress and tension",
        eyebrow="Adaptive guitar flow",
        card_title="Neuro Music Flow",
        detail_title="A live guitar flow session driven by concentration, relaxation, and EEG bands",
        duration="10 min",
        description="Let warm acoustic guitar layers, pulse field, and ambient ribbons reshape themselves around your live EEG state.",
        detail_body=(
            "Neuro Music Flow is a continuous guitar-reactive training session. Concentration and relaxation shape the "
            "main direction of the mix, while Delta, Theta, Alpha, SMR, and Beta push the guitar layers between warm "
            "fingerstyle calm, bright picked rhythm, and gentle melodic motion."
        ),
        instructions=(
            "Calibrate first, then settle into a comfortable state. Concentration brings out brighter picking and "
            "rhythmic drive, relaxation deepens the warmer acoustic layers, and the live EEG bands reshape the "
            "guitar texture in the background."
        ),
        calibration_copy="Relax into a stable baseline so the guitar layers can respond smoothly once the live session begins.",
        preview_label="MUSIC",
        colors=("#13273f", "#7dc8d7"),
        enabled=True,
        controller_factory=NeuroMusicFlowController,
        widget_kind="neuro_music_flow",
        music_profile="music_flow",
    ),
    TrainingGameSpec(
        game_id="neuroflow",
        section="Improve concentration",
        eyebrow="Focus launcher",
        card_title="Neuroflow Launcher",
        detail_title="A staged focus-to-launch workflow driven by raw EEG and PSD",
        duration="Continuous",
        description="Move through device detection, resistance check, quick calibration, EEG streaming, spectral analysis, and focus-triggered app launch.",
        detail_body=(
            "Neuroflow is not a short mini-game. It is a staged launcher flow that mirrors the original Neuroflow "
            "logic: resistances must pass, quick calibration must complete, the concentration index is computed from "
            "raw PSD band powers, and sustained focus launches the selected desktop app."
        ),
        instructions=(
            "Keep the headset connected, pass the resistance check, run quick calibration, and then sustain the "
            "focus threshold until the dwell bar completes. Neuroflow uses Beta / (Theta + Alpha) with hysteresis "
            "and cooldown, just like the original launcher."
        ),
        calibration_copy="Neuroflow uses the embedded quick-calibration flow and then transitions directly into focus launch mode.",
        preview_label="NEUROFLOW",
        colors=("#18314f", "#40b6ff"),
        enabled=True,
        controller_factory=NeuroflowPlaceholderController,
        widget_kind="neuroflow",
        soundtrack_enabled=False,
        music_profile="concentration",
    ),
    TrainingGameSpec(
        game_id="mind_maze",
        section="Improve concentration",
        eyebrow="Mind Maze",
        card_title="A maze game for concentration",
        detail_title="A maze game for concentration",
        duration="10 min",
        description="Navigate a glowing maze using concentration and relaxation in real time.",
        detail_body=(
            "Mind Maze trains attention switching and steady control. Concentration climbs the maze, relaxation "
            "drops through lower corridors, and once you reach horizontal routes the same signals steer right and left."
        ),
        instructions=(
            "Calibrate first. During play, follow the on-screen hint: concentration climbs or advances right when the "
            "maze calls for focus, and relaxation drops or backtracks when the route needs a calmer state."
        ),
        calibration_copy="Relax and hold the indicator in the ready zone to unlock the maze.",
        preview_label="MAZE",
        colors=("#7b2d1d", "#db9054"),
        enabled=True,
        controller_factory=MindMazeController,
        widget_kind="mind_maze",
        music_profile="concentration",
    ),
    TrainingGameSpec(
        game_id="prosthetic_arm",
        section="Assistive motor control",
        eyebrow="Assistive control",
        card_title="Prosthetic Arm Lab",
        detail_title="A target-sequence prosthetic arm trainer with live control and Arm Lab diagnostics",
        duration="12 min",
        description="Practice open, neutral, and close arm states while the live control panel mirrors the arm in simulation or hardware.",
        detail_body=(
            "Prosthetic Arm Lab adapts the supplied Phaseon arm-control concept into Training Lab. The scored training "
            "routine prompts open, neutral, and close targets in sequence, while Arm Lab shows the same control stream "
            "through live metrics, BrainBit diagnostics, and Arduino output when hardware is connected."
        ),
        instructions=(
            "Focus to close the arm, soften attention to open it, and hover between the thresholds for neutral. "
            "During training, follow the highlighted state, hold it until the sequence advances, and use Arm Lab for "
            "BrainBit diagnostics or Arduino setup when needed."
        ),
        calibration_copy="Relax into a clean baseline before the first grip sequence starts.",
        preview_label="ARM",
        colors=("#2d4737", "#87d2a1"),
        enabled=True,
        controller_factory=ProstheticArmController,
        widget_kind="prosthetic_arm",
        soundtrack_enabled=False,
        music_profile="concentration",
    ),
    TrainingGameSpec(
        game_id="full_reboot",
        section="Relax before sleep",
        eyebrow="Deep wind-down",
        card_title="Full reboot",
        detail_title="A guided sleep wind-down with breathing, body settling, and deep descent",
        duration="25 min",
        description="Ease into sleep through three guided stages that reward steady relaxation and quiet the signal over time.",
        detail_body=(
            "Full reboot is a guided neurofeedback session designed for bedtime. It starts with breath pacing, then "
            "moves into body settling and finally a deeper sleep-descent stage where concentration spikes are gently "
            "discouraged and sustained relaxation makes the scene and music softer."
        ),
        instructions=(
            "Calibrate first, then let the session guide you. Relaxation deepens each stage, balanced steadiness "
            "helps hold transitions, and concentration spikes raise restlessness and slow the wind-down."
        ),
        calibration_copy="Relax your breathing and settle into a clean baseline before the wind-down begins.",
        preview_label="SLEEP",
        colors=("#22304f", "#9caedb"),
        enabled=True,
        controller_factory=FullRebootController,
        widget_kind="full_reboot",
        music_profile="sleep",
    ),
    TrainingGameSpec(
        game_id="tug_of_war",
        section="Arcade neurofeedback",
        eyebrow="Arena duel",
        card_title="Tug of War",
        detail_title="A player-versus-system rope duel driven by concentration",
        duration="6 min",
        description="Pull against the system, hold the Player zone, and survive rising AI pressure across three rounds.",
        detail_body=(
            "Tug of War is now a player-versus-system neurofeedback duel. Concentration helps your side pull the rope "
            "toward the Player zone, while relaxation gives the system extra counter-force and lets the AI steal ground. "
            "Each round raises the pressure, so steady focus and quick recoveries matter more than brief spikes."
        ),
        instructions=(
            "Concentrate to pull harder for your side. If you relax too much, the system gains rope pressure and starts "
            "dragging the knot toward its capture zone. Hold the Player zone long enough to win the round before the AI "
            "locks in its own capture streak."
        ),
        calibration_copy="Build a clean baseline first so the rope physics react smoothly once the arena opens.",
        preview_label="DUEL",
        colors=("#173a74", "#38d7c5"),
        enabled=True,
        controller_factory=TugOfWarController,
        widget_kind="tug_of_war",
        soundtrack_enabled=True,
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="space_shooter",
        section="Arcade neurofeedback",
        eyebrow="Neuro arcade",
        card_title="Space Shooter",
        detail_title="A retro vertical shooter for lateral control, burst timing, and wave clears",
        duration="9 min",
        description="Sweep a star corridor, burst through enemy waves, and grab key pickups before the sector closes.",
        detail_body=(
            "Space Shooter now plays like a portrait arcade rush. Concentration slides the ship right, relaxation "
            "slides it left, and a balanced steady hold triggers a short burst-fire window while the ship keeps "
            "shooting automatically. Clear each descending wave, collect weapon and repair pickups, and protect your hull."
        ),
        instructions=(
            "Concentrate to move right, relax to move left, and hold a balanced steady state to trigger burst fire. "
            "Stay aligned with incoming formations, collect pickups, and clear all three waves in each sector."
        ),
        calibration_copy="Settle into a stable baseline so lateral movement and burst timing stay readable.",
        preview_label="SPACE",
        colors=("#10294e", "#57b8ff"),
        enabled=True,
        controller_factory=SpaceShooterController,
        widget_kind="space_shooter",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="jump_ball",
        section="Arcade neurofeedback",
        eyebrow="BCI Runner",
        card_title="Dino Runner",
        detail_title="A Chrome Dino–style runner controlled by focus, relaxation, and gyroscope",
        duration="8 min",
        description="Run across a desert as a T-Rex, jumping over cacti and dodging pterodactyls using BCI and head tilt.",
        detail_body=(
            "Dino Runner is a side-scrolling obstacle course inspired by the classic offline dinosaur game. "
            "Concentration controls running speed, relaxation slows or reverses the scroll, and tilting your head "
            "up triggers a jump while tilting down makes the dino duck under flying obstacles."
        ),
        instructions=(
            "Focus to run forward, relax to slow down or reverse, tilt your head up to jump over cacti, "
            "and tilt down to duck under pterodactyls. Build combos by clearing obstacles cleanly."
        ),
        calibration_copy="Hold a clean baseline so speed and jump responsiveness stay calibrated during the run.",
        preview_label="DINO",
        colors=("#535353", "#f7f7f7"),
        enabled=True,
        controller_factory=JumpBallController,
        widget_kind="jump_ball",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="bubble_burst",
        section="Arcade neurofeedback",
        eyebrow="Arcade puzzler",
        card_title="Bubble Burst",
        detail_title="A glossy bubble puzzler for shot timing, queue swaps, and full-board clears",
        duration="9 min",
        description="Clear the hanging cluster with a limited shot budget, swap the queue, and keep bubbles out of the launcher zone.",
        detail_body=(
            "Bubble Burst now follows a glossy mobile-style bubble shooter flow. Concentration nudges the launcher "
            "right, relaxation nudges it left, and a balanced steady hold fires the current bubble. Optional queue swapping "
            "helps rescue awkward shots, but the core goal is simple: clear every bubble before you run out of shots or crowd the launcher."
        ),
        instructions=(
            "Concentrate to move the aim right, relax to move it left, and hold a balanced steady state to fire. "
            "Match groups of three or more, use the swap button when needed, and clear the whole board before the shot budget runs out."
        ),
        calibration_copy="Settle into a stable baseline so aim movement and burst timing feel consistent.",
        preview_label="BUBBLE",
        colors=("#214f86", "#7de0ff"),
        enabled=True,
        controller_factory=BubbleBurstController,
        widget_kind="bubble_burst",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="pattern_recall",
        section="Memory and cognitive control",
        eyebrow="Memory loop",
        card_title="Pattern Recall Pro",
        detail_title="A layered pattern game for focus and chunked recall",
        duration="9 min",
        description="Memorize longer patterns, survive distractor previews, and rebuild the sequence chunk by chunk.",
        detail_body=(
            "Pattern Recall Pro deepens the original memory loop with longer sequences, chunk checkpoints, and a "
            "distractor preview on the final stage. It rewards steady EEG control and strong working-memory retention."
        ),
        instructions=(
            "Watch the pattern, then rebuild it. Concentrate to move forward, relax to move backward, and hold a "
            "balanced steady state to confirm the highlighted tile."
        ),
        calibration_copy="Build a neutral baseline first so balanced confirm holds stay reliable during recall.",
        preview_label="PATTERN",
        colors=("#5a3578", "#caa6ff"),
        enabled=True,
        controller_factory=PatternRecallController,
        widget_kind="memory",
        music_profile="memory",
    ),
    TrainingGameSpec(
        game_id="candy_cascade",
        section="Memory and cognitive control",
        eyebrow="Cascade logic",
        card_title="Candy Cascade",
        detail_title="A match-3 board for swap selection, cascades, and blocker clearing",
        duration="10 min",
        description="Cycle through legal swaps, lock in the best move, and clear blockers through cascading matches.",
        detail_body=(
            "Candy Cascade adapts match-3 play to EEG control. Concentration cycles forward through legal swaps, "
            "relaxation cycles backward, and a balanced confirm hold commits the highlighted move and resolves the board."
        ),
        instructions=(
            "Concentrate to cycle forward through legal swaps, relax to cycle backward, and hold a balanced steady "
            "state to confirm the highlighted move. Clear blockers while building enough score to finish the board."
        ),
        calibration_copy="Build a neutral baseline first so swap cycling and confirm holds stay reliable.",
        preview_label="MATCH",
        colors=("#7a2f52", "#ffc978"),
        enabled=True,
        controller_factory=CandyCascadeController,
        widget_kind="candy_cascade",
        music_profile="memory",
    ),
    TrainingGameSpec(
        game_id="neon_vice",
        section="Arcade neurofeedback",
        eyebrow="BCI Shooter",
        card_title="Neon Vice",
        detail_title="Top-down arena shooter with BCI controls",
        duration="9 min",
        description="Take on waves of enemies in a neon-soaked Vice City–style arena. Aim with gyroscope, fire with focus, shield with relaxation.",
        detail_body=(
            "Neon Vice is a top-down arena shooter inspired by Hotline Miami and GTA Vice City. "
            "Use your brain signals to control movement speed and trigger auto-fire while tilting your head to aim. "
            "Clear enemy waves across three increasingly dangerous levels and climb the combo leaderboard."
        ),
        instructions=(
            "Tilt your head left/right to aim. Concentrate to sprint and auto-fire bullets. "
            "Relax to slow down and activate a shield that absorbs one hit. "
            "Clear all waves to complete each level."
        ),
        calibration_copy="Hold your head in a comfortable neutral position while we calibrate the gyroscope and EEG baseline.",
        preview_label="VICE",
        colors=("#ff2d95", "#1a0a2e"),
        enabled=True,
        controller_factory=NeonViceController,
        widget_kind="neon_vice",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="hill_climb_racer",
        section="Arcade neurofeedback",
        eyebrow="Physics Racer",
        card_title="Hill Climb Racer",
        detail_title="Side-scrolling physics racer with BCI controls",
        duration="10 min",
        description="Drive over hilly terrain using focus to accelerate and relaxation to brake. Tilt your head to balance in mid-air and pull off flips for bonus points.",
        detail_body=(
            "Hill Climb Racer is a side-scrolling physics racer inspired by the classic Hill Climb Racing. "
            "Your brain signals control the gas and brake — concentrate to speed up and relax to slow down. "
            "When you launch off hills, tilt your head to balance the car and land safely. "
            "Collect coins and fuel canisters across three terrains: Countryside, Desert Canyon, and Arctic Ridge."
        ),
        instructions=(
            "Focus to accelerate (gas pedal). Relax to brake and slow down. "
            "Tilt your head left/right to balance the car in mid-air. "
            "Collect fuel canisters to keep driving and coins for score. Complete the target distance to clear each level."
        ),
        calibration_copy="Hold your head in a comfortable neutral position while we calibrate the gyroscope and EEG baseline.",
        preview_label="\U0001f3d4\ufe0f",
        colors=("#2d8f4e", "#1a3a2e"),
        enabled=True,
        controller_factory=HillClimbRacerController,
        widget_kind="hill_climb_racer",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="gravity_drift",
        section="Arcade neurofeedback",
        eyebrow="Neon Tunnel",
        card_title="Gravity Drift",
        detail_title="A neon tunnel flyer with gyro steering and brain-powered shields",
        duration="9 min",
        description="Pilot an orb through a neon tunnel. Tilt to steer, focus for speed & shield, relax for bullet-time.",
        detail_body=(
            "Gravity Drift combines gyroscope head-tilt with concentration and relaxation for a hybrid piloting "
            "experience. Focus engages a speed boost and shield, relaxation triggers slow-motion bullet-time to "
            "thread tight gaps, and steady control cruises through the neon corridor."
        ),
        instructions=(
            "Tilt your head to steer the orb. Focus to activate speed boost and shield. "
            "Relax to enter bullet-time for tight gaps. Survive all three tunnels."
        ),
        calibration_copy="Hold your head centred for gyro calibration and settle into a stable EEG baseline.",
        preview_label="DRIFT",
        colors=("#0a0218", "#00ffe6"),
        enabled=True,
        controller_factory=GravityDriftController,
        widget_kind="gravity_drift",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="synapse_serpent",
        section="Arcade neurofeedback",
        eyebrow="Neural Snake",
        card_title="Synapse Serpent",
        detail_title="A brain-controlled snake on a neural circuit board",
        duration="8 min",
        description="Tilt to steer the serpent, focus for points, and relax to phase-shift through your own tail.",
        detail_body=(
            "Synapse Serpent reimagines the classic snake game on a neon circuit-board grid. Gyroscope tilt steers "
            "the serpent, concentration scores bonus points and grows the snake faster, while relaxation activates "
            "a phase-shift that lets you pass through your own tail for a limited time."
        ),
        instructions=(
            "Tilt your head to steer the snake. Eat food to grow. Focus for combo points. "
            "Relax to phase-shift through your tail."
        ),
        calibration_copy="Centre your head and build a stable baseline for clean gyro direction and EEG response.",
        preview_label="SNAKE",
        colors=("#040610", "#00ffc8"),
        enabled=True,
        controller_factory=SynapseSerpentController,
        widget_kind="synapse_serpent",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="aero_zen",
        section="Arcade neurofeedback",
        eyebrow="Ink-wash Flyer",
        card_title="Aero Zen",
        detail_title="A minimalist crane flyer through an ink-wash landscape",
        duration="9 min",
        description="Fly a paper crane through mountains. Relax for thermal lift and clear skies, focus for wind bursts.",
        detail_body=(
            "Aero Zen is a meditative side-scroller drawn in Japanese sumi-e ink-wash style. Gyroscope Y-axis "
            "controls altitude, relaxation generates thermal updrafts and clears storm clouds while colouring the "
            "monochrome world, and focus triggers wind bursts for speed. Collect torii gates for zen score."
        ),
        instructions=(
            "Tilt to change altitude. Relax to ride thermals, clear storms, and paint colour into the world. "
            "Focus for wind bursts. Fly through torii gates for zen points."
        ),
        calibration_copy="Hold a comfortable neutral tilt while we calibrate altitude control and EEG baseline.",
        preview_label="ZEN",
        colors=("#f0ebe1", "#3c3732"),
        enabled=True,
        controller_factory=AeroZenController,
        widget_kind="aero_zen",
        music_profile="calm",
    ),
    TrainingGameSpec(
        game_id="neural_drive",
        section="Arcade neurofeedback",
        eyebrow="EEG Road Runner",
        card_title="Neural Drive",
        detail_title="An EEG-powered perspective road game where your mind steers the car",
        duration="8 min",
        description="Concentrate to steer right, relax to go left. Drive through brick-wall gates without crashing.",
        detail_body=(
            "Neural Drive puts you behind the wheel of a perspective road runner controlled entirely by your "
            "brainwaves — no gyroscope needed. Concentration shifts the car right, relaxation steers it left. "
            "Brick-wall gates scroll toward you from the horizon; thread through each gap cleanly for points. "
            "Three escalating circuits push gap width narrower and gate speed higher each level."
        ),
        instructions=(
            "Concentrate to steer right. Relax to drift left. Guide the car through each gate gap. "
            "Hit a wall and you stun for 2 seconds. Clear all target gates on each circuit to advance."
        ),
        calibration_copy="Relax and hold a neutral mental state so we can capture your EEG baseline before driving.",
        preview_label="DRIVE",
        colors=("#0a1020", "#0066ff"),
        enabled=True,
        controller_factory=NeuralDriveController,
        widget_kind="neural_drive",
        music_profile="arcade",
    ),
    TrainingGameSpec(
        game_id="chrono_shift",
        section="Arcade neurofeedback",
        eyebrow="Time Runner",
        card_title="Chrono Shift",
        detail_title="A time-manipulation runner with chrono-gated obstacles",
        duration="9 min",
        description="Control the flow of time with your brain. Focus for fast-forward, relax for slow-motion, and steer through chrono gates.",
        detail_body=(
            "Chrono Shift is a forward-scrolling runner where your mental state warps the flow of time. "
            "Concentration triggers fast-forward mode with a 2\u00d7 score multiplier but faster, harder obstacles. "
            "Relaxation activates slow-motion for Matrix-style precision through tight gaps. Chrono Gates \u2014 "
            "colour-coded obstacles \u2014 only open in the matching time mode, forcing rapid brain-state switching."
        ),
        instructions=(
            "Tilt your head to steer the chrono-orb. Focus to enter fast-forward (red gates open, 2\u00d7 score). "
            "Relax to enter slow-motion (blue gates open, precision bonus). White gates are always open. "
            "Survive all three temporal zones."
        ),
        calibration_copy="Hold your head centred for gyro calibration and settle into a stable EEG baseline.",
        preview_label="CHRONO",
        colors=("#0a0420", "#ff9020"),
        enabled=True,
        controller_factory=ChronoShiftController,
        widget_kind="chrono_shift",
        music_profile="arcade",
    ),
]


def active_training_specs() -> list[TrainingGameSpec]:
    return [spec for spec in TRAINING_SPECS if spec.enabled]


# ── Game IDs that belong to the dedicated GAMES section ──────────────
GAME_SECTION_IDS: set[str] = {
    "tug_of_war",
    "space_shooter",
    "jump_ball",
    "bubble_burst",
    "neon_vice",
    "hill_climb_racer",
    "pattern_recall",
    "candy_cascade",
    "mind_maze",
    "gravity_drift",
    "synapse_serpent",
    "aero_zen",
    "chrono_shift",
    "neural_drive",
}


def active_game_specs() -> list[TrainingGameSpec]:
    """Return enabled specs that belong to the GAMES section."""
    return [spec for spec in TRAINING_SPECS if spec.enabled and spec.game_id in GAME_SECTION_IDS]


def active_training_only_specs() -> list[TrainingGameSpec]:
    """Return enabled specs that stay in the Training Lab (non-game exercises)."""
    return [spec for spec in TRAINING_SPECS if spec.enabled and spec.game_id not in GAME_SECTION_IDS]
