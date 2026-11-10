"""Find shot attempts and makes from a tracks file (ball and rim boxes only).

Usage:
    ml/.venv/bin/python ml/tools/shots.py ml/data/ontario.tracks-v2.json --video "backend/sample_data/<game>.mp4"

How it decides, per frame, in image coordinates (the camera pans, but ball and rim are in
the same frame, so that doesn't matter):
- Only "game" rims count: not ceiling hoops, and at least 60% as wide as the widest rim
  in the frame (far-court hoops from other games are small).
- Attempt: the ball enters the zone above a game rim (up to 3 rim-widths above it,
  half a rim-width to either side) after being out of it for SHOT_GAP seconds.
- Make: within MAKE_WINDOW seconds of an attempt, the ball is seen moving down with its
  center inside the rim's width, at or just below the rim. Otherwise a miss.
Writes <tracks>.shots.json and, with --video, a sheet of make frames and one of misses.
These are rules, not a model; the stats sheet is the check.

Status (Nov 3, game 1): attempts look right (128, ball in flight at a game rim in every
sampled one). Make/miss agreed with a hand check on 7 of 8 shots used for tuning but only
5 of 9 clear fresh ones: at 10 fps a rim-out and a make look too alike. Next: detect at
30 fps in a window around each attempt, and train a small make/miss classifier on
labeled rim clips.
"""

import argparse
import json
import random
from pathlib import Path

# A rim whose box ends this far (share of frame height) above the game's typical rim is a raised
# ceiling hoop. Relative, not fixed: a high camera puts every game rim near the top of the frame
# (Menlo-Atherton's rims sit at 20% of the height, game 1's at 31%).
CEILING_GAP = 0.09
SHOT_GAP = 2.0
MAKE_WINDOW = 1.5
MIN_BALL, MIN_RIM = 0.2, 0.5


def ceiling_line(doc: dict) -> float:
    """Share of frame height above which a rim counts as a ceiling hoop, from this game's rims."""
    frame_h = doc["frame_size"][1]
    ys = sorted(b[4] / frame_h for _, boxes in doc["frames"] for b in boxes if b[0] == 3 and b[5] >= MIN_RIM)
    return ys[len(ys) // 2] - CEILING_GAP if ys else 0.0


def game_rims(boxes, frame_h, line):
    rims = [b for b in boxes if b[0] == 3 and b[5] >= MIN_RIM and b[4] / frame_h >= line]
    if not rims:
        return []
    widest = max(b[3] - b[1] for b in rims)
    return [b for b in rims if b[3] - b[1] >= 0.6 * widest]


def best_ball(boxes, prev=None):
    """The game ball: nearest the last seen ball when that was recent, else the surest one.
    A stray low-score "ball" elsewhere in the frame otherwise breaks the ball's path."""
    balls = [b for b in boxes if b[0] == 0 and b[5] >= MIN_BALL]
    if not balls:
        return None
    if prev is not None:
        px, py = prev
        return min(balls, key=lambda b: abs((b[1] + b[3]) / 2 - px) + abs((b[2] + b[4]) / 2 - py) - 100 * b[5])
    return max(balls, key=lambda b: b[5])


def find_shots(doc: dict) -> list[dict]:
    frame_h, line = doc["frame_size"][1], ceiling_line(doc)
    shots, open_shot, last_in_zone, last_ball = [], None, -999.0, None
    for t, boxes in doc["frames"]:
        recent = last_ball[:2] if last_ball and t - last_ball[2] <= 0.5 else None
        ball, rims = best_ball(boxes, recent), game_rims(boxes, frame_h, line)
        if ball is not None:
            bx, by = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
            last_ball = (bx, by, t)
            for r in rims:
                x0, y0, x1, y1 = r[1:5]
                w = x1 - x0
                above = x0 - 0.5 * w <= bx <= x1 + 0.5 * w and y0 - 3 * w <= by <= y0 + 0.2 * (y1 - y0)
                if above:
                    if open_shot is None and t - last_in_zone >= SHOT_GAP:
                        open_shot = {"t": t, "rim": [round(v) for v in r[1:5]], "ball_score": ball[5],
                                     "rim_score": r[5], "path": []}
                    last_in_zone = t
                near_rim = abs(bx - (x0 + x1) / 2) < 3 * w and by < y1 + 6 * (y1 - y0)
                if open_shot and near_rim and abs((x0 + x1) / 2 - (open_shot["rim"][0] + open_shot["rim"][2]) / 2) < 2 * w:
                    open_shot["path"].append((t, bx, by, x0, y0, x1, y1))
                    break
        if open_shot and t - open_shot["t"] > MAKE_WINDOW:
            shots.append(decide(open_shot))
            open_shot = None
    if open_shot:
        shots.append(decide(open_shot))
    return shots


def decide(shot: dict) -> dict:
    """Make = within 0.5 s the ball goes from above the rim to below the rim's bottom while
    inside its width (the net can take 2-3 frames), and in the next 0.4 s it neither goes
    back up nor reverses its sideways direction. A rim-out bounces: it comes in moving one
    way and leaves moving the other, or pops up. A make keeps its line through the net,
    even at an angle. If the ball is lost right after (hidden by the net or players), it
    still counts, with less evidence."""
    path, made, evidence = shot.pop("path"), False, 0
    for i, (t0, bx0, by0, x0, y0, x1, y1) in enumerate(path):
        w, h = x1 - x0, y1 - y0
        inside = lambda bx, slack: x0 - slack * w <= bx <= x1 + slack * w
        if not (by0 < y0 + 0.2 * h and inside(bx0, 0.25)):
            continue
        for j in range(i + 1, len(path)):
            t1, bx1, by1 = path[j][:3]
            if t1 - t0 > 0.5:
                break
            if by1 > y1 and inside(bx1, 0.1):
                follow = [p for p in path[j + 1:] if p[0] - t1 <= 0.4]
                dx_in = bx1 - bx0
                dx_out = follow[-1][1] - bx1 if follow else 0.0
                pops_up = any(p[2] < by1 - 0.5 * h for p in follow)
                reverses = dx_in * dx_out < 0 and abs(dx_out) > 0.2 * w
                if not pops_up and not reverses and all(inside(p[1], 0.6) for p in follow):
                    made, evidence = True, 1 + len(follow)
                    shot["make_t"] = t1
                break
        if made:
            break
    shot["made"] = made
    shot["evidence"] = evidence
    # Rough confidence until it's calibrated against stats sheets.
    shot["confidence"] = round(min(1.0, 0.5 * shot["ball_score"] + 0.3 * shot["rim_score"] + 0.2 * min(1, evidence)), 2)
    return shot


def sheet(video: Path, shots: list[dict], out: Path, title: str) -> None:
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    tiles = []
    for s in shots[:12]:
        t = s.get("make_t", s["t"])
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        x0, y0, x1, y1 = s["rim"]
        w = x1 - x0
        cx, cy = (x0 + x1) // 2, y0
        crop = img[max(0, cy - 4 * w):cy + 3 * w, max(0, cx - 4 * w):cx + 4 * w].copy()
        crop = cv2.resize(crop, (320, 280))
        m, s_ = divmod(int(t), 60)
        cv2.putText(crop, f"{m}:{s_:02d}", (8, 28), 0, 0.9, (0, 255, 255), 2)
        tiles.append(crop)
    if not tiles:
        return
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 4)
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    img = np.vstack(rows)
    cv2.putText(img, title, (8, img.shape[0] - 10), 0, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--window", type=float, nargs=2, metavar=("START", "END"),
                        help="only count shots between these seconds (tip-off and final buzzer)")
    args = parser.parse_args()
    doc = json.loads(args.tracks.read_text())
    shots = find_shots(doc)
    start, end = args.window or (0.0, doc["frames"][-1][0])
    shots = [s for s in shots if start <= s["t"] <= end]
    made = [s for s in shots if s["made"]]
    minutes = (end - start) / 60
    print(f"{len(shots)} attempts, {len(made)} makes over {minutes:.0f} min "
          f"({len(shots) / minutes:.1f} attempts/min, {len(made) / max(1, len(shots)):.0%} made)")
    out = args.tracks.with_suffix(".shots.json")
    out.write_text(json.dumps(shots, indent=1))
    print("wrote", out)
    if args.video:
        random.seed(0)
        for name, group in (("makes", made), ("misses", [s for s in shots if not s["made"]])):
            pick = sorted(random.sample(group, min(12, len(group))), key=lambda s: s["t"])
            path = args.tracks.with_name(args.tracks.stem + f".{name}.jpg")
            sheet(args.video, pick, path, f"12 random {name}")
            print("wrote", path)


if __name__ == "__main__":
    main()
