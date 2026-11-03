"""Track players through a clip and sort each track into Valley or Opponent by jersey color.

Usage:
    ml/.venv/bin/python ml/tools/track_teams.py --game ontario-christian-high-school-game-angle-1 --start 600
    ml/.venv/bin/python ml/tools/track_teams.py --game ... --start 600 --run v1     # use a trained AIM model

Steps: detect players at 10 fps, link them across frames with ByteTrack, take the median
torso color of each track, and give the track to whichever team's jersey color
(ml/games.yaml) is closer. Tracks too close to call are marked "unsure".

Writes ml/runs/tracking/<game>_<start>[_<run>]/: sheet.jpg (boxes colored by team, with
track ids) and stats.json. With no labels for tracks yet, the checks are indirect:
long tracks are good, and more than 5 players per team in a frame means bench or crowd
people got in, or a player went to the wrong team.
"""

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import supervision as sv
import torch
import yaml
from yolox.data.data_augment import ValTransform
from yolox.exp import get_exp
from yolox.utils import postprocess

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
SIZE = 960

# Reference jersey colors in BGR; add one here when a new team color shows up in games.yaml.
JERSEY_BGR = {
    "light blue": (225, 190, 140),
    "white": (235, 235, 235),
    "black": (35, 35, 35),
}
TEAM_DRAW = {"Valley": (255, 160, 40), "Opponent": (40, 40, 230), "unsure": (160, 160, 160), "referee": (200, 80, 170)}


class Detector:
    """COCO YOLOX-M (person = player) or a trained AIM model (player and referee classes)."""

    def __init__(self, run: str | None):
        exp = get_exp(None, "yolox-m")
        if run:
            state = torch.load(ML / "runs" / run / "aim_yolox_m.pth", map_location="cpu", weights_only=False)
            exp.num_classes = state["num_classes"]
            self.classes = {1: "player", 2: "referee"}
            cutoffs = json.loads((ML / "runs" / run / "report.json").read_text())
            self.cutoff = {n: cutoffs[n]["cutoff"] for n in ("player", "referee")}
        else:
            state = torch.load(ML / "data" / "weights" / "yolox_m.pth", map_location="cpu", weights_only=False)
            self.classes = {0: "player"}
            self.cutoff = {"player": 0.5}
        self.exp = exp
        self.model = exp.get_model()
        self.model.load_state_dict(state["model"])
        self.model.eval()

    def __call__(self, image):
        h, w = image.shape[:2]
        ratio = min(SIZE / h, SIZE / w)
        tensor, _ = ValTransform(legacy=False)(image, None, (SIZE, SIZE))
        with torch.no_grad():
            out = postprocess(self.model(torch.from_numpy(tensor).unsqueeze(0).float()), self.exp.num_classes,
                              conf_thre=min(self.cutoff.values()), nms_thre=0.45)[0]
        rows = []
        for x0, y0, x1, y1, obj, cls_conf, cls in ([] if out is None else out.tolist()):
            name = self.classes.get(int(cls))
            if name and obj * cls_conf >= self.cutoff[name]:
                rows.append((x0 / ratio, y0 / ratio, x1 / ratio, y1 / ratio, obj * cls_conf, name))
        return rows


def torso_lab(image, box):
    """Median Lab color of the jersey area: middle half across, 20-50% down the box."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    crop = image[int(y0 + 0.2 * h):int(y0 + 0.5 * h), int(x0 + 0.25 * w):int(x1 - 0.25 * w)]
    if crop.size == 0:
        return None
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    return np.median(lab, axis=0)


def to_lab(bgr):
    return cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)


def feature(lab):
    """Gym light shifts brightness a lot and hue much less, so brightness counts for half."""
    return np.array([0.5 * lab[0], lab[1], lab[2]], dtype=np.float32)


def assign_teams(colors: dict, refs: dict, min_samples: int = 5) -> dict:
    """Split tracks into two color groups from this film, then name each group by the
    closer team color. Fixed reference colors alone fail: white looks gray under gym light."""
    meds = {tid: np.median(labs, axis=0) for tid, labs in colors.items()}
    steady = [tid for tid, labs in colors.items() if len(labs) >= min_samples]
    if len(steady) < 2:
        return {tid: "unsure" for tid in meds}
    data = np.stack([feature(meds[t]) for t in steady])
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, _, centers = cv2.kmeans(data, 2, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    (t0, r0), (t1, r1) = refs.items()
    # Pick the naming of the two groups that best matches the reference colors.
    keep = (np.linalg.norm(centers[0] - feature(r0)) + np.linalg.norm(centers[1] - feature(r1))
            <= np.linalg.norm(centers[0] - feature(r1)) + np.linalg.norm(centers[1] - feature(r0)))
    names = (t0, t1) if keep else (t1, t0)
    gap = float(np.linalg.norm(centers[0] - centers[1]))
    team = {}
    for tid, med in meds.items():
        d = [float(np.linalg.norm(feature(med) - c)) for c in centers]
        best = int(np.argmin(d))
        # Unsure when the track sits near the middle of the two groups.
        team[tid] = names[best] if d[1 - best] - d[best] >= 0.25 * gap else "unsure"
    return team


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    parser.add_argument("--start", type=float, default=600, help="clip start, seconds into the game")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--run", default=None, help="trained run in ml/runs/ (default: COCO model)")
    args = parser.parse_args()

    game = next(g for g in yaml.safe_load((ML / "games.yaml").read_text())["games"] if g["id"] == args.game)
    refs = {"Valley": to_lab(JERSEY_BGR[game["valley_jersey"]]), "Opponent": to_lab(JERSEY_BGR[game["opponent_jersey"]])}
    detector = Detector(args.run)
    tracker = sv.ByteTrack(frame_rate=args.fps, lost_track_buffer=3 * args.fps)

    video = cv2.VideoCapture(str(REPO / game["file"]))
    src_fps = video.get(cv2.CAP_PROP_FPS)
    video.set(cv2.CAP_PROP_POS_MSEC, args.start * 1000)
    step = max(1, round(src_fps / args.fps))
    frames, colors, started = [], {}, time.monotonic()
    index = 0
    while len(frames) < args.seconds * args.fps:
        ok, image = video.read()
        if not ok:
            break
        index += 1
        if (index - 1) % step:
            continue
        rows = detector(image)
        players = [r for r in rows if r[5] == "player"]
        dets = sv.Detections(
            xyxy=np.array([r[:4] for r in players], dtype=float).reshape(-1, 4),
            confidence=np.array([r[4] for r in players], dtype=float),
            class_id=np.zeros(len(players), dtype=int),
        )
        tracked = tracker.update_with_detections(dets)
        for box, tid in zip(tracked.xyxy, tracked.tracker_id):
            lab = torso_lab(image, box)
            if lab is not None:
                colors.setdefault(int(tid), []).append(lab)
        frames.append({
            "image": image if len(frames) % max(1, int(args.seconds * args.fps // 6)) == 0 else None,
            "tracks": [(box.tolist(), int(tid)) for box, tid in zip(tracked.xyxy, tracked.tracker_id)],
            "refs": [r[:4] for r in rows if r[5] == "referee"],
        })
    elapsed = time.monotonic() - started

    team = assign_teams(colors, refs)

    lengths = [len(v) / args.fps for v in colors.values()]
    per_frame = [{t: sum(1 for _, tid in f["tracks"] if team.get(tid) == t) for t in ("Valley", "Opponent")}
                 for f in frames]
    stats = {
        "game": args.game, "start": args.start, "seconds": len(frames) / args.fps, "model": args.run or "coco",
        "frames": len(frames), "seconds_per_frame": round(elapsed / max(1, len(frames)), 2),
        "tracks": len(colors), "tracks_1s_or_longer": sum(l >= 1 for l in lengths),
        "median_track_seconds": round(float(np.median(lengths)), 1) if lengths else 0,
        "tracks_by_team": {t: sum(1 for v in team.values() if v == t) for t in ("Valley", "Opponent", "unsure")},
        "avg_on_screen": {t: round(float(np.mean([p[t] for p in per_frame])), 1) for t in ("Valley", "Opponent")},
        "frames_with_over_5": {t: sum(p[t] > 5 for p in per_frame) for t in ("Valley", "Opponent")},
    }
    out = ML / "runs" / "tracking" / f"{args.game}_{int(args.start)}{'_' + args.run if args.run else ''}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.json").write_text(json.dumps(stats, indent=2))

    tiles = []
    for f in frames:
        if f["image"] is None:
            continue
        img = f["image"].copy()
        for box, tid in f["tracks"]:
            x0, y0, x1, y1 = map(int, box)
            c = TEAM_DRAW[team.get(tid, "unsure")]
            cv2.rectangle(img, (x0, y0), (x1, y1), c, 3)
            cv2.putText(img, str(tid), (x0, y0 - 8), 0, 1.0, c, 3)
        for x0, y0, x1, y1 in f["refs"]:
            cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), TEAM_DRAW["referee"], 3)
        tiles.append(cv2.resize(img, (800, 450)))
    tiles = tiles[:6] + [np.zeros((450, 800, 3), np.uint8)] * (6 - len(tiles[:6]))
    cv2.imwrite(str(out / "sheet.jpg"), np.vstack([np.hstack(tiles[0:3]), np.hstack(tiles[3:6])]),
                [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(json.dumps(stats, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
