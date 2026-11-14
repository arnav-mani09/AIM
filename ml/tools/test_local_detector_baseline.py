"""Standard-library-only checks for baseline safety and coverage contracts."""

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from local_detector_baseline import (
    CATEGORIES, file_record, run, validate_coco, validate_predictions, verify_manifest, write_new,
)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.coco = {
            "categories": [{"id": category_id, "name": name} for category_id, name in CATEGORIES.items()],
            "images": [{"id": image_id, "width": 100, "height": 80} for image_id in (802, 803)],
            "annotations": [{"id": 1, "image_id": 802, "category_id": 0, "bbox": [1, 2, 3, 4]}],
        }
        self.prediction = {"image_id": 802, "category_id": 0, "bbox": [1, 2, 3, 4], "score": 0.2}

    def test_provenance_detects_same_size_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source"
            path.write_bytes(b"abc")
            manifest = {"files": [file_record(path)]}
            verify_manifest(manifest)
            path.write_bytes(b"abd")
            with self.assertRaisesRegex(ValueError, "Provenance changed"):
                verify_manifest(manifest)

    def test_provenance_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source"
            path.write_bytes(b"abc")
            manifest = {"files": [file_record(path)]}
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                verify_manifest(manifest)

    def test_zero_detection_is_not_unprocessed(self):
        coverage = validate_predictions(self.coco, [], [802])
        self.assertEqual(coverage["zero_detection_image_ids"], [802])
        self.assertEqual(coverage["unprocessed_image_ids"], [803])
        self.assertFalse(coverage["complete"])
        self.assertTrue(validate_predictions(self.coco, [], [802, 803])["complete"])

    def test_foreign_prediction_is_rejected(self):
        self.prediction["image_id"] = 999
        with self.assertRaisesRegex(ValueError, "Unknown/foreign"):
            validate_predictions(self.coco, [self.prediction], [802])

    def test_prediction_on_unprocessed_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unprocessed"):
            validate_predictions(self.coco, [self.prediction], [803])

    def test_foreign_processed_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown/foreign"):
            validate_predictions(self.coco, [], [999])

    def test_duplicate_processed_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_predictions(self.coco, [], [802, 802])

    def test_unknown_category_rejected(self):
        self.prediction["category_id"] = 9
        with self.assertRaisesRegex(ValueError, "Unknown category"):
            validate_predictions(self.coco, [self.prediction], [802])

    def test_annotation_foreign_id_rejected(self):
        self.coco["annotations"][0]["image_id"] = 999
        with self.assertRaisesRegex(ValueError, "Unknown/foreign"):
            validate_coco(self.coco)

    def test_category_mapping_and_image_sizes_exact(self):
        modified = copy.deepcopy(self.coco)
        modified["categories"][0]["name"] = "other"
        with self.assertRaisesRegex(ValueError, "Category"):
            validate_coco(modified)
        self.coco["images"][0]["width"] = 0
        with self.assertRaisesRegex(ValueError, "dimensions"):
            validate_coco(self.coco)

    def test_overwrite_refused_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            write_new(path, {"original": True})
            with self.assertRaises(FileExistsError):
                write_new(path, {"replacement": True})
            self.assertEqual(json.loads(path.read_text()), {"original": True})

    def test_existing_run_directory_refused_before_loading_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                run(SimpleNamespace(output=Path(directory)))
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
