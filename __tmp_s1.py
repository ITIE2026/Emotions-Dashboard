import re
path = r'c:\Users\asus\Documents\dashboard\Emotions-Dashboard\bci_dashboard\gui\training_games.py'
f = open(path, 'r', encoding='utf-8'); content = f.read(); f.close()
original = content
content = re.sub(r'\n\n\nclass NeuroRacerController\(ArcadeTrainingController\):.*?(?=\n\n\nclass NeonDriftArenaController)', '', content, flags=re.DOTALL)
content = re.sub(r'\n\n\nclass NeonDriftArenaController\(ArcadeTrainingController\):.*?(?=\n\n\nclass BubbleBurstController)', '', content, flags=re.DOTALL)
content = re.sub(r'\n# ---------------------------------------------------------------------------\n#  Astral Glider \u2014 gyroscope-steered space navigation\n# ---------------------------------------------------------------------------\n.*?(?=\n# ---------------------------------------------------------------------------\n# Neon Vice)', '', content, flags=re.DOTALL)
content = re.sub(r'\n    TrainingGameSpec\(\s*\n\s*game_id=\x22neuro_racer\x22,.*?\),', '', content, flags=re.DOTALL)
content = re.sub(r'\n    TrainingGameSpec\(\s*\n\s*game_id=\x22neon_drift_arena\x22,.*?\),', '', content, flags=re.DOTALL)
content = re.sub(r'\n    TrainingGameSpec\(\s*\n\s*game_id=\x22astral_glider\x22,.*?\),', '', content, flags=re.DOTALL)
if content == original:
    print('WARNING: No changes were made!')
else:
    removed = len(original) - len(content)
    print(f'Removed {removed} characters from training_games.py')
    open(path, 'w', encoding='utf-8').write(content)
    print('training_games.py saved successfully')
checks = ['class NeuroRacerController','class NeonDriftArenaController','class AstralGliderController','game_id=\x22neuro_racer\x22','game_id=\x22neon_drift_arena\x22','game_id=\x22astral_glider\x22']
[ print(f'STILL PRESENT: {c}') if c in content else print(f'REMOVED OK: {c}') for c in checks ]
