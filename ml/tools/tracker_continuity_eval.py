"""Bounded, actual supervision 0.26.1 ByteTrack experiment; no film inference."""

import hashlib
import importlib.metadata
import inspect
import json
import signal
import time
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/tracker_continuity_20261113"
CONFIGS = {
    "current": dict(track_activation_threshold=0.5, frame_rate=10,
                    lost_track_buffer=30, minimum_matching_threshold=0.8,
                    minimum_consecutive_frames=1),
    "buffer_3s": dict(track_activation_threshold=0.5, frame_rate=10,
                      lost_track_buffer=90, minimum_matching_threshold=0.8,
                      minimum_consecutive_frames=1),
}
WINDOWS = (("mitty", 253.1, (964, 961)), ("mitty", 1150.7, (3767, 3805)),
           ("riordan", 3613.3, (11127, 11120)), ("riordan", 5496.8, (17531, 17522)))
SCORES = (0.1, 0.100001, 0.499999, 0.5, 0.500001, 0.599999, 0.6, 0.600001)


def actual_dependencies():
    try:
        import numpy as np
        import supervision as sv
    except ImportError as error:
        raise unittest.SkipTest(f"Actual tracker dependency unavailable: {error}") from error
    if sv.__version__ != "0.26.1":
        raise unittest.SkipTest(f"Requires deployed pin supervision==0.26.1; found {sv.__version__}")
    return np, sv


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def save(name, value):
    with (OUTPUT / name).open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def observation(identity, x=100, y=100, score=0.9, team="A"):
    return {"key": identity, "box": [x, y, x + 40, y + 100],
            "score": score, "team": team}


def synthetic_inputs():
    cases = {}
    for gap in (5, 18, 35):
        cases[f"occlusion_{gap}_frames"] = [
            [] if 10 <= frame < 10 + gap else [observation("person_A", x=100 + frame)]
            for frame in range(60)]
    for relation in ("same_team", "opposing_team"):
        other_team = "A" if relation == "same_team" else "B"
        cases[f"crossing_{relation}"] = [
            [observation("person_A", x=60 + 4 * frame),
             observation("person_B", x=261 - 4 * frame, team=other_team)]
            if frame not in (23, 24, 25, 26) else [] for frame in range(52)]
        cases[f"stale_replacement_{relation}"] = [
            [observation("person_A")] if frame < 10 else [] if frame < 28 else
            [observation("different_person_B", team=other_team)] for frame in range(45)]
    for mode in ("smooth", "abrupt"):
        cases[f"camera_translation_{mode}"] = [
            [observation("person_A", x=100 + (3 * frame if mode == "smooth" else
                                             120 * (frame >= 20))),
             observation("person_B", x=350 + (3 * frame if mode == "smooth" else
                                             120 * (frame >= 20)), team="B")]
            for frame in range(45)]
    return cases


def run_tracker(frames, config, deadline=None):
    np, sv = actual_dependencies()
    tracker = sv.ByteTrack(**config)
    outputs = []
    for rows in frames:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("20-second cached-window wall limit exceeded")
        detections = sv.Detections(
            xyxy=np.array([row["box"] for row in rows], dtype=float).reshape(-1, 4),
            confidence=np.array([row["score"] for row in rows], dtype=float),
            class_id=np.ones(len(rows), dtype=int),
            data={"input_row": np.arange(len(rows), dtype=int)},
        )
        tracked = tracker.update_with_detections(detections)
        frame_output = []
        if not len(tracked):
            outputs.append(frame_output)
            continue
        for row_index, track_id in zip(tracked.data["input_row"], tracked.tracker_id):
            row_index, track_id = int(row_index), int(track_id)
            frame_output.append({"input_row": row_index, "track_id": track_id,
                                 "key": rows[row_index]["key"]})
        if len({row["track_id"] for row in frame_output}) != len(frame_output):
            raise AssertionError("One replay ID assigned to co-visible output boxes")
        outputs.append(frame_output)
    return outputs


def continuity_summary(frames, outputs, synthetic=False):
    per_key, per_track = defaultdict(list), defaultdict(set)
    for frame_index, rows in enumerate(outputs):
        for row in rows:
            per_key[row["key"]].append((frame_index, row["track_id"]))
            per_track[row["track_id"]].add(row["key"])
    supplied = sum(map(len, frames))
    emitted = sum(map(len, outputs))
    detail = {}
    for key in sorted({row["key"] for rows in frames for row in rows}):
        samples = per_key[key]
        ids = sorted({track_id for _, track_id in samples})
        detail[key] = {
            "output_boxes": len(samples), "replay_ids": ids,
            "distinct_replay_ids_minus_one": max(0, len(ids) - 1),
            "successive_output_id_changes": sum(first[1] != second[1]
                                                for first, second in zip(samples, samples[1:])),
            "output_gap_runs": sum(second[0] > first[0] + 1
                                   for first, second in zip(samples, samples[1:])),
        }
    result = {"supplied_boxes": supplied, "output_boxes": emitted,
              "output_coverage": emitted / supplied if supplied else None,
              "distinct_replay_ids": len(per_track), "per_input_key": detail,
              "replay_ids_spanning_multiple_input_keys": {
                  str(track_id): sorted(keys) for track_id, keys in per_track.items() if len(keys) > 1}}
    if synthetic:
        result["known_identity_fragments"] = sum(
            item["distinct_replay_ids_minus_one"] for item in detail.values())
        result["known_identity_id_changes"] = sum(
            item["successive_output_id_changes"] for item in detail.values())
        result["contaminated_replay_ids"] = sum(len(keys) > 1 for keys in per_track.values())
    return result


def threshold_probe():
    result = {}
    for score in SCORES:
        fresh = [[observation("person_A", score=score)] for _ in range(4)]
        ongoing = [[observation("person_A", score=0.9)] for _ in range(4)]
        ongoing += [[observation("person_A", score=score)] for _ in range(3)]
        lost = [[observation("person_A")], [], [observation("person_A", score=score)]]
        result[str(score)] = {}
        for name, config in CONFIGS.items():
            result[str(score)][name] = {
                "fresh_output_by_frame": [len(rows) for rows in run_tracker(fresh, config)],
                "ongoing_probe_output_by_frame": [len(rows) for rows in run_tracker(ongoing, config)[4:]],
                "lost_track_probe_output": len(run_tracker(lost, config)[-1]),
            }
    return result


def overlap_count(frames, threshold=0.3):
    pairs = 0
    for rows in frames:
        for index, first in enumerate(rows):
            for second in rows[index + 1:]:
                left, top = max(first["box"][0], second["box"][0]), max(first["box"][1], second["box"][1])
                right, bottom = min(first["box"][2], second["box"][2]), min(first["box"][3], second["box"][3])
                intersection = max(0, right - left) * max(0, bottom - top)
                areas = [(row["box"][2] - row["box"][0]) * (row["box"][3] - row["box"][1])
                         for row in (first, second)]
                union = sum(areas) - intersection
                pairs += bool(union > 0 and intersection / union >= threshold)
    return pairs


def replay_window(game, center, focal_ids, document):
    start = time.monotonic()
    deadline = start + 20
    frames = [frame for frame in document["frames"] if center - 5 <= frame[0] <= center + 3]
    if document["fps"] != 10 or len(frames) < 2:
        raise ValueError("Expected existing 10fps cache window")
    if any(abs(second[0] - first[0] - 0.1) > 0.00001
           for first, second in zip(frames, frames[1:])):
        raise ValueError("Cache timestamps have gaps; refusing invented tracker timing")
    inputs = [[{"key": str(box[6]), "box": box[1:5], "score": box[5]}
               for box in boxes if box[0] == 1] for _, boxes in frames]
    frozen = {"game": game, "shot_t": center, "focal_cached_ids": focal_ids,
              "timestamps": [frame[0] for frame in frames], "frames": inputs,
              "input_kind": "rounded_post_tracker_player_boxes_not_raw_detector_proposals",
              "cold_start": True, "warmup_seconds_before_shot": 5}
    filename = f"{game}_{center}_inputs.json"
    save(filename, frozen)
    results = {}
    for name, config in CONFIGS.items():
        outputs = run_tracker(inputs, config, deadline)
        summary = continuity_summary(inputs, outputs)
        summary["focal_cached_id_diagnostics"] = {
            str(key): summary["per_input_key"].get(str(key)) for key in focal_ids}
        results[name] = summary
        save(f"{game}_{center}_{name}_outputs.json", outputs)
    elapsed = time.monotonic() - start
    if elapsed > 20:
        raise TimeoutError("20-second cached-window wall limit exceeded")
    return {"input_file": filename, "input_sha256": digest(OUTPUT / filename),
            "start_t": frames[0][0], "end_t": frames[-1][0], "frames": len(inputs),
            "input_pair_frames_with_iou_at_least_0.3": overlap_count(inputs),
            "elapsed_wall_seconds": elapsed, "configs": results,
            "identity_truth_available": False, "production_parity": False}


def package_inventory():
    _, sv = actual_dependencies()
    package = Path(inspect.getfile(sv)).parent
    files = {str(path): digest(path) for path in sorted(package.rglob("*.py"))}
    versions = {}
    for name in ("supervision", "numpy", "scipy"):
        distribution = importlib.metadata.distribution(name)
        versions[name] = distribution.version
        for entry in distribution.files or []:
            if str(entry).endswith(("/METADATA", ".so", ".dylib")):
                path = Path(distribution.locate_file(entry))
                if path.is_file():
                    files[str(path)] = digest(path)
    return {"versions": versions, "files": files}


def audit_inventory(before):
    return {path: digest(ROOT / path) if (ROOT / path).is_file() else None for path in before}


def timeout_handler(signum, frame):
    raise TimeoutError("120-second experiment CPU limit exceeded")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "summary.json").exists():
        raise FileExistsError("Frozen experiment already exists; refusing overwrite")
    actual_dependencies()
    before = json.loads((OUTPUT / "source_inventory_before.json").read_text())
    initial_changes = [path for path, value in audit_inventory(before).items() if value != before[path]]
    if initial_changes:
        raise RuntimeError(f"Existing source changed before experiment: {initial_changes}")
    packages = package_inventory()
    save("package_inventory_before.json", packages)
    source_paths = [ROOT / "worker/vision.py", ROOT / "worker/film_worker.py",
                    ROOT / "ml/tools/assist_identity.py", ROOT / "ml/docs/assist_accuracy.md",
                    Path(__file__), ROOT / "ml/tools/test_tracker_continuity_eval.py"]
    cache_paths = {game: ROOT / f"ml/data/tracks/valley-vs-archbishop-{game}.v4.json"
                   for game in ("mitty", "riordan")}
    frozen_paths = source_paths + list(cache_paths.values())
    frozen_paths += list((ROOT / "ml/data/labels/assist_identity_20261112").glob("*identity.jpg"))
    inputs_before = {str(path): digest(path) for path in frozen_paths}
    _, sv = actual_dependencies()
    runtime_config = {name: {"constructor": config,
                            "max_time_lost": sv.ByteTrack(**config).max_time_lost,
                            "det_thresh": sv.ByteTrack(**config).det_thresh}
                      for name, config in CONFIGS.items()}
    save("config.json", runtime_config)
    cases = synthetic_inputs()
    save("synthetic_inputs.json", cases)
    cpu_start, wall_start = time.process_time(), time.monotonic()
    previous_handler = signal.signal(signal.SIGPROF, timeout_handler)
    signal.setitimer(signal.ITIMER_PROF, 120)
    try:
        synthetic = {}
        for case, frames in cases.items():
            synthetic[case] = {}
            for name, config in CONFIGS.items():
                outputs = run_tracker(frames, config)
                synthetic[case][name] = continuity_summary(frames, outputs, synthetic=True)
                save(f"synthetic_{case}_{name}_outputs.json", outputs)
        thresholds = threshold_probe()
        cached = {}
        for game, path in cache_paths.items():
            document = json.loads(path.read_text())
            for window_game, center, focal in WINDOWS:
                if game == window_game:
                    cached[f"{game}_{center}"] = replay_window(game, center, focal, document)
        timing = {"experiment_cpu_seconds": time.process_time() - cpu_start,
                  "experiment_wall_seconds": time.monotonic() - wall_start,
                  "cpu_limit_seconds": 120, "cached_window_wall_limit_seconds": 20}
    finally:
        signal.setitimer(signal.ITIMER_PROF, 0)
        signal.signal(signal.SIGPROF, previous_handler)
    after = audit_inventory(before)
    save("source_inventory_after.json", after)
    changed = [path for path in before if before[path] != after[path]]
    packages_after = package_inventory()
    save("package_inventory_after.json", packages_after)
    inputs_after = {str(path): digest(path) for path in frozen_paths}
    if changed or packages != packages_after or inputs_before != inputs_after:
        raise RuntimeError(f"Preservation audit failed: {changed}")
    summary = {"configs": runtime_config, "synthetic": synthetic, "threshold_probe": thresholds,
               "cached_windows": cached, "timing": timing,
               "input_hashes_before": inputs_before, "input_hashes_after": inputs_after,
               "preservation": {"existing_files_checked": len(before), "changed": changed,
                                "package_unchanged": True},
               "limitations": ["Post-tracker cache omits suppressed/unmatched raw detections",
                               "Rounded boxes/scores and cold starts preclude production parity",
                               "Cached IDs are diagnostic keys, not person identity truth",
                               "No real ID-switch metric, alias, team truth, or accuracy claim"],
               "decision": "No safe production configuration fix established"}
    save("summary.json", summary)
    print(json.dumps({"decision": summary["decision"], "timing": timing,
                      "preservation": summary["preservation"]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except unittest.SkipTest as error:
        print(json.dumps({"status": "skipped", "reason": str(error)}))
