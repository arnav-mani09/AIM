"""Focused tests do not load weights or decode film."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rim_source_rate_eval as evaluation


class SourceRateTests(unittest.TestCase):
    def test_alignment_uses_packet_identity_not_fps(self):
        packets = [{"pos": "100", "pts": 90001}, {"pos": "200", "pts": 93002}]
        frames = [{"pts": 93002, "best_effort_timestamp": 93002,
                   "pkt_pos": "200", "pict_type": "P"}]
        result = evaluation.align_frames(frames, packets, "1/90000", "1", "1.1")
        self.assertEqual(result[0]["source_video_sample_index"], 1)
        self.assertEqual(result[0]["pts"], 93002)
        self.assertNotEqual(result[0]["seconds"], 31 / 30)

    def test_alignment_rejects_mismatched_pts(self):
        with self.assertRaises(ValueError):
            evaluation.align_frames([{"pts": 90, "best_effort_timestamp": 90, "pkt_pos": "1"}],
                                    [{"pos": "1", "pts": 91}], "1/90", "0", "2")

    def test_exact_bounds_no_rounding_in(self):
        packets = [{"pos": str(index), "pts": pts} for index, pts in enumerate((89999, 90000, 90001))]
        frames = [{"pts": packet["pts"], "best_effort_timestamp": packet["pts"],
                   "pkt_pos": packet["pos"], "pict_type": "P"} for packet in packets]
        result = evaluation.align_frames(frames, packets, "1/90000", "1", "1")
        self.assertEqual([frame["pts"] for frame in result], [90000])

    def test_duplicate_pts_rejected(self):
        frame = {"pts": 90, "best_effort_timestamp": 90, "pkt_pos": "1", "pict_type": "P"}
        with self.assertRaises(ValueError):
            evaluation.align_frames([frame, frame], [{"pos": "1", "pts": 90}], "1/90", "0", "2")

    def test_protocol_preservation(self):
        import json
        protocol = json.loads(evaluation.BASELINE.read_text())["protocol"]
        self.assertEqual(evaluation.validate_protocol(protocol), protocol)
        for key, value in (("nms", 0.5), ("input_size", 640), ("threads", 8),
                           ("score_floor", 0.05), ("class_agnostic", True),
                           ("class_cutoffs", {"ball": 0.3})):
            changed = copy.deepcopy(protocol)
            changed[key] = value
            with self.assertRaises(ValueError):
                evaluation.validate_protocol(changed)

    def test_refuses_foreign_or_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "new"
            with self.assertRaises(ValueError):
                evaluation.create_output(path)
            with patch.object(evaluation, "OUTPUT", path):
                evaluation.create_output(path)
                with self.assertRaises(FileExistsError):
                    evaluation.create_output(path)

    def test_write_new_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.json"
            evaluation.write_new(path, {"frozen": True})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                evaluation.write_new(path, {"frozen": False})
            self.assertEqual(path.read_bytes(), before)

    def test_no_interpolation_and_real_cutoffs(self):
        sample = {"seconds": 1, "selected_decoder_index": 0}
        rows = [{"category": 0, "xyxy": [98, 80, 102, 84], "score": 0.19,
                 "passes_class_cutoff": False},
                {"category": 3, "xyxy": [90, 90, 110, 100], "score": 0.6,
                 "passes_class_cutoff": True}]
        records = [{"sample": sample, "retained_postprocess_ball_rim": rows}]
        self.assertEqual(evaluation.observed_path(records, 100), [])
        rows[0].update(score=0.21, passes_class_cutoff=True)
        result = evaluation.observed_path(records, 100)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["point"], [1, 100, 82, 90, 90, 110, 100])

    def test_observed_insertion_changes_only_centering_gate(self):
        coordinates = [
            [4422.933322222222, 1367.777587890625, 161.82415771484375,
             1295.0703125, 184.62060546875, 1355.6640625, 210.87860107421875],
            [4423.0333222222225, 1352.57470703125, 217.460205078125,
             1296.7637939453125, 186.64352416992188, 1355.9022216796875, 214.20474243164062],
            [4423.133322222222, 1336.5360107421875, 278.5990295410156,
             1291.3580322265625, 186.95596313476562, 1356.6351318359375, 216.73880004882812],
            [4423.233322222222, 1324.24853515625, 342.151611328125,
             1289.64697265625, 190.06771850585938, 1351.54052734375, 216.83908081054688],
        ]
        selected = [{"point": point, "ball_score": 0.8, "rim_score": 0.8} for point in coordinates]
        inserted = {"point": [4423.066655555555, 1348.6915283203125, 235.11195373535156,
                              1295.1812744140625, 187.92735290527344, 1356.3677978515625,
                              214.0308074951172], "ball_score": 0.8389244048561721,
                    "rim_score": 0.7821771908168955}
        untouched = copy.deepcopy(selected)
        before = evaluation.path_decision(selected, 4423.9)
        augmented = sorted([*selected, inserted], key=lambda point: point["point"][0])
        after = evaluation.path_decision(augmented, 4423.9)
        self.assertTrue(before["decide_result"]["made"])
        self.assertFalse(after["decide_result"]["made"])
        checks = after["first_under_net"]["primary_checks"]
        self.assertEqual([key for key, passed in checks.items() if not passed], ["centered_exit"])
        self.assertAlmostEqual(after["first_under_net"]["point"][1], 0.3745431330300854)
        self.assertEqual(selected, untouched)

    def test_tampered_frozen_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frame.png"
            path.write_bytes(b"original")
            record = evaluation.file_record(path)
            evaluation.checked_record(record)
            path.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                evaluation.checked_record(record)

    def test_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            actual = Path(temporary) / "actual"
            actual.mkdir()
            link = Path(temporary) / "linked"
            link.symlink_to(actual, target_is_directory=True)
            with patch.object(evaluation, "OUTPUT", link):
                with self.assertRaises(ValueError):
                    evaluation.create_output(link)


if __name__ == "__main__":
    unittest.main()
