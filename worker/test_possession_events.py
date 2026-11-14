"""Checks for the event step's team rebounds and turnovers (worker/possession_events.py) on a
small made-up game, no film or real data. Needs the ml environment (numpy, cv2, yaml):
    ml/.venv/bin/python -m unittest worker.test_possession_events -v
"""

import math
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml" / "tools"))
import possession_events as PE  # noqa: E402
import shot_events  # noqa: E402


def fake_game(change_at=30.0, length=60.0):
    """Six players moving about. Track 1 (color group 0) dribbles until change_at, then track 2
    (group 1) has the ball: one change of possession with no shot, so a turnover."""
    frames = []
    for k in range(int(length * 10)):
        t = k / 10
        # Each player moves on his own (in step, it would look like a camera pan, not play).
        wob = [60 * math.sin(t * 2.0 + i * 1.3) for i in range(6)]
        players = [[1, 300 + 200 * i + wob[i], 300, 380 + 200 * i + wob[i], 500, 0.9, i + 1] for i in range(6)]
        holder = players[0] if t < change_at else players[1]
        ball = [0, holder[1] + 30, 420, holder[1] + 50, 440, 0.8, -1]
        frames.append([t, [*players, ball, [3, 1700, 200, 1740, 215, 0.9, -1]]])
    return {"fps": 10, "frame_size": [1920, 1080], "frames": frames,
            "tracks": {str(i + 1): {"group": i % 2} for i in range(6)},
            "group_centers_lab": [[200, 128, 128], [60, 140, 110]]}


INFO = {"halftime": 100.0, "valley_basket_first_half": "left"}


class FallbackTest(unittest.TestCase):
    def test_unreadable_film_falls_back_with_lower_confidence(self):
        got = PE.build_possession(fake_game(), [], INFO, (0, 59.9), None, {0: "Valley", 1: "Opponent"},
                                  "/no/such/film.mp4", log=lambda m: None)
        self.assertFalse(got["info"]["film_read"])
        self.assertIn("can't read", got["info"]["film_error"])
        tos = [e for e in got["events"] if e["type"] == "to"]
        self.assertEqual([(e["team"], round(e["t"])) for e in tos], [("valley", 30)])
        self.assertLess(tos[0]["confidence"], 0.6)    # 0.6 with the film read
        self.assertFalse(tos[0]["hidden"])
        self.assertEqual((tos[0]["shot_type"], tos[0]["made"]), ("none", False))

    def test_coach_colors_name_the_teams(self):
        got = PE.build_possession(fake_game(), [], INFO, (0, 59.9), None, {0: "Opponent", 1: "Valley"},
                                  None, log=lambda m: None)
        self.assertEqual([e["team"] for e in got["events"] if e["type"] == "to"], ["opponent"])


class SiteEventsTest(unittest.TestCase):
    def test_rebound_uncertainty_reason_survives_site_conversion(self):
        raw = [{"type": "oreb", "team": "Valley", "t": 11.0, "shot_t": 10.0,
                "how": "inferred_control", "evidence": "corroborated_track_team"}]
        event = PE.site_events(raw, film_read=True)[0]
        self.assertEqual(event["detail"]["evidence"], "corroborated_track_team")
        self.assertLess(event["confidence"], 0.5)
        self.assertIsNone(event["player_number"])

    def test_shape_hidden_and_confidence(self):
        raw = [{"type": "oreb", "team": "Valley", "t": 10.123, "shot_t": 9.0, "how": "again"},
               {"type": "dreb", "team": "Opponent", "t": 20, "shot_t": 18.0, "how": "default", "track": 4},
               {"type": "stl", "team": "Opponent", "t": 30},
               {"type": "ast", "team": "Valley", "t": 40, "passer_track": 2, "shooter_track": 3}]
        out = PE.site_events(raw, film_read=True)
        self.assertEqual([(e["type"], e["team"], e["hidden"]) for e in out],
                         [("oreb", "valley", False), ("dreb", "opponent", False),
                          ("stl", "opponent", True), ("ast", "valley", True)])
        self.assertEqual((out[0]["t"], out[0]["confidence"], out[1]["confidence"]), (10.12, 0.8, 0.5))
        self.assertEqual(out[1]["detail"]["track"], 4)
        self.assertEqual(PE.site_events(raw[:1], film_read=False)[0]["confidence"], 0.56)


class BoxScoreTest(unittest.TestCase):
    def test_missing_play_data_is_not_zero(self):
        box = shot_events.box_score([], plays_known=False)
        for line in box.values():
            self.assertEqual(line["pts"], 0)
            self.assertTrue(all(line[key] is None for key in ("oreb", "dreb", "reb", "to")))
        self.assertEqual(shot_events.box_score([])["valley"]["to"], 0)

    def test_build_events_reports_failed_and_skipped_plays_as_missing(self):
        info = {**INFO, "votes": {"left": 10, "right": 0}, "warmup_dropped": 0, "dead_ball_dropped": 0}
        with mock.patch.object(shot_events.game_window, "find_window", return_value={"found": True, "start": 0, "end": 60}), \
             mock.patch.object(shot_events.shot_rules, "find_shots", return_value=[]), \
             mock.patch.object(shot_events, "group_names", return_value=({0: "Valley", 1: "Opponent"}, False)), \
             mock.patch.object(shot_events.shot_split, "split", return_value=([], info)), \
             mock.patch.object(PE, "build_possession", side_effect=RuntimeError("possession failed")) as build:
            failed = shot_events.build_events({})
            self.assertEqual(failed["possession"], {"error": "possession failed"})
            self.assertIsNone(failed["box_score"]["valley"]["to"])
            skipped = shot_events.build_events({}, possession=False)
            self.assertIsNone(skipped["possession"])
            self.assertIsNone(skipped["box_score"]["valley"]["reb"])
            build.return_value = {"events": [], "info": {"method": "v2"}}
            build.side_effect = None
            empty = shot_events.build_events({})
            self.assertEqual(empty["box_score"]["valley"]["to"], 0)

    def test_plays_count_and_hidden_ones_do_not(self):
        events = [
            {"type": "shot", "team": "valley", "shot_type": "fg2", "made": True},
            {"type": "oreb", "team": "valley", "shot_type": "none", "made": False},
            {"type": "dreb", "team": "valley", "shot_type": "none", "made": False},
            {"type": "dreb", "team": "valley", "shot_type": "none", "made": False, "status": "deleted"},
            {"type": "to", "team": "valley", "shot_type": "none", "made": False},
            {"type": "stl", "team": "valley", "shot_type": "none", "made": False, "hidden": True},
        ]
        line = shot_events.box_score(events)["valley"]
        self.assertEqual((line["fga"], line["pts"], line["oreb"], line["dreb"], line["reb"], line["to"]),
                         (1, 2, 1, 1, 2, 1))


if __name__ == "__main__":
    unittest.main()
