"""Checks for the event step's 2-or-3 mapping. Needs the ml environment (numpy, cv2):
    ml/.venv/bin/python -m unittest worker/test_shot_events.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shot_events  # noqa: E402


class ShotTypeConfidenceTest(unittest.TestCase):
    def test_no_call_means_none(self):
        self.assertIsNone(shot_events.shot_type_confidence({"points": None}))
        self.assertIsNone(shot_events.shot_type_confidence({}))

    def test_near_the_line_is_unsure_and_far_is_sure(self):
        on_line = shot_events.shot_type_confidence({"points": 3, "margin": 0.6, "arc_source": "own frame"})
        deep = shot_events.shot_type_confidence({"points": 3, "margin": 6.0, "arc_source": "own frame"})
        inside = shot_events.shot_type_confidence({"points": 2, "margin": -8.0, "arc_source": "own frame"})
        self.assertLess(on_line, 0.7)
        self.assertEqual(deep, 0.95)
        self.assertEqual(inside, 0.95)

    def test_game_average_arc_is_capped(self):
        self.assertEqual(shot_events.shot_type_confidence({"points": 3, "margin": 6.0, "arc_source": "game average"}), 0.85)

    def test_behind_the_basket(self):
        self.assertEqual(shot_events.shot_type_confidence({"points": 2, "margin": None}), 0.6)


class BoxScoreTest(unittest.TestCase):
    def test_threes_count_as_field_goals_and_score_three(self):
        events = [
            {"team": "valley", "shot_type": "fg3", "made": True},
            {"team": "valley", "shot_type": "fg3", "made": False},
            {"team": "valley", "shot_type": "fg2", "made": True},
            {"team": "valley", "shot_type": "ft", "made": True},
            {"team": "valley", "shot_type": "fg3", "made": True, "status": "deleted"},
        ]
        self.assertEqual(shot_events.box_score(events)["valley"],
                         {"fgm": 2, "fga": 3, "fg3m": 1, "fg3a": 2, "ftm": 1, "fta": 1, "pts": 6})


if __name__ == "__main__":
    unittest.main()
