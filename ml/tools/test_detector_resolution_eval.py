"""Standard-library guard tests; no model execution or dependency mocking."""

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from detector_resolution_eval import (
    digest, file_record, run, validate_comparability, validate_size, verify_frozen, write_new,
)


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "protocol": {"input_size": 960, "budget_seconds": 540, "threads": 4,
                         "class_cutoffs": {"ball": 0.2}, "image_order": [802, 803]},
            "checkpoint": {"sha256": "checkpoint"}, "images": [{"id": 802}, {"id": 803}],
            "categories": [{"id": 0, "name": "ball"}], "dependencies": {"torch": "local"},
            "annotations": {"sha256": "annotations"},
        }
        self.variant = copy.deepcopy(self.baseline)
        self.variant["protocol"].update(input_size=1280, budget_seconds=180)

    def test_exact_size_and_stride_bounds(self):
        self.assertEqual(validate_size(1280), 1280)
        for size in (0, 319, 1290, 1312, 1279, 960, 1280.0, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_size(size)

    def test_only_resolution_and_budget_may_differ(self):
        validate_comparability(self.baseline, self.variant)
        for key, value in (("threads", 8), ("image_order", [803, 802]),
                           ("class_cutoffs", {"ball": 0.1}), ("nms", 0.5)):
            variant = copy.deepcopy(self.variant)
            variant["protocol"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_comparability(self.baseline, variant)

    def test_checkpoint_images_categories_dependencies_and_labels_bound(self):
        for key in ("checkpoint", "images", "categories", "dependencies", "annotations"):
            variant = copy.deepcopy(self.variant)
            variant[key] = {"sha256": "changed"}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_comparability(self.baseline, variant)

    def test_same_size_source_mutation_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, manifest = Path(directory) / "source", Path(directory) / "manifest.json"
            source.write_bytes(b"abc")
            write_new(manifest, {"files": [file_record(source)]})
            expected = digest(manifest)
            verify_frozen(manifest, expected)
            source.write_bytes(b"abd")
            with self.assertRaisesRegex(ValueError, "Provenance changed"):
                verify_frozen(manifest, expected)

    def test_manifest_mutation_detected_even_if_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"files": []}))
            expected = digest(manifest)
            manifest.write_text(json.dumps({"files": [], "changed": True}))
            with self.assertRaisesRegex(ValueError, "manifest bytes changed"):
                verify_frozen(manifest, expected)

    def test_existing_output_refused_before_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                run(SimpleNamespace(input_size=1280, output=Path(directory)))
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
