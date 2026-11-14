"""Synthetic sequence/evaluation regressions; these are not film accuracy labels."""

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assist_eval import annotation_template, evaluate, main
from assist_sequences import AssistConfig, detect_assists


def hold(tid, start, end, left, **extra):
    box = [left, 0, left + 20, 100]
    return {"tid": tid, "t0": start, "t1": end, "first": box[:], "last": box[:],
            "box": box[:], "n": 3, "team": "Valley", "sure": True, **extra}


def fixture():
    split = {"shots": [{"t": 3.0, "kind": "FG", "made": True, "team": "Valley", "shooter_track": 2}]}
    runs = [hold(1, 0.5, 1.0, 0), hold(2, 1.6, 2.1, 300)]
    observations = [{"t": time, "ball": [horizontal, 50],
                     "players": [{"tid": run["tid"], "box": run["first"][:]} for run in runs]}
                    for time, horizontal in ((1.1, 70), (1.3, 150), (1.5, 240))]
    return split, runs, observations


class AssistSequenceTest(unittest.TestCase):
    def detect(self, split=None, runs=None, observations=None, **kwargs):
        defaults = fixture()
        return detect_assists(split if split is not None else defaults[0],
                              runs if runs is not None else defaults[1],
                              observations if observations is not None else defaults[2], **kwargs)

    def reason(self, result, expected):
        self.assertEqual(result["events"], [])
        self.assertEqual(result["decisions"][0]["reason"], expected)

    def test_observed_pass_catch_make_compatible_event(self):
        result = self.detect()
        event = result["events"][0]
        self.assertEqual((event["type"], event["t"], event["shot_t"], event["track"]), ("ast", 1.0, 3.0, 1))
        self.assertIsNone(event["player"])
        self.assertEqual(event["identity_status"], "track_only_unverified")
        self.assertEqual(event["review_status"], "unreviewed")

    def test_inputs_not_mutated(self):
        inputs = fixture()
        original = copy.deepcopy(inputs)
        detect_assists(*inputs)
        self.assertEqual(inputs, original)

    def test_mismatch_audit_does_not_promote_nearest_or_aliased_holder(self):
        split, runs, observations = fixture()
        split["shots"][0]["shooter_track"] = 3
        result = detect_assists(split, runs, observations, identity_map={2: 3})
        self.reason(result, "shooter_hold_mismatch")
        audit = result["decisions"][0]["shooter_hold_observation"]
        self.assertEqual(audit["hold_track"], 2)
        self.assertEqual(audit["track_relation"], "unresolved_tracks")
        self.assertFalse(audit["identity_verified"])

    def test_time_local_uncertainty_blocks_otherwise_valid_sequence(self):
        runs = fixture()[1]
        runs[1].update(sure=False, team_evidence="unverified_interval")
        result = self.detect(runs=runs)
        self.reason(result, "uncertain_shooter_hold")
        self.assertEqual(result["decisions"][0]["shooter_hold_observation"]["team_evidence"], "unverified_interval")

    def test_no_flight_no_assist(self):
        self.reason(self.detect(observations=[]), "no_distinct_player_ball_flight")

    def test_single_ball_sample_is_insufficient(self):
        self.reason(self.detect(observations=fixture()[2][:1]), "no_distinct_player_ball_flight")

    def test_partial_flight_does_not_establish_completed_pass(self):
        observations = fixture()[2]
        for observation, horizontal in zip(observations, (40, 70, 100)):
            observation["ball"][0] = horizontal
        self.reason(self.detect(observations=observations), "no_distinct_player_ball_flight")

    def test_large_unobserved_flight_gap_rejected(self):
        observations = fixture()[2][::2]
        self.reason(self.detect(observations=observations), "no_distinct_player_ball_flight")

    def test_ball_dribble_inside_holder_is_not_a_pass(self):
        observations = fixture()[2]
        for observation in observations:
            observation["ball"] = [10, 90]
        self.reason(self.detect(observations=observations), "no_distinct_player_ball_flight")

    def test_reverse_ball_flight_rejected(self):
        observations = fixture()[2]
        for observation, horizontal in zip(observations, (240, 150, 70)):
            observation["ball"][0] = horizontal
        self.reason(self.detect(observations=observations), "no_distinct_player_ball_flight")

    def test_track_switch_without_co_visibility_rejected(self):
        observations = fixture()[2]
        for observation in observations:
            observation["players"] = observation["players"][:1]
        self.reason(self.detect(observations=observations), "no_distinct_player_ball_flight")

    def test_shared_camera_translation_does_not_create_or_destroy_flight(self):
        observations = fixture()[2]
        for index, observation in enumerate(observations):
            offset = 200 * index
            observation["ball"][0] += offset
            for player in observation["players"]:
                player["box"][0] += offset
                player["box"][2] += offset
        self.assertEqual(len(self.detect(observations=observations)["events"]), 1)

    def test_shooter_unknown_never_falls_back_to_teammate(self):
        split = fixture()[0]
        split["shots"][0]["shooter_track"] = None
        self.reason(self.detect(split=split), "unknown_shooter_or_team")

    def test_known_shooter_not_latest_holder_rejected(self):
        split = fixture()[0]
        split["shots"][0]["shooter_track"] = 99
        self.reason(self.detect(split=split), "shooter_hold_mismatch")

    def test_same_id_and_explicit_identity_alias_rejected(self):
        runs = fixture()[1]
        runs[0]["tid"] = 2
        self.reason(self.detect(runs=runs), "same_player_or_track_switch")
        self.reason(self.detect(identity_map={1: "person-A", 2: "person-A"}), "same_player_or_track_switch")

    def test_unknown_team_not_discarded_between_pass_and_catch(self):
        runs = fixture()[1]
        runs.insert(1, hold(3, 1.15, 1.25, 150, team=None, sure=False))
        self.reason(self.detect(runs=runs), "intervening_or_uncertain_holder")

    def test_opponent_or_referee_touch_not_assist(self):
        for extra in ({"team": "Opponent"}, {"ref": True}, {"sure": False}, {"contested": 0.8}):
            runs = fixture()[1]
            runs[0].update(extra)
            with self.subTest(extra=extra):
                self.reason(self.detect(runs=runs), "intervening_or_uncertain_holder")

    def test_uncertain_receiver_rejected(self):
        runs = fixture()[1]
        runs[1]["sure"] = False
        self.reason(self.detect(runs=runs), "uncertain_shooter_hold")

    def test_handoff_and_overlap_rejected(self):
        for start in (1.05, 0.9):
            runs = fixture()[1]
            runs[1]["t0"] = start
            self.reason(self.detect(runs=runs), "handoff_overlap_or_long_gap")

    def test_close_handoff_even_with_observed_ball_rejected(self):
        observations = fixture()[2]
        for observation in observations:
            observation["players"][1]["box"] = [50, 0, 70, 100]
            observation["ball"] = [35, 50]
        self.reason(self.detect(observations=observations), "no_distinct_player_ball_flight")

    def test_long_gap_and_stale_catch_rejected(self):
        runs = fixture()[1]
        runs[0].update(t0=-0.5, t1=-0.2)
        self.reason(self.detect(runs=runs), "handoff_overlap_or_long_gap")
        split = fixture()[0]
        split["shots"][0]["t"] = 4.1
        self.reason(self.detect(split=split), "drive_or_stale_catch")

    def test_fragmented_dribble_drive_accumulates_hold_duration(self):
        split = fixture()[0]
        split["shots"][0]["t"] = 4.0
        runs = fixture()[1]
        runs[1]["t1"] = 2.5
        runs.append(hold(2, 2.7, 3.6, 300))
        self.reason(self.detect(split=split, runs=runs), "drive_or_stale_catch")

    def test_short_drive_travel_rejected(self):
        runs = fixture()[1]
        runs[1]["last"] = [410, 0, 430, 100]
        self.reason(self.detect(runs=runs), "drive_or_stale_catch")

    def test_miss_and_rebound_between_pass_and_make_rejected(self):
        split = fixture()[0]
        split["shots"].insert(0, {"t": 1.4, "kind": "FG", "made": False, "team": "Valley"})
        self.reason(self.detect(split=split), "intervening_shot_or_rebound")

    def test_free_throw_and_misses_not_candidates(self):
        for change in ({"kind": "FT"}, {"made": False}, {"kind": "dead_ball"}):
            split = fixture()[0]
            split["shots"][0].update(change)
            self.assertEqual(self.detect(split=split), {"events": [], "decisions": []})

    def test_duplicate_shot_not_double_counted(self):
        split = fixture()[0]
        split["shots"].append(dict(split["shots"][0]))
        self.assertEqual(len(self.detect(split=split)["events"]), 1)

    def test_invalid_config_rejected(self):
        for kwargs in ({"pass_air_min": 2, "pass_air_max": 1}, {"min_flight_samples": 1}, {"assist_window": float("nan")}):
            with self.assertRaises(ValueError):
                AssistConfig(**kwargs)


def label(time, truth, **extra):
    return {"shot_t": time, "team": "Valley", "label": truth, "reviewer": "synthetic test",
            "evidence": "synthetic fixture, NOT film", "notes": "unit test only", **extra}


class AssistEvaluationTest(unittest.TestCase):
    def test_cache_replay_refuses_source_drift(self):
        with patch("assist_eval.input_provenance", side_effect=[{"version": 1}, {"version": 2}]), \
                patch("assist_eval.cached_inputs", return_value=(*fixture(), [])):
            with self.assertRaisesRegex(RuntimeError, "changed during replay"):
                main(["--tracks", "unused.json", "--game", "synthetic"])

    def test_stable_cache_replay_retains_compatible_summary(self):
        with patch("assist_eval.input_provenance", return_value={"version": 1}), \
                patch("assist_eval.cached_inputs", return_value=(*fixture(), [])), patch("builtins.print"):
            result = main(["--tracks", "unused.json", "--game", "synthetic"])
        self.assertEqual(result["bounded_candidates"], 1)
        self.assertEqual(result["accuracy"], "not measured; candidate counts are not correctness")

    def test_positive_negative_uncertain_and_unreviewed(self):
        events = [{"shot_t": time, "team": "Valley"} for time in (1, 2, 5, 6)]
        rows = [label(1, "assist"), label(2, "no_assist"), label(3, "assist"),
                label(4, "no_assist"), label(5, "uncertain"), label(6, "unreviewed")]
        result = evaluate(events, {"annotations": rows})
        self.assertEqual([result[key] for key in ("tp", "fp", "fn", "tn")], [1, 1, 1, 1])
        self.assertEqual(result["precision_on_reviewed"], 0.5)
        self.assertEqual(result["recall_on_reviewed"], 0.5)
        self.assertEqual(result["predictions_outside_reviewed"], 2)

    def test_empty_labels_do_not_imply_perfect_accuracy(self):
        result = evaluate([{"shot_t": 1, "team": "Valley"}], {"annotations": []})
        self.assertIsNone(result["accuracy_on_reviewed"])
        self.assertIsNone(result["precision_on_reviewed"])
        self.assertIsNone(result["recall_on_reviewed"])

    def test_labels_require_review_evidence(self):
        row = label(1, "assist", evidence="")
        with self.assertRaises(ValueError):
            evaluate([], {"annotations": [row]})

    def test_wrong_team_is_not_true_positive(self):
        result = evaluate([{"shot_t": 1, "team": "Opponent"}], {"annotations": [label(1, "assist")]})
        self.assertEqual(result["fn"], 1)
        self.assertEqual(result["predictions_outside_reviewed"], 1)

    def test_attribution_separate_from_detection(self):
        result = evaluate([{"shot_t": 1, "team": "Valley", "passer_track": 9, "shooter_track": 2}],
                          {"annotations": [label(1, "assist", passer_track=1, shooter_track=2)]})
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["attribution_checked"], 1)
        self.assertEqual(result["attribution_correct"], 0)

    def test_duplicate_and_ambiguous_matching_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate([], {"annotations": [label(1, "assist"), label(1, "no_assist")]})
        with self.assertRaises(ValueError):
            evaluate([{"shot_t": 1, "team": "Valley"}, {"shot_t": 1.1, "team": "Valley"}],
                     {"annotations": [label(1, "assist")]})

    def test_template_predictions_are_never_labels(self):
        result = detect_assists(*fixture())
        template = annotation_template("development", result, result["events"])
        self.assertEqual(template["annotations"][0]["label"], "unreviewed")
        self.assertIsNone(template["annotations"][0]["passer_track"])
        self.assertEqual(evaluate(result["events"], template)["reviewed_opportunities"], 0)


if __name__ == "__main__":
    unittest.main()
