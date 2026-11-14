"""Actual pinned tracker tests; box associations are not human identity truth."""

import json
import unittest
from unittest.mock import patch

import numpy as np
from supervision.tracker.byte_tracker import core, matching

import tracking_association_trace as trace


class AssociationTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = trace.capture.read_lines(trace.capture.OUTPUT / "inputs.jsonl")
        cls.expected = trace.capture.read_lines(trace.capture.OUTPUT / "outputs.jsonl")

    def test_actual_mutation_captured_before_clamp(self):
        record = self.inputs[0]
        tracker = trace.sv.ByteTrack(**trace.capture.TRACKER)
        captured = []
        for record in self.inputs[:4]:
            probe = trace.StageTrace(record)
            with probe.installed():
                tracker.update_with_detections(trace.capture.unpack_detections(record["detections"]))
            captured.extend(probe.events)
        changed = [event for event in captured if "matches" in event and
                   event["cost_before"] != event["cost_after"]]
        self.assertTrue(changed)
        for event in changed:
            self.assertTrue(trace.check_assignment(event))
            before = np.asarray(event["cost_before"]["values"])
            self.assertTrue(np.any(before > event["threshold"] + 1e-4))

    def test_exception_restores_all_wrappers_and_descriptor(self):
        original = (matching.iou_distance, matching.fuse_score, matching.linear_assignment,
                    core.STrack.__dict__["multi_predict"])
        for owner, name in ((matching, "iou_distance"), (matching, "fuse_score"),
                            (matching, "linear_assignment"), (core.STrack, "multi_predict")):
            with self.subTest(name=name):
                probe = trace.StageTrace(self.inputs[0])
                with patch.object(owner, name, side_effect=RuntimeError("injected failure")) as failing:
                    with self.assertRaisesRegex(RuntimeError, "injected failure"):
                        with probe.installed():
                            trace.sv.ByteTrack(**trace.capture.TRACKER).update_with_detections(
                                trace.capture.unpack_detections(self.inputs[0]["detections"]))
                    self.assertIs(getattr(owner, name), failing)
                self.assertEqual(original, (matching.iou_distance, matching.fuse_score,
                                           matching.linear_assignment, core.STrack.__dict__["multi_predict"]))

    def test_full_raw_parity_and_stage_identity(self):
        rows, output = trace.replay(self.inputs, self.expected)
        self.assertEqual(output, self.expected)
        for row in rows:
            assignments = [event for event in row["events"] if "matches" in event]
            self.assertEqual([event["stage"] for event in assignments[:3]], list(trace.STAGES))
            self.assertEqual([event["threshold"] for event in assignments[:3]], [.8, .5, .7])
            if len(assignments) == 4:
                self.assertEqual(assignments[3]["stage"], "public_rematch")
                self.assertEqual(assignments[3]["threshold"], .5)
            for event in assignments:
                self.assertTrue(trace.check_assignment(event))
            public = next(event for event in row["events"] if event["stage"] == "public_rematch")
            winners = sorted(public["matches"])
            self.assertEqual([public["columns"][column]["external_id"] for _, column in winners],
                             row["output"]["arrays"]["tracker_id"]["values"])

    def test_frozen_trace_has_exact_outputs(self):
        artifact = trace.OUTPUT / "traces.json"
        if not artifact.exists():
            self.skipTest("Run bounded evidence capture first")
        rows = json.loads(artifact.read_text())
        self.assertEqual(len(rows), 244)
        for row, expected in zip(rows, self.expected):
            self.assertEqual(row["output"], expected["detections"])

    def focal(self):
        artifact = trace.OUTPUT / "traces.json"
        if not artifact.exists():
            self.skipTest("Run bounded evidence capture first")
        return json.loads(artifact.read_text())

    def test_riordan_gate_loss_and_unconfirmed_delay_not_rematch(self):
        rows = self.focal()
        edges = trace.focal_witnesses(rows, self.inputs)["edges"]
        rejected = next(edge for edge in edges if edge["sample"] == 152)
        self.assertAlmostEqual(rejected["input_cost"], .8118542438594284, places=14)
        self.assertGreater(1 - rejected["iou"], .8)
        self.assertEqual(rejected["clamped_cost"], .8001)
        self.assertFalse(rejected["accepted"])
        high = next(event for event in rows[152]["events"] if event["stage"] == "high")
        column = high["column_proposals"].index([2])
        self.assertTrue(all(costs[column] > .8 for costs in high["cost_before"]["values"]))
        states = rows[152]["after"]
        self.assertTrue(any(track["external_id"] == 5 for track in states["lost_tracks"]))
        self.assertTrue(any(track["external_id"] == 32 and not track["activated"]
                            for track in states["tracked_tracks"]))
        public = next(event for event in rows[152]["events"] if event["stage"] == "public_rematch")
        self.assertNotIn(32, [track["external_id"] for track in public["columns"]])
        recovered = next(edge for edge in edges if edge["sample"] == 153 and edge["stage"] == "unconfirmed")
        self.assertTrue(recovered["accepted"])

    def test_mitty_competition_precedes_public_rematch_despite_lab_similarity(self):
        rows = self.focal()
        edges = trace.focal_witnesses(rows, self.inputs)["edges"]
        white, blue = [next(edge for edge in edges if edge["sample"] == 92 and
                           edge["stage"] == "high" and edge["proposal_index"] == proposal)
                       for proposal in (4, 7)]
        self.assertLess(white["input_cost"], .8)
        self.assertLess(blue["input_cost"], white["input_cost"])
        self.assertEqual(white["input_cost"] - blue["input_cost"], .000464978055600751)
        self.assertTrue(blue["accepted"])
        self.assertFalse(white["accepted"])
        high = next(event for event in rows[92]["events"] if event["stage"] == "high")
        for proposal in (4, 7):
            column = high["column_proposals"].index([proposal])
            self.assertTrue(all(high["cost_before"]["values"][row][column] > .8
                                for row, track in enumerate(high["rows"]) if track["external_id"] != 38))
        event = next(event for event in rows[92]["events"] if event["stage"] == "public_rematch")
        self.assertTrue(any(event["rows"][row]["proposal_refs"] == [7] and
                            event["columns"][column]["external_id"] == 38 for row, column in event["matches"]))
        lab_before = np.asarray(self.inputs[91]["proposals"][7]["torso"]["lab"])
        lab_after = np.asarray(self.inputs[92]["proposals"][7]["torso"]["lab"])
        self.assertEqual(float(np.linalg.norm(lab_before - lab_after)), 3.0)

    def test_overlap_controls_and_referee_class_routing(self):
        rows = self.focal()
        witness = trace.focal_witnesses(rows, self.inputs)
        self.assertTrue(all(control["inputs"] == control["outputs"] == 9 for control in witness["controls"]))
        for sample, referee, player in ((213, 10, 11), (214, 9, 10)):
            record = self.inputs[sample]
            self.assertNotIn(referee, record["player_proposal_indices"])
            self.assertIn(player, record["player_proposal_indices"])
            low = next(event for event in rows[sample]["events"] if event["stage"] == "low")
            column = low["column_proposals"].index([player])
            self.assertEqual([costs[column] for costs in low["cost_before"]["values"]], [1.0])
        self.assertEqual(witness["public_rematch_disagreements"], [])
        self.assertEqual(witness["public_rematch_agrees_with_internal_matched_proposals"], 2174)


if __name__ == "__main__":
    unittest.main()
