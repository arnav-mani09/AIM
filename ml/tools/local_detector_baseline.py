"""Frozen, bounded CPU still-image agreement baseline; never reads old predictions."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import signal
import sys
import time
import traceback


ML = Path(__file__).resolve().parents[1]
CATEGORIES = {0: "ball", 1: "player", 2: "referee", 3: "rim"}
CUTOFFS = {"ball": 0.20, "player": 0.10, "referee": 0.35, "rim": 0.50}
LIMITATION = (
    "Agreement with existing annotations only, not adjudicated actual-world precision, "
    "recall or generalization. Menlo CURRENT44 is development/checkpoint-selection data, "
    "not an untouched holdout. Historical training membership is unknown. CPU float32 "
    "still images with YOLOX ValTransform are not full deployment GPU preprocessing, "
    "tracking or interpolation. Local checkpoint identity does not establish live weights."
)


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def file_record(path):
    path = Path(path).resolve()
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": digest(path)}


def write_new(path, payload):
    with Path(path).open("x") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")


def verify_manifest(manifest):
    for record in manifest["files"]:
        if file_record(record["path"]) != record:
            raise ValueError(f"Provenance changed: {record['path']}")


def validate_coco(coco):
    categories = {item["id"]: item["name"] for item in coco["categories"]}
    if categories != CATEGORIES or len(coco["categories"]) != len(CATEGORIES):
        raise ValueError("Category IDs/names must match the four-class worker mapping exactly")
    images = {image["id"]: image for image in coco["images"]}
    if len(images) != len(coco["images"]) or not images:
        raise ValueError("Image IDs must be unique and nonempty")
    for image in images.values():
        if type(image["id"]) is not int or any(type(image[key]) is not int or image[key] <= 0
                                              for key in ("width", "height")):
            raise ValueError("Invalid image ID or dimensions")
    annotation_ids = set()
    for annotation in coco["annotations"]:
        if annotation["id"] in annotation_ids:
            raise ValueError("Duplicate annotation ID")
        annotation_ids.add(annotation["id"])
        validate_box(annotation, images)
        if annotation.get("iscrowd", 0):
            raise ValueError("Crowd annotations require a different matching protocol")
    return images


def validate_box(box, images):
    if type(box["image_id"]) is not int or box["image_id"] not in images:
        raise ValueError(f"Unknown/foreign image ID: {box['image_id']}")
    if type(box["category_id"]) is not int or box["category_id"] not in CATEGORIES:
        raise ValueError(f"Unknown category ID: {box['category_id']}")
    coordinates = box["bbox"]
    if len(coordinates) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                         for value in coordinates) or min(coordinates[2:]) <= 0:
        raise ValueError("Invalid xywh box")


def validate_predictions(coco, predictions, processed_ids):
    images = validate_coco(coco)
    if len(processed_ids) != len(set(processed_ids)):
        raise ValueError("Duplicate processed image IDs")
    if any(type(image_id) is not int or image_id not in images for image_id in processed_ids):
        raise ValueError("Unknown/foreign processed image ID")
    processed = set(processed_ids)
    for prediction in predictions:
        validate_box(prediction, images)
        if prediction["image_id"] not in processed:
            raise ValueError("Prediction belongs to an unprocessed image")
        if not math.isfinite(prediction["score"]) or not 0 <= prediction["score"] <= 1:
            raise ValueError("Invalid prediction score")
    return {
        "processed_image_ids": processed_ids,
        "unprocessed_image_ids": [image_id for image_id in images if image_id not in processed],
        "zero_detection_image_ids": [image_id for image_id in processed_ids
                                     if not any(box["image_id"] == image_id for box in predictions)],
        "complete": len(processed_ids) == len(images),
    }


def evaluate(coco, predictions, processed_ids):
    from detector_report import IOU, match

    if IOU != 0.5:
        raise ValueError("Matching IoU changed")
    coverage = validate_predictions(coco, predictions, processed_ids)
    labels, predicted = defaultdict(list), defaultdict(list)
    for annotation in coco["annotations"]:
        if annotation["image_id"] in processed_ids:
            labels[annotation["image_id"]].append(annotation)
    for prediction in predictions:
        predicted[prediction["image_id"]].append(prediction)
    metrics, errors = {}, defaultdict(lambda: {"missed_annotations": [], "unmatched_predictions": []})
    for category_id, name in CATEGORIES.items():
        found, missed, wrong = match(labels, predicted, category_id, CUTOFFS[name])
        true_positive, false_negative, false_positive = len(found), len(missed), len(wrong)
        metrics[name] = {
            "cutoff": CUTOFFS[name], "matched": true_positive,
            "missed_annotations": false_negative, "unmatched_predictions": false_positive,
            "labels": true_positive + false_negative,
            "annotation_agreement_precision": true_positive / (true_positive + false_positive)
            if true_positive + false_positive else None,
            "annotation_agreement_recall": true_positive / (true_positive + false_negative)
            if true_positive + false_negative else None,
        }
        for annotation in missed:
            errors[annotation["image_id"]]["missed_annotations"].append(annotation)
        for prediction in wrong:
            errors[prediction["image_id"]]["unmatched_predictions"].append(prediction)
    images = {image["id"]: image for image in coco["images"]}
    ranked = sorted(errors, key=lambda image_id: (
        -sum(len(boxes) for boxes in errors[image_id].values()), image_id))[:12]
    review = [{"image": images[image_id], **errors[image_id]} for image_id in ranked]
    return {"coverage": coverage, "metrics": metrics, "limitations": LIMITATION}, review


def deadline_expired(signum, frame):
    raise TimeoutError("Local wall-time budget exhausted")


def run(args):
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    predictions, processed_ids, timings = [], [], []
    manifest = None
    manifest_sha = None
    coco = None
    status, failure = "failed", None
    signal.signal(signal.SIGALRM, deadline_expired)
    signal.setitimer(signal.ITIMER_REAL, args.seconds)
    try:
        import cv2
        import numpy as np
        import torch
        import torchvision
        import yolox
        from yolox.data.data_augment import ValTransform
        from yolox.exp import get_exp
        from yolox.utils import postprocess

        torch.set_num_threads(args.threads)
        torch.set_num_interop_threads(1)
        cv2.setNumThreads(1)
        torch.manual_seed(0)
        annotation_bytes = args.annotations.read_bytes()
        coco = json.loads(annotation_bytes)
        images = validate_coco(coco)
        if len(images) != 44:
            raise ValueError(f"CURRENT44 expected exactly 44 images; got {len(images)}")
        with (args.output / "annotations.json").open("xb") as handle:
            handle.write(annotation_bytes)
        (args.output / "annotations.json").chmod(0o444)
        image_records = []
        for image in images.values():
            path = (args.images / image["file_name"]).resolve()
            if not path.is_relative_to(args.images.resolve()):
                raise ValueError("Image path escapes image directory")
            decoded = cv2.imread(str(path))
            if decoded is None or decoded.shape[:2] != (image["height"], image["width"]):
                raise ValueError(f"Image dimension/decode mismatch: {path}")
            image_records.append({**image, **file_record(path)})
        sources = [Path(__file__), ML / "tools/detector_report.py", ML / "train_modal.py",
                   ML / "tools/prelabel.py", ML.parent / "worker/vision.py"]
        sources += sorted(Path(yolox.__file__).parent.rglob("*.py"))
        versions = {name: importlib.metadata.version(name) for name in
                    ("torch", "torchvision", "numpy", "yolox")}
        versions["cv2"] = cv2.__version__
        manifest = {
            "created_utc": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
            "checkpoint": file_record(args.checkpoint),
            "annotations": file_record(args.annotations), "images": image_records,
            "categories": coco["categories"], "dependencies": versions,
            "runtime": {"python": sys.version, "platform": platform.platform(),
                        "torch": torch.__version__, "torchvision": torchvision.__version__,
                        "numpy": np.__version__, "executable": sys.executable},
            "protocol": {
                "device": "cpu", "dtype": "float32", "threads": args.threads,
                "interop_threads": 1, "opencv_threads": 1, "seed": 0,
                "budget_seconds": args.seconds, "max_images": args.max_images,
                "image_order": list(images), "input_size": args.input_size,
                "architecture": "yolox-m", "num_classes": 4,
                "transform": "ValTransform(legacy=False), BGR uint8, bilinear resize, top-left pad 114, CHW float32",
                "box_restore": "divide xyxy by min(input_size/height,input_size/width), then xywh; no clipping",
                "score": "objectness * class confidence", "score_floor": 0.1,
                "class_cutoffs": CUTOFFS, "nms": 0.45, "class_agnostic": False,
                "matching": "detector_report.match greedy confidence-first per image/class, IoU >= 0.5",
                "serialization": "torch.load(map_location='cpu', weights_only=True); no unsafe fallback",
                "population": "CURRENT44 Menlo development/checkpoint-selection annotation snapshot",
            },
            "limitations": LIMITATION,
            "files": [file_record(path) for path in sources] +
                     [file_record(args.checkpoint), file_record(args.annotations),
                      file_record(args.output / "annotations.json")] +
                     [file_record(record["path"]) for record in image_records],
        }
        manifest_path = args.output / "manifest.json"
        write_new(manifest_path, manifest)
        manifest_path.chmod(0o444)
        manifest_sha = digest(manifest_path)
        print(f"Manifest frozen: {manifest_sha}", flush=True)
        verify_manifest(manifest)
        state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
        if state["num_classes"] != 4 or state["input_size"] != args.input_size:
            raise ValueError("Checkpoint metadata disagrees with frozen architecture/input size")
        experiment = get_exp(None, "yolox-m")
        experiment.num_classes = 4
        model = experiment.get_model()
        model.load_state_dict(state["model"], strict=True)
        model = model.cpu().float().eval()
        transform = ValTransform(legacy=False)
        for image in list(images.values())[:args.max_images]:
            frame_started = time.monotonic()
            decoded = cv2.imread(str(args.images / image["file_name"]))
            if decoded is None or decoded.shape[:2] != (image["height"], image["width"]):
                raise ValueError("Image dimensions changed before inference")
            ratio = min(args.input_size / image["height"], args.input_size / image["width"])
            tensor, _ = transform(decoded, None, (args.input_size, args.input_size))
            with torch.inference_mode():
                output = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()),
                                     4, conf_thre=0.1, nms_thre=0.45, class_agnostic=False)[0]
            frame_predictions = []
            for left, top, right, bottom, objectness, confidence, category in (
                    [] if output is None else output.cpu().tolist()):
                if category != int(category) or int(category) not in CATEGORIES:
                    raise ValueError("Unknown model category")
                category_id = int(category)
                score = objectness * confidence
                if score >= CUTOFFS[CATEGORIES[category_id]]:
                    frame_predictions.append({
                        "image_id": image["id"], "category_id": category_id, "score": score,
                        "bbox": [left / ratio, top / ratio, (right - left) / ratio, (bottom - top) / ratio],
                    })
            validate_predictions(coco, frame_predictions, [image["id"]])
            predictions.extend(frame_predictions)
            processed_ids.append(image["id"])
            elapsed = time.monotonic() - frame_started
            timings.append({"image_id": image["id"], "seconds": elapsed})
            print(f"Processed {len(processed_ids)}/44 id={image['id']} boxes={len(frame_predictions)} seconds={elapsed:.3f}", flush=True)
        status = "complete" if len(processed_ids) == len(images) else "partial"
    except Exception as exception:
        status = "partial" if processed_ids else "failed"
        failure = {"type": type(exception).__name__, "message": str(exception),
                   "traceback": traceback.format_exc()}
        print(failure["traceback"], file=sys.stderr, flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    unchanged = False
    if manifest is not None:
        try:
            verify_manifest(manifest)
            if digest(args.output / "manifest.json") != manifest_sha:
                raise ValueError("Frozen manifest bytes changed")
            unchanged = True
        except Exception as exception:
            status = "invalid_provenance"
            failure = {"type": type(exception).__name__, "message": str(exception)}
    write_new(args.output / "predictions.json", predictions)
    coverage = validate_predictions(coco, predictions, processed_ids) if coco else None
    report = {
        "status": status, "failure": failure, "manifest_sha256": manifest_sha,
        "provenance_verified_after": unchanged, "coverage": coverage,
        "runtime_seconds": time.monotonic() - started, "image_timings": timings,
        "command": [sys.executable, *sys.argv], "limitations": LIMITATION,
    }
    if processed_ids and unchanged:
        agreement, review = evaluate(coco, predictions, processed_ids)
        report.update(agreement)
        write_new(args.output / "error_review.json", {
            "selection": "Up to 12 frames ranked by total missed annotation + unmatched prediction count; no confidence masking",
            "interpretation": "Unmatched predictions may be annotation omissions, not proven false objects",
            "frames": review,
        })
    write_new(args.output / "result.json", report)
    write_new(args.output / "processed_images.json", {"manifest_sha256": manifest_sha, "coverage": coverage})
    print(json.dumps(report, indent=2), flush=True)
    return 0 if status == "complete" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=ML / "data/dataset/annotations/instances_val2017.json")
    parser.add_argument("--images", type=Path, default=ML / "data/dataset/val2017")
    parser.add_argument("--checkpoint", type=Path, default=ML / "runs/v4/aim_yolox_m.pth")
    parser.add_argument("--output", type=Path, default=ML / "data/labels/local_detector_baseline_20261112")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=540)
    parser.add_argument("--max-images", type=int, default=44)
    parser.add_argument("--input-size", type=int, default=960)
    args = parser.parse_args()
    if not 1 <= args.threads <= 8 or not 1 <= args.seconds <= 600 or not 1 <= args.max_images <= 44:
        parser.error("Require threads 1..8, seconds 1..600 and max-images 1..44")
    if args.input_size != 960:
        parser.error("This frozen baseline protocol requires input size 960")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
