"""Bounded, non-equivalent source-rate diagnostic; no production or label writes."""

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

from local_detector_baseline import CUTOFFS, digest, file_record, write_new
import shots
from rim_outcome_audit import explain


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/rim_source_rate_20261112"
BASELINE = ROOT / "ml/data/labels/local_detector_baseline_20261112/manifest.json"
AUDIT = ROOT / "ml/data/labels/rim_outcome_audit_20261112/audit.json"
PROVENANCE = ROOT / "ml/data/labels/blind_film_review_20261112/provenance.json"
WINDOWS = (("disputed", "4422.7", "4423.9", 1325),
           ("positive", "866.4", "866.9", 573))
CAP = 70
SECONDS = 180


def checked_record(record):
    if file_record(record["path"]) != record:
        raise ValueError(f"Frozen input changed: {record['path']}")


def validate_protocol(protocol):
    expected = {"device": "cpu", "dtype": "float32", "threads": 4,
                "interop_threads": 1, "opencv_threads": 1, "seed": 0,
                "input_size": 960, "architecture": "yolox-m", "num_classes": 4,
                "score_floor": 0.1, "class_cutoffs": CUTOFFS,
                "nms": 0.45, "class_agnostic": False,
                "serialization": "torch.load(map_location='cpu', weights_only=True); no unsafe fallback"}
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f"Baseline protocol changed: {key}")
    return copy.deepcopy(protocol)


def create_output(path):
    if path.resolve() != OUTPUT.resolve() or path.is_symlink():
        raise ValueError("Only the dedicated new private artifact directory is allowed")
    path.mkdir(mode=0o700, parents=False, exist_ok=False)


def align_frames(decoded, packets, time_base, start, end):
    by_position = {str(packet["pos"]): (index, packet)
                   for index, packet in enumerate(packets)}
    retained = []
    for decoder_index, frame in enumerate(decoded):
        pts = int(frame["pts"])
        seconds = pts * Fraction(time_base)
        if not Fraction(start) <= seconds <= Fraction(end):
            continue
        index, packet = by_position[str(frame["pkt_pos"])]
        if int(packet["pts"]) != pts or int(frame["best_effort_timestamp"]) != pts:
            raise ValueError("Packet/decoder PTS mismatch")
        retained.append({"pts": pts, "time_base": time_base,
                         "seconds": float(seconds), "seconds_fraction": str(seconds),
                         "source_video_sample_index": index,
                         "probe_decoder_index": decoder_index,
                         "packet_position": int(frame["pkt_pos"]),
                         "picture_type": frame["pict_type"]})
    if not retained or len(retained) > CAP:
        raise ValueError("Empty or over-budget decoded window")
    if any(after["pts"] <= before["pts"] for before, after in zip(retained, retained[1:])):
        raise ValueError("Non-monotonic or duplicate PTS")
    return retained


def probe(arguments):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", *arguments,
                                               "-of", "json"], timeout=60))


def prepare():
    recovering_empty_decode = (OUTPUT.exists()
                               and {path.name for path in OUTPUT.iterdir()} == {"failed_preparation"}
                               and {path.name for path in (OUTPUT / "failed_preparation").iterdir()} == {"decode.log"})
    if OUTPUT.exists() and not recovering_empty_decode:
        raise FileExistsError("Refusing to overwrite prior experiment")
    baseline = json.loads(BASELINE.read_text())
    protocol = validate_protocol(baseline["protocol"])
    for record in baseline["files"]:
        checked_record(record)
    checked_record(baseline["checkpoint"])
    audit = json.loads(AUDIT.read_text())
    for path, checksum in audit["inputs_sha256"].items():
        if digest(ROOT / path) != checksum:
            raise ValueError(f"Audit input changed: {path}")
    source_record = json.loads(PROVENANCE.read_text())["sources"]["riordan"]
    source = ROOT / source_record["path"]
    if digest(source) != source_record["sha256"] or source.stat().st_size != source_record["size_bytes"]:
        raise ValueError("Source differs from frozen film provenance")
    stream = probe(["-select_streams", "v:0", "-show_streams", str(source)])["streams"][0]
    packets = probe(["-select_streams", "v:0", "-show_packets", "-show_entries",
                     "packet=pts,dts,pos,duration,flags", str(source)])["packets"]
    if (stream["has_b_frames"] != 0 or len(packets) != int(stream["nb_frames"])
            or any(packet["pts"] != packet["dts"] for packet in packets)
            or any(after["pts"] <= before["pts"] for before, after in zip(packets, packets[1:]))):
        raise ValueError("Cannot establish monotonic MP4 sample/PTS identity")
    if not recovering_empty_decode:
        create_output(OUTPUT)
    samples, commands = [], []
    for name, start, end, anchor in WINDOWS:
        directory = OUTPUT / name
        directory.mkdir()
        frames = probe(["-select_streams", "v:0", "-read_intervals", f"{start}%{float(end) + 0.01}",
                        "-show_frames", "-show_entries",
                        "frame=pts,best_effort_timestamp,pkt_pos,pict_type", str(source)])["frames"]
        aligned = align_frames(frames, packets, stream["time_base"], start, end)
        command = ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-threads", "1", "-copyts",
                   "-ss", str(float(start) - 0.001), "-t", str(float(end) - float(start) + 0.02),
                   "-i", str(source),
                   "-an", "-vf", f"select='between(pts,{aligned[0]['pts']},{aligned[-1]['pts']})',showinfo",
                   "-fps_mode", "passthrough", "-frames:v", str(len(aligned)),
                   "-threads", "1", str(directory / "frame_%03d.png")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
        (directory / "decode.log").write_text(completed.stderr)
        emitted = [(int(index), int(pts)) for index, pts in re.findall(
            r"n:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:", completed.stderr)]
        images = sorted(directory.glob("frame_*.png"))
        if len(images) != len(aligned) or [pts for _, pts in emitted] != [frame["pts"] for frame in aligned]:
            raise ValueError("Decoded PNG/ffprobe exact PTS alignment failed")
        commands.append(command)
        for frame, image, (index, _) in zip(aligned, images, emitted):
            samples.append({**frame, "window": name, "rim_anchor_x": anchor,
                            "selected_decoder_index": index, "file": file_record(image)})
    if len(samples) > CAP:
        raise ValueError("Total extraction cap exceeded")
    dependencies = {name: importlib.metadata.version(name) for name in baseline["dependencies"]
                    if name != "cv2"}
    import cv2
    dependencies["cv2"] = cv2.__version__
    if dependencies != baseline["dependencies"]:
        raise ValueError("Dependencies differ from frozen baseline")
    manifest = {
        "status": "fresh_non_equivalent_to_historical_cache",
        "historical_limit": "Cache contains model name/fps but no checkpoint hash, config or actual source PTS/frame identity; no exact historical-frame comparisons are asserted.",
        "baseline_manifest": file_record(BASELINE), "checkpoint": baseline["checkpoint"],
        "source": file_record(source), "stream": stream, "video_packet_count": len(packets),
        "index_semantics": "source_video_sample_index is zero-based MP4 video packet/sample ordinal matched by decoder pkt_pos, not time*fps; selected_decoder_index is showinfo n after bounded selection. probe_decoder_index includes seek preroll. Global decoder frame ordinal is not assumed.",
        "protocol": protocol, "budget_seconds": SECONDS, "frame_cap": CAP,
        "dependencies": dependencies, "samples": samples, "extraction_commands": commands,
        "decoder_version": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
        "files": [file_record(Path(__file__)), file_record(AUDIT), file_record(PROVENANCE),
                  file_record(ROOT / "ml/tools/shots.py"), file_record(ROOT / "ml/tools/rim_outcome_audit.py"),
                  *baseline["files"], file_record(source)] + [sample["file"] for sample in samples],
    }
    write_new(OUTPUT / "manifest.json", manifest)
    (OUTPUT / "manifest.json").chmod(0o444)
    print(f"Frozen {len(samples)} full frames; manifest {digest(OUTPUT / 'manifest.json')}", flush=True)


def verify_experiment(manifest):
    validate_protocol(manifest["protocol"])
    if not 0 < len(manifest["samples"]) <= CAP or manifest["budget_seconds"] != SECONDS:
        raise ValueError("Invalid experiment budget")
    for record in manifest["files"]:
        checked_record(record)


def infer():
    import cv2
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.exp import get_exp
    from yolox.utils import postprocess

    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    verify_experiment(manifest)
    manifest_sha = digest(OUTPUT / "manifest.json")
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    torch.manual_seed(0)
    state = torch.load(manifest["checkpoint"]["path"], map_location="cpu", weights_only=True)
    if state["num_classes"] != 4 or state["input_size"] != 960:
        raise ValueError("Pinned checkpoint metadata mismatch")
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
            if image is None or image.shape[:2] != (1080, 1920):
                raise ValueError("Full-frame decode dimensions changed")
            ratio = min(960 / image.shape[0], 960 / image.shape[1])
            tensor, _ = transform(image, None, (960, 960))
            with torch.inference_mode():
                output = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()),
                                     4, conf_thre=0.1, nms_thre=0.45, class_agnostic=False)[0]
            retained = []
            for left, top, right, bottom, objectness, confidence, category in (
                    [] if output is None else output.cpu().tolist()):
                if category not in (0, 3):
                    continue
                score = objectness * confidence
                retained.append({"category": int(category), "xyxy": [coordinate / ratio for coordinate in
                                 (left, top, right, bottom)], "objectness": objectness,
                                 "class_confidence": confidence, "score": score,
                                 "passes_class_cutoff": score >= CUTOFFS["ball" if category == 0 else "rim"]})
            record = {"sample": sample, "retained_postprocess_ball_rim": retained,
                      "seconds": time.monotonic() - frame_started}
            handle.write(json.dumps(record, allow_nan=False) + "\n")
            handle.flush()
            print(f"{sample['window']} PTS={sample['pts']} t={sample['seconds']:.6f} {record['seconds']:.3f}s", flush=True)
    verify_experiment(manifest)
    if digest(OUTPUT / "manifest.json") != manifest_sha:
        raise ValueError("Manifest mutated")
    write_new(OUTPUT / "inference.json", {"status": "complete", "manifest_sha256": manifest_sha,
              "inference_seconds": time.monotonic() - started, "provenance_verified_after": True,
              "outputs": "All retained ball/rim rows after score floor .1 and class-aware NMS .45; not logits, pre-NMS or below-floor detections."})


def observed_path(records, anchor):
    selected, previous = [], None
    for record in records:
        sample = record["sample"]
        time_seconds = sample["seconds"]
        boxes = [[row["category"], *row["xyxy"], row["score"], -1]
                 for row in record["retained_postprocess_ball_rim"] if row["passes_class_cutoff"]]
        rims = [box for box in boxes if box[0] == 3 and abs((box[1] + box[3]) / 2 - anchor) < 150]
        recent = previous[:2] if previous and time_seconds - previous[2] <= 0.5 else None
        ball = shots.best_ball(boxes, recent)
        if ball is None or not rims:
            continue
        rim = min(rims, key=lambda box: abs((box[1] + box[3]) / 2 - anchor))
        center_x, center_y = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
        previous = (center_x, center_y, time_seconds)
        if (abs(center_x - (rim[1] + rim[3]) / 2) < 3 * (rim[3] - rim[1])
                and center_y < rim[4] + 6 * (rim[4] - rim[2])):
            selected.append({"point": [time_seconds, center_x, center_y, *rim[1:5]],
                             "sample": sample, "ball_score": ball[5], "rim_score": rim[5]})
    return selected


def path_decision(selected, observed_until):
    if not selected:
        return {"status": "no_observed_path"}
    first = selected[0]
    shot = {"t": first["point"][0], "rim": first["point"][3:],
            "ball_score": first["ball_score"], "rim_score": first["rim_score"],
            "path": [point["point"] for point in selected]}
    return explain(shot, observed_until)


def analyze():
    import cv2
    import numpy as np

    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    verify_experiment(manifest)
    records = [json.loads(line) for line in (OUTPUT / "detections.jsonl").read_text().splitlines()]
    if len(records) != len(manifest["samples"]):
        raise ValueError("Incomplete inference; no complete decision claims")
    report = {"historical_comparisons": [], "historical_alignment": manifest["historical_limit"],
              "context_limit": "Conditional decide() on observed bounded paths, no interpolation. Local rim anchor is audit ROI, not full-game game_rims/ceiling selection; no initial rescue/still-ball/open-shot state, global attempt counting, dead-ball veto or whole find_shots parity.",
              "windows": {}}
    for name, start, end, anchor in WINDOWS:
        window_records = [record for record in records if record["sample"]["window"] == name]
        selected = observed_path(window_records, anchor)
        end_time = window_records[-1]["sample"]["seconds"]
        phases = {str(phase): path_decision([point for point in selected
                  if point["sample"]["selected_decoder_index"] % 3 == phase], end_time)
                  for phase in range(3)}
        report["windows"][name] = {"observed_samples": selected,
            "dense": path_decision(selected, end_time), "fresh_decimated_phases": phases,
            "sample_count": len(window_records), "actual_observed_until": end_time,
            "requested_window": [start, end]}
        tiles = []
        for record in window_records:
            sample = record["sample"]
            image = cv2.imread(sample["file"]["path"])
            for row in record["retained_postprocess_ball_rim"]:
                color = (0, 220, 0) if row["passes_class_cutoff"] else (0, 140, 255)
                left, top, right, bottom = [round(value) for value in row["xyxy"]]
                cv2.rectangle(image, (left, top), (right, bottom), color, 1)
                cv2.putText(image, f"{row['category']}:{row['score']:.3f}", (left, max(12, top - 3)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
            left, right = anchor - 190, anchor + 230
            crop = image[0:520, left:right].copy()
            banner = np.zeros((48, crop.shape[1], 3), dtype=np.uint8)
            cv2.putText(banner, f"PTS {sample['pts']} * {sample['time_base']}", (6, 17), 0, 0.48, (255, 255, 255), 1)
            cv2.putText(banner, f"t={sample['seconds']:.6f} sample={sample['source_video_sample_index']}",
                        (6, 37), 0, 0.44, (255, 255, 255), 1)
            tile = np.vstack([banner, crop])
            overlay = OUTPUT / name / f"overlay_{sample['selected_decoder_index']:03d}.png"
            if overlay.exists():
                raise FileExistsError(overlay)
            if not cv2.imwrite(str(overlay), tile):
                raise ValueError("Overlay encode failed")
            tiles.append(tile)
        for batch in range(0, len(tiles), 8):
            subset = tiles[batch:batch + 8]
            subset += [np.zeros_like(subset[0])] * (-len(subset) % 4)
            sheet = np.vstack([np.hstack(subset[index:index + 4]) for index in range(0, len(subset), 4)])
            cv2.imwrite(str(OUTPUT / name / f"sheet_{batch:03d}.png"), sheet)
    write_new(OUTPUT / "analysis.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "run", "infer", "analyze"))
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
    elif args.stage == "infer":
        infer()
    elif args.stage == "analyze":
        analyze()
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
        write_new(OUTPUT / "budget.json", {"wall_seconds": time.monotonic() - started,
                                          "cap_seconds": SECONDS})
        analyze()


if __name__ == "__main__":
    main()
