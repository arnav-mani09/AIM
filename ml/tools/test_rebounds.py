import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import possession as P
import rebound_eval as E


def shot(time=10.0, team="Valley", made=False, kind="FG"):
    return {"t": time, "team": team, "made": made, "kind": kind, "basket": "left"}


def hold(time=11.0, duration=0.7, team="Opponent", **kwargs):
    return {"t0": time, "t1": time + duration - 0.1, "tid": 7, "team": team,
            "sure": True, "contested": 0.0, **kwargs}


class ReboundTest(unittest.TestCase):
    def decisions(self, runs=(), shots=None, window=(0, 30), half_break=None):
        doc = {"fps": 10, "frames": []}
        return P.rebound_decisions_v2(doc, {"shots": shots or [shot()]}, window, half_break, runs)

    def event(self, runs=(), **kwargs):
        return self.decisions(runs, **kwargs)[0]["event"]

    def test_sustained_control_names_observed_track(self):
        event = self.event([hold()])
        self.assertEqual((event["type"], event["how"], event["track"]), ("dreb", "control", 7))

    def test_short_touch_is_not_control_or_player_credit(self):
        event = self.event([hold(duration=0.3)])
        self.assertEqual(event["how"], "touch")
        self.assertNotIn("track", event)
        self.assertLess(event["confidence"], 0.5)

    def test_contested_overlap_not_observed_control(self):
        event = self.event([hold(contested=0.8)])
        self.assertEqual(event["how"], "touch")
        self.assertNotIn("track", event)

    def test_tip_before_control_does_not_credit_later_teammate(self):
        event = self.event([hold(duration=0.3), hold(time=12)])
        self.assertEqual(event["team"], "Opponent")
        self.assertNotIn("track", event)

    def test_opposing_touch_lowers_confidence_of_later_control(self):
        event = self.event([hold(duration=0.3, team="Valley"), hold(time=12)])
        self.assertEqual(event["how"], "inferred_control")
        self.assertNotIn("track", event)

    def test_unknown_early_control_not_replaced_by_later_colored_holder(self):
        event = self.event([hold(team=None, sure=False), hold(time=16, team="Valley")])
        self.assertEqual((event["how"], event["evidence"]), ("unresolved", "control_team_unknown"))
        self.assertNotIn("track", event)

    def test_current_strong_color_beats_switched_track(self):
        event = self.event([hold(team="Opponent", vote=0.8)])
        self.assertEqual((event["team"], event["how"]), ("Valley", "control"))

    def test_weak_color_is_not_sure_from_track_vote(self):
        event = self.event([hold(vote=-0.3)])
        self.assertEqual(event["how"], "inferred_control")

    def test_conflicting_weak_color_and_track_are_unknown(self):
        event = self.event([hold(team="Valley", vote=-0.3)])
        self.assertEqual(event["evidence"], "control_team_unknown")
        self.assertNotIn("track", event)

    def test_later_strong_color_corroborates_uncertain_control_team(self):
        event = self.event([hold(team="Valley", vote=-0.3),
                            hold(time=13, team="Valley", vote=0.8)])
        self.assertEqual((event["type"], event["team"]), ("oreb", "Valley"))
        self.assertEqual((event["how"], event["evidence"]),
                         ("inferred_control", "corroborated_track_team"))
        self.assertEqual(event["t"], 11.0)
        self.assertNotIn("track", event)
        self.assertLess(event["confidence"], 0.5)

    def test_corroboration_requires_independent_local_color(self):
        event = self.event([hold(team="Valley", vote=-0.3), hold(time=13, team="Valley")])
        self.assertEqual(event["evidence"], "control_team_unknown")

    def test_corroboration_does_not_cross_opposing_contact(self):
        event = self.event([hold(team="Valley", vote=-0.3),
                            hold(time=12, team="Opponent", vote=-0.8),
                            hold(time=13, team="Valley", vote=0.8)])
        self.assertEqual(event["evidence"], "control_team_unknown")

    def test_corroboration_does_not_cross_referee_contact(self):
        event = self.event([hold(team="Valley", vote=-0.3),
                            hold(time=12, team=None, ref=True),
                            hold(time=13, team="Valley", vote=0.8)])
        self.assertEqual(event["evidence"], "control_team_unknown")

    def test_contested_later_color_does_not_corroborate_control(self):
        event = self.event([hold(team="Valley", vote=-0.3),
                            hold(time=13, team="Valley", vote=0.8, contested=0.8)])
        self.assertEqual(event["evidence"], "control_team_unknown")

    def test_no_control_preserves_inferred_rebound(self):
        event = self.event()
        self.assertEqual((event["type"], event["how"]), ("dreb", "unresolved"))
        self.assertNotIn("track", event)

    def test_next_shot_bounds_holder_search(self):
        event = self.event([hold(time=14)], shots=[shot(), shot(13, team="Opponent", made=True)])
        self.assertEqual(event["how"], "unresolved")

    def test_halftime_bounds_search(self):
        event = self.event([hold(time=15)], half_break=(12, 14))
        self.assertEqual(event["how"], "unresolved")

    def test_referee_blocks_repeat_shot_inference(self):
        result = self.decisions([hold(ref=True, team=None)], shots=[shot(), shot(14, made=True)])
        self.assertIsNone(result[0]["event"])
        self.assertEqual(result[0]["reason"], "dead_ball_before_control")

    def test_raw_referee_detection_blocks_rebound(self):
        with patch.object(P, "rebound_ref_handled", return_value=True):
            self.assertIsNone(self.event([hold()]))

    def test_player_overlapping_baseline_referee_is_not_dead_ball(self):
        boxes = [[0, 40, 40, 50, 50, 0.9], [2, 0, 0, 100, 100, 0.9],
                 [1, 20, 10, 80, 100, 0.9, 7]]
        doc = {"fps": 10, "frames": [(index / 10, boxes) for index in range(10)]}
        self.assertFalse(P.rebound_ref_handled(doc, 0, 0.9))
        doc["frames"] = [(time, boxes[:2]) for time, boxes in doc["frames"]]
        self.assertTrue(P.rebound_ref_handled(doc, 0, 0.9))

    def test_repeat_shot_is_inferred_not_observed(self):
        event = self.event(shots=[shot(), shot(14, made=True)])
        self.assertEqual(event["how"], "repeat_shot")
        self.assertLess(event["event_conf"], 0.75)

    def test_free_throw_is_not_repeat_field_goal(self):
        event = self.event(shots=[shot(), shot(14, made=True, kind="FT")])
        self.assertEqual(event["how"], "unresolved")

    def test_nonlive_misses_do_not_get_rebounds(self):
        self.assertEqual(self.decisions(shots=[shot(made=True)]), [])
        self.assertEqual(self.decisions(shots=[shot(kind="fouled")]), [])

    def test_dead_ball_after_touch_is_unknown_not_observed_player(self):
        event = self.event([hold(duration=0.3), hold(time=12, ref=True, team=None)])
        self.assertEqual(event["evidence"], "dead_ball_after_possible_touch")
        self.assertNotIn("track", event)

    def test_downstream_adapter_preserves_evidence_confidence(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))
        from possession_events import site_events
        for event in (self.event(), self.event([hold(duration=0.3)]), self.event([hold(vote=-0.3)])):
            self.assertEqual(site_events([event], True)[0]["confidence"], event["event_conf"])
            self.assertLess(site_events([event], False)[0]["confidence"], event["event_conf"])

    def test_eval_unknown_not_scored_and_bounded(self):
        fixture = {"game": "synthetic", "events": [], "split": {"shots": [shot()]},
                   "window": (0, 30), "half_break": None, "runs": []}
        original = copy.deepcopy(fixture)
        report = E.compare({"fps": 10, "frames": []}, fixture, limit=1)
        self.assertEqual(report["scores"]["labeled"], 0)
        self.assertEqual(report["scores"]["unknown"], 1)
        self.assertEqual(len(report["review_shot_times"]), 1)
        self.assertEqual(fixture, original)


if __name__ == "__main__":
    unittest.main()
