import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(ROOT, "bci_dashboard")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from gui.training_audio import compute_adaptive_mix  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
