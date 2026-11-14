"""One append-only, predetermined offline safety batch; no truth or runtime writes."""

import argparse
import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

import rim_context_eval as context
import rim_source_rate_eval as source
import shots
from local_detector_baseline import CUTOFFS, digest, file_record, write_new


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/rim_rescan_safety_20261113"
MANIFEST = OUTPUT / "manifest_revised.json"
CENSUS = ROOT / "ml/data/labels/rim_rescan_coverage_20261112"
GAMES = ("mitty", "riordan")
CAP = 500
SECONDS = 600
PRIOR = tuple(ROOT / "ml/data/labels" / name for name in (
    "rim_source_rate_20261112", "rim_context_20261112", "rim_rescan_pilot_20261113"))
REVIEW = ROOT / "ml/data/labels/blind_film_review_20261112/observations.frozen.json"


def load(path):
    return json.loads(Path(path).read_text())


def create_output(path):
    if path != OUTPUT or path.is_symlink() or path.resolve() != OUTPUT:
        raise ValueError("Only the dedicated new safety directory is allowed")
    path.mkdir(mode=0o700, exist_ok=False)


def envelope(event, data, stream):
    trace = data["traces"][event["selected_trace_index"]]
    path = trace["path"]
    crossing = trace.get("first_under_net")
    end = max(event["t"] + shots.MAKE_WINDOW, path[-1][0], trace["observed_until"],
              crossing["point"][0] + .4 if crossing else event["t"])
    start = max(0, data["cache"]["first_t"], min(event["t"], path[0][0]) - .5)
    end = min(float(stream["duration"]), data["cache"]["last_t"], end + .5)
    return {"start": start, "end": end, "event_ids": [event["event_id"]],
            "estimated_frames": math.ceil((Fraction(str(end)) - Fraction(str(start))) *
                                          Fraction(stream["avg_frame_rate"])) + 1}


def prior_exclusions():
    intervals = {game: [] for game in GAMES}
    identities = {game: set() for game in GAMES}
    for entry in load(REVIEW)["window_coverage"]:
        game = entry["window"].split("_")[0]
        intervals[game].append({"interval": entry["requested_interval_s"], "origin": str(REVIEW)})
    for directory in PRIOR:
        for path in sorted(set(directory.rglob("*manifest*.json")) | set(directory.glob("selection.json"))):
            data = load(path)
            for window in data.get("windows", []):
                if isinstance(window, dict):
                    game, start, end = window["game"], window["start"], window["end"]
                    identities[game].update(window["event_ids"])
                else:
                    game, (_, start, end, _) = "riordan", window
                intervals[game].append({"interval": [float(start), float(end)], "origin": str(path)})
            for case in data.get("selected", []):
                identities[case["game"]].add(case["event"]["event_id"])
            for command in data.get("extraction_commands", []):
                start = float(command[command.index("-ss") + 1])
                end = start + float(command[command.index("-t") + 1])
                intervals["riordan"].append({"interval": [start, end], "origin": str(path)})
            for game in GAMES:
                samples = [sample for sample in data.get("samples", []) if sample.get("game", "riordan") == game]
                for name in sorted({sample["window"] for sample in samples}):
                    times = [sample["seconds"] for sample in samples if sample["window"] == name]
                    intervals[game].append({"interval": [min(times), max(times)], "origin": str(path)})
    return intervals, identities


def select(games, streams, intervals, identities):
    selected, failures, audit = [], [], {}
    for game in GAMES:
        data = games[game]
        available = []
        excluded = []
        for event in data["events"]:
            if event["cohort"] != "eligible_game" or not event["made"]:
                continue
            window = envelope(event, data, streams[game])
            overlaps = [entry for entry in intervals[game]
                        if window["start"] <= entry["interval"][1] and entry["interval"][0] <= window["end"]]
            if event["event_id"] in identities[game] or overlaps:
                excluded.append({"event_id": event["event_id"], "prior_id": event["event_id"] in identities[game],
                                 "overlaps": overlaps, "window": window})
            else:
                available.append(event)
        audit[game] = {"excluded": excluded, "available_trigger_ids": [event["event_id"] for event in available if event["triggered"]]}
        picked = []
        for category in ("FG", "FT"):
            strict = [event for event in available if event["triggered"] and event["category"] == category and event not in picked]
            if not strict:
                failures.append({"game": game, "requested_stratum": category,
                                 "status": "unavailable_after_prior_id_and_envelope_exclusions"})
            pool = strict or [event for event in available if event["triggered"] and event not in picked]
            event = min(pool, key=lambda item: (item["t"], item["event_id"]), default=None)
            if event is None:
                raise ValueError("Cannot select two new triggers in the same game")
            picked.append(event)
            selected.append({"game": game, "stratum": "trigger", "requested_category": category,
                             "fallback": not bool(strict), "event": event})
        reference = next((event for event in picked if event["category"] == "FG"), picked[0])
        pool = [event for event in available if not event["triggered"] and event["category"] == "FG"]
        control = min(pool, key=lambda item: (abs(item["t"] - reference["t"]), item["event_id"]), default=None)
        if control is None:
            failures.append({"game": game, "requested_stratum": "untriggered_FG_control", "status": "unavailable"})
        else:
            selected.append({"game": game, "stratum": "untriggered_control", "reference_event_id": reference["event_id"], "event": control})
    return selected, failures, audit


def check_budget(windows, samples=None):
    if len(windows) > 6 or sum(window["estimated_frames"] for window in windows) > CAP:
        raise ValueError("Frozen window/frame budget exceeded")
    if samples is not None and (not samples or len(samples) > CAP):
        raise ValueError("Actual native-frame budget exceeded")


def freeze():
    if OUTPUT.exists():
        raise FileExistsError("Refusing existing evidence, including incomplete batches")
    games = {game: load(CENSUS / f"{game}.json") for game in GAMES}
    provenance, baseline = load(source.PROVENANCE), load(source.BASELINE)
    protocol = source.validate_protocol(baseline["protocol"])
    sources = {}
    for game in GAMES:
        original = provenance["sources"][game]
        record = file_record(ROOT / original["path"])
        if any(record[key] != original[key] for key in ("sha256", "size_bytes")):
            raise ValueError("Source film changed")
        stream = next(item for item in original["ffprobe"]["streams"] if item["codec_type"] == "video")
        sources[game] = {"file": record, "stream": stream}
    intervals, identities = prior_exclusions()
    selected, failures, exclusions = select(games, {game: value["stream"] for game, value in sources.items()}, intervals, identities)
    windows = []
    for case in selected:
        game, event = case["game"], case["event"]
        case["rim_anchor_x"] = sum(event["final_find_shots_result"]["rim"][::2]) / 2
        window = envelope(event, games[game], sources[game]["stream"])
        windows.append({**window, "game": game, "name": f"{game}_{len(windows)}"})
    check_budget(windows)
    if context.dependencies() != baseline["dependencies"]:
        raise ValueError("Pinned dependency versions changed")
    paths = [Path(__file__), Path(__file__).with_name("test_rim_rescan_safety.py"), REVIEW,
             source.PROVENANCE, source.BASELINE]
    paths += list(CENSUS.glob("*.json"))
    paths += [ROOT / "ml/docs" / name for name in ("rim_context_eval.md", "rim_rescan_coverage.md", "rim_rescan_pilot.md")]
    paths += [path for directory in PRIOR for path in directory.rglob("*") if path.is_file()]
    for relative, identity in load(CENSUS / "inputs_after.json").items():
        if relative.startswith("ml/data/tracks/"):
            record = file_record(ROOT / relative)
            if any(record[key] != identity[key] for key in ("sha256", "size_bytes")):
                raise ValueError("Census cache changed")
            paths.append(ROOT / relative)
    import yolox
    paths += list(Path(yolox.__file__).parent.rglob("*.py"))
    paths += [Path(module.__file__) for module in list(sys.modules.values())
              if getattr(module, "__file__", None) and "/ml/tools/" in module.__file__ and Path(module.__file__).is_file()]
    source.checked_record(baseline["checkpoint"])
    frozen = {"selected": selected, "selection_failures": failures, "exclusions": exclusions,
        "excluded_intervals": intervals, "excluded_event_ids": {game: sorted(values) for game, values in identities.items()},
        "selection_rule": "Per game earliest eligible accepted trigger FG, then FT; unavailable category falls back earliest remaining trigger in same game. Envelope overlap or prior event ID excluded. Ties event_id. Nearest accepted eligible untriggered FG control to first selected FG (else first selected attempt), same exclusions, ties event_id. No outcome-based substitutions.",
        "windows": windows, "sources": sources, "checkpoint": baseline["checkpoint"], "protocol": protocol,
        "dependencies": baseline["dependencies"], "files": [file_record(path) for path in sorted(set(paths))],
        "frame_cap": CAP, "window_cap": 6, "budget_seconds": SECONDS, "reuse_count": 0,
        "context_policy": "Census envelope unchanged; dense observed above-rim prefix shared before three fresh modulo-three phases; independent phases separately; unchanged full prospective .4s guards, missing detections separate.",
        "historical_limit": "No historical-box alignment, checkpoint equivalence, outcome truth, stat gain or production override.",
        "decoder_version": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]}
    create_output(OUTPUT)
    write_new(OUTPUT / "selection.json", frozen)
    (OUTPUT / "selection.json").chmod(0o444)
    print("Frozen before decode:", digest(OUTPUT / "selection.json"), flush=True)
    for case in selected:
        print(case["stratum"], case["event"]["event_id"], "fallback", case.get("fallback", False), flush=True)


def verify(frozen):
    source.validate_protocol(frozen["protocol"])
    if (frozen["frame_cap"], frozen["window_cap"], frozen["budget_seconds"]) != (CAP, 6, SECONDS):
        raise ValueError("Budget changed")
    check_budget(frozen["windows"])
    revision_path = OUTPUT / "decode_revision.json"
    revision = load(revision_path) if revision_path.exists() else None
    if revision:
        source.checked_record(revision["selection"])
    for record in [*frozen["files"], frozen["checkpoint"], *[item["file"] for item in frozen["sources"].values()]]:
        replacement = next((entry for entry in revision["owned_sources"] if entry["original"] == record), None) if revision else None
        if replacement:
            source.checked_record(replacement["snapshot"])
            if any(replacement["snapshot"][key] != record[key] for key in ("sha256", "size_bytes")):
                raise ValueError("Frozen source snapshot mismatch")
            if replacement["current"]["path"] != record["path"] or Path(record["path"]).name not in ("rim_rescan_safety.py", "test_rim_rescan_safety.py"):
                raise ValueError("Unowned revision")
            source.checked_record(replacement["current"])
        else:
            source.checked_record(record)
    if context.dependencies() != frozen["dependencies"]:
        raise ValueError("Dependencies changed")


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


def decode():
    frozen = load(OUTPUT / "selection.json")
    verify(frozen)
    samples, outcomes = [], []
    for window in frozen["windows"]:
        started = time.monotonic()
        directory = OUTPUT / (window["name"] + "_decoded")
        directory.mkdir()
        film = frozen["sources"][window["game"]]
        path, stream = film["file"]["path"], film["stream"]
        try:
            arguments = ["-select_streams", "v:0", "-read_intervals", f"{window['start']}%{window['end'] + .05}"]
            packets = source.probe([*arguments, "-show_packets", "-show_entries", "packet=pts,dts,pos", path])["packets"]
            if stream["has_b_frames"] or any(packet["pts"] != packet["dts"] for packet in packets):
                raise ValueError("Unproven packet/decoder ordering")
            frames = source.probe([*arguments, "-show_frames", "-show_entries", "frame=pts,best_effort_timestamp,pkt_pos,pict_type", path])["frames"]
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
                samples.append({**frame, "packet_ordinal_scope": "bounded probe only, not global frame ordinal",
                    "window": window["name"], "game": window["game"], "selected_decoder_index": index, "file": file_record(image)})
            outcomes.append({"window": window["name"], "status": "complete", "count": len(aligned), "seconds": time.monotonic() - started})
        except Exception as exception:
            outcomes.append({"window": window["name"], "status": "decode_failure", "error": repr(exception), "seconds": time.monotonic() - started})
    if samples:
        check_budget(frozen["windows"], samples)
    write_new(MANIFEST, {"selection": file_record(OUTPUT / "selection.json"), "revision": file_record(OUTPUT / "decode_revision.json"),
                         "samples": samples, "decode_outcomes": outcomes})
    MANIFEST.chmod(0o444)


def sheets():
    import cv2
    import numpy as np

    frozen, manifest = load(OUTPUT / "selection.json"), load(MANIFEST)
    inventory = []
    for case, window in zip(frozen["selected"], frozen["windows"]):
        tiles = []
        samples = [sample for sample in manifest["samples"] if sample["window"] == window["name"]]
        left = max(0, min(1500, round(case["rim_anchor_x"]) - 210))
        for sample in samples:
            image = cv2.imread(sample["file"]["path"])
            crop = image[40:400, left:left + 420].copy()
            banner = np.zeros((28, 420, 3), dtype=np.uint8)
            cv2.putText(banner, f"PTS {sample['pts']} t {sample['seconds']:.9f}", (4, 19), 0, .44, (255, 255, 255), 1)
            tiles.append(np.vstack([banner, crop]))
        for offset in range(0, len(tiles), 12):
            subset = tiles[offset:offset + 12]
            subset += [np.zeros_like(subset[0])] * (-len(subset) % 4)
            image = np.vstack([np.hstack(subset[index:index + 4]) for index in range(0, len(subset), 4)])
            path = OUTPUT / f"{window['name']}_native_{offset:03d}.png"
            if path.exists() or not cv2.imwrite(str(path), image):
                raise ValueError("Refusing sheet overwrite or write failure")
            inventory.append({"event_id": case["event"]["event_id"], "file": file_record(path), "samples": samples[offset:offset + 12]})
    write_new(OUTPUT / "sheets_revised.json", inventory)


def infer():
    import cv2
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.exp import get_exp
    from yolox.utils import postprocess

    frozen, manifest = load(OUTPUT / "selection.json"), load(MANIFEST)
    verify(frozen)
    source.checked_record(manifest["selection"])
    source.checked_record(manifest["revision"])
    check_budget(frozen["windows"], manifest["samples"])
    for sample in manifest["samples"]:
        source.checked_record(sample["file"])
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
    loop_seconds = time.monotonic() - started
    verify(frozen)
    write_new(OUTPUT / "inference.json", {"status": "complete", "manifest_sha256": digest(MANIFEST),
        "loop_wall_seconds": loop_seconds, "new_inferences": len(manifest["samples"]), "reuse_count": 0})


def bounded_inference():
    if any((OUTPUT / name).exists() for name in ("budget.json", "inference.log", "detections.jsonl")):
        raise FileExistsError("No inference retries or budget resets")
    started = time.monotonic()
    status = "complete"
    try:
        with (OUTPUT / "inference.log").open("x") as handle:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "infer-child"], stdout=handle,
                           stderr=subprocess.STDOUT, timeout=SECONDS, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exception:
        status = "bounded_failure"
        write_new(OUTPUT / "failure.json", {"status": status, "error": repr(exception)})
    write_new(OUTPUT / "budget.json", {"status": status, "inference_child_wall_seconds": time.monotonic() - started,
                                     "cap_seconds": SECONDS})


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
    return "unchanged" if dense["decide_result"]["made"] == phase["decide_result"]["made"] else "changed"


def analyze():
    frozen, manifest = load(OUTPUT / "selection.json"), load(MANIFEST)
    verify(frozen)
    source.checked_record(manifest["selection"])
    source.checked_record(manifest["revision"])
    records = [json.loads(line) for line in (OUTPUT / "detections.jsonl").read_text().splitlines()] if (OUTPUT / "detections.jsonl").exists() else []
    if [row["sample"] for row in records] != manifest["samples"][:len(records)]:
        raise ValueError("Inference ordering/identity mismatch")
    report = {"cases": [], "selection_failures": frozen["selection_failures"], "historical_limit": frozen["historical_limit"],
              "scope": "Conditional local-ROI decide, not full-game replay. Unknown is not miss. No truth inputs or official credit."}
    complete_run = (OUTPUT / "inference.json").exists() and load(OUTPUT / "budget.json")["status"] == "complete"
    if complete_run and load(OUTPUT / "inference.json")["manifest_sha256"] != digest(MANIFEST):
        raise ValueError("Completion manifest mismatch")
    for case, window in zip(frozen["selected"], frozen["windows"]):
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
        complete = complete_run and len(rows) == sum(sample["window"] == window["name"] for sample in manifest["samples"]) and any(
            outcome["window"] == window["name"] and outcome["status"] == "complete" for outcome in manifest["decode_outcomes"])
        comparisons = {phase: comparison(dense, trace) if complete else "unknown" for phase, trace in shared.items()}
        missing = {"ball_pts": [], "local_rim_pts": []}
        for row in rows:
            retained = [item for item in row["retained_postprocess_ball_rim"] if item["passes_class_cutoff"]]
            if not any(item["category"] == 0 for item in retained):
                missing["ball_pts"].append(row["sample"]["pts"])
            if not any(item["category"] == 3 and abs(sum(item["xyxy"][::2]) / 2 - case["rim_anchor_x"]) < 150 for item in retained):
                missing["local_rim_pts"].append(row["sample"]["pts"])
        report["cases"].append({"event_id": case["event"]["event_id"], "stratum": case["stratum"], "window": window,
            "decoded_and_inferred_complete": complete, "dense": dense, "shared_prefix_until": prefix,
            "common_context_phases": shared, "independent_phases": independent, "paired_comparisons": comparisons,
            "missing_detections_whole_window": missing, "frame_count": len(rows), "frame_loop_wall_seconds": sum(row["seconds"] for row in rows),
            "case_result": "unknown" if "unknown" in comparisons.values() else ("changed" if "changed" in comparisons.values() else "unchanged")})
    write_new(OUTPUT / "analysis.json", report)
    write_new(OUTPUT / "integrity.json", {"frozen_inputs_unchanged": True, "selection": file_record(OUTPUT / "selection.json"),
        "manifest": file_record(MANIFEST), "detections": file_record(OUTPUT / "detections.jsonl") if records else None,
        "frame_count": len(records), "complete": complete_run and len(records) == len(manifest["samples"])})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "decode", "sheets", "infer", "infer-child", "analyze", "verify"))
    stage = parser.parse_args().stage
    if stage == "verify":
        verify(load(OUTPUT / "selection.json"))
    else:
        {"freeze": freeze, "decode": decode, "sheets": sheets, "infer": bounded_inference,
         "infer-child": infer, "analyze": analyze}[stage]()


if __name__ == "__main__":
    main()
