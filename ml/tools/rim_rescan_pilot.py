"""Six-case offline pilot; append-only private evidence, never runtime overrides."""

import argparse
import copy
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import rim_context_eval as context
import rim_rescan_coverage as census
import rim_source_rate_eval as source_rate
from local_detector_baseline import CUTOFFS, digest, file_record, write_new


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/rim_rescan_pilot_20261113"
CENSUS = census.OUTPUT
CAP = 500
SECONDS = 600
TARGETS = {"mitty": (967.10, 1782.20), "riordan": (860.10, 1788.60)}


def load(path):
    return json.loads(Path(path).read_text())


def create_output(path):
    if path != OUTPUT or path.is_symlink() or path.resolve() != OUTPUT:
        raise ValueError("Only the dedicated private pilot directory is allowed")
    path.mkdir(mode=0o700, exist_ok=False)


def select_control(events, target, excluded):
    eligible = [event for event in events if event["cohort"] == "eligible_game"
                and event["made"] and not event["triggered"] and event["event_id"] not in excluded]
    matched = [event for event in eligible if event["category"] == "FG"]
    return min(matched or eligible, key=lambda event: (abs(event["t"] - target), event["event_id"]), default=None)


def selection(games, reviewed, old_manifests):
    selected, failures, exclusions = [], [], {}
    for game, targets in TARGETS.items():
        data = games[game]
        intervals = [entry["requested_interval_s"] for entry in reviewed["window_coverage"]
                     if entry["window"].startswith(game + "_")]
        for manifest in old_manifests:
            for name, start, end, _ in manifest["windows"]:
                intervals.append([float(start), float(end)] if manifest["game"] == game else [-1, -1])
        excluded = {event["event_id"] for event in data["events"]
                    if any(start <= event["t"] <= end for start, end in intervals)}
        exclusions[game] = {"event_ids": sorted(excluded), "intervals": intervals}
        for target in targets:
            matches = [event for event in data["events"] if abs(event["t"] - target) < 1e-8
                       and event["cohort"] == "eligible_game" and event["made"] and event["triggered"]]
            if len(matches) != 1:
                raise ValueError("Required trigger absent or ambiguous")
            selected.append({"game": game, "stratum": "trigger", "event": matches[0]})
        control = select_control(data["events"], targets[0], excluded)
        if control is None:
            failures.append({"game": game, "stratum": "control", "status": "no_strict_eligible_control"})
        else:
            selected.append({"game": game, "stratum": "untriggered_control", "event": control})
    return selected, failures, exclusions


def check_budget(windows, samples=None):
    if len(windows) > 6 or sum(window["estimated_frames"] for window in windows) > CAP:
        raise ValueError("Frozen window/frame budget exceeded")
    if samples is not None and (not samples or len(samples) > CAP):
        raise ValueError("Actual source-frame budget exceeded")


def align_frames(frames, packets, time_base, start, end):
    by_position = {str(packet["pos"]): packet for packet in packets}
    aligned = []
    for index, frame in enumerate(frames):
        pts = int(frame["pts"])
        seconds = pts * Fraction(time_base)
        if not Fraction(str(start)) <= seconds <= Fraction(str(end)):
            continue
        packet = by_position[str(frame["pkt_pos"])]
        if int(packet["pts"]) != pts or int(frame["best_effort_timestamp"]) != pts:
            raise ValueError("Exact decoder/packet PTS mismatch")
        aligned.append({"pts": pts, "time_base": time_base, "seconds": float(seconds),
            "seconds_fraction": str(seconds), "packet_position": int(frame["pkt_pos"]),
            "probe_decoder_index": index, "picture_type": frame["pict_type"]})
    if not aligned or any(after["pts"] <= before["pts"] for before, after in zip(aligned, aligned[1:])):
        raise ValueError("Empty or non-monotonic frame identities")
    return aligned


def freeze():
    if OUTPUT.exists():
        raise FileExistsError("Refusing existing pilot, including incomplete runs")
    games = {game: load(CENSUS / f"{game}.json") for game in TARGETS}
    reviewed_path = ROOT / "ml/data/labels/blind_film_review_20261112/observations.frozen.json"
    old_manifests = [{"game": "riordan", "windows": source_rate.WINDOWS},
                     {"game": "riordan", "windows": context.WINDOWS}]
    selected, failures, exclusions = selection(games, load(reviewed_path), old_manifests)
    baseline = load(source_rate.BASELINE)
    protocol = source_rate.validate_protocol(baseline["protocol"])
    if context.dependencies() != baseline["dependencies"]:
        raise ValueError("Frozen dependency versions differ")
    provenance = load(source_rate.PROVENANCE)
    sources, windows = {}, []
    for game, data in games.items():
        original = provenance["sources"][game]
        record = file_record(ROOT / original["path"])
        if any(record[key] != original[key] for key in ("sha256", "size_bytes")):
            raise ValueError("Source differs from existing provenance")
        stream = next(item for item in original["ffprobe"]["streams"] if item["codec_type"] == "video")
        sources[game] = {"file": record, "stream": stream}
        requests = []
        for case in [case for case in selected if case["game"] == game]:
            event = case["event"]
            trace = data["traces"][event["selected_trace_index"]]
            case["historical_trace"] = trace
            case["rim_anchor_x"] = sum(event["final_find_shots_result"]["rim"][::2]) / 2
            forced = {**event, "triggered": True}
            requests.extend(census.workload([forced], data["traces"], max(0, data["cache"]["first_t"]),
                min(float(stream["duration"]), data["cache"]["last_t"]), Fraction(stream["avg_frame_rate"]))["requested_windows"])
        for index, window in enumerate(census.merge_windows(requests, Fraction(stream["avg_frame_rate"]))):
            windows.append({**window, "game": game, "name": f"{game}_{index}"})
    check_budget(windows)
    paths = [Path(__file__), ROOT / "ml/tools/test_rim_rescan_pilot.py", reviewed_path,
             source_rate.PROVENANCE, source_rate.BASELINE, ROOT / "ml/docs/rim_context_eval.md",
             ROOT / "ml/docs/rim_rescan_coverage.md"]
    paths += [CENSUS / name for name in ("mitty.json", "riordan.json", "summary.json", "inputs_after.json")]
    for name in ("rim_context_eval.py", "rim_source_rate_eval.py", "rim_rescan_coverage.py", "rim_outcome_audit.py",
                 "local_detector_baseline.py", "shots.py", "makes_eval.py"):
        paths.append(ROOT / "ml/tools" / name)
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and ("/yolox/" in path or "/ml/tools/" in path) and Path(path).is_file():
            paths.append(Path(path))
    old_inputs = load(CENSUS / "inputs_after.json")
    for relative, identity in old_inputs.items():
        if relative.startswith("ml/data/tracks/"):
            record = file_record(ROOT / relative)
            if any(record[key] != identity[key] for key in ("sha256", "size_bytes")):
                raise ValueError("Census cache changed")
            paths.append(ROOT / relative)
    import yolox
    paths.extend(Path(yolox.__file__).parent.rglob("*.py"))
    source_rate.checked_record(baseline["checkpoint"])
    frozen = {"selected": selected, "selection_failures": failures, "exclusions": exclusions,
        "selection_rule": "Required four triggers; nearest-time eligible accepted untriggered FG per game if available, otherwise eligible accepted FT; exclude prior blind-review and source-rescan intervals; ties ascending event_id. No image-based substitution.",
        "windows": windows, "sources": sources, "checkpoint": baseline["checkpoint"], "protocol": protocol,
        "dependencies": baseline["dependencies"], "files": [file_record(path) for path in sorted(set(paths))],
        "frame_cap": CAP, "window_cap": 6, "budget_seconds": SECONDS, "reuse_count": 0,
        "historical_limit": "No historical checkpoint/config/source-frame equivalence; historical calls are not paired comparisons.",
        "context_policy": "Existing merged envelope, shared dense initial above-rim prefix; independent modulo-three phases explicit missing context; prospective guard .4s measured separately from detection coverage.",
        "decoder_version": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]}
    create_output(OUTPUT)
    write_new(OUTPUT / "selection.json", frozen)
    (OUTPUT / "selection.json").chmod(0o444)
    print("Frozen before decoding:", digest(OUTPUT / "selection.json"), flush=True)
    for case in selected:
        print(case["stratum"], case["event"]["event_id"], flush=True)


def verify(frozen):
    source_rate.validate_protocol(frozen["protocol"])
    if (frozen["frame_cap"], frozen["window_cap"], frozen["budget_seconds"]) != (CAP, 6, SECONDS):
        raise ValueError("Budget changed")
    check_budget(frozen["windows"])
    for record in [*frozen["files"], frozen["checkpoint"], *[item["file"] for item in frozen["sources"].values()]]:
        source_rate.checked_record(record)
    if context.dependencies() != frozen["dependencies"]:
        raise ValueError("Dependencies changed")


def decode():
    frozen = load(OUTPUT / "selection.json")
    verify(frozen)
    samples, outcomes = [], []
    for window in frozen["windows"]:
        directory = OUTPUT / window["name"]
        directory.mkdir()
        source = frozen["sources"][window["game"]]
        path, stream = source["file"]["path"], source["stream"]
        try:
            packets = source_rate.probe(["-select_streams", "v:0", "-read_intervals", f"{window['start']}%{window['end'] + .05}",
                "-show_packets", "-show_entries", "packet=pts,dts,pos", path])["packets"]
            frames = source_rate.probe(["-select_streams", "v:0", "-read_intervals", f"{window['start']}%{window['end'] + .05}",
                "-show_frames", "-show_entries", "frame=pts,best_effort_timestamp,pkt_pos,pict_type", path])["frames"]
            aligned = align_frames(frames, packets, stream["time_base"], window["start"], window["end"])
            if len(samples) + len(aligned) > CAP:
                raise ValueError("Total actual frame budget exceeded")
            command = ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-threads", "1", "-copyts", "-ss", str(window["start"] - .001),
                "-t", str(window["end"] - window["start"] + .05), "-i", path, "-an", "-vf",
                f"select='between(pts,{aligned[0]['pts']},{aligned[-1]['pts']})',showinfo", "-fps_mode", "passthrough",
                "-frames:v", str(len(aligned)), "-threads", "1", str(directory / "frame_%03d.png")]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
            write_new(directory / "decoder.json", {"command": command, "stderr": completed.stderr, "packets": packets, "frames": frames})
            emitted = [(int(index), int(pts)) for index, pts in re.findall(r"n:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:", completed.stderr)]
            images = sorted(directory.glob("frame_*.png"))
            if len(images) != len(aligned) or [pts for _, pts in emitted] != [frame["pts"] for frame in aligned]:
                raise ValueError("Exact decoder/packet/PNG PTS mismatch")
            for frame, image, (index, _) in zip(aligned, images, emitted):
                samples.append({**frame, "packet_ordinal_scope": "bounded ffprobe read, not global source index",
                    "window": window["name"], "game": window["game"], "selected_decoder_index": index, "file": file_record(image)})
            outcomes.append({"window": window["name"], "status": "complete", "count": len(aligned),
                "first_pts": aligned[0]["pts"], "last_pts": aligned[-1]["pts"], "requested": window})
        except Exception as exception:
            outcomes.append({"window": window["name"], "status": "decode_failure", "error": repr(exception)})
    if samples:
        check_budget(frozen["windows"], samples)
    write_new(OUTPUT / "manifest.json", {"selection": file_record(OUTPUT / "selection.json"), "samples": samples, "decode_outcomes": outcomes})
    (OUTPUT / "manifest.json").chmod(0o444)


def infer():
    import cv2
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.exp import get_exp
    from yolox.utils import postprocess

    frozen, manifest = load(OUTPUT / "selection.json"), load(OUTPUT / "manifest.json")
    verify(frozen)
    source_rate.checked_record(manifest["selection"])
    for sample in manifest["samples"]:
        source_rate.checked_record(sample["file"])
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    torch.manual_seed(0)
    state = torch.load(frozen["checkpoint"]["path"], map_location="cpu", weights_only=True)
    if state["num_classes"] != 4 or state["input_size"] != 960:
        raise ValueError("Checkpoint metadata changed")
    experiment = get_exp(None, "yolox-m")
    experiment.num_classes = 4
    model = experiment.get_model()
    model.load_state_dict(state["model"], strict=True)
    model = model.cpu().float().eval()
    transform = ValTransform(legacy=False)
    started = time.monotonic()
    with (OUTPUT / "detections.jsonl").open("x") as handle:
        for sample in manifest["samples"]:
            frame_started = time.monotonic()
            image = cv2.imread(sample["file"]["path"])
            if image is None or image.shape != (1080, 1920, 3):
                raise ValueError("Native dimensions changed")
            ratio = min(960 / image.shape[0], 960 / image.shape[1])
            tensor, _ = transform(image, None, (960, 960))
            with torch.inference_mode():
                output = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()), 4,
                    conf_thre=.1, nms_thre=.45, class_agnostic=False)[0]
            retained = []
            for left, top, right, bottom, objectness, confidence, category in ([] if output is None else output.cpu().tolist()):
                if category not in (0, 3):
                    continue
                score = objectness * confidence
                retained.append({"category": int(category), "xyxy": [value / ratio for value in (left, top, right, bottom)],
                    "objectness": objectness, "class_confidence": confidence, "score": score,
                    "passes_class_cutoff": score >= CUTOFFS["ball" if category == 0 else "rim"]})
            handle.write(json.dumps({"sample": sample, "retained_postprocess_ball_rim": retained,
                "seconds": time.monotonic() - frame_started}, allow_nan=False) + "\n")
            handle.flush()
            print(sample["window"], sample["pts"], flush=True)
    loop_seconds = time.monotonic() - started
    verify(frozen)
    write_new(OUTPUT / "inference.json", {"status": "complete", "manifest": file_record(OUTPUT / "manifest.json"),
        "detections": file_record(OUTPUT / "detections.jsonl"), "loop_seconds": loop_seconds,
        "new_inferences": len(manifest["samples"]), "reuse_count": 0})


def evaluate(records, anchor):
    if not records:
        return {"status": "missing_records", "decision_not_evaluated": True}
    try:
        return context.evaluate(records, anchor)
    except ValueError as exception:
        if str(exception) != "No common initial in-zone above-rim observation":
            raise
        return {"status": "missing_initial_context", "decision_not_evaluated": True, "decoded_count": len(records)}


def comparison(dense, phase):
    if "decide_result" not in dense or "decide_result" not in phase:
        return "unknown"
    return "changed" if dense["decide_result"]["made"] != phase["decide_result"]["made"] else "unchanged"


def sheets(records, case):
    import cv2
    import numpy as np

    directory = OUTPUT / (case["event"]["event_id"].replace(":", "_"))
    directory.mkdir()
    tiles = []
    for record in records:
        sample = record["sample"]
        image = cv2.imread(sample["file"]["path"])
        rims = [row for row in record["retained_postprocess_ball_rim"] if row["category"] == 3 and row["passes_class_cutoff"]
                and abs(sum(row["xyxy"][::2]) / 2 - case["rim_anchor_x"]) < 150]
        center = round(sum(rims[0]["xyxy"][::2]) / 2) if rims else round(case["rim_anchor_x"])
        left = max(0, min(1500, center - 210))
        crop = image[40:400, left:left + 420].copy()
        banner = np.zeros((32, 420, 3), dtype=np.uint8)
        cv2.putText(banner, f"PTS {sample['pts']} t {sample['seconds']:.9f}", (5, 20), 0, .45, (255, 255, 255), 1)
        tiles.append(np.vstack([banner, crop]))
    for index in range(0, len(tiles), 12):
        subset = tiles[index:index + 12]
        subset += [np.zeros_like(subset[0])] * (-len(subset) % 4)
        image = np.vstack([np.hstack(subset[offset:offset + 4]) for offset in range(0, len(subset), 4)])
        path = directory / f"native_{index:03d}.png"
        if path.exists() or not cv2.imwrite(str(path), image):
            raise ValueError("Refusing image overwrite or write failure")


def analyze():
    frozen, manifest = load(OUTPUT / "selection.json"), load(OUTPUT / "manifest.json")
    verify(frozen)
    records = [json.loads(line) for line in (OUTPUT / "detections.jsonl").read_text().splitlines()] if (OUTPUT / "detections.jsonl").exists() else []
    if records != [] and [row["sample"] for row in records] != manifest["samples"][:len(records)]:
        raise ValueError("Inference ordering/identity mismatch")
    report = {"cases": [], "selection_failures": frozen["selection_failures"], "historical_limit": frozen["historical_limit"],
        "scope": "Conditional local-ROI decide; no full find_shots/rescue/dead-ball parity, truth labels, official scoring, or automatic stats gain."}
    for case in frozen["selected"]:
        window = next(window for window in frozen["windows"] if case["event"]["event_id"] in window["event_ids"])
        rows = [copy.deepcopy(row) for row in records if row["sample"]["window"] == window["name"]]
        for row in rows:
            row["sample"]["rim_anchor_x"] = case["rim_anchor_x"]
        dense = evaluate(rows, case["rim_anchor_x"])
        prefix = dense.get("attempt_path_starts_at")
        shared, independent = {}, {}
        for phase in range(3):
            shared[str(phase)] = evaluate([row for row in rows if prefix is not None and
                (row["sample"]["seconds"] <= prefix or row["sample"]["selected_decoder_index"] % 3 == phase)], case["rim_anchor_x"])
            independent[str(phase)] = evaluate([row for row in rows if row["sample"]["selected_decoder_index"] % 3 == phase], case["rim_anchor_x"])
        complete = len(rows) == sum(sample["window"] == window["name"] for sample in manifest["samples"]) and any(
            outcome["window"] == window["name"] and outcome["status"] == "complete" for outcome in manifest["decode_outcomes"])
        comparisons = {phase: comparison(dense, trace) if complete else "unknown" for phase, trace in shared.items()}
        report["cases"].append({"event_id": case["event"]["event_id"], "stratum": case["stratum"], "historical_made": case["event"]["made"],
            "window": window, "decoded_and_inferred_complete": complete, "dense": dense, "shared_prefix_until": prefix,
            "common_context_phases": shared, "independent_phases": independent, "paired_comparisons": comparisons,
            "case_result": "unknown" if "unknown" in comparisons.values() else ("changed" if "changed" in comparisons.values() else "unchanged")})
        if rows:
            sheets(rows, case)
    write_new(OUTPUT / "analysis.json", report)


def run():
    freeze()
    decode()
    started = time.monotonic()
    try:
        with (OUTPUT / "inference.log").open("x") as handle:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "infer"], stdout=handle,
                stderr=subprocess.STDOUT, timeout=SECONDS, check=True)
        status = "complete"
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exception:
        status = "bounded_failure"
        write_new(OUTPUT / "failure.json", {"status": status, "error": repr(exception)})
    write_new(OUTPUT / "budget.json", {"inference_child_wall_seconds": time.monotonic() - started, "cap_seconds": SECONDS, "status": status})
    analyze()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "decode", "infer", "analyze", "run"))
    stage = parser.parse_args().stage
    {"freeze": freeze, "decode": decode, "infer": infer, "analyze": analyze, "run": run}[stage]()


if __name__ == "__main__":
    main()
