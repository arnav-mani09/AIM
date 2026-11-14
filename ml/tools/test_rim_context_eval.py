"""Focused private-context and immutable artifact regression checks."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import rim_context_eval as evaluation


class ContextTests(unittest.TestCase):
    def test_common_prefix_requires_observed_above_in_zone(self):
        entry = {"point": [1, 100, 85, 90, 90, 110, 100], "rim_score": .8}
        self.assertEqual(evaluation.common_prefix([entry]), 1)
        entry["point"][2] = 100
        with self.assertRaises(ValueError):
            evaluation.common_prefix([entry])

    def test_horizon_is_not_detection_coverage(self):
        records = [{"sample": {"seconds": time, "pts": index, "rim_anchor_x": 100},
                    "retained_postprocess_ball_rim": []}
                   for index, time in enumerate([1.1, 1.2, 1.4, 1.5])]
        trace = {"first_under_net": {"point": [1, 0, 2]}}
        coverage = evaluation.coverage(records, [], trace)
        self.assertTrue(coverage["decoded_horizon_complete"])
        self.assertFalse(coverage["all_guard_frames_have_selected_pair"])
        self.assertEqual(len(coverage["missing_ball_pts"]), 3)
        self.assertEqual(len(coverage["missing_local_rim_pts"]), 3)
        self.assertFalse(evaluation.coverage(records[:2], [], trace)["decoded_horizon_complete"])

    def test_reuse_needs_all_identity_fields(self):
        sample = {"pts": 90, "time_base": "1/90", "source_video_sample_index": 1,
                  "packet_position": 12, "file": {"sha256": "abc", "size_bytes": 1}}
        manifest = {key: {"value": 1} for key in ("checkpoint", "protocol", "dependencies", "source")}
        self.assertTrue(evaluation.reusable(sample, sample, manifest, manifest))
        for key in manifest:
            changed = copy.deepcopy(manifest)
            changed[key] = {"different": 2}
            self.assertFalse(evaluation.reusable(sample, sample, manifest, changed))
        for key in ("pts", "time_base", "source_video_sample_index", "packet_position", "file"):
            changed = copy.deepcopy(sample)
            changed[key] = {"sha256": "bad", "size_bytes": 1} if key == "file" else "bad"
            self.assertFalse(evaluation.reusable(sample, changed, manifest, manifest))

    def test_no_foreign_output_or_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact"
            with self.assertRaises(ValueError):
                evaluation.create_output(path)
            evaluation.write_new(path, {"frozen": True})
            record = evaluation.file_record(path)
            with self.assertRaises(FileExistsError):
                evaluation.write_new(path, {"frozen": False})
            evaluation.prior.checked_record(record)
            path.write_text("tampered")
            with self.assertRaises(ValueError):
                evaluation.prior.checked_record(record)

    def test_trigger_is_evidence_only_and_uses_previous_observation(self):
        trace = {"decide_result": {"made": True}, "first_under_net": {"index": 1},
                 "rim_unit_path": [[1, .44, 1.1], [1.1, .2, 3]]}
        self.assertTrue(evaluation.trigger(trace))
        trace["decide_result"]["made"] = False
        self.assertFalse(evaluation.trigger(trace))

    def test_observed_zone_entry_excludes_pre_attempt_below_net(self):
        records = []
        for index, (time, horizontal, vertical) in enumerate([(1, 1, 3), (1.1, .2, -.5), (1.2, .2, 1), (1.3, .2, 2), (1.8, .2, 4)]):
            center_x, center_y = 100 + horizontal * 20, 90 + vertical * 10
            rows = [{"category": 0, "xyxy": [center_x - 2, center_y - 2, center_x + 2, center_y + 2],
                     "score": .8, "passes_class_cutoff": True},
                    {"category": 3, "xyxy": [90, 90, 110, 100], "score": .8, "passes_class_cutoff": True}]
            records.append({"sample": {"seconds": time, "pts": index, "rim_anchor_x": 100},
                            "retained_postprocess_ball_rim": rows})
        trace = evaluation.evaluate(records, 100)
        self.assertEqual(trace["pre_attempt_observations_excluded"], 1)
        self.assertEqual(trace["attempt_path_starts_at"], 1.1)
        self.assertTrue(trace["decide_result"]["made"])
        self.assertEqual(trace["first_under_net"]["point"][0], 1.3)

    @unittest.skipUnless((evaluation.OUTPUT / "integrity.json").exists(), "requires completed private experiment")
    def test_actual_evidence_integrity_and_context(self):
        integrity_path = evaluation.OUTPUT / "integrity_context.json"
        integrity = json.loads((integrity_path if integrity_path.exists() else evaluation.OUTPUT / "integrity.json").read_text())
        for record in integrity["files"]:
            evaluation.prior.checked_record(record)
        manifest = json.loads((evaluation.OUTPUT / "manifest.json").read_text())
        self.assertLessEqual(len(manifest["samples"]), 125)
        self.assertEqual(manifest["budget_seconds"], 240)
        report_path = evaluation.OUTPUT / "analysis_context.json"
        report = json.loads((report_path if report_path.exists() else evaluation.OUTPUT / "analysis.json").read_text())
        for window in report["windows"].values():
            for trace in [window["dense"], *window["common_context_phases"].values(), *window["pure_phases"].values()]:
                if trace.get("status") == "missing_initial_context":
                    self.assertTrue(trace["decision_not_evaluated"])
                    continue
                self.assertGreater(trace["above_rim_observations"], 0)
                self.assertTrue(trace["coverage"]["decoded_horizon_complete"])


if __name__ == "__main__":
    unittest.main()
