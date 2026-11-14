import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import supervision as sv

import tracking_raw_capture as capture


class RawCaptureTests(unittest.TestCase):
    def payload(self, score=.9):
        return capture.pack_detections(sv.Detections(
            xyxy=np.array([[10., 10., 30., 60.]]), confidence=np.array([score]),
            class_id=np.array([1], dtype=int)))

    def test_serialization(self):
        payload = json.loads(json.dumps(self.payload()))
        self.assertEqual(capture.pack_detections(capture.unpack_detections(payload)), payload)
        self.assertIsNone(payload["arrays"]["tracker_id"])

    def test_empty_shapes_and_frames(self):
        empty = sv.Detections(xyxy=np.empty((0, 4)), confidence=np.empty(0), class_id=np.empty(0, dtype=int))
        packed = capture.pack_detections(empty)
        self.assertEqual(capture.unpack_detections(packed).xyxy.shape, (0, 4))
        records = [{"sample_index": index, "window": "test", "pts": index,
                    "detections": packed} for index in range(3)]
        result = capture.replay_records(records, [])
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["detections"]["arrays"]["xyxy"]["shape"], [0, 4])

    def test_actual_parity_and_distinct_input_output(self):
        records = [{"sample_index": index, "window": "test", "pts": index,
                    "detections": self.payload(score)} for index, score in enumerate((.4, .9, .9))]
        expected = capture.replay_records(records, [])
        self.assertEqual(len(records[0]["detections"]["arrays"]["confidence"]["values"]), 1)
        self.assertEqual(expected[0]["detections"]["arrays"]["confidence"]["values"], [])
        self.assertEqual(capture.replay_records(json.loads(json.dumps(records)), expected), expected)
        wrong = copy.deepcopy(expected)
        wrong[-1]["pts"] = -1
        with self.assertRaises(ValueError):
            capture.replay_records(records, wrong)

    def test_pts_selection_and_packet_alignment(self):
        frames = [{"pts": str(index), "best_effort_timestamp": str(index),
                   "pkt_pos": str(index+100), "pict_type": "P"} for index in range(181)]
        selected = capture.select_frames(frames, "1/30", "0", "6")
        self.assertEqual([int(frame["pts"]) for _, frame in selected], list(range(0, 181, 3)))
        packets = [{"pts": frame["pts"], "pos": frame["pkt_pos"]} for frame in frames]
        aligned = capture.align_frames([frame for _, frame in selected], packets, "1/30", "0", "6")
        self.assertEqual(aligned[-1]["source_video_sample_index"], 180)
        packets[0]["pts"] = "1"
        with self.assertRaises(ValueError):
            capture.align_frames([frame for _, frame in selected], packets, "1/30", "0", "6")

    def test_pts_tie_and_bounds(self):
        frames = [{"pts": str(index)} for index in range(-1, 123)]
        selected = capture.select_frames(frames, "1/20", "0", "6")
        self.assertEqual(len(selected), 61)
        self.assertTrue(all(0 <= int(frame["pts"]) <= 120 for _, frame in selected))
        sparse = capture.select_frames([{"pts": "0"}, {"pts": "2"}], "1/10", "0", "6")
        self.assertEqual(sparse[0][1]["pts"], "0")

    def test_torso_clipping_empty_and_native(self):
        image = np.full((100, 200, 3), 128, dtype=np.uint8)
        crop = capture.torso_lab(image, [0., 0., 200., 100.])
        self.assertEqual(crop["crop_xyxy"], [50, 20, 150, 50])
        self.assertEqual(crop["pixels"], 3000)
        clipped = capture.torso_lab(image, [-200., -100., 400., 200.])
        self.assertTrue(clipped["clipped"])
        self.assertEqual(capture.torso_lab(image, [-200., 0., -100., 20.])["status"], "empty_crop")
        self.assertEqual(capture.torso_lab(image, [1., 1., 1., 4.])["status"], "invalid_box")

    def test_provenance_detects_same_size_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source"
            path.write_text("first")
            record = capture.file_record(path)
            capture.checked_record(record)
            path.write_text("other")
            with self.assertRaises(ValueError):
                capture.checked_record(record)

    def test_partial_truncated_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text('{"sample_index":0}\n{"sample_')
            self.assertEqual(capture.read_lines(path), [{"sample_index": 0}])


if __name__ == "__main__":
    unittest.main()
