"""One frozen 1280-input CPU development-agreement experiment against CURRENT44."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import signal
import sys
import time
import traceback

from local_detector_baseline import (
    CATEGORIES, CUTOFFS, LIMITATION, ML, deadline_expired, digest, evaluate,
    file_record, validate_coco, validate_predictions, verify_manifest, write_new,
)


BASELINE_SHA = "4b8991eb63c17edba2a2647bdf62399b65873e843703ba116c0d7398723355c2"
DEFAULT_BASELINE = ML / "data/labels/local_detector_baseline_20261112"
DEFAULT_OUTPUT = ML / "data/labels/detector_resolution_20261112"


def validate_size(size):
    if type(size) is not int or not 320 <= size <= 1280 or size % 32:
        raise ValueError("Input size must be an integer multiple of 32 within 320..1280")
    if size != 1280:
        raise ValueError("This single controlled experiment requires input size 1280")
    return size


def validate_comparability(baseline, variant):
    expected = dict(baseline["protocol"], input_size=1280, budget_seconds=180)
    if variant["protocol"] != expected:
        raise ValueError("Protocol drift beyond explicit resolution/budget differences")
    for key in ("checkpoint", "images", "categories", "dependencies"):
        if baseline[key] != variant[key]:
            raise ValueError(f"Incomparable {key}")
    if baseline["annotations"]["sha256"] != variant["annotations"]["sha256"]:
        raise ValueError("Incomparable annotation bytes")
    validate_size(variant["protocol"]["input_size"])


def verify_frozen(path, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError(f"Frozen manifest bytes changed: {path}")
    manifest = json.loads(path.read_text())
    verify_manifest(manifest)
    return manifest


def comparison(coco, baseline_predictions, predictions, processed_ids):
    from detector_report import match

    baseline_subset = [item for item in baseline_predictions if item["image_id"] in processed_ids]
    baseline_agreement, _ = evaluate(coco, baseline_subset, processed_ids)
    variant_agreement, _ = evaluate(coco, predictions, processed_ids)
    labels = defaultdict(list)
    for annotation in coco["annotations"]:
        if annotation["image_id"] in processed_ids:
            labels[annotation["image_id"]].append(annotation)
    grouped = []
    for population in (baseline_subset, predictions):
        groups = defaultdict(list)
        for item in population:
            groups[item["image_id"]].append(item)
        grouped.append(groups)
    changes, ball_outcomes = {}, []
    for category_id, name in CATEGORIES.items():
        matched_sets, missed_sets, unmatched = [], [], []
        for groups in grouped:
            _, missed, wrong = match(labels, groups, category_id, CUTOFFS[name])
            missed_ids = {item["id"] for item in missed}
            matched_sets.append({item["id"] for boxes in labels.values() for item in boxes
                                 if item["category_id"] == category_id} - missed_ids)
            missed_sets.append(missed_ids)
            unmatched.append(sorted(wrong, key=lambda item: (item["image_id"], -item["score"])))
        changes[name] = {
            "newly_matched_annotation_ids": sorted(matched_sets[1] - matched_sets[0]),
            "lost_matched_annotation_ids": sorted(matched_sets[0] - matched_sets[1]),
            "baseline_unmatched_predictions": unmatched[0],
            "variant_unmatched_predictions": unmatched[1],
            "unmatched_count_delta": len(unmatched[1]) - len(unmatched[0]),
        }
        if category_id == 0:
            ball_outcomes = [{"annotation_id": item["id"], "image_id": item["image_id"],
                              "bbox": item["bbox"],
                              "variant_outcome": "matched" if item["id"] in matched_sets[1] else "missed"}
                             for item in coco["annotations"] if item["id"] in missed_sets[0]]
    return {"processed_image_ids": processed_ids, "complete": variant_agreement["coverage"]["complete"],
            "baseline_same_subset_metrics": baseline_agreement["metrics"],
            "variant_same_subset_metrics": variant_agreement["metrics"],
            "changes": changes, "baseline_missed_ball_outcomes_on_subset": ball_outcomes}


def run(args):
    validate_size(args.input_size)
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    predictions, processed_ids, timings = [], [], []
    manifest_sha, coco, manifest = None, None, None
    status, failure = "failed", None
    previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
    signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        baseline_path = args.baseline / "manifest.json"
        baseline = verify_frozen(baseline_path, BASELINE_SHA)
        baseline_result = json.loads((args.baseline / "result.json").read_text())
        baseline_predictions = json.loads((args.baseline / "predictions.json").read_text())
        if (baseline_result["status"] != "complete" or
                baseline_result["manifest_sha256"] != BASELINE_SHA or
                not baseline_result["provenance_verified_after"]):
            raise ValueError("Baseline must be complete with verified pinned provenance")
        annotation_path = args.baseline / "annotations.json"
        annotation_bytes = annotation_path.read_bytes()
        coco = json.loads(annotation_bytes)
        images = validate_coco(coco)
        if len(images) != 44 or list(images) != baseline["protocol"]["image_order"]:
            raise ValueError("Expected exactly the frozen ordered CURRENT44 images")
        reproduced, _ = evaluate(coco, baseline_predictions, list(images))
        if (reproduced["metrics"] != baseline_result["metrics"] or
                reproduced["coverage"] != baseline_result["coverage"]):
            raise ValueError("Baseline saved metrics/coverage do not reproduce")
        import cv2
        import numpy as np
        import torch
        import torchvision
        import yolox
        from yolox.data.data_augment import ValTransform
        from yolox.exp import get_exp
        from yolox.utils import postprocess

        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        cv2.setNumThreads(1)
        torch.manual_seed(0)
        snapshot = args.output / "annotations.json"
        snapshot.write_bytes(annotation_bytes)
        snapshot.chmod(0o444)
        versions = {name: importlib.metadata.version(name) for name in
                    ("torch", "torchvision", "numpy", "yolox")}
        versions["cv2"] = cv2.__version__
        dependency_paths = [Path(module.__file__) for module in (torch, torchvision, np, cv2, yolox)]
        dependency_paths += [Path(torch._C.__file__)]
        dependency_paths += list(Path(cv2.__file__).parent.glob("*.so"))
        dependency_paths += list(Path(np.__file__).parent.rglob("*.so"))
        dependency_paths += list(Path(torchvision.__file__).parent.glob("*.so"))
        sources = [Path(__file__), Path(__file__).with_name("test_detector_resolution_eval.py")]
        bound_paths = [Path(record["path"]) for record in baseline["files"]]
        bound_paths += [baseline_path, args.baseline / "result.json", args.baseline / "predictions.json",
                        annotation_path, snapshot, *sources, *dependency_paths]
        manifest = {
            "created_utc": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
            "baseline_manifest_sha256": BASELINE_SHA,
            "checkpoint": baseline["checkpoint"], "annotations": file_record(snapshot),
            "images": baseline["images"], "categories": coco["categories"],
            "dependencies": versions, "runtime": baseline["runtime"] | {
                "python": sys.version, "executable": sys.executable},
            "protocol": dict(baseline["protocol"], input_size=args.input_size, budget_seconds=180),
            "explicit_experiment": {
                "checkpoint_training_input_size": 960, "inference_input_size": 1280,
                "description": "Dynamic fully convolutional YOLOX inference at 1280 with unchanged 960-trained weights; intentional experiment, not metadata/config equivalence",
            },
            "limitations": LIMITATION,
            "files": [file_record(path) for path in dict.fromkeys(bound_paths)],
        }
        validate_comparability(baseline, manifest)
        manifest_path = args.output / "manifest.json"
        write_new(manifest_path, manifest)
        manifest_path.chmod(0o444)
        manifest_sha = digest(manifest_path)
        verify_frozen(manifest_path, manifest_sha)
        print(f"Manifest frozen before inference: {manifest_sha}", flush=True)
        state = torch.load(baseline["checkpoint"]["path"], map_location="cpu", weights_only=True)
        if state["num_classes"] != 4 or state["input_size"] != 960:
            raise ValueError("Expected four-class checkpoint trained at 960; no silent override")
        experiment = get_exp(None, "yolox-m")
        experiment.num_classes = 4
        experiment.test_size = (args.input_size, args.input_size)
        model = experiment.get_model()
        model.load_state_dict(state["model"], strict=True)
        model = model.cpu().float().eval()
        transform = ValTransform(legacy=False)
        for image in images.values():
            frame_started = time.monotonic()
            image_path = next(record["path"] for record in baseline["images"] if record["id"] == image["id"])
            decoded = cv2.imread(image_path)
            if decoded is None or decoded.shape[:2] != (image["height"], image["width"]):
                raise ValueError("Image dimension/decode mismatch")
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
                category_id, score = int(category), objectness * confidence
                if score >= CUTOFFS[CATEGORIES[category_id]]:
                    frame_predictions.append({
                        "image_id": image["id"], "category_id": category_id, "score": score,
                        "bbox": [left / ratio, top / ratio, (right - left) / ratio, (bottom - top) / ratio],
                    })
            validate_predictions(coco, frame_predictions, [image["id"]])
            predictions.extend(frame_predictions)
            processed_ids.append(image["id"])
            timings.append({"image_id": image["id"], "seconds": time.monotonic() - frame_started})
            print(f"Processed {image['id']}: {len(processed_ids)}/44", flush=True)
        status = "complete"
    except Exception as exception:
        status = "partial" if processed_ids else "failed"
        failure = {"type": type(exception).__name__, "message": str(exception),
                   "traceback": traceback.format_exc()}
        print(failure["traceback"], file=sys.stderr, flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    inference_finished_seconds = time.monotonic() - started
    verified = False
    try:
        verify_frozen(args.baseline / "manifest.json", BASELINE_SHA)
        if manifest_sha is not None:
            verify_frozen(args.output / "manifest.json", manifest_sha)
            verified = True
    except Exception as exception:
        status = "invalid_provenance"
        failure = {"type": type(exception).__name__, "message": str(exception)}
    write_new(args.output / "predictions.json", predictions)
    coverage = validate_predictions(coco, predictions, processed_ids) if coco else None
    report = {"status": status, "failure": failure, "manifest_sha256": manifest_sha,
              "baseline_and_variant_provenance_verified_after": verified, "coverage": coverage,
              "inference_finished_seconds": inference_finished_seconds, "image_timings": timings,
              "command": [sys.executable, *sys.argv], "limitations": LIMITATION}
    if processed_ids and verified:
        agreement, review = evaluate(coco, predictions, processed_ids)
        report.update(agreement)
        compared = comparison(coco, baseline_predictions, predictions, processed_ids)
        baseline_frame_seconds = sum(item["seconds"] for item in baseline_result["image_timings"]
                                     if item["image_id"] in processed_ids)
        variant_frame_seconds = sum(item["seconds"] for item in timings)
        report["throughput"] = {
            "baseline_same_subset_frame_seconds": baseline_frame_seconds,
            "variant_frame_seconds": variant_frame_seconds,
            "baseline_frames_per_second": len(processed_ids) / baseline_frame_seconds,
            "variant_frames_per_second": len(processed_ids) / variant_frame_seconds,
            "frame_latency_ratio": variant_frame_seconds / baseline_frame_seconds,
            "baseline_full_run_seconds": baseline_result["runtime_seconds"],
        }
        write_new(args.output / "comparison.json", compared)
        write_new(args.output / "error_review.json", {"frames": review})
    report["runtime_seconds"] = time.monotonic() - started
    write_new(args.output / "processed_images.json", {"manifest_sha256": manifest_sha, "coverage": coverage})
    write_new(args.output / "result.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "image_timings"}, indent=2), flush=True)
    return 0 if status == "complete" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input-size", type=int, default=1280)
    args = parser.parse_args()
    try:
        validate_size(args.input_size)
    except ValueError as exception:
        parser.error(str(exception))
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
