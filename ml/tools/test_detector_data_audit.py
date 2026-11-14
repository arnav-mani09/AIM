import copy
import math
from pathlib import Path
import struct
import tempfile
import unittest

from detector_data_audit import CLASSES, candidates, coverage, export_review_frames, jpeg_size, leakage, prediction_inventory


class DetectorDataAuditTests(unittest.TestCase):
    def setUp(self):
        self.coco = {
            "images": [{"id": 1, "file_name": "game__t00001.jpg", "width": 1920, "height": 1080}],
            "categories": [{"id": category, "name": name} for category, name in CLASSES.items()],
            "annotations": [{"id": 1, "image_id": 1, "category_id": 0, "bbox": [10, 10, 12, 12]}],
        }
        self.prediction = {"image_id": 1, "category_id": 0, "bbox": [10, 10, 12, 12], "score": 0.9}

    def test_id_match_does_not_prove_provenance(self):
        result = prediction_inventory([self.prediction], self.coco)
        self.assertEqual(result["overlapping_current_val_ids"], 1)
        self.assertEqual(result["provenance_status"], "unknown")
        self.assertTrue(all(value is None for value in result["per_class_metrics"].values()))

    def test_foreign_predictions_not_silently_filtered(self):
        prediction = dict(self.prediction, image_id=99)
        result = prediction_inventory([prediction], self.coco)
        self.assertEqual(result["foreign_image_ids"], [99])
        self.assertEqual(result["val_ids_without_predictions_not_proven_unscored"], [1])

    def test_invalid_predictions(self):
        for prediction in [dict(self.prediction, score=math.nan), dict(self.prediction, category_id=9), dict(self.prediction, bbox=[0, 0, -1, 5])]:
            self.assertEqual(prediction_inventory([prediction], self.coco)["invalid_prediction_indices"], [0])

    def test_coverage_sizes_and_missing_labels_are_not_recall(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "game__t00001.jpg"
            path.write_bytes(b"\xff\xd8\xff\xc0" + struct.pack(">HBHH", 7, 8, 1080, 1920))
            self.assertEqual(jpeg_size(path), (1920, 1080))
            result = coverage(self.coco, Path(temporary))
        self.assertEqual(result["validation_errors"], [])
        self.assertEqual(result["classes"]["ball"]["short_side_at_960_lt_8"], 1)
        self.assertEqual(result["classes"]["player"]["images_without_label_not_proven_negative"], 1)

    def test_duplicate_and_dangling_annotations_rejected(self):
        coco = copy.deepcopy(self.coco)
        coco["images"].append(dict(coco["images"][0]))
        coco["annotations"].append(dict(coco["annotations"][0], image_id=99))
        with tempfile.TemporaryDirectory() as temporary:
            errors = coverage(coco, Path(temporary))["validation_errors"]
        self.assertIn("duplicate image IDs", errors)
        self.assertIn("duplicate annotation IDs", errors)
        self.assertTrue(any("unknown image/category" in error for error in errors))

    def test_leakage_uses_games_and_bytes(self):
        split = {"games": {"game": 1}, "image_manifest": [{"id": 1, "file_name": "game__t1.jpg", "sha256": "abc"}]}
        result = leakage(split, split)
        self.assertEqual(result["shared_games"], ["game"])
        self.assertEqual(result["val_images_identical_to_train"], ["game__t1.jpg"])

    def test_candidates_bounded_balanced_and_not_labels(self):
        event = {"bucket": "not found", "truth": {"seen_old": 20, "seen_new": 21}}
        report = {"games": {"a": {"events": [event] * 4}, "b": {"events": [event] * 4}}}
        result = candidates(report, 3)
        self.assertEqual([item["game"] for item in result], ["a", "b", "a"])
        self.assertEqual(result[0]["window_seconds"], [8, 23])
        self.assertIn("not_a_detector_error", result[0]["status"])
        self.assertEqual(candidates(report, 0), [])

    def test_truncated_jpeg_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jpg"
            path.write_bytes(b"\xff\xd8\xff\xc0\x00")
            with self.assertRaises(ValueError):
                jpeg_size(path)

    def test_export_only_existing_bounded_review_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            output = Path(temporary) / "output"
            source.mkdir()
            output.mkdir()
            (source / self.coco["images"][0]["file_name"]).write_bytes(b"original frame")
            records = export_review_frames(self.coco, source, output, [1])
            self.assertEqual(records[0]["image_id"], 1)
            self.assertEqual((output / records[0]["file_name"]).read_bytes(), b"original frame")
            for image_ids in ([99], [1, 1], list(range(9))):
                with self.assertRaises(ValueError):
                    export_review_frames(self.coco, source, output, image_ids)


if __name__ == "__main__":
    unittest.main()
