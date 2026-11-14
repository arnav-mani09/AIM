"""Private full-context source-frame diagnostic; never writes production artifacts."""

import argparse
import copy
from fractions import Fraction
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import shots
import rim_source_rate_eval as prior
from local_detector_baseline import CUTOFFS, digest, file_record, write_new


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/rim_context_20261112"
WINDOWS = (("positive", "866.0", "867.4", 573),
           ("disputed", "4422.2", "4424.5", 1325))
CAP = 125
SECONDS = 240
TRIGGER = "Accepted first-under-net exit whose immediately preceding observed point is outside NET_EXIT_X; request evidence only, not an outcome override."


def create_output(path):
    if path != OUTPUT or path.is_symlink() or path.resolve() != ROOT / "ml/data/labels/rim_context_20261112":
        raise ValueError("Only the dedicated private output is allowed")
    path.mkdir(mode=0o700, exist_ok=False)


def dependencies():
    import cv2
    names = ("torch", "torchvision", "numpy", "yolox")
    return {**{name: importlib.metadata.version(name) for name in names}, "cv2": cv2.__version__}


def reusable(sample, old_sample, manifest, old_manifest):
    return (manifest["checkpoint"] == old_manifest["checkpoint"]
            and manifest["protocol"] == old_manifest["protocol"]
            and manifest["dependencies"] == old_manifest["dependencies"]
            and manifest["source"] == old_manifest["source"]
            and all(sample[key] == old_sample[key] for key in
                    ("pts", "time_base", "source_video_sample_index", "packet_position"))
            and all(sample["file"][key] == old_sample["file"][key]
                    for key in ("sha256", "size_bytes")))


def verify(manifest):
    prior.validate_protocol(manifest["protocol"])
    if not 0 < len(manifest["samples"]) <= CAP or manifest["budget_seconds"] != SECONDS:
        raise ValueError("Invalid frame/time cap")
    identities = [(sample["pts"], sample["time_base"]) for sample in manifest["samples"]]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate frame identity")
    for sample in manifest["samples"]:
        bounds = next((window for window in WINDOWS if window[0] == sample["window"]), None)
        if bounds is None or not Fraction(bounds[1]) <= sample["pts"] * Fraction(sample["time_base"]) <= Fraction(bounds[2]):
            raise ValueError("Out-of-window source frame")
        prior.checked_record(sample["file"])
    snapshots = {}
    snapshot_path = OUTPUT / "source_snapshots.json"
    if snapshot_path.exists():
        for binding in json.loads(snapshot_path.read_text())["sources"]:
            original, snapshot = binding["original"], binding["snapshot"]
            if original["path"] not in {str(Path(__file__)), str(ROOT / "ml/tools/test_rim_context_eval.py")}:
                raise ValueError("Only this experiment's source revisions may be snapshotted")
            if any(original[key] != snapshot[key] for key in ("sha256", "size_bytes")):
                raise ValueError("Source snapshot differs from frozen original")
            prior.checked_record(snapshot)
            snapshots[original["path"]] = binding
    for record in manifest["files"]:
        if record["path"] in snapshots:
            if record != snapshots[record["path"]]["original"]:
                raise ValueError("Snapshot binding differs from pre-inference source record")
        else:
            prior.checked_record(record)
    revision = OUTPUT / "analysis_revision_manifest.json"
    if revision.exists():
        for record in json.loads(revision.read_text())["files"]:
            prior.checked_record(record)
    prior.checked_record(manifest["checkpoint"])
    if dependencies() != manifest["dependencies"]:
        raise ValueError("Dependency version changed")


def prepare():
    if OUTPUT.exists():
        raise FileExistsError("Refusing existing artifacts")
    old = json.loads((prior.OUTPUT / "manifest.json").read_text())
    prior.verify_experiment(old)
    prior.checked_record(old["checkpoint"])
    completion = json.loads((prior.OUTPUT / "inference.json").read_text())
    if completion["status"] != "complete" or completion["manifest_sha256"] != digest(prior.OUTPUT / "manifest.json"):
        raise ValueError("Prior inference is not bound to frozen manifest")
    old_rows = [json.loads(line) for line in (prior.OUTPUT / "detections.jsonl").read_text().splitlines()]
    if [row["sample"] for row in old_rows] != old["samples"]:
        raise ValueError("Prior output/sample ordering mismatch")
    audit = json.loads(prior.AUDIT.read_text())
    for path, checksum in audit["inputs_sha256"].items():
        if digest(ROOT / path) != checksum:
            raise ValueError(f"Audit source changed: {path}")
    source = old["source"]
    prior.checked_record(source)
    packets = prior.probe(["-select_streams", "v:0", "-show_packets", "-show_entries",
                           "packet=pts,dts,pos,duration,flags", source["path"]])["packets"]
    if old["stream"]["has_b_frames"] or any(packet["pts"] != packet["dts"] for packet in packets):
        raise ValueError("Unproven source sample ordering")
    manifest = {"protocol": copy.deepcopy(old["protocol"]), "checkpoint": old["checkpoint"],
                "source": source, "dependencies": dependencies(), "budget_seconds": SECONDS,
                "frame_cap": CAP, "windows": WINDOWS, "trigger_preregistered": TRIGGER,
                "historical_limit": old["historical_limit"],
                "phase_design": "Prefix through first observed in-zone above-rim point shared by all phases; subsequent decoded indices modulo 3. Also report independent pure phases. Ball selection rerun for each phase, no interpolation or rim hold.",
                "files": [], "samples": [], "extraction_commands": [],
                "decoder_version": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]}
    if manifest["dependencies"] != old["dependencies"]:
        raise ValueError("Dependency mismatch")
    create_output(OUTPUT)
    old_by_pts = {row["sample"]["pts"]: (index, row) for index, row in enumerate(old_rows)}
    for name, start, end, anchor in WINDOWS:
        directory = OUTPUT / name
        directory.mkdir()
        decoded = prior.probe(["-select_streams", "v:0", "-read_intervals", f"{start}%{float(end) + .01}",
                               "-show_frames", "-show_entries", "frame=pts,best_effort_timestamp,pkt_pos,pict_type", source["path"]])["frames"]
        aligned = prior.align_frames(decoded, packets, old["stream"]["time_base"], start, end)
        command = ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-threads", "1", "-copyts",
                   "-ss", str(float(start) - .001), "-t", str(float(end) - float(start) + .02),
                   "-i", source["path"], "-an", "-vf",
                   f"select='between(pts,{aligned[0]['pts']},{aligned[-1]['pts']})',showinfo",
                   "-fps_mode", "passthrough", "-frames:v", str(len(aligned)), "-threads", "1",
                   str(directory / "frame_%03d.png")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
        (directory / "decode.log").write_text(result.stderr)
        emitted = [(int(index), int(pts)) for index, pts in re.findall(
            r"n:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:", result.stderr)]
        images = sorted(directory.glob("frame_*.png"))
        if len(images) != len(aligned) or [pts for _, pts in emitted] != [frame["pts"] for frame in aligned]:
            raise ValueError("Exact PNG/decoder/packet PTS alignment failed")
        for frame, image, (index, _) in zip(aligned, images, emitted):
            sample = {**frame, "window": name, "rim_anchor_x": anchor,
                      "selected_decoder_index": index, "file": file_record(image), "reuse_row": None}
            if frame["pts"] in old_by_pts:
                old_index, old_row = old_by_pts[frame["pts"]]
                if reusable(sample, old_row["sample"], manifest, old):
                    sample["reuse_row"] = old_index
            manifest["samples"].append(sample)
        manifest["extraction_commands"].append(command)
    bound_paths = [Path(__file__), ROOT / "ml/tools/test_rim_context_eval.py", prior.OUTPUT / "manifest.json",
                   prior.OUTPUT / "detections.jsonl", prior.OUTPUT / "inference.json", prior.AUDIT,
                   ROOT / "ml/tools/rim_source_rate_eval.py", ROOT / "ml/tools/rim_outcome_audit.py"]
    manifest["files"] = [*old["files"], *[file_record(path) for path in bound_paths]]
    manifest["reuse_count"] = sum(sample["reuse_row"] is not None for sample in manifest["samples"])
    manifest["reuse_binding"] = "Prior complete inference manifest SHA plus exact raw-output file SHA frozen here before inference; each reuse_row binds identical PNG SHA/bytes, integer PTS/sample identity, source, checkpoint, full protocol and versions. Historical cache remains non-equivalent."
    verify(manifest)
    write_new(OUTPUT / "manifest.json", manifest)
    (OUTPUT / "manifest.json").chmod(0o444)
    print(f"Frozen {len(manifest['samples'])} frames, {manifest['reuse_count']} reusable; manifest {digest(OUTPUT / 'manifest.json')}", flush=True)


def infer():
    import cv2
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.exp import get_exp
    from yolox.utils import postprocess

    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    verify(manifest)
    manifest_sha = digest(OUTPUT / "manifest.json")
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    torch.manual_seed(0)
    state = torch.load(manifest["checkpoint"]["path"], map_location="cpu", weights_only=True)
    if state["num_classes"] != 4 or state["input_size"] != 960:
        raise ValueError("Checkpoint metadata changed")
    experiment = get_exp(None, "yolox-m")
    experiment.num_classes = 4
    model = experiment.get_model()
    model.load_state_dict(state["model"], strict=True)
    model = model.cpu().float().eval()
    transform = ValTransform(legacy=False)
    old = json.loads((prior.OUTPUT / "manifest.json").read_text())
    old_rows = [json.loads(line) for line in (prior.OUTPUT / "detections.jsonl").read_text().splitlines()]
    with (OUTPUT / "detections.jsonl").open("x") as handle:
        for sample in manifest["samples"]:
            started = time.monotonic()
            reused = sample["reuse_row"] is not None
            if reused:
                old_row = old_rows[sample["reuse_row"]]
                if not reusable(sample, old_row["sample"], manifest, old):
                    raise ValueError("Reuse binding failed")
                retained = old_row["retained_postprocess_ball_rim"]
            else:
                image = cv2.imread(sample["file"]["path"])
                if image is None or image.shape != (1080, 1920, 3):
                    raise ValueError("Unexpected native dimensions")
                ratio = min(960 / image.shape[0], 960 / image.shape[1])
                tensor, _ = transform(image, None, (960, 960))
                with torch.inference_mode():
                    output = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()),
                                         4, conf_thre=.1, nms_thre=.45, class_agnostic=False)[0]
                retained = []
                for left, top, right, bottom, objectness, confidence, category in ([] if output is None else output.cpu().tolist()):
                    if category not in (0, 3):
                        continue
                    score = objectness * confidence
                    retained.append({"category": int(category), "xyxy": [coordinate / ratio for coordinate in (left, top, right, bottom)],
                                     "objectness": objectness, "class_confidence": confidence, "score": score,
                                     "passes_class_cutoff": score >= CUTOFFS["ball" if category == 0 else "rim"]})
            handle.write(json.dumps({"sample": sample, "retained_postprocess_ball_rim": retained,
                                     "reused": reused, "seconds": time.monotonic() - started}, allow_nan=False) + "\n")
            handle.flush()
            print(f"{sample['window']} PTS={sample['pts']} reused={reused}", flush=True)
    verify(manifest)
    if digest(OUTPUT / "manifest.json") != manifest_sha:
        raise ValueError("Manifest mutated")
    write_new(OUTPUT / "inference.json", {"status": "complete", "manifest_sha256": manifest_sha,
              "detections": file_record(OUTPUT / "detections.jsonl"), "provenance_verified_after": True,
              "new_inferences": len(manifest["samples"]) - manifest["reuse_count"], "reused": manifest["reuse_count"]})


def validate_outputs(manifest, records, completion):
    if completion["manifest_sha256"] != digest(OUTPUT / "manifest.json") or completion["status"] != "complete":
        raise ValueError("Incomplete or unbound inference")
    prior.checked_record(completion["detections"])
    if [record["sample"] for record in records] != manifest["samples"]:
        raise ValueError("Missing, reordered or substituted inference")


def common_prefix(selected):
    for entry in selected:
        point = entry["point"]
        rim = [3, *point[3:], entry["rim_score"], -1]
        if shots.rim_units(point)[2] < .3 and shots.in_zone(point[1], point[2], rim):
            return point[0]
    raise ValueError("No common initial in-zone above-rim observation")


def trigger(trace):
    crossing = trace.get("first_under_net")
    if not trace.get("decide_result", {}).get("made") or not crossing or crossing["index"] == 0:
        return False
    return abs(trace["rim_unit_path"][crossing["index"] - 1][1]) > shots.NET_EXIT_X


def coverage(records, selected, trace):
    crossing = trace.get("first_under_net")
    if not crossing:
        return {"status": "no_under_net_observation"}
    exit_time = crossing["point"][0]
    required_until = exit_time + .4
    selected_pts = {entry["sample"]["pts"] for entry in selected}
    guard = [record for record in records if exit_time < record["sample"]["seconds"] <= required_until + 1e-9]
    missing_ball, missing_rim, omitted_path = [], [], []
    for record in guard:
        sample = record["sample"]
        rows = [row for row in record["retained_postprocess_ball_rim"] if row["passes_class_cutoff"]]
        if not any(row["category"] == 0 for row in rows):
            missing_ball.append(sample["pts"])
        if not any(row["category"] == 3 and abs((row["xyxy"][0] + row["xyxy"][2]) / 2 - sample["rim_anchor_x"]) < 150 for row in rows):
            missing_rim.append(sample["pts"])
        if sample["pts"] not in selected_pts:
            omitted_path.append(sample["pts"])
    return {"exit_time": exit_time, "required_until": required_until,
            "decoded_until": records[-1]["sample"]["seconds"],
            "decoded_horizon_complete": records[-1]["sample"]["seconds"] >= required_until,
            "guard_frame_count": len(guard), "missing_ball_pts": missing_ball,
            "missing_local_rim_pts": missing_rim, "not_in_selected_path_pts": omitted_path,
            "all_guard_frames_have_selected_pair": bool(guard) and not omitted_path,
            "limit": "No output is not absence/occlusion truth; selected-pair coverage is separate from decoded duration."}


def evaluate(records, anchor):
    observed = prior.observed_path(records, anchor)
    start = common_prefix(observed)
    selected = [entry for entry in observed if entry["point"][0] >= start]
    trace = prior.path_decision(selected, records[-1]["sample"]["seconds"])
    trace["coverage"] = coverage(records, selected, trace)
    trace["candidate_second_pass"] = trigger(trace)
    trace["above_rim_observations"] = sum(shots.rim_units(entry["point"])[2] < .3 for entry in selected)
    trace["selected_observations"] = selected
    trace["decoded_count"] = len(records)
    trace["attempt_path_starts_at"] = start
    trace["pre_attempt_observations_excluded"] = len(observed) - len(selected)
    crossing = trace.get("first_under_net")
    trace["failed_primary"] = ([name for name, passed in crossing["primary_checks"].items() if not passed]
                               if crossing and crossing["last_above"] else ["missing_above_rim_context"])
    trace["failed_gap"] = ([name for name, passed in crossing["gap_checks"].items() if not passed]
                           if crossing and crossing["last_above"] else ["missing_above_rim_context"])
    return trace


def overlays(records, name, anchor):
    import cv2
    import numpy as np

    tiles = []
    for record in records:
        sample = record["sample"]
        image = cv2.imread(sample["file"]["path"])
        for row in record["retained_postprocess_ball_rim"]:
            color = (0, 220, 0) if row["passes_class_cutoff"] else (0, 140, 255)
            left, top, right, bottom = [round(value) for value in row["xyxy"]]
            cv2.rectangle(image, (left, top), (right, bottom), color, 1)
            cv2.putText(image, f"{row['category']}:{row['score']:.3f}", (left, max(12, top - 3)), 0, .35, color, 1)
        crop = image[0:520, anchor - 190:anchor + 230].copy()
        banner = np.zeros((48, 420, 3), dtype=np.uint8)
        cv2.putText(banner, f"PTS {sample['pts']} * {sample['time_base']}", (6, 17), 0, .48, (255, 255, 255), 1)
        cv2.putText(banner, f"t={sample['seconds']:.6f} sample={sample['source_video_sample_index']}", (6, 37), 0, .44, (255, 255, 255), 1)
        tile = np.vstack([banner, crop])
        path = OUTPUT / name / f"overlay_{sample['selected_decoder_index']:03d}.png"
        if path.exists() or not cv2.imwrite(str(path), tile):
            raise ValueError("Overlay exists or failed")
        tiles.append(tile)
    for index in range(0, len(tiles), 8):
        subset = tiles[index:index + 8]
        subset += [np.zeros_like(subset[0])] * (-len(subset) % 4)
        sheet = np.vstack([np.hstack(subset[start:start + 4]) for start in range(0, len(subset), 4)])
        path = OUTPUT / name / f"sheet_{index:03d}.png"
        if path.exists() or not cv2.imwrite(str(path), sheet):
            raise ValueError("Sheet exists or failed")


def analyze(revision=False):
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    verify(manifest)
    records = [json.loads(line) for line in (OUTPUT / "detections.jsonl").read_text().splitlines()]
    validate_outputs(manifest, records, json.loads((OUTPUT / "inference.json").read_text()))
    report = {"windows": {}, "historical_limit": manifest["historical_limit"],
              "scope": "Conditional unchanged decide on observed local-ROI paths, not find_shots/rescue/dead-ball or physical truth.",
              "trigger": TRIGGER}
    for name, start, end, anchor in WINDOWS:
        window = [record for record in records if record["sample"]["window"] == name]
        dense = evaluate(window, anchor)
        prefix = common_prefix(dense["selected_observations"])
        phases, pure = {}, {}
        for phase in range(3):
            phases[str(phase)] = evaluate([record for record in window if record["sample"]["seconds"] <= prefix
                                          or record["sample"]["selected_decoder_index"] % 3 == phase], anchor)
            pure_records = [record for record in window if record["sample"]["selected_decoder_index"] % 3 == phase]
            try:
                pure[str(phase)] = evaluate(pure_records, anchor)
            except ValueError as exception:
                if str(exception) != "No common initial in-zone above-rim observation":
                    raise
                pure[str(phase)] = {"status": "missing_initial_context", "decoded_count": len(pure_records),
                                    "above_rim_observations": 0, "decision_not_evaluated": True}
        report["windows"][name] = {"dense": dense, "common_prefix_until": prefix,
                                    "common_context_phases": phases, "pure_phases": pure}
        if not revision:
            overlays(window, name, anchor)
    audit = json.loads(prior.AUDIT.read_text())
    report["cached_trigger_coverage"] = {"population": "All six pre-existing curated audit trajectories; NOT all game attempts or accuracy ground truth.",
        "cases": [{"game": case["game"], "review_id": case["review_id"],
                   "made": case["decide_result"]["made"], "trigger": trigger(case),
                   "provisional_interpretation": case["provisional_interpretation"]} for case in audit["cases"]]}
    write_new(OUTPUT / ("analysis_context.json" if revision else "analysis.json"), report)
    integrity_name = "integrity_context.json" if revision else "integrity.json"
    generated = [path for path in OUTPUT.rglob("*") if path.is_file() and path.name != integrity_name]
    write_new(OUTPUT / integrity_name, {"files": [file_record(path) for path in sorted(generated)]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "infer", "analyze", "analyze-revision", "run"))
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
    elif args.stage == "infer":
        infer()
    elif args.stage == "analyze":
        analyze()
    elif args.stage == "analyze-revision":
        write_new(OUTPUT / "analysis_revision_manifest.json", {
            "reason": "Observed pre-shot below-net motion must not be fed to decide as the attempt's first under-net sample. Start path at first observed in_zone point, as main attempt opening does; no threshold or timestamp exception.",
            "inference_repeated": False,
            "files": [file_record(path) for path in (Path(__file__), ROOT / "ml/tools/test_rim_context_eval.py",
                      OUTPUT / "source_snapshots.json", OUTPUT / "manifest.json", OUTPUT / "inference.json",
                      OUTPUT / "detections.jsonl")]})
        analyze(revision=True)
    else:
        prepare()
        started = time.monotonic()
        try:
            with (OUTPUT / "inference.log").open("x") as handle:
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "infer"],
                               stdout=handle, stderr=subprocess.STDOUT, timeout=SECONDS, check=True)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exception:
            write_new(OUTPUT / "failure.json", {"status": "bounded_failure", "error": str(exception),
                                               "wall_seconds": time.monotonic() - started})
            raise
        write_new(OUTPUT / "budget.json", {"wall_seconds": time.monotonic() - started, "cap_seconds": SECONDS})
        analyze()


if __name__ == "__main__":
    main()
