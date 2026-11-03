"""Player detection and tracking for a whole game, used by film_worker.detect_players.

Reads frames at 10 fps from ffmpeg, runs the AIM YOLOX detector on the GPU in batches,
links player boxes into tracks with ByteTrack, and keeps each track's jersey color so
the backend can name the two teams once it knows their colors.
"""

import subprocess
from pathlib import Path

import cv2
import numpy as np
import supervision as sv
import torch
import torch.nn.functional as F

CLASSES = {0: "ball", 1: "player", 2: "referee", 3: "rim"}
PLAYER = 1
MAX_HEIGHT = 1080  # the detector was trained on 1080p frames
PAD_VALUE = 114.0  # YOLOX pads with gray


def load_model(weights: Path, device: str = "cuda"):
    from yolox.exp import get_exp

    state = torch.load(weights, map_location="cpu", weights_only=False)
    exp = get_exp(None, "yolox-m")
    exp.num_classes = state["num_classes"]
    model = exp.get_model()
    model.load_state_dict(state["model"])
    model = model.to(device).eval()
    if device == "cuda":
        model = model.half()
    return model, exp.num_classes, state["input_size"]


def output_size(width: int, height: int) -> tuple[int, int]:
    """Frame size the detector sees: at most MAX_HEIGHT tall, even width. Boxes use it."""
    out_h = min(height, MAX_HEIGHT)
    return round(width * out_h / height / 2) * 2, out_h


def read_frames(path: Path, fps: int, width: int, height: int):
    """Yield (seconds, BGR frame) at `fps`, scaled to output_size()."""
    out_w, out_h = output_size(width, height)
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={out_w}:{out_h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=out_w * out_h * 3 * 4)
    size, index = out_w * out_h * 3, 0
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield index / fps, np.frombuffer(buf, np.uint8).reshape(out_h, out_w, 3)
            index += 1
    finally:
        proc.stdout.close()
        proc.wait()


def preprocess(frames: list, size: int, device: str):
    """Resize and pad a batch on the GPU the way YOLOX's ValTransform does on the CPU."""
    h, w = frames[0].shape[:2]
    ratio = min(size / h, size / w)
    batch = torch.from_numpy(np.stack(frames)).to(device).permute(0, 3, 1, 2).float()
    batch = F.interpolate(batch, size=(int(h * ratio), int(w * ratio)), mode="bilinear", align_corners=False)
    padded = torch.full((len(frames), 3, size, size), PAD_VALUE, device=device)
    padded[:, :, : batch.shape[2], : batch.shape[3]] = batch
    return (padded.half() if device == "cuda" else padded), ratio


def torso_lab(image, box):
    """Median Lab color of the jersey area: middle half across, 20-50% down the box."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    crop = image[int(y0 + 0.2 * h):int(y0 + 0.5 * h), int(x0 + 0.25 * w):int(x1 - 0.25 * w)]
    if crop.size == 0:
        return None
    return np.median(cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3), axis=0)


def color_groups(colors: dict, min_samples: int = 5) -> dict:
    """Split tracks into two jersey-color groups (0 and 1), or "unsure" near the middle.
    Gym light shifts brightness much more than hue, so brightness counts for half."""
    feature = lambda lab: np.array([0.5 * lab[0], lab[1], lab[2]], dtype=np.float32)
    meds = {tid: np.median(labs, axis=0) for tid, labs in colors.items()}
    steady = [tid for tid, labs in colors.items() if len(labs) >= min_samples]
    if len(steady) < 2:
        return {"centers_lab": [], "track_group": {str(t): "unsure" for t in meds}}
    data = np.stack([feature(meds[t]) for t in steady])
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, _, centers = cv2.kmeans(data, 2, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    gap = float(np.linalg.norm(centers[0] - centers[1]))
    groups = {}
    for tid, med in meds.items():
        d = [float(np.linalg.norm(feature(med) - c)) for c in centers]
        best = int(np.argmin(d))
        groups[str(tid)] = best if d[1 - best] - d[best] >= 0.25 * gap else "unsure"
    # Centers back in plain Lab (brightness un-halved) so they can be compared to jersey colors.
    return {"centers_lab": [[float(c[0] * 2), float(c[1]), float(c[2])] for c in centers], "track_group": groups}


def detect_and_track(path: Path, info: dict, weights: Path, model_version: str, fps: int = 10,
                     batch_size: int = 16, cutoffs: dict | None = None, new_track_score: float = 0.5,
                     device: str = "cuda", log=print) -> dict:
    """Run the detector over the whole game. Returns the tracks document (see film_worker).

    Player boxes down to cutoffs["player"] go to ByteTrack, which uses the weak ones only to
    keep existing tracks alive; a new track needs a box scoring new_track_score or more."""
    cutoffs = cutoffs or {"ball": 0.2, "player": 0.1, "referee": 0.35, "rim": 0.5}
    from yolox.utils import postprocess

    model, num_classes, size = load_model(weights, device)
    tracker = sv.ByteTrack(track_activation_threshold=new_track_score, frame_rate=fps, lost_track_buffer=3 * fps)
    frames_out, colors, spans = [], {}, {}
    pending: list = []
    min_cut = min(cutoffs.values())

    def flush():
        images = [img for _, img in pending]
        tensor, ratio = preprocess(images, size, device)
        with torch.no_grad():
            outputs = postprocess(model(tensor).float(), num_classes, conf_thre=min_cut, nms_thre=0.45)
        for (t, image), out in zip(pending, outputs):
            rows = [] if out is None else out.cpu().numpy()
            keep = []
            for x0, y0, x1, y1, obj, cls_conf, cls in rows:
                name, score = CLASSES[int(cls)], float(obj * cls_conf)
                if score >= cutoffs[name]:
                    keep.append((int(cls), *(float(v / ratio) for v in (x0, y0, x1, y1)), score))
            players = [k for k in keep if k[0] == PLAYER]
            dets = sv.Detections(
                xyxy=np.array([k[1:5] for k in players], dtype=float).reshape(-1, 4),
                confidence=np.array([k[5] for k in players], dtype=float),
                class_id=np.full(len(players), PLAYER, dtype=int),
            )
            tracked = tracker.update_with_detections(dets)
            boxes = [[c, round(a, 1), round(b, 1), round(x, 1), round(y, 1), round(s, 3), -1]
                     for c, a, b, x, y, s in keep if c != PLAYER]
            for box, score, tid in zip(tracked.xyxy, tracked.confidence, tracked.tracker_id):
                tid = int(tid)
                boxes.append([PLAYER, *[round(float(v), 1) for v in box], round(float(score), 3), tid])
                lab = torso_lab(image, box)
                if lab is not None:
                    colors.setdefault(tid, []).append(lab)
                span = spans.setdefault(tid, [t, t, 0])
                span[1], span[2] = t, span[2] + 1
            frames_out.append([round(t, 2), boxes])
        pending.clear()

    next_log = 300  # seconds of game
    for t, image in read_frames(path, fps, info["width"], info["height"]):
        pending.append((t, image))
        if len(pending) == batch_size:
            flush()
            if t >= next_log:
                log(f"detected {t / 60:.0f} min")
                next_log += 300
    if pending:
        flush()

    groups = color_groups(colors)
    tracks = {
        str(tid): {"start": s, "end": e, "frames": n, "group": groups["track_group"].get(str(tid), "unsure"),
                   "color_lab": [round(float(v), 1) for v in np.median(colors[tid], axis=0)] if tid in colors else None}
        for tid, (s, e, n) in spans.items()
    }
    return {
        "version": 1,
        "model": model_version,
        "fps": fps,
        "classes": CLASSES,
        "box_format": "[class, x0, y0, x1, y1, score, track_id]; track_id is -1 for ball, referee and rim",
        "frame_size": list(output_size(info["width"], info["height"])),
        "group_centers_lab": groups["centers_lab"],
        "tracks": tracks,
        "frames": frames_out,
    }
