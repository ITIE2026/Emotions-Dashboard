import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui.training_audio import AdaptiveMusicEngine, STEM_NAMES, TRAINING_AUDIO_ASSET_DIR, compute_adaptive_mix  # noqa: E402


class TrainingAudioTests(unittest.TestCase):
    def test_sleep_profile_emphasizes_sleep_and_relax_layers(self):
        mix = compute_adaptive_mix(
            "sleep",
            conc_delta=-0.4,
            relax_delta=1.6,
            view_state={"music_scene": "sleep_descent", "serenity": 84.0, "restlessness": 8.0},
        )
        self.assertGreater(mix["sleep"], mix["focus"])
        self.assertGreater(mix["relax"], mix["concentration"])

    def test_concentration_profile_emphasizes_focus_layers(self):
        mix = compute_adaptive_mix(
            "concentration",
            conc_delta=1.8,
            relax_delta=0.2,
            view_state={"music_scene": "maze_focus", "serenity": 52.0, "restlessness": 18.0},
        )
        self.assertGreater(mix["concentration"], mix["sleep"])
        self.assertGreater(mix["focus"], mix["relax"])

    def test_arcade_profile_keeps_sleep_layer_low(self):
        mix = compute_adaptive_mix(
            "arcade",
            conc_delta=1.5,
            relax_delta=0.4,
            view_state={"music_scene": "space_run", "serenity": 60.0, "restlessness": 22.0},
        )
        self.assertLessEqual(mix["sleep"], 0.05)
        self.assertGreater(mix["concentration"], mix["sleep"])

    def test_music_flow_profile_uses_band_powers_to_shift_mix(self):
        focus_mix = compute_adaptive_mix(
            "music_flow",
            conc_delta=1.1,
            relax_delta=0.2,
            view_state={"music_scene": "music_flow", "serenity": 52.0, "restlessness": 30.0},
            band_powers={"delta": 0.02, "theta": 0.04, "alpha": 0.10, "smr": 0.22, "beta": 0.62},
        )
        calm_mix = compute_adaptive_mix(
            "music_flow",
            conc_delta=0.2,
            relax_delta=1.1,
            view_state={"music_scene": "music_flow", "serenity": 78.0, "restlessness": 12.0},
            band_powers={"delta": 0.32, "theta": 0.42, "alpha": 0.18, "smr": 0.03, "beta": 0.05},
        )
        self.assertGreater(focus_mix["concentration"], calm_mix["concentration"])
        self.assertGreater(focus_mix["focus"], calm_mix["focus"])
        self.assertGreater(calm_mix["sleep"], focus_mix["sleep"])
        self.assertGreater(calm_mix["relax"], focus_mix["relax"])

    def test_music_flow_profile_falls_back_cleanly_without_band_powers(self):
        mix_without_bands = compute_adaptive_mix(
            "music_flow",
            conc_delta=0.6,
            relax_delta=0.7,
            view_state={"music_scene": "music_flow", "serenity": 61.0, "restlessness": 18.0},
        )
        mix_with_empty_bands = compute_adaptive_mix(
            "music_flow",
            conc_delta=0.6,
            relax_delta=0.7,
            view_state={"music_scene": "music_flow", "serenity": 61.0, "restlessness": 18.0},
            band_powers={},
        )
        self.assertEqual(mix_without_bands, mix_with_empty_bands)

    def test_packaged_soundtrack_assets_resolve_from_repo(self):
        engine = AdaptiveMusicEngine(
            None,
            TRAINING_AUDIO_ASSET_DIR,
            {"Aurora Drift": {"bundle": "aurora_drift"}},
        )
        resolved = engine.resolve_soundtrack_paths("Aurora Drift")
        self.assertEqual(set(resolved.keys()), set(STEM_NAMES))
        for stem, path in resolved.items():
            self.assertTrue(path.endswith(f"{stem}.wav"))
            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.normpath(path).startswith(os.path.normpath(TRAINING_AUDIO_ASSET_DIR)))

    def test_packaged_guitar_assets_resolve_from_repo(self):
        engine = AdaptiveMusicEngine(
            None,
            TRAINING_AUDIO_ASSET_DIR,
            {"Monsoon Strings": {"bundle": "monsoon_strings"}},
        )
        resolved = engine.resolve_soundtrack_paths("Monsoon Strings")
        self.assertEqual(set(resolved.keys()), set(STEM_NAMES))
        for stem, path in resolved.items():
            self.assertTrue(path.endswith(f"{stem}.wav"))
            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.normpath(path).startswith(os.path.normpath(TRAINING_AUDIO_ASSET_DIR)))

    def test_missing_packaged_assets_use_fallback_generation(self):
        with tempfile.TemporaryDirectory() as asset_dir, tempfile.TemporaryDirectory() as fallback_dir:
            engine = AdaptiveMusicEngine(
                None,
                asset_dir,
                {"Missing Score": {"bundle": "missing_score"}},
                fallback_dir=fallback_dir,
            )
            resolved = engine.resolve_soundtrack_paths("Missing Score")
            self.assertEqual(set(resolved.keys()), set(STEM_NAMES))
            for path in resolved.values():
                self.assertTrue(os.path.exists(path))
                self.assertTrue(os.path.normpath(path).startswith(os.path.normpath(fallback_dir)))


if __name__ == "__main__":
    unittest.main()
