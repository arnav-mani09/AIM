"""Offline coverage/provenance inventory; never infer labels or detector accuracy."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import struct
import subprocess


CLASSES = {0: "ball", 1: "player", 2: "referee", 3: "rim"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jpeg_size(path):
    with Path(path).open("rb") as source:
        if source.read(2) != b"\xff\xd8":
            raise ValueError("not JPEG")
        while True:
            marker = source.read(1)
            if not marker:
                raise ValueError("JPEG has no size marker")
            if marker != b"\xff":
                continue
            while marker == b"\xff":
                marker = source.read(1)
            if marker in (b"\xd9", b"\xda", b""):
                raise ValueError("JPEG has no size marker")
            if marker == b"\x00" or marker == b"\x01" or b"\xd0" <= marker <= b"\xd7":
                continue
            raw = source.read(2)
            if len(raw) != 2:
                raise ValueError("truncated JPEG")
            length = struct.unpack(">H", raw)[0]
            if length < 2:
                raise ValueError("invalid JPEG marker length")
            if marker[0] in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                raw = source.read(5)
                if len(raw) != 5:
                    raise ValueError("truncated JPEG size")
                _, height, width = struct.unpack(">BHH", raw)
                return width, height
            source.seek(length - 2, 1)


def game_of(image):
    return image["file_name"].split("__", 1)[0]


def coverage(coco, image_dir):
    images = {image["id"]: image for image in coco["images"]}
    errors = []
    if len(images) != len(coco["images"]):
        errors.append("duplicate image IDs")
    if {item["id"]: item["name"] for item in coco["categories"]} != CLASSES:
        errors.append("category mapping differs from runtime")
    annotation_ids = [item["id"] for item in coco["annotations"]]
    if len(set(annotation_ids)) != len(annotation_ids):
        errors.append("duplicate annotation IDs")
    by_image = defaultdict(Counter)
    sizes = defaultdict(list)
    for annotation in coco["annotations"]:
        image = images.get(annotation["image_id"])
        category = annotation["category_id"]
        box = annotation["bbox"]
        if image is None or category not in CLASSES:
            errors.append(f"annotation {annotation['id']}: unknown image/category")
            continue
        if len(box) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in box) or min(box[2:]) <= 0:
            errors.append(f"annotation {annotation['id']}: invalid bbox")
            continue
        left, top, width, height = box
        if left < -0.01 or top < -0.01 or left + width > image["width"] + 0.01 or top + height > image["height"] + 0.01:
            errors.append(f"annotation {annotation['id']}: out-of-bounds bbox")
        if annotation.get("iscrowd", 0):
            errors.append(f"annotation {annotation['id']}: crowd needs evaluator handling")
        by_image[image["id"]][category] += 1
        ratio = 960 / max(image["width"], image["height"])
        sizes[category].append((width * height, min(width, height) * ratio))
    image_records = []
    for image in coco["images"]:
        path = image_dir / image["file_name"]
        record = dict(image)
        try:
            record["sha256"] = sha256(path)
            record["actual_size"] = list(jpeg_size(path))
            if record["actual_size"] != [image["width"], image["height"]]:
                errors.append(f"image {image['id']}: size mismatch")
        except (OSError, ValueError) as error:
            errors.append(f"image {image['id']}: {error}")
        image_records.append(record)
    classes = {}
    for category, name in CLASSES.items():
        values = sizes[category]
        classes[name] = {
            "labels": len(values),
            "images_with_label": sum(bool(by_image[image_id][category]) for image_id in images),
            "images_without_label_not_proven_negative": sum(not by_image[image_id][category] for image_id in images),
            "original_area_lt_32_squared": sum(area < 1024 for area, _ in values),
            "short_side_at_960_lt_8": sum(side < 8 for _, side in values),
            "short_side_at_960_lt_16": sum(side < 16 for _, side in values),
        }
    return {
        "images": len(images), "games": dict(Counter(game_of(image) for image in images.values())),
        "classes": classes, "validation_errors": errors, "image_manifest": image_records,
    }


def prediction_inventory(predictions, coco):
    image_ids = {image["id"] for image in coco["images"]}
    predicted_ids = {prediction["image_id"] for prediction in predictions}
    errors = []
    for index, prediction in enumerate(predictions):
        box = prediction.get("bbox", [])
        score = prediction.get("score")
        if prediction.get("category_id") not in CLASSES or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1 or len(box) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in box) or min(box[2:]) <= 0:
            errors.append(index)
    return {
        "boxes": len(predictions), "image_ids_with_predictions": len(predicted_ids),
        "overlapping_current_val_ids": len(predicted_ids & image_ids),
        "foreign_image_ids": sorted(predicted_ids - image_ids),
        "val_ids_without_predictions_not_proven_unscored": sorted(image_ids - predicted_ids),
        "invalid_prediction_indices": errors,
        "provenance_status": "unknown",
        "reason": "Bare predictions contain no annotation, image, training split, or checkpoint hashes. ID overlap alone cannot bind provenance.",
        "per_class_metrics": {name: None for name in CLASSES.values()},
    }


def leakage(train, val):
    train_images, val_images = train["image_manifest"], val["image_manifest"]
    train_hashes = {image["sha256"] for image in train_images if "sha256" in image}
    return {
        "shared_games": sorted(set(train["games"]) & set(val["games"])),
        "shared_image_ids": sorted({image["id"] for image in train_images} & {image["id"] for image in val_images}),
        "shared_filenames": sorted({image["file_name"] for image in train_images} & {image["file_name"] for image in val_images}),
        "val_images_identical_to_train": [image["file_name"] for image in val_images if image.get("sha256") in train_hashes],
        "historical_training_leakage": "unknown_without_run_training_manifests",
    }


def candidates(report, limit):
    queues = []
    for game, details in sorted(report["games"].items()):
        queue = []
        for index, event in enumerate(details["events"]):
            if event.get("bucket") != "not found" or not event.get("truth"):
                continue
            truth = event["truth"]
            queue.append({
                "game": game, "source_event_index": index,
                "source_bucket": event["bucket"], "score_change": truth,
                "window_seconds": [max(0, truth["seen_old"] - 12), truth["seen_new"] + 2],
                "status": "unreviewed_not_a_detector_error_or_training_label",
                "review": "Inspect ball visibility/occlusion, player/referee boxes, rim and score delay; downstream miss does not establish detector failure.",
            })
        queues.append(queue)
    selected = []
    while any(queues) and len(selected) < limit:
        for queue in queues:
            if queue and len(selected) < limit:
                selected.append(queue.pop(0))
    return selected


def export_review_frames(coco, image_dir, output, image_ids):
    images = {image["id"]: image for image in coco["images"]}
    if len(image_ids) > 8 or len(set(image_ids)) != len(image_ids) or any(image_id not in images for image_id in image_ids):
        raise ValueError("review IDs must be unique existing validation IDs, at most eight")
    records = []
    for image_id in image_ids:
        image = images[image_id]
        source = image_dir / image["file_name"]
        destination = output / Path(image["file_name"]).name
        shutil.copyfile(source, destination)
        records.append({"image_id": image_id, "file_name": image["file_name"], "sha256": sha256(destination),
                        "status": "unreviewed_current_annotation_frame_not_a_certified_detector_error"})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument("--candidate-limit", type=int, default=12)
    parser.add_argument("--review-image-id", type=int, action="append", default=[])
    args = parser.parse_args()
    if not 0 <= args.candidate_limit <= 24:
        parser.error("candidate limit must be between 0 and 24")
    root = args.root.resolve()
    private = root / "ml/data/labels/detector_audit_20261112"
    output = args.output.resolve()
    if output != private and private not in output.parents:
        parser.error("output must stay inside private ml/data/labels/detector_audit_20261112")
    dataset = root / "ml/data/dataset"
    sources = {}

    def load(path):
        sources[str(path.relative_to(root))] = sha256(path)
        return json.loads(path.read_text())

    annotations = {split: load(dataset / f"annotations/instances_{split}.json") for split in ("train2017", "val2017")}
    splits = {split: coverage(coco, dataset / split) for split, coco in annotations.items()}
    runs = {}
    for path in sorted((root / "ml/runs").glob("*/val_predictions.json")):
        runs[path.parent.name] = prediction_inventory(load(path), annotations["val2017"])
        for name in ("aim_yolox_m.pth", "train_log.txt", "summary.json", "report.json"):
            source = path.parent / name
            if source.exists():
                sources[str(source.relative_to(root))] = sha256(source)
    for relative in ("ml/tools/detector_data_audit.py", "ml/tools/test_detector_data_audit.py", "ml/tools/detector_report.py", "ml/tools/export_dataset.py", "ml/train_modal.py", "ml/classes.yaml", "ml/games.yaml", "ml/exclude_frames.yaml", "worker/vision.py", "worker/film_worker.py", "ml/data/weights/yolox_m.pth"):
        path = root / relative
        if path.exists():
            sources[relative] = sha256(path)
    selected = []
    if args.failure_report:
        selected = candidates(load(args.failure_report.resolve()), args.candidate_limit)
    output.mkdir(parents=True, exist_ok=True)
    review_frames = export_review_frames(annotations["val2017"], dataset / "val2017", output, args.review_image_id)
    result = {
        "schema_version": 1, "python": platform.python_version(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "sources_sha256": sources, "splits": splits, "leakage": leakage(splits["train2017"], splits["val2017"]),
        "runs": runs, "full_game_unknown_detection_recall": None,
        "candidate_source": str(args.failure_report) if args.failure_report else None,
        "candidates": selected, "review_frames": review_frames,
    }
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {output / 'audit.json'}; {len(selected)} unreviewed windows; no detector metrics asserted")


if __name__ == "__main__":
    main()
