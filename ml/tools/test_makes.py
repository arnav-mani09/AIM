"""Synthetic make-rule and scoreboard-evaluation regressions; no film or labels required."""

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import makes_eval
import shots


RIM = [100, 100, 120, 110]


def ball(center_x, center_y, score=0.9):
    return [0, center_x - 2, center_y - 2, center_x + 2, center_y + 2, score]


def attempt(points, **extra):
    result = {"t": 0.0, "rim": RIM[:], "ball_score": 0.9, "rim_score": 0.9,
              "path": [(time, 110 + 20 * horizontal, 100 + 10 * vertical, *RIM)
                       for time, horizontal, vertical in points]}
    result.update(extra)
    return result


def prediction(time, made=True, team="Valley", kind="FG", **extra):
    return {"t": time, "made": made, "team": team, "kind": kind, **extra}


def change(time, delta=2, team="Valley", old=None):
    return {"seen_new": time, "seen_old": time - 0.25 if old is None else old,
            "delta": delta, "team": team}


class MakeRuleTest(unittest.TestCase):
    def test_clean_drop_is_a_make(self):
        result = shots.decide(attempt([(0.0, 0.0, -1.0), (0.2, 0.0, 0.8), (0.4, 0.0, 2.0)]))
        self.assertTrue(result["made"])
        self.assertEqual(result["make_t"], 0.4)

    def test_rim_out_and_upward_bounce_are_misses(self):
        paths = [[(0.0, 0.0, -1.0), (0.2, 0.0, 0.8), (0.4, 0.5, 2.0)],
                 [(0.0, 0.0, -1.0), (0.4, 0.0, 2.0), (0.6, 0.0, -0.2)]]
        for path in paths:
            with self.subTest(path=path):
                self.assertFalse(shots.decide(attempt(path))["made"])

    def test_net_disappearance_needs_observation_after_last_detection(self):
        path = [(0.0, 0.0, -1.0), (0.2, 0.0, 0.8)]
        self.assertFalse(shots.decide(attempt(path))["made"])
        self.assertFalse(shots.decide(attempt(path), observed_until=0.6)["made"])
        self.assertTrue(shots.decide(attempt(path), observed_until=0.8)["made"])

    def test_net_disappearance_cannot_override_sideways_excursion(self):
        path = [(0.0, 0.0, -1.0), (0.1, 0.9, 0.4), (0.2, 0.0, 0.8)]
        self.assertFalse(shots.decide(attempt(path), observed_until=1.0)["made"])

    def test_net_disappearance_cannot_override_later_bounce(self):
        path = [(0.0, 0.0, -1.0), (0.2, 0.0, 0.8), (0.8, 0.0, -0.5)]
        self.assertFalse(shots.decide(attempt(path), observed_until=1.5)["made"])

    def test_empty_path_is_a_miss(self):
        self.assertFalse(shots.decide(attempt([]))["made"])

    def test_quick_putback_is_separate_from_initial_miss(self):
        points = [(0, -0.5), (0.2, 0.1), (0.8, 2.0), (1.0, 4.0),
                  (0.5, 2.0), (0.2, 0.8), (0.0, 0.1), (0.0, -1.0),
                  (0.0, -0.5), (0.0, 0.8), (0.0, 2.0)]
        frames = [(index / 10, [[3, *RIM, 0.9], ball(110 + 20 * horizontal, 100 + 10 * vertical)])
                  for index, (horizontal, vertical) in enumerate(points)]
        frames.extend((index / 10, [[3, *RIM, 0.9]]) for index in range(len(points), 25))
        found = shots.find_shots({"fps": 10, "frame_size": [1000, 500], "frames": frames})
        self.assertEqual(len(found), 2)
        self.assertEqual([shot["made"] for shot in found], [False, True])
        self.assertAlmostEqual(found[1]["t"], 0.6)

    def test_return_above_rim_needs_new_flight_at_same_basket(self):
        original = attempt([(0.0, 0.0, -1.0), (0.1, 0.0, 0.8)])
        current = (0.2, 110, 99, *RIM)
        self.assertFalse(shots.returning_above_rim(original, current))
        returning = attempt([(0.0, 0.0, -1.0), (0.1, 0.8, 3.0), (0.2, 0.0, 0.8)])
        self.assertTrue(shots.returning_above_rim(returning, (0.3, 110, 99, *RIM)))
        self.assertFalse(shots.returning_above_rim(returning, (1.0, 110, 99, *RIM)))
        self.assertFalse(shots.returning_above_rim(returning, (0.3, 510, 99, 500, 100, 520, 110)))

    def test_made_basket_followed_by_upward_ball_is_not_split(self):
        points = [(0.0, 0.0, -1.0), (0.1, 0.0, 0.8), (0.2, 0.0, 2.0),
                  (0.3, 0.0, 3.0), (0.7, 0.0, 0.8), (0.8, 0.0, -0.2)]
        frames = [(time, [[3, *RIM, 0.9], ball(110 + 20 * horizontal, 100 + 10 * vertical)])
                  for time, horizontal, vertical in points]
        found = shots.find_shots({"fps": 10, "frame_size": [1000, 500], "frames": frames})
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["made"])

    def test_ball_jump_gate_does_not_hide_valid_candidate(self):
        outside = ball(shots.JUMP_PX + 1, 0, 1.0)
        inside = ball(shots.JUMP_PX - 1, 0, 0.2)
        self.assertIs(shots.best_ball([outside, inside], (0, 0)), inside)
        self.assertIsNone(shots.best_ball([outside], (0, 0)))

    def test_rim_following_preserves_panning_make(self):
        frames = []
        for index in range(18):
            time = index / 10
            offset = 25 * index
            rim = [3, 100 + offset, 100, 120 + offset, 110, 0.9]
            boxes = [rim]
            if index <= 4:
                boxes.append(ball(110 + offset, 90 + 8 * index))
            frames.append((time, boxes))
        doc = {"fps": 10, "frame_size": [1000, 500], "frames": frames}
        found = shots.find_shots(doc)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["made"])
        self.assertNotIn("_rim_x", found[0])

    def test_truncated_film_does_not_infer_net_disappearance(self):
        frames = [(0.0, [[3, *RIM, 0.9], ball(110, 90)]),
                  (0.1, [[3, *RIM, 0.9], ball(110, 108)])]
        doc = {"fps": 10, "frame_size": [1000, 500], "frames": frames}
        self.assertFalse(shots.find_shots(doc)[0]["made"])

    def test_dead_ball_veto_requires_complete_post_make_observations(self):
        full = {"fps": 10, "frame_size": [1000, 500],
                "frames": [(index / 10, [[3, *RIM, 0.9]]) for index in range(101)]}
        shot = {"t": 2.0, "make_t": 2.0, "rim": RIM[:]}
        with patch("shot_split.motion", return_value=0.3):
            self.assertTrue(shots.dead_ball_make(full, shot))
            truncated = {**full, "frames": full["frames"][:40]}
            self.assertFalse(shots.dead_ball_make(truncated, shot))
            missing_rims = {**full, "frames": [(time, []) for time, _ in full["frames"]]}
            self.assertFalse(shots.dead_ball_make(missing_rims, shot))
            gap = {**full, "frames": full["frames"][:30] + full["frames"][40:]}
            self.assertFalse(shots.dead_ball_make(gap, shot))

    def test_camera_departure_requires_sustained_edge_exit(self):
        shot = {"rim": RIM[:]}
        doc = {"fps": 10, "frame_size": [1000, 500],
               "frames": [(index / 10, [[3, *RIM, 0.9]] if index < 5 else [])
                          for index in range(20)]}
        self.assertEqual(shots.camera_leaves(doc, shot, 0, 1), 0.5)
        doc["frames"] = doc["frames"][:10]
        self.assertIsNone(shots.camera_leaves(doc, shot, 0, 1))


class ScoreMatchingTest(unittest.TestCase):
    def test_event_report_preserves_event_predictions_and_undefined_metrics(self):
        truth, predictions = [change(12)], [prediction(10), prediction(30)]
        original = copy.deepcopy((truth, predictions))
        report = makes_eval.event_report(truth, predictions)
        self.assertEqual((report["matched"], report["unmatched_makes"]), (1, 1))
        self.assertEqual((report["precision"], report["recall"]), (0.5, 1.0))
        self.assertEqual(report["events"][0]["bucket"], "found")
        self.assertEqual((truth, predictions), original)
        empty = makes_eval.event_report([], [])
        self.assertIsNone(empty["precision"])
        self.assertIsNone(empty["recall"])

    def test_one_prediction_cannot_cover_two_scores(self):
        buckets, false = makes_eval.match([change(12), change(13)], [prediction(10)])
        self.assertEqual(sum(bucket[0] == "found" for bucket in buckets), 1)
        self.assertEqual(sum(bucket[0] == "called miss" for bucket in buckets), 0)
        self.assertEqual(false, [])

    def test_matching_maximizes_coverage_in_overlapping_windows(self):
        truth = [change(12), change(20)]
        predictions = [prediction(10), prediction(2.1)]
        original = copy.deepcopy((truth, predictions))
        buckets, false = makes_eval.match(truth, predictions)
        self.assertEqual([bucket[0] for bucket in buckets], ["found", "found"])
        self.assertEqual(false, [])
        self.assertEqual((truth, predictions), original)

    def test_wrong_team_and_unmatched_make(self):
        buckets, false = makes_eval.match([change(12)], [prediction(10, team="Opponent")])
        self.assertEqual(buckets[0][0], "wrong team")
        self.assertEqual(len(false), 1)

    def test_called_miss_and_dropped_buckets(self):
        for predicted, expected in [(prediction(10, made=False), "called miss"),
                                    (prediction(10, kind="warmup"), "dropped")]:
            with self.subTest(expected=expected):
                buckets, false = makes_eval.match([change(12)], [predicted])
                self.assertEqual(buckets[0][0], expected)
                self.assertEqual(false, [])

    def test_unknown_points_do_not_claim_wrong_three_point_classification(self):
        for points, expected in [(None, ""), (2, "called 2"), (3, "")]:
            with self.subTest(points=points):
                buckets, _ = makes_eval.match([change(12, delta=3)], [prediction(10, points=points)])
                self.assertEqual(buckets[0][3], expected)

    def test_zero_make_timestamp_is_preserved(self):
        self.assertEqual(makes_eval.make_time({"t": 5, "make_t": 0}), 0)
        self.assertEqual(makes_eval.make_time({"t": 5, "make_t": None}), 5)

    def test_hidden_overlay_extends_matching_window(self):
        buckets, _ = makes_eval.match([change(30, old=5)], [prediction(6)])
        self.assertEqual(buckets[0][0], "found")

    def test_lag_preference_for_single_score(self):
        buckets, false = makes_eval.match([change(12)], [prediction(3), prediction(9.8)])
        self.assertEqual(buckets[0][2]["t"], 9.8)
        self.assertEqual(false[0]["t"], 3)

    def test_truth_totals_and_invalid_increments(self):
        totals = {"Valley": {"FGM": 1, "FTM": 1, "3PM": 1, "PTS": 4}}
        makes_eval.validate_truth([change(12, delta=3), change(20, delta=1)], totals)
        for truth in [[change(12, delta=4)], [change(12, delta=-1)],
                      [change(12, delta=3)], [change(12, old=13)]]:
            with self.subTest(truth=truth), self.assertRaises(ValueError):
                makes_eval.validate_truth(truth, totals)

    def test_hudl_missing_game_cannot_read_another_game(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "totals.yaml"
            path.write_text("games:\n  - id: first\n    team_totals:\n  - id: second\n"
                            "    valley: {fg2: 1/2, fg3: 0/1, ft: 1/2}\n")
            with patch.object(makes_eval, "HUDL", path):
                for game in ("missing", "first"):
                    with self.subTest(game=game), self.assertRaises(ValueError):
                        makes_eval.hudl(game)

    def test_no_film_cli_marks_points_unavailable_and_defaults_to_mitty(self):
        truth = [change(12, delta=3)]
        totals = {"Valley": {"FGM": 1, "FGA": 1, "FTM": 0, "FTA": 0, "3PM": 1, "PTS": 3},
                  "Opponent": {"FGM": 0, "FGA": 0, "FTM": 0, "FTA": 0, "3PM": 0, "PTS": 0}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truth.json"
            report_path = Path(directory) / "report.json"
            path.write_text(json.dumps({"mitty": truth}))
            output = io.StringIO()
            with patch.object(makes_eval, "TRUTH", path), patch.object(makes_eval, "hudl", return_value=totals), \
                    patch.object(makes_eval, "run_pipeline", return_value=({}, [prediction(10)])) as pipeline, \
                    patch.object(sys, "argv", ["makes_eval.py", "--no-film", "--report-json", str(report_path)]), \
                    contextlib.redirect_stdout(output):
                makes_eval.main()
            report = json.loads(report_path.read_text())
            self.assertFalse(report["film"])
            self.assertEqual(report["games"]["mitty"]["matched"], 1)
            self.assertEqual(len(report["truth_sha256"]), 64)
            self.assertEqual(report["games"]["mitty"]["predictions"], [prediction(10)])
            pipeline.assert_called_once_with("mitty", film=False)
            self.assertIn("3PM n/a PTS n/a", output.getvalue())
            self.assertNotIn("called 2", output.getvalue())
            self.assertIn("event precision 100.0%, recall 100.0%", output.getvalue())


if __name__ == "__main__":
    unittest.main()
