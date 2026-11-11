"""Join broken player tracks into longer ones.

Usage:
    ml/.venv/bin/python ml/tools/stitch_tracks.py ml/data/tracks/valley-vs-archbishop-mitty.v4.json
    ml/.venv/bin/python ml/tools/stitch_tracks.py <tracks.json> --check 15 --video "backend/sample_data/<game>.mp4"

ByteTrack starts a new track id whenever it loses a player for a moment: two players cross,
the camera pans them out of frame, or the detector misses a few frames. A 90 minute game
ends up with about 10,000 tracks for 20 to 30 people. This tool links a track that ends to
one that starts shortly after, when they look like the same person:

- The gap is short (up to MAX_GAP seconds) and the tracks never overlap in time.
- Same class (player or referee) and not opposite teams ("unsure" may join either team).
- Close in court position. The camera pans, so positions are compared in "pan-corrected"
  coordinates: each frame's camera shift is the median movement of the boxes that kept
  their track id from the frame before, and that shift is added up over time.
- Similar jersey color (the per-track color the detector already stores) and similar box size.
- With --video, similar look: a color histogram of the box near each end, read from the film
  in one pass (about 5 minutes per game, saved to <tracks>.looks.npz so reruns take seconds).

A link is taken only when it is clearly the best match for both tracks and neither end is
next to a teammate. Two teammates in the same jersey look alike, so a wrong join there would
hand one player's stats to another; leaving a track broken is the safer mistake.
Writes <tracks>.stitched.json (same format, new track ids) and <tracks>.stitch_map.json
(old id -> new id). With --check N and --video, also writes N sheets of join crops
(last box before the gap, first box after) in 4 x 4 grids for a hand check.

Status (Nov 11, Mitty and Riordan, with --video): about 930 joins per game, tracks down 8 to 9%,
share of player time in tracks over 10 s up from 60% to 63-66%. Hand check: 2 to 3 wrong joins
in 16 per game. Looser settings join 4 times as many tracks but half of those joins are wrong
(teammates swapped in crowds). Big gains need a learned look model (person re-ID) or jersey
numbers, not looser rules.
"""

import argparse
import bisect
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

MAX_GAP = 2.0          # seconds between the end of one track and the start of the next
MAX_COLOR = 30.0       # jersey color distance (Lab units, lightness counts most)
SIZE_RATIO = 1.6       # box heights may differ by at most this factor
LOOSE_DIST = 0.8       # box heights: candidates this close count as possible matches
TIGHT_DIST = 0.4       # box heights (plus 0.4 per second of gap): how close a join must be
MARGIN = 0.5           # the best match must beat the runner-up by this much
MAX_APP = 0.45         # histogram distance (0 same, 1 nothing alike) above which looks don't match
CROWD = 0.5            # box heights: a teammate this close at either end blocks the join
TEAM_CLASSES = (1,)    # players get team checks; referees (class 2) carry no track id in v4


def camera_pan(frames: list) -> list[tuple[float, float]]:
    """Cumulative camera shift per frame, from boxes that kept their track id."""
    pan, prev, cx, cy = [], {}, 0.0, 0.0
    for _, boxes in frames:
        cur = {b[6]: ((b[1] + b[3]) / 2, (b[2] + b[4]) / 2) for b in boxes if len(b) > 6 and b[6] >= 0}
        dx = [prev[k][0] - v[0] for k, v in cur.items() if k in prev]
        dy = [prev[k][1] - v[1] for k, v in cur.items() if k in prev]
        if len(dx) >= 3:
            # Players move too, but the median over 5 to 12 people is mostly the camera.
            cx += statistics.median(dx)
            cy += statistics.median(dy)
        pan.append((cx, cy))
        prev = cur
    return pan


def track_ends(doc: dict, pan: list) -> dict:
    """For each track: first and last few boxes in pan-corrected coordinates."""
    seen = defaultdict(list)
    for i, (t, boxes) in enumerate(doc["frames"]):
        for b in boxes:
            if len(b) > 6 and b[6] >= 0:
                x, y = (b[1] + b[3]) / 2 + pan[i][0], b[4] + pan[i][1]  # feet, not center
                seen[b[6]].append((t, x, y, b[4] - b[2], b[0], i, b[1:5]))
    ends = {}
    for tid, pts in seen.items():
        head, tail = pts[:5], pts[-5:]
        # Speed at the end of the track, used to guess where the player went during the gap.
        if len(tail) >= 2 and tail[-1][0] > tail[0][0]:
            dt = tail[-1][0] - tail[0][0]
            vx, vy = (tail[-1][1] - tail[0][1]) / dt, (tail[-1][2] - tail[0][2]) / dt
        else:
            vx = vy = 0.0
        inner = min(len(pts) - 1, 4)
        ends[tid] = {"first": pts[0], "last": pts[-1], "v": (vx, vy), "cls": pts[0][4],
                     "probe_start": pts[inner], "probe_end": pts[-1 - inner],
                     "h_end": statistics.median(p[3] for p in tail),
                     "h_start": statistics.median(p[3] for p in head), "n": len(pts)}
    return ends


def appearance(video: Path, doc: dict, ends: dict, cache: Path) -> None:
    """Add a color histogram of each track's box near its start and near its end, read in one
    pass over the film (seeking is slow). Head, jersey, shorts and shoes all count, so two
    teammates in the same jersey can still differ by skin, hair, shorts or shoes.
    Saved to `cache` so reruns skip the film."""
    import cv2
    import numpy as np

    if cache.exists():
        saved = np.load(cache)
        for key in saved.files:
            tid, side = key.rsplit("_", 1)
            if int(tid) in ends:
                ends[int(tid)]["hist_" + side] = saved[key]
        return

    want = defaultdict(list)  # video frame number -> [(track, "start"/"end", box)]
    cap = cv2.VideoCapture(str(video))
    vfps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    for tid, e in ends.items():
        for side in ("start", "end"):
            t, *_, box = e["probe_" + side]
            want[round(t * vfps)].append((tid, side, box))
    last = max(want)
    n = 0
    while n <= last:
        if not cap.grab():
            break
        if n in want:
            ok, img = cap.retrieve()
            if ok:
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                for tid, side, (x0, y0, x1, y1) in want[n]:
                    x0, y0 = max(0, int(x0)), max(0, int(y0))
                    # Trim the box sides, where the background and neighbors show.
                    pad = int((x1 - x0) * 0.2)
                    crop = hsv[y0:int(y1), x0 + pad:max(x0 + pad + 1, int(x1) - pad)]
                    if crop.size == 0:
                        continue
                    parts = []
                    for lo, hi in ((0.0, 0.5), (0.5, 1.0)):  # top half (jersey, head), bottom (shorts, legs)
                        part = crop[int(lo * len(crop)):max(int(lo * len(crop)) + 1, int(hi * len(crop)))]
                        h = cv2.calcHist([part], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256])
                        parts.append(cv2.normalize(h, None).flatten())
                    ends[tid]["hist_" + side] = np.concatenate(parts).astype("float32")
        n += 1
    np.savez_compressed(cache, **{f"{tid}_{side}": e["hist_" + side]
                                  for tid, e in ends.items() for side in ("start", "end") if "hist_" + side in e})


def hist_dist(ea: dict, eb: dict) -> float | None:
    import cv2

    if "hist_end" not in ea or "hist_start" not in eb:
        return None
    return float(cv2.compareHist(ea["hist_end"], eb["hist_start"], cv2.HISTCMP_BHATTACHARYYA))


def color_dist(a, b) -> float:
    # Lightness separates the teams best (white vs blue); weight it double.
    return ((2 * (a[0] - b[0])) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def crowded(doc: dict, pan: list, end: tuple, tid: int, group, meta: dict) -> bool:
    """True when another same-team (or unsure) player stands within CROWD box heights of this
    box in the same frame. Breaks in a crowd are where joins go wrong: two teammates in the
    same jersey look alike, so a nearby teammate could be the one who carries on."""
    t, x, y, h, cls, i, _ = end
    for b in doc["frames"][i][1]:
        if b[0] != cls or len(b) < 7 or b[6] < 0 or b[6] == tid:
            continue
        g = meta[str(b[6])]["group"]
        if group != "unsure" and g != "unsure" and g != group:
            continue
        bx, by = (b[1] + b[3]) / 2 + pan[i][0], b[4] + pan[i][1]
        if ((bx - x) ** 2 + (by - y) ** 2) ** 0.5 < CROWD * h:
            return True
    return False


def candidates(doc: dict, ends: dict) -> list:
    """Every possible link that passes the loose gates, with its score (lower is better)."""
    meta = doc["tracks"]
    by_start = sorted(ends, key=lambda k: ends[k]["first"][0])
    starts = [ends[k]["first"][0] for k in by_start]
    out = []
    for a, ea in ends.items():
        ta = ea["last"][0]
        lo = bisect.bisect_right(starts, ta)  # strictly after: no time overlap
        hi = bisect.bisect_right(starts, ta + MAX_GAP)
        ma = meta[str(a)]
        for b in by_start[lo:hi]:
            eb, mb = ends[b], meta[str(b)]
            if eb["cls"] != ea["cls"]:
                continue
            ga, gb = ma["group"], mb["group"]
            if ea["cls"] in TEAM_CLASSES and ga != "unsure" and gb != "unsure" and ga != gb:
                continue
            h = max(ea["h_end"], eb["h_start"])
            if h / max(1.0, min(ea["h_end"], eb["h_start"])) > SIZE_RATIO:
                continue
            c = color_dist(ma["color_lab"], mb["color_lab"])
            if c > MAX_COLOR:
                continue
            gap = eb["first"][0] - ta
            # Where the player would be if they kept moving, capped at half a second's worth.
            k = min(gap, 0.5)
            px, py = ea["last"][1] + ea["v"][0] * k, ea["last"][2] + ea["v"][1] * k
            d = ((eb["first"][1] - px) ** 2 + (eb["first"][2] - py) ** 2) ** 0.5 / h
            if d > LOOSE_DIST + 1.2 * gap:
                continue
            cost = d + c / 25 + 0.5 * gap + (0.3 if "unsure" in (ga, gb) else 0)
            app = hist_dist(ea, eb)
            if app is not None:
                if app > MAX_APP:
                    continue
                cost += 3 * app
            out.append((cost, a, b, round(gap, 2), round(d, 2), round(c, 1), None if app is None else round(app, 2)))
    return sorted(out)


def stitch(doc: dict, video: Path | None = None, cache: Path | None = None) -> tuple[dict, dict, list]:
    """Take a link only when it is clearly the best choice for both tracks:
    - close enough (the tight distance gate),
    - each track's best option, beating the runner-up on either side by MARGIN,
    - and neither end happens next to a teammate (see crowded()).
    Loose candidates count as runners-up, so a second plausible match blocks a join."""
    pan = camera_pan(doc["frames"])
    ends = track_ends(doc, pan)
    if video:
        appearance(video, doc, ends, cache)
    meta = doc["tracks"]
    cands = candidates(doc, ends)
    by_a, by_b = defaultdict(list), defaultdict(list)
    for c in cands:
        by_a[c[1]].append(c[0])
        by_b[c[2]].append(c[0])
    links, used_end, used_start, nxt = [], set(), set(), {}
    for cost, a, b, gap, d, c, app in cands:
        if a in used_end or b in used_start or d > TIGHT_DIST + 0.4 * gap:
            continue
        ra, rb = by_a[a], by_b[b]  # sorted costs; this link is the cheapest if it is ra[0]
        if ra[0] < cost or rb[0] < cost:
            continue
        if (len(ra) > 1 and ra[1] - cost < MARGIN) or (len(rb) > 1 and rb[1] - cost < MARGIN):
            continue
        if crowded(doc, pan, ends[a]["last"], a, meta[str(a)]["group"], meta) or \
                crowded(doc, pan, ends[b]["first"], b, meta[str(b)]["group"], meta):
            continue
        used_end.add(a)
        used_start.add(b)
        nxt[a] = b
        links.append({"from": a, "to": b, "gap": gap, "dist": d, "color": c, "look": app, "cost": round(cost, 2)})
    # Follow each chain from its head; links only go forward in time, so there are no loops.
    mapping, new_id = {}, 0
    for tid in sorted(ends, key=lambda k: ends[k]["first"][0]):
        if tid in used_start:
            continue
        new_id += 1
        cur = tid
        while cur is not None:
            mapping[cur] = new_id
            cur = nxt.get(cur)
    return mapping, ends, links


def rebuild(doc: dict, mapping: dict) -> dict:
    out = dict(doc)
    out["frames"] = [[t, [b[:6] + [mapping.get(b[6], b[6]) if b[6] >= 0 else -1] if len(b) > 6 else b
                          for b in boxes]] for t, boxes in doc["frames"]]
    groups = defaultdict(list)
    for old, new in mapping.items():
        groups[new].append(doc["tracks"][str(old)])
    tracks = {}
    for new, parts in groups.items():
        n = sum(p["frames"] for p in parts)
        votes = defaultdict(int)
        for p in parts:
            votes[p["group"]] += p["frames"]
        sure = {g: v for g, v in votes.items() if g != "unsure"}
        tracks[str(new)] = {
            "start": min(p["start"] for p in parts), "end": max(p["end"] for p in parts), "frames": n,
            "group": max(sure, key=sure.get) if sure else "unsure",
            "color_lab": [round(sum(p["color_lab"][i] * p["frames"] for p in parts) / n, 1) for i in range(3)],
            "parts": len(parts),
        }
    out["tracks"] = tracks
    out["stitched_from"] = len(doc["tracks"])
    return out


def summary(tracks: dict, fps: float) -> dict:
    lengths = [v["end"] - v["start"] for v in tracks.values()]
    total = sum(v["frames"] for v in tracks.values())
    long_ = sum(v["frames"] for v in tracks.values() if v["end"] - v["start"] > 10)
    return {"tracks": len(tracks), "median_s": round(statistics.median(lengths), 1),
            "share_time_in_tracks_over_10s": round(long_ / total, 3)}


def check_sheets(video: Path, ends: dict, links: list, n: int, out_stem: Path) -> list[Path]:
    """One image per sampled join: crop before the gap (left) and after it (right)."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    random.seed(1)
    pick = random.sample(links, min(n, len(links)))
    paths = []

    def crop(t, box):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        if not ok:
            return np.zeros((300, 200, 3), np.uint8)
        x0, y0, x1, y1 = [int(v) for v in box]
        pw, ph = (x1 - x0) // 2, (y1 - y0) // 4
        c = img[max(0, y0 - ph):y1 + ph, max(0, x0 - pw):x1 + pw].copy()
        cv2.rectangle(c, (x0 - max(0, x0 - pw), y0 - max(0, y0 - ph)),
                      (x1 - max(0, x0 - pw), y1 - max(0, y0 - ph)), (0, 255, 255), 2)
        return cv2.resize(c, (200, 300))

    tiles = []
    for k, ln in enumerate(pick):
        a, b = ends[ln["from"]]["last"], ends[ln["to"]]["first"]
        img = np.hstack([crop(a[0], a[6]), np.full((300, 8, 3), 255, np.uint8), crop(b[0], b[6])])
        cv2.putText(img, f"{k + 1}: gap {ln['gap']}s t={a[0]:.0f}", (4, 290), 0, 0.5, (0, 255, 255), 1)
        tiles.append(np.vstack([img, np.zeros((10, img.shape[1], 3), np.uint8)]))
    # Grids of 4 x 4 joins, so a hand check is a few images instead of dozens.
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 4)
    for g in range(0, len(tiles), 16):
        rows = [np.hstack(tiles[i:i + 4]) for i in range(g, min(g + 16, len(tiles)), 4)]
        p = out_stem.with_name(out_stem.stem + f".joins{g // 16 + 1}.jpg")
        cv2.imwrite(str(p), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 80])
        paths.append(p)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--video", type=Path, help="the game film: adds a look check (about 5 min per game)")
    parser.add_argument("--check", type=int, default=0, help="write this many join crops for a hand check")
    args = parser.parse_args()
    t0 = time.time()
    doc = json.loads(args.tracks.read_text())
    stem = args.tracks.with_suffix("")
    mapping, ends, links = stitch(doc, args.video, stem.with_name(stem.name + ".looks.npz"))
    new = rebuild(doc, mapping)
    before, after = summary(doc["tracks"], doc["fps"]), summary(new["tracks"], doc["fps"])
    stitched = stem.with_name(stem.name + ".stitched.json")
    stitched.write_text(json.dumps(new, separators=(",", ":")))
    stem.with_name(stem.name + ".stitch_map.json").write_text(
        json.dumps({"map": {str(k): v for k, v in mapping.items()}, "links": links}))
    print(f"before: {before}")
    print(f"after:  {after}  ({len(links)} joins, {time.time() - t0:.0f} s)")
    print("wrote", stitched)
    if args.check and args.video:
        for p in check_sheets(args.video, ends, links, args.check, stitched):
            print("wrote", p)


if __name__ == "__main__":
    main()
