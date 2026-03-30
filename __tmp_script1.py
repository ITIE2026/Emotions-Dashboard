import re

path = r"c:\Users\asus\Documents\dashboard\Emotions-Dashboard\bci_dashboard\gui\training_games.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# 1. Remove NeuroRacerController class (everything from the blank lines before class to just before NeonDriftArenaController)
content = re.sub(
    r'\n\n\nclass NeuroRacerController\(ArcadeTrainingController\):.*?(?=\n\n\nclass NeonDriftArenaController)',
    '',
    content,
    flags=re.DOTALL
)

# 2. Remove NeonDriftArenaController class (up to just before BubbleBurstController)
content = re.sub(
    r'\n\n\nclass NeonDriftArenaController\(ArcadeTrainingController\):.*?(?=\n\n\nclass BubbleBurstController)',
    '',
    content,
    flags=re.DOTALL
)

# 3. Remove Astral Glider constants + AstralGliderController class (section comment to just before _NV_ constants section comment)
content = re.sub(
    r'\n# ---------------------------------------------------------------------------\n#  Astral Glider \xe2\x80\x94 gyroscope-steered space navigation\n# ---------------------------------------------------------------------------\n.*?(?=\n# ---------------------------------------------------------------------------\n# Neon Vice)',
    '',
    content,
    flags=re.DOTALL
)

# 4. Remove neuro_racer TRAINING_SPECS entry
content = re.sub(
    r'\n    TrainingGameSpec\(\s*\n\s*game_id="neuro_racer",.*?\),',
    '',
    content,
    flags=re.DOTALL
)

# 5. Remove neon_drift_arena TRAINING_SPECS entry
content = re.sub(
    r'\n    TrainingGameSpec\(\s*\n\s*game_id="neon_drift_arena",.*?\),',
    '',
    content,
    flags=re.DOTALL
)

# 6. Remove astral_glider TRAINING_SPECS entry
content = re.sub(
    r'\n    TrainingGameSpec\(\s*\n\s*game_id="astral_glider",.*?\),',
    '',
    content,
    flags=re.DOTALL
)

if content == original:
    print("WARNING: No changes were made!")
else:
    removed = len(original) - len(content)
    print(f"Removed {removed} characters from training_games.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("training_games.py saved successfully")

checks = ["class NeuroRacerController", "class NeonDriftArenaController", "class AstralGliderController",
          'game_id="neuro_racer"', 'game_id="neon_drift_arena"', 'game_id="astral_glider"']
for check in checks:
    if check in content:
        print(f"STILL PRESENT: {check}")
    else:
        print(f"REMOVED OK: {check}")
