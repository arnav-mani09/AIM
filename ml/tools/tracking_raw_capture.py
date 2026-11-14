"""Private bounded native-frame detector input capture; never changes production."""

import argparse
from fractions import Fraction
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from local_detector_baseline import CUTOFFS, digest, file_record, write_new
from rim_source_rate_eval import align_frames, checked_record, probe, validate_protocol


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/tracking_raw_capture_20261113"
BASELINE = ROOT / "ml/data/labels/local_detector_baseline_20261112/manifest.json"
PROVENANCE = ROOT / "ml/data/labels/blind_film_review_20261112/provenance.json"
WINDOWS = (("mitty", "253.1"), ("mitty", "1150.7"),
           ("riordan", "3613.3"), ("riordan", "5496.8"))
TRACKER = dict(track_activation_threshold=0.5, frame_rate=10, lost_track_buffer=30,
               minimum_matching_threshold=0.8, minimum_consecutive_frames=1)
SECONDS = 400


def select_frames(frames, time_base, start, end):
    """Nearest real PTS to inclusive 0.1s targets; earlier PTS breaks ties."""
    start, end, base = Fraction(start), Fraction(end), Fraction(time_base)
    candidates = [(index, frame) for index, frame in enumerate(frames)
                  if start <= int(frame["pts"]) * base <= end]
    if not candidates or end - start != 6:
        raise ValueError("Expected a nonempty exact six-second window")
    if any(int(after[1]["pts"]) <= int(before[1]["pts"])
           for before, after in zip(candidates, candidates[1:])):
        raise ValueError("Non-monotonic PTS")
    selected = {}
    for target_index in range(61):
        target = start + Fraction(target_index, 10)
        index, frame = min(candidates, key=lambda item:
                           (abs(int(item[1]["pts"]) * base - target), int(item[1]["pts"])))
        selected[int(frame["pts"])] = (index, frame)
    return [selected[pts] for pts in sorted(selected)]


def torso_lab(image, box):
    import cv2
    import numpy as np

    left, top, right, bottom = map(float, box)
    width, height = right - left, bottom - top
    if not all(math.isfinite(value) for value in box) or width <= 0 or height <= 0:
        return {"lab": None, "status": "invalid_box", "crop_xyxy": None}
    requested = [int(left + .25 * width), int(top + .2 * height),
                 int(right - .25 * width), int(top + .5 * height)]
    image_height, image_width = image.shape[:2]
    clipped = [max(0, min(limit, value)) for value, limit in
               zip(requested, (image_width, image_height, image_width, image_height))]
    x0, y0, x1, y1 = clipped
    empty = x1 <= x0 or y1 <= y0
    lab = None if empty else np.median(cv2.cvtColor(image[y0:y1, x0:x1],
                       cv2.COLOR_BGR2LAB).reshape(-1, 3), axis=0).tolist()
    return {"lab": lab, "status": "empty_crop" if empty else "ok",
            "requested_crop_xyxy": requested, "crop_xyxy": clipped,
            "clipped": clipped != requested, "pixels": max(0, x1-x0) * max(0, y1-y0),
            "occlusion_assessed": False,
            "meaning": "local OpenCV uint8 Lab team-appearance evidence, not person identity"}


def pack_detections(detections):
    fields = ("xyxy", "confidence", "class_id", "tracker_id", "mask")
    return {"arrays": {field: None if getattr(detections, field) is None else
                       {"dtype": str(getattr(detections, field).dtype),
                        "shape": list(getattr(detections, field).shape),
                        "values": getattr(detections, field).tolist()} for field in fields},
            "data": {}, "metadata": {}}


def unpack_detections(payload):
    import numpy as np
    import supervision as sv

    arrays = {}
    for name, record in payload["arrays"].items():
        arrays[name] = None if record is None else np.asarray(record["values"],
                      dtype=record["dtype"]).reshape(record["shape"])
    if payload["data"] or payload["metadata"]:
        raise ValueError("Only original worker empty data/metadata supported")
    return sv.Detections(**arrays)


def read_lines(path):
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    records = []
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
    return records


def append_record(handle, record):
    handle.write(json.dumps(record, allow_nan=False) + "\n")
    handle.flush()


def verify(manifest):
    validate_protocol(manifest["protocol"])
    if manifest["tracker"] != TRACKER or manifest["budget_seconds"] != SECONDS:
        raise ValueError("Configuration changed")
    if not 0 < len(manifest["samples"]) <= 244:
        raise ValueError("Invalid frame budget")
    for record in manifest["files"]:
        checked_record(record)


def prepare():
    if OUTPUT.exists():
        raise FileExistsError("Never overwrite or retry the private capture")
    baseline = json.loads(BASELINE.read_text())
    protocol = validate_protocol(baseline["protocol"])
    for record in baseline["files"]:
        checked_record(record)
    sources = json.loads(PROVENANCE.read_text())["sources"]
    OUTPUT.mkdir(mode=0o700)
    source_records, streams, packets_by_game = {}, {}, {}
    for game in ("mitty", "riordan"):
        frozen = sources[game]
        source = ROOT / frozen["path"]
        record = file_record(source)
        if record["sha256"] != frozen["sha256"] or record["size_bytes"] != frozen["size_bytes"]:
            raise ValueError("Source no longer matches frozen provenance")
        stream = probe(["-select_streams", "v:0", "-show_streams", str(source)])["streams"][0]
        packets = probe(["-select_streams", "v:0", "-show_packets", "-show_entries",
                         "packet=pts,dts,pos,duration,flags", str(source)])["packets"]
        if (stream["has_b_frames"] != 0 or len(packets) != int(stream["nb_frames"])
                or any(packet["pts"] != packet["dts"] for packet in packets)):
            raise ValueError("Source packet ordinal cannot establish frame identity")
        source_records[game], streams[game], packets_by_game[game] = record, stream, packets
        write_new(OUTPUT / f"{game}_packets.json", packets)
    samples, commands = [], []
    for game, event in WINDOWS:
        start, end = Fraction(event)-3, Fraction(event)+3
        name = f"{game}_{event}"
        directory = OUTPUT / name
        directory.mkdir()
        source, stream = source_records[game]["path"], streams[game]
        arguments = ["-select_streams", "v:0", "-read_intervals", f"{float(start)}%{float(end)+.05}",
                     "-show_frames", "-show_entries", "frame=pts,best_effort_timestamp,pkt_pos,pict_type", source]
        decoded = probe(arguments)["frames"]
        selection = select_frames(decoded, stream["time_base"], start, end)
        aligned = align_frames([frame for _, frame in selection], packets_by_game[game],
                               stream["time_base"], start, end)
        expression = "+".join(f"eq(pts,{frame['pts']})" for frame in aligned)
        command = ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-threads", "1", "-copyts",
                   "-ss", str(float(start)-.001), "-t", "6.05", "-i", source, "-an",
                   "-vf", f"select='{expression}',showinfo", "-fps_mode", "passthrough",
                   "-frames:v", str(len(aligned)), "-threads", "1", str(directory / "frame_%03d.png")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=True)
        (directory / "decode.log").write_text(completed.stderr)
        emitted = [(int(index), int(pts)) for index, pts in re.findall(
            r"n:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:", completed.stderr)]
        images = sorted(directory.glob("frame_*.png"))
        if ([pts for _, pts in emitted] != [frame["pts"] for frame in aligned]
                or len(images) != len(aligned)):
            raise ValueError("Exact packet/decoder/showinfo/PNG alignment failed")
        commands.append({"probe": arguments, "decode": command})
        for frame, image, (probe_index, _), (selected_index, _) in zip(aligned, images, selection, emitted):
            samples.append({**frame, "probe_decoder_index": probe_index,
                            "selected_decoder_index": selected_index, "window": name, "game": game,
                            "event": event, "start": str(start), "end": str(end), "file": file_record(image),
                            "native_width": stream["width"], "native_height": stream["height"]})
    import supervision
    import yolox
    packages = [Path(supervision.__file__).parent, Path(yolox.__file__).parent]
    files = [file_record(path) for package in packages for path in sorted(package.rglob("*.py"))]
    files += [file_record(Path(__file__)), file_record(ROOT / "ml/tools/test_tracking_raw_capture.py"),
              file_record(BASELINE), file_record(PROVENANCE), *baseline["files"],
              *source_records.values(), *[sample["file"] for sample in samples],
              *[file_record(OUTPUT / f"{game}_packets.json") for game in source_records],
              file_record(ROOT / "ml/tools/rim_source_rate_eval.py")]
    manifest = {"schema": 1, "protocol": protocol, "tracker": TRACKER, "budget_seconds": SECONDS,
                "checkpoint": baseline["checkpoint"], "sources": source_records, "streams": streams,
                "samples": samples, "commands": commands,
                "selection": "61 targets start+k/10 seconds, k=0..60; nearest in-window real integer PTS, earlier tie, deduplicate",
                "tracker_history": "Independent cold-start per window, sequential selected frames including empties; no production history",
                "frame_index_semantics": "zero-based source video packet ordinal matched using pkt_pos and exact PTS; no time*fps index",
                "dependencies": {name: importlib.metadata.version(name) for name in
                                 ("torch", "torchvision", "numpy", "scipy", "supervision", "yolox", "opencv-python")},
                "python": sys.version, "executable": sys.executable,
                "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
                "files": list({record["path"]: record for record in files}.values())}
    write_new(OUTPUT / "manifest.json", manifest)
    (OUTPUT / "manifest.json").chmod(0o444)
    print(f"Prepared {len(samples)} native frames", flush=True)


def infer():
    import cv2
    import numpy as np
    import supervision as sv
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.exp import get_exp
    from yolox.utils import postprocess

    if sv.__version__ != "0.26.1":
        raise ValueError("Requires actual supervision 0.26.1")
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    verify(manifest)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    cv2.setNumThreads(1)
    state = torch.load(manifest["checkpoint"]["path"], map_location="cpu", weights_only=True)
    if state["num_classes"] != 4 or state["input_size"] != 960:
        raise ValueError("Checkpoint metadata mismatch")
    experiment = get_exp(None, "yolox-m")
    experiment.num_classes = 4
    model = experiment.get_model()
    model.load_state_dict(state["model"], strict=True)
    model = model.cpu().float().eval()
    transform = ValTransform(legacy=False)
    window, tracker = None, None
    with (OUTPUT / "inputs.jsonl").open("x") as inputs, (OUTPUT / "outputs.jsonl").open("x") as outputs:
        for sample_index, sample in enumerate(manifest["samples"]):
            started = time.monotonic()
            if sample["window"] != window:
                window, tracker = sample["window"], sv.ByteTrack(**TRACKER)
            image = cv2.imread(sample["file"]["path"])
            if image is None or image.shape[:2] != (sample["native_height"], sample["native_width"]):
                raise ValueError("Native dimensions changed")
            ratio = min(960/image.shape[0], 960/image.shape[1])
            tensor, _ = transform(image, None, (960, 960))
            with torch.inference_mode():
                output = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()),
                                     4, conf_thre=.1, nms_thre=.45, class_agnostic=False)[0]
            rows = [] if output is None else output.cpu().numpy()
            proposals, player_indices = [], []
            for postprocess_index, row in enumerate(rows):
                left, top, right, bottom, obj, confidence, category = row
                category = int(category)
                if category not in (1, 2):
                    continue
                score = float(obj * confidence)
                box = [float(value / ratio) for value in (left, top, right, bottom)]
                passes = score >= CUTOFFS["player" if category == 1 else "referee"]
                proposal = {"postprocess_index": postprocess_index, "class_id": category,
                            "postprocess_row_float32": row.tolist(), "xyxy": box,
                            "objectness": float(obj), "class_confidence": float(confidence),
                            "score": score, "passes_class_cutoff": passes,
                            "torso": torso_lab(image, box)}
                if category == 1 and passes:
                    player_indices.append(len(proposals))
                proposals.append(proposal)
            dets = sv.Detections(xyxy=np.array([proposals[index]["xyxy"] for index in player_indices],
                                dtype=float).reshape(-1, 4),
                                confidence=np.array([proposals[index]["score"] for index in player_indices], dtype=float),
                                class_id=np.full(len(player_indices), 1, dtype=int))
            record = {"sample_index": sample_index, "window": window, "pts": sample["pts"],
                      "proposals": proposals, "player_proposal_indices": player_indices,
                      "detections": pack_detections(dets)}
            append_record(inputs, record)
            tracked = tracker.update_with_detections(dets)
            append_record(outputs, {"sample_index": sample_index, "window": window, "pts": sample["pts"],
                                    "detections": pack_detections(tracked)})
            print(f"{sample_index+1}/{len(manifest['samples'])} {window} pts={sample['pts']} "
                  f"proposals={len(proposals)} inputs={len(player_indices)} outputs={len(tracked)} "
                  f"{time.monotonic()-started:.3f}s", flush=True)
    verify(manifest)
    write_new(OUTPUT / "inference_verified.json", {"status": "complete", "provenance_verified_after": True})


def replay_records(inputs, expected):
    import supervision as sv

    if sv.__version__ != "0.26.1":
        raise ValueError("Actual tracker version mismatch")
    tracker, window, replayed = None, None, []
    for record in inputs:
        if record["window"] != window:
            window, tracker = record["window"], sv.ByteTrack(**TRACKER)
        output = tracker.update_with_detections(unpack_detections(record["detections"]))
        replayed.append({key: record[key] for key in ("sample_index", "window", "pts")})
        replayed[-1]["detections"] = pack_detections(output)
    if replayed[:len(expected)] != expected or len(expected) > len(replayed):
        raise ValueError("Fresh capture output parity failed")
    return replayed


def replay():
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    verify(manifest)
    inputs, expected = read_lines(OUTPUT / "inputs.jsonl"), read_lines(OUTPUT / "outputs.jsonl")
    replayed = replay_records(inputs, expected)
    write_new(OUTPUT / "replayed_outputs.json", replayed)
    result = {"status": "complete" if len(inputs) == len(expected) == len(manifest["samples"]) else "partial",
              "captured_inputs": len(inputs), "captured_outputs": len(expected),
              "replayed_inputs": len(replayed), "exact_parity_frames": len(expected),
              "manifest_sha256": digest(OUTPUT / "manifest.json"),
              "inputs": file_record(OUTPUT / "inputs.jsonl"), "outputs": file_record(OUTPUT / "outputs.jsonl"),
              "replay": file_record(OUTPUT / "replayed_outputs.json"), "provenance_verified": True,
              "identity_scope": "exact array values/dtypes/shapes and IDs versus fresh CPU capture only; not historical/GPU equivalence"}
    write_new(OUTPUT / "replay.json", result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "infer", "replay"))
    args = parser.parse_args()
    if args.mode == "infer":
        infer()
    elif args.mode == "replay":
        replay()
    else:
        prepare()
        environment = {**os.environ, **{key: "4" for key in
                       ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}}
        started = time.monotonic()
        status, returncode = "partial_timeout", None
        with (OUTPUT / "inference.log").open("x") as log:
            try:
                completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "infer"],
                                           stdout=log, stderr=subprocess.STDOUT, env=environment, timeout=SECONDS)
                returncode = completed.returncode
                status = "complete" if returncode == 0 else "partial_failure"
            except subprocess.TimeoutExpired:
                pass
        write_new(OUTPUT / "capture_status.json", {"status": status, "returncode": returncode,
                  "hard_child_budget_seconds": SECONDS, "elapsed_seconds": time.monotonic()-started,
                  "budget_includes": "process startup/imports, verification, model load, inference, final verification",
                  "attempts": 1, "retry": False})
        replay()


if __name__ == "__main__":
    main()
