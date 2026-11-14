import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_game_eval as evaluation


def event(identifier="real", time=10, kind="point", team="Valley", player="12", points=2):
    result = {"id": identifier, "time": time, "type": kind, "team": team,
              "player": player, "evidence": "independent source review at timestamp"}
    if kind == "point":
        result["points"] = points
    return result


def fixture():
    return {"schema_version": 1, "game": "synthetic", "timeline": [0, 60],
            "timeline_independently_confirmed": True, "timeline_evidence": "source boundary review",
            "source": {"path": "synthetic.json", "sha256": "0" * 64, "split_role": "development"},
            "teams": ["Valley", "Opponent"],
            "intervals": [{"id": "first", "start": 0, "end": 60, "status": "reviewed_complete",
                           "reviewer_type": "human", "reviewer": "independent development reviewer",
                           "independent_of_predictions": True, "evidence": "all source timeline reviewed"}],
            "truth_events": [event()], "predicted_events": [event("predicted")], "review_log": []}


class FullGameEvalTest(unittest.TestCase):
    def score(self, document, kind="point", tolerance=1):
        return evaluation.evaluate(document, tolerance)["interval_metrics"][kind]

    def test_correct_and_no_annotation_burden(self):
        report = evaluation.evaluate(fixture())
        self.assertEqual(report["interval_metrics"]["point"]["precision"], 1)
        self.assertTrue(report["full_game_coverage"])
        self.assertFalse(report["held_out"])
        self.assertIsNone(report["review_burden"])
        self.assertIsNone(report["coach_time_gain"])

    def test_duplicate_prediction_only_matches_once(self):
        document = fixture()
        document["predicted_events"].append(event("duplicate"))
        metrics = self.score(document)
        self.assertEqual(metrics["matched"], 1)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(len(metrics["false_event_ids"]), 1)

    def test_model_or_unspecified_review_cannot_certify_full_game(self):
        for reviewer_type in ("model", "unknown", None):
            document = fixture()
            if reviewer_type is None:
                document["intervals"][0].pop("reviewer_type")
            else:
                document["intervals"][0]["reviewer_type"] = reviewer_type
            report = evaluation.evaluate(document)
            self.assertTrue(report["complete_timeline_coverage"])
            self.assertIsNone(report["full_game_metrics"])
            self.assertEqual(report["reference_status"], "provisional_or_unspecified")
            self.assertEqual(report["interval_metrics"]["point"]["precision"], 1)

    def test_human_adjudication_requires_named_reviewer(self):
        document = fixture()
        document["intervals"][0]["reviewer"] = ""
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)

    def test_fractional_partition_does_not_depend_on_duration_sum_roundoff(self):
        document = fixture()
        document["timeline"] = [0.1, 0.8]
        document["truth_events"] = []
        document["predicted_events"] = []
        template = document["intervals"][0]
        document["intervals"] = [{**template, "id": str(index), "start": start, "end": end}
                                 for index, (start, end) in enumerate(((0.1, 0.3), (0.3, 0.6), (0.6, 0.8)))]
        self.assertTrue(evaluation.evaluate(document)["full_game_coverage"])

    def test_ambiguous_truth_or_competing_prediction_fails(self):
        for extra in (event("other", time=10.5), event("other")):
            document = fixture()
            document["truth_events"].append(extra)
            with self.assertRaises(ValueError):
                evaluation.evaluate(document)
        document = fixture()
        document["predicted_events"].append(event("other", player="3"))
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)

    def test_blank_unknown_or_missing_status_fails(self):
        for status in ("", None, "unknown"):
            document = fixture()
            document["intervals"][0]["status"] = status
            with self.assertRaises(ValueError):
                evaluation.evaluate(document)
        document = fixture()
        del document["intervals"][0]["status"]
        with self.assertRaises(KeyError):
            evaluation.evaluate(document)

    def test_unreviewed_empty_truth_is_not_negative(self):
        document = fixture()
        document["intervals"][0]["status"] = "unreviewed"
        document["truth_events"] = []
        report = evaluation.evaluate(document)
        self.assertIsNone(report["full_game_metrics"])
        self.assertIsNone(report["interval_metrics"]["point"]["precision"])
        self.assertIsNone(report["interval_metrics"]["point"]["recall"])
        self.assertEqual(report["unscored_prediction_ids"], ["predicted"])
        self.assertEqual(report["interval_metrics"]["point"]["false_event_ids"], [])

    def test_affirmative_complete_negative_interval(self):
        document = fixture()
        document["truth_events"] = []
        metrics = self.score(document)
        self.assertEqual(metrics["precision"], 0)
        self.assertEqual(metrics["false_event_ids"], ["predicted"])
        self.assertIsNone(metrics["recall"])

    def test_partial_unobservable_and_gaps_excluded(self):
        for status in ("partially_reviewed", "unobservable"):
            document = fixture()
            document["intervals"][0]["status"] = status
            if status == "unobservable":
                document["truth_events"] = []
            report = evaluation.evaluate(document)
            self.assertTrue(report["partial"])
            self.assertEqual(report["unscored_prediction_ids"], ["predicted"])
        document = fixture()
        document["intervals"] = []
        document["truth_events"] = []
        report = evaluation.evaluate(document)
        self.assertEqual(report["unlisted_seconds"], 60)
        self.assertEqual(report["unscored_prediction_ids"], ["predicted"])

    def test_half_open_interval_boundaries(self):
        document = fixture()
        document["intervals"][0]["end"] = 10
        document["intervals"].append({"id": "second", "start": 10, "end": 60,
                                       "status": "unreviewed"})
        document["truth_events"] = []
        self.assertEqual(evaluation.evaluate(document)["unscored_prediction_ids"], ["predicted"])
        document["predicted_events"][0]["time"] = 0
        self.assertEqual(self.score(document)["false_event_ids"], ["predicted"])
        document["predicted_events"][0]["time"] = 60
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)

    def test_tolerance_does_not_bridge_review_boundaries(self):
        document = fixture()
        document["intervals"][0]["end"] = 10
        other = copy.deepcopy(document["intervals"][0])
        other.update(id="second", start=10, end=60)
        document["intervals"].append(other)
        document["truth_events"][0]["time"] = 9.9
        metrics = self.score(document)
        self.assertEqual(metrics["matched"], 0)
        self.assertEqual(metrics["recall"], 0)

    def test_nonfinite_invalid_times_and_tolerances(self):
        for time in (float("nan"), float("inf"), -1, True, "10"):
            for key in ("truth_events", "predicted_events"):
                document = fixture()
                document[key][0]["time"] = time
                with self.assertRaises(ValueError):
                    evaluation.evaluate(document)
        for tolerance in (float("nan"), -1, 31, True):
            with self.assertRaises(ValueError):
                evaluation.evaluate(fixture(), tolerance)
        document = fixture()
        document["intervals"][0]["end"] = float("inf")
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)

    def test_missing_predictions_expose_missing_shots_and_other_events(self):
        document = fixture()
        document["truth_events"].extend([event("rebound", time=20, kind="rebound"),
                                          event("assist", time=30, kind="assist")])
        document["predicted_events"] = []
        report = evaluation.evaluate(document)
        for kind in evaluation.TYPES:
            self.assertEqual(report["interval_metrics"][kind]["recall"], 0)
            self.assertEqual(len(report["interval_metrics"][kind]["missed_event_ids"]), 1)

    def test_wrong_team_player_and_value_separate(self):
        document = fixture()
        document["predicted_events"][0]["team"] = "Opponent"
        metrics = self.score(document)
        self.assertEqual((metrics["precision"], metrics["recall"], metrics["team_accuracy"]), (0, 0, 0))
        self.assertIsNone(metrics["player_accuracy"])
        document = fixture()
        document["predicted_events"][0].update(player="3", points=3)
        metrics = self.score(document)
        self.assertEqual(metrics["precision"], 1)
        self.assertEqual(metrics["team_accuracy"], 1)
        self.assertEqual(metrics["player_accuracy"], 0)
        self.assertEqual(metrics["points_value_accuracy"], 0)
        document["truth_events"][0]["player"] = None
        self.assertIsNone(self.score(document)["player_accuracy"])

    def test_incomplete_boundaries_and_nonindependent_reviews(self):
        document = fixture()
        document["timeline_independently_confirmed"] = False
        self.assertIsNone(evaluation.evaluate(document)["full_game_metrics"])
        document["intervals"][0]["independent_of_predictions"] = False
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)

    def test_invalid_points_overlap_ids_and_truth_in_unreviewed(self):
        for mutate in (
            lambda doc: doc["truth_events"][0].update(points=0),
            lambda doc: doc["truth_events"][0].update(points=True),
            lambda doc: doc["intervals"].append(copy.deepcopy(doc["intervals"][0])),
            lambda doc: doc["predicted_events"].append(copy.deepcopy(doc["predicted_events"][0])),
            lambda doc: doc["intervals"][0].update(status="unreviewed"),
        ):
            document = fixture()
            mutate(document)
            with self.assertRaises(ValueError):
                evaluation.evaluate(document)

    def test_explicit_review_logs_only(self):
        document = fixture()
        document["review_log"] = [{"id": "session-1", "evidence": "session timer and correction log", "reviewer_role": "analyst",
                                   "active_seconds": 45, "reviewed_events": 3, "corrections": 1}]
        burden = evaluation.evaluate(document)["review_burden"]
        self.assertEqual(burden["active_seconds"], 45)
        self.assertEqual(burden["by_role_active_seconds"], {"analyst": 45})
        document["review_log"].append(copy.deepcopy(document["review_log"][0]))
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)
        document["review_log"].pop()
        document["review_log"][0]["active_seconds"] = -1
        with self.assertRaises(ValueError):
            evaluation.evaluate(document)

    def test_deterministic_export_hashes_no_truth_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = root / "window.json"
            window.write_text(json.dumps({"found": True, "start": 100, "end": 350}))
            first, second = root / "one.json", root / "two.json"
            template = evaluation.export_template(window, "synthetic", first)
            evaluation.export_template(window, "synthetic", second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(template["source"]["sha256"], evaluation.digest(window))
            self.assertEqual(template["source"]["split_role"], "development")
            self.assertEqual([(item["start"], item["end"]) for item in template["intervals"]],
                             [(100, 220), (220, 340), (340, 350)])
            self.assertEqual(template["truth_events"], [])
            report = evaluation.evaluate(template)
            self.assertIsNone(report["full_game_metrics"])
            with self.assertRaises(FileExistsError):
                evaluation.export_template(window, "synthetic", first)
            with self.assertRaises(FileExistsError):
                evaluation.write_new(first, {})


if __name__ == "__main__":
    unittest.main()
