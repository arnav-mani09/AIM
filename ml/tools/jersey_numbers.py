"""Read jersey numbers per player track (first prototype).

Usage (all steps from the ml venv; Modal login comes from ~/.modal.toml):
    ml/.venv/bin/python ml/tools/jersey_numbers.py crops ml/data/tracks/<game>.v4.json --video "backend/sample_data/<game>.mp4"
    ml/.venv/bin/python ml/tools/jersey_numbers.py read  ml/data/jerseys/<game>.v4.crops.pkl [--local]
    ml/.venv/bin/python ml/tools/jersey_numbers.py vote  ml/data/tracks/<game>.v4.json [--sheet 30]

Steps:
1. crops: for each player track seen for at least 3 s, pick up to 12 moments where the player is
   big enough (box at least 150 px tall), the detector is sure, and no other player or referee
   covers the torso. Cut the torso (top 10% to 55% of the box) out of the film. Runs on the laptop
   (film decoding, about 5 minutes per game with 4 processes).
2. read: EasyOCR, digits only, on each crop after a contrast boost and a zoom to 240 px tall.
   About 0.3 s per crop on a laptop, so by default it runs on Modal T4 GPUs in parallel.
3. vote: per track, the most common reading wins if at least 2 crops agree and it has at least
   half of the readings. Tracks often switch to another player partway through (about 11k tracks
   per game), so a split vote is expected and those tracks get no number.

Writes ml/data/jerseys/<game>.v4.{crops.pkl, reads.json, jerseys.json} and, with --sheet, a contact
sheet of random accepted tracks for a hand check. Everything stays in ml/data (gitignored): the
crops show minors.
"""

import argparse
import json
import pickle
import random
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

ML = Path(__file__).resolve().parents[1]
OUT = ML / "data" / "jerseys"

MIN_TRACK_FRAMES = 30   # 3 s at 10 fps; shorter tracks are mostly fragments
MIN_HEIGHT = 150        # px at 1080p; smaller players' numbers are a few pixels tall
MIN_SCORE = 0.8
MAX_COVER = 0.15        # share of the torso another box may cover
CROPS_PER_TRACK = 12
MIN_CANDIDATES = 3
READ_HEIGHT = 240
MIN_READ_CONF = 0.3


def torso(b):
    x0, y0, x1, y1 = b[1:5]
    w, h = x1 - x0, y1 - y0
    return x0 - 0.05 * w, y0 + 0.10 * h, x1 + 0.05 * w, y0 + 0.55 * h


def covered(rect, other):
    ix = max(0.0, min(rect[2], other[3]) - max(rect[0], other[1]))
    iy = max(0.0, min(rect[3], other[4]) - max(rect[1], other[2]))
    return ix * iy / ((rect[2] - rect[0]) * (rect[3] - rect[1]))


# ---------- step 1: crops ----------

def pick_crops(doc: dict) -> dict:
    """track id -> list of (time, torso rect) to cut, spread evenly over the track."""
    cands = defaultdict(list)
    for t, boxes in doc["frames"]:
        people = [b for b in boxes if b[0] in (1, 2)]
        for b in people:
            if b[0] != 1 or b[4] - b[2] < MIN_HEIGHT or b[5] < MIN_SCORE:
                continue
            r = torso(b)
            if any(o is not b and covered(r, o) > MAX_COVER for o in people):
                continue
            cands[b[6]].append((t, r))
    picks = {}
    for tid, info in doc["tracks"].items():
        c = cands.get(int(tid), [])
        if info["frames"] < MIN_TRACK_FRAMES or len(c) < MIN_CANDIDATES:
            continue
        n = min(CROPS_PER_TRACK, len(c))
        picks[tid] = [c[round(i * (len(c) - 1) / max(1, n - 1))] for i in range(n)]
    return picks


def _cut(job):
    """Decode one stretch of the film and cut the crops whose frames fall in it."""
    import cv2

    video, fps, wants = job  # wants: sorted [(frame index, track id, rect)]
    cap = cv2.VideoCapture(video)
    out, pos, i = [], -1, 0
    while i < len(wants):
        target = wants[i][0]
        if pos < 0 or target - pos > 150:
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            pos = target - 1
        while pos < target:
            cap.grab()
            pos += 1
        ok, img = cap.retrieve()
        while i < len(wants) and wants[i][0] == target:
            _, tid, (x0, y0, x1, y1) = wants[i]
            if ok:
                H, W = img.shape[:2]
                c = img[max(0, int(y0)):min(H, int(y1)), max(0, int(x0)):min(W, int(x1))]
                if c.size:
                    out.append((tid, round(target / fps, 2), cv2.imencode(".jpg", c, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()))
            i += 1
    return out


def make_crops(tracks: Path, video: Path, workers: int = 4) -> Path:
    import cv2

    doc = json.loads(tracks.read_text())
    picks = pick_crops(doc)
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    wants = sorted((round(t * fps), tid, r) for tid, items in picks.items() for t, r in items)
    chunk = -(-len(wants) // workers)
    jobs = [(str(video), fps, wants[k:k + chunk]) for k in range(0, len(wants), chunk)]
    with Pool(workers) as pool:
        crops = [c for part in pool.map(_cut, jobs) for c in part]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (tracks.stem + ".crops.pkl")
    path.write_bytes(pickle.dumps(crops))
    print(f"{len(picks)} tracks, {len(crops)} crops -> {path}")
    return path


# ---------- step 2: read ----------

def read_batch(jpegs: list[bytes], gpu) -> list[list]:
    """EasyOCR readings for each crop: [[text, confidence], ...] with 1 or 2 digits."""
    import cv2
    import easyocr
    import numpy as np

    reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)
    clahe = cv2.createCLAHE(2.0, (4, 4))
    out = []
    for jpg in jpegs:
        c = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        s = READ_HEIGHT / c.shape[0]
        c = cv2.resize(c, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        lab = cv2.cvtColor(c, cv2.COLOR_BGR2LAB)
        lab[..., 0] = clahe.apply(lab[..., 0])
        c = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        res = reader.readtext(c, allowlist="0123456789", text_threshold=0.5, low_text=0.3, mag_ratio=1.5)
        out.append([[txt, round(float(cf), 3)] for _, txt, cf in res if 1 <= len(txt) <= 2])
    return out


try:  # the GPU reader; Modal also imports this file inside its containers
    import modal
except ImportError:
    modal = None

if modal:
    app = modal.App("aim-jersey-numbers")
    image = (
        modal.Image.debian_slim(python_version="3.10")
        .pip_install("easyocr==1.7.2", "opencv-python-headless==4.10.0.84", "numpy<2")
        .run_commands("python -c \"import easyocr; easyocr.Reader(['en'], gpu=False)\"")
    )

    @app.function(image=image, gpu="T4", timeout=1800, max_containers=20)
    def remote_read(jpegs: list[bytes]) -> list[list]:
        return read_batch(jpegs, gpu=True)


def read_crops(crops_path: Path, local: bool) -> Path:
    crops = pickle.loads(crops_path.read_bytes())
    jpegs = [c[2] for c in crops]
    if local:
        reads = read_batch(jpegs, gpu="mps")
    else:
        size = 1500
        with app.run():
            parts = list(remote_read.map([jpegs[k:k + size] for k in range(0, len(jpegs), size)]))
        reads = [r for p in parts for r in p]
    path = crops_path.with_name(crops_path.name.replace(".crops.pkl", ".reads.json"))
    path.write_text(json.dumps([[tid, t, r] for (tid, t, _), r in zip(crops, reads)]))
    print(f"{len(reads)} crops read, {sum(1 for r in reads if r)} with digits -> {path}")
    return path


# ---------- step 3: vote ----------

def best_reading(r: list) -> str | None:
    r = [x for x in r if x[1] >= MIN_READ_CONF and not (len(x[0]) == 2 and x[0][0] == "0" and x[0] != "00")]
    return max(r, key=lambda x: x[1])[0] if r else None


def vote(reads: list) -> dict:
    per = defaultdict(list)
    for tid, t, r in reads:
        per[tid].append(best_reading(r))
    result = {}
    for tid, rs in per.items():
        got = [x for x in rs if x]
        if not got:
            result[tid] = {"number": None, "crops": len(rs), "reads": 0}
            continue
        (num, agree), = Counter(got).most_common(1)
        share = agree / len(got)
        ok = agree >= 2 and share >= 0.5
        result[tid] = {"number": num if ok else None, "crops": len(rs), "reads": len(got), "agree": agree,
                       "confidence": round(share * min(1.0, agree / 4), 2) if ok else 0.0,
                       "votes": dict(Counter(got).most_common(4))}
    return result


def team_names(doc: dict) -> dict:
    """Group 0/1 -> Valley/Opponent. Every test game so far is Valley light blue vs white, so the
    lighter group (higher L in Lab) is the opponent. Revisit when a game has other colors."""
    L = [c[0] for c in doc["group_centers_lab"]]
    light = 0 if L[0] > L[1] else 1
    return {light: "Opponent (white)", 1 - light: "Valley (light blue)", "unsure": "unsure"}


def sheet(crops_path: Path, result: dict, n: int, out: Path) -> list:
    import cv2
    import numpy as np

    crops = pickle.loads(crops_path.read_bytes())
    by = defaultdict(list)
    for tid, t, jpg in crops:
        by[tid].append(jpg)
    random.seed(1)
    picked = random.sample(sorted(k for k, v in result.items() if v["number"]), n)
    rows = []
    for k, tid in enumerate(picked):
        jp = by[tid]
        tiles = []
        for j in [round(i * (len(jp) - 1) / 5) for i in range(6)]:
            img = cv2.imdecode(np.frombuffer(jp[j], np.uint8), cv2.IMREAD_COLOR)
            tiles.append(cv2.resize(img, (90, 110)))
        label = np.zeros((110, 110, 3), np.uint8)
        cv2.putText(label, f"#{k + 1}", (4, 30), 0, 0.8, (0, 255, 255), 2)
        cv2.putText(label, result[tid]["number"], (4, 85), 0, 1.4, (255, 255, 255), 3)
        rows.append(np.hstack([label] + tiles))
    half = -(-len(rows) // 2)
    for part, rs in ((1, rows[:half]), (2, rows[half:])):
        cv2.imwrite(str(out.with_name(out.stem + f"_{part}.jpg")), np.vstack(rs), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return picked


def report(tracks: Path, n_sheet: int) -> None:
    doc = json.loads(tracks.read_text())
    reads_path = OUT / (tracks.stem + ".reads.json")
    result = vote(json.loads(reads_path.read_text()))
    (OUT / (tracks.stem + ".jerseys.json")).write_text(json.dumps(result, indent=1))
    names = team_names(doc)
    numbered = {k: v for k, v in result.items() if v["number"]}
    long_tracks = [k for k, v in doc["tracks"].items() if v["frames"] >= MIN_TRACK_FRAMES]
    seconds = lambda ks: sum(doc["tracks"][k]["frames"] for k in ks) / 10
    print(f"{len(long_tracks)} tracks of 3 s or more, {len(result)} had usable crops, {len(numbered)} got a number")
    print(f"screen time covered: {seconds(numbered) / 60:.0f} of {seconds(long_tracks) / 60:.0f} player-minutes")
    team_time = defaultdict(Counter)
    for k, v in numbered.items():
        team_time[names[doc["tracks"][k]["group"]]][v["number"]] += doc["tracks"][k]["frames"] / 10
    for team, c in sorted(team_time.items()):
        print(f"  {team}: " + ", ".join(f"#{num} {sec / 60:.0f}m" for num, sec in c.most_common() if sec >= 30))
    if n_sheet:
        picked = sheet(OUT / (tracks.stem + ".crops.pkl"), result, n_sheet, OUT / (tracks.stem + ".check.jpg"))
        print("hand-check sheets:", OUT / (tracks.stem + ".check_{1,2}.jpg"))
        for k, tid in enumerate(picked):
            v = result[tid]
            print(f"  #{k + 1} track {tid} -> {v['number']} conf {v['confidence']} votes {v['votes']}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="step", required=True)
    c = sub.add_parser("crops")
    c.add_argument("tracks", type=Path)
    c.add_argument("--video", type=Path, required=True)
    r = sub.add_parser("read")
    r.add_argument("crops", type=Path)
    r.add_argument("--local", action="store_true", help="read on this laptop instead of Modal (slow)")
    v = sub.add_parser("vote")
    v.add_argument("tracks", type=Path)
    v.add_argument("--sheet", type=int, default=0, help="number of random numbered tracks to put on a check sheet")
    a = p.parse_args()
    if a.step == "crops":
        make_crops(a.tracks, a.video)
    elif a.step == "read":
        read_crops(a.crops, a.local)
    else:
        report(a.tracks, a.sheet)


if __name__ == "__main__":
    main()
