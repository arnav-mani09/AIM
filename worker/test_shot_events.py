"""Checks for the event step's 2-or-3 mapping. Needs the ml environment (numpy, cv2):
    ml/.venv/bin/python -m unittest worker/test_shot_events.py -v
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml" / "tools"))
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
    def test_independent_category_coverage(self):
        events = [{"type": "oreb", "team": "valley"}, {"type": "to", "team": "opponent"}]
        for category, unknown in (("rebounds", "to"), ("turnovers", "reb")):
            with self.subTest(category=category):
                coverage = {"rebounds": "unavailable", "turnovers": "unavailable", category: "partial"}
                score = shot_events.box_score(events, coverage)
                self.assertIsNone(score["valley"][unknown])
                self.assertIsNone(score["opponent"][unknown])

    def test_threes_count_as_field_goals_and_score_three(self):
        events = [
            {"team": "valley", "shot_type": "fg3", "made": True},
            {"team": "valley", "shot_type": "fg3", "made": False},
            {"team": "valley", "shot_type": "fg2", "made": True},
            {"team": "valley", "shot_type": "ft", "made": True},
            {"team": "valley", "shot_type": "fg3", "made": True, "status": "deleted"},
        ]
        self.assertEqual(shot_events.box_score(events)["valley"],
                         {"fgm": 2, "fga": 3, "fg3m": 1, "fg3a": 2, "ftm": 1, "fta": 1, "pts": 6,
                          "oreb": 0, "dreb": 0, "reb": 0, "to": 0})


class ExtractionCoverageTest(unittest.TestCase):
    def build(self, enabled=True, error=None, info=None):
        possession = SimpleNamespace(build_possession=lambda *args: {"events": [], "info": info or {}})
        if error:
            def fail(*args):
                raise RuntimeError(error)
            possession.build_possession = fail
        split_info = {"votes": {"a": 1, "b": 0}, "valley_basket_first_half": "left",
                      "warmup_dropped": 0, "dead_ball_dropped": 0}
        with patch.object(shot_events.game_window, "find_window", return_value={"found": False}), \
                patch.object(shot_events.shot_rules, "find_shots", return_value=[]), \
                patch.object(shot_events.shot_split, "split", return_value=([], split_info)), \
                patch.dict(sys.modules, {"possession_events": possession}):
            return shot_events.build_events({"frames": [[10]]}, possession=enabled)

    def test_success_empty_is_complete_even_without_info_fields(self):
        result = self.build()
        self.assertEqual(result["play_coverage"], {"rebounds": "complete", "turnovers": "complete"})
        self.assertEqual(result["box_score"]["valley"]["reb"], 0)
        self.assertEqual(result["box_score"]["opponent"]["to"], 0)

    def test_skipped_and_failed_are_unavailable(self):
        for result in (self.build(enabled=False), self.build(error="broken"), self.build(info={"error": "bad"})):
            self.assertEqual(result["play_coverage"], {"rebounds": "unavailable", "turnovers": "unavailable"})
            self.assertIsNone(result["box_score"]["valley"]["reb"])
            self.assertIsNone(result["box_score"]["opponent"]["to"])

    def test_tracker_fallback_is_successful_extraction(self):
        result = self.build(info={"method": "v2", "film_read": False, "film_error": "no film"})
        self.assertEqual(result["play_coverage"]["rebounds"], "complete")


class CourtSpotTest(unittest.TestCase):
    """Court spots from the unsquashed arc. A circle arc (a == b) at the rim's floor point makes
    the picture and the court line up, so directions can be read off directly."""

    def setUp(self):
        import three_point
        self.tp = three_point
        r = 100.0
        self.arc = ((three_point.BX, three_point.BY, r, r, 0.0), 1.0)
        self.r = r

    def spot(self, side, dx, dy, dist=None):
        return self.tp.court_spot(self.arc, side, self.tp.BX + dx, self.tp.BY + dy, dist)

    def test_straight_out_is_the_top_of_the_key(self):
        x, y = self.spot("left", self.r * 1.2, 0)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, round(19.75 * 1.2, 1))
        x, y = self.spot("right", -self.r * 1.2, 0, 24.0)
        self.assertEqual((x, y), (0.0, 24.0))

    def test_sides_follow_the_basket(self):
        # Near the camera (lower in the picture) is your left at the left basket, your right at the right one.
        self.assertLess(self.spot("left", 10, 50)[0], 0)
        self.assertGreater(self.spot("right", -10, 50)[0], 0)

    def test_behind_the_rim_is_kept_on_the_court(self):
        x, y = self.spot("left", -30, 80, 20.0)
        self.assertGreaterEqual(y, 0)
        self.assertAlmostEqual((x * x + y * y) ** 0.5, 20.0, places=0)

    def test_distance_is_capped(self):
        x, y = self.spot("left", 500, 0, 80.0)
        self.assertEqual(y, 45.0)

    def test_zones_agree_with_the_call(self):
        zone = self.tp.zone_of
        self.assertEqual(zone(0, 2, 2), "restricted_area")
        self.assertEqual(zone(3, 9, 2), "paint")
        self.assertEqual(zone(-12, 10, 2), "mid_range_left")
        self.assertEqual(zone(-21, 2, 3), "corner_three_left")
        self.assertEqual(zone(16, 14, 3), "wing_three_right")
        self.assertEqual(zone(2, 22, 3), "top_of_key_three")
        # A 2 at 21 ft (feet on the line) is still a 2-point zone.
        self.assertEqual(zone(15, 15, 2), "mid_range_right")


if __name__ == "__main__":
    unittest.main()
