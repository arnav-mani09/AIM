"""Repeatable check of three_point.py on the games that have tracks and a Hudl box score.

Usage:
    ml/.venv/bin/python ml/tools/three_point_eval.py [--games mitty,riordan]
    ml/.venv/bin/python ml/tools/three_point_eval.py --games mitty --zoom 312.4,1290.1   # check sheets

Prints 3PA and 3PM per team next to Hudl, then scores every field goal that has a hand label
(a field goal with no takeoff found counts as a 2, as on the site). Hudl gives only totals, so the
per-shot truth is made from the film: for made shots, how much the score bug went up; for misses,
by eye on zoomed crops of the shooter's feet at takeoff with the arc drawn in, from --zoom. Labels live in
ml/data/labels/three_point_truth.json as {game: {shot time: 2 | 3 | "?"}} ("?" means the film
can't tell, and is skipped). The time is the shot's "t" rounded to 0.1 s.

Results go to ml/data/tracks/<game>.v4.threes_eval.json so a sheet can be drawn without a rerun.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_point as T  # noqa: E402

ML = Path(__file__).resolve().parents[1]
ROOT = ML.parent
LABELS = ML / "data/labels/three_point_truth.json"
HUDL = ML / "data/stats/2026-27-hudl-box-scores.yaml"
GAMES = {
    "mitty": ("valley-vs-archbishop-mitty", "Valley Christian vs Archbishop Mitty CCS - Tactical.mp4"),
    "riordan": ("valley-vs-archbishop-riordan", "Valley Christian vs Archbishop Riordan - Tactical.mp4"),
}


def hudl_threes(name):
    """{team: (made, attempts)} from the Hudl box score file, found by the game id."""
    text = HUDL.read_text()
    i = text.find("id: " + name)
    out = {}
    for team in ("valley", "opponent"):
        m = re.search(team + r":\s*\{[^}]*?fg3:\s*(\d+)/(\d+)", text[i:])
        out[team.capitalize()] = (int(m.group(1)), int(m.group(2)))
    return out


def key(s):
    return f"{s['t']:.1f}"


def run(game):
    gid, film = GAMES[game]
    tracks = ML / f"data/tracks/{gid}.v4.json"
    doc = json.loads(tracks.read_text())
    shots = json.loads(tracks.with_suffix(".split.json").read_text())["shots"]
    arcs = T.classify(doc, shots, ROOT / "backend/sample_data" / film)
    out = tracks.with_suffix(".threes_eval.json")
    out.write_text(json.dumps({"arcs": {k: [list(map(float, v[0])), float(v[1])] for k, v in arcs.items()},
                               "shots": shots}, indent=0))
    return doc, shots, arcs


def report(game, shots, labels):
    fg = [s for s in shots if s.get("kind") == "FG"]
    hudl = hudl_threes(GAMES[game][0])
    print(f"== {game}")
    for team in ("Valley", "Opponent"):
        th = [s for s in fg if s.get("team") == team and s.get("points") == 3]
        hm, ha = hudl[team]
        print(f"  {team:9} 3PT AIM {sum(s['made'] for s in th):2}/{len(th):2}   Hudl {hm:2}/{ha:2}")
    lab = labels.get(game, {})
    right = wrong = 0
    misses = []
    for s in fg:
        truth = lab.get(key(s))
        call = 3 if s.get("points") == 3 else 2   # no takeoff found stays a 2, as on the site
        if truth in (2, 3):
            if truth == call:
                right += 1
            else:
                wrong += 1
                misses.append(f"{key(s)} {s['team'][0]} truth {truth} call {call} m={s.get('margin')}")
    if right + wrong:
        print(f"  hand labels: {right}/{right + wrong} right")
        for m in misses:
            print("   wrong:", m)
    return right, wrong


def zoom_sheet(game, times, out):
    """Crops around the shooter's feet at frames -3 and 0 from takeoff (tracks run at 10 frames a
    second), next to the whole frame, and the takeoff frame again with the game-average arc (magenta), the feet (red) and the line point
    used for the call (cyan)."""
    gid, film = GAMES[game]
    tracks = ML / f"data/tracks/{gid}.v4.json"
    res = json.loads(tracks.with_suffix(".threes_eval.json").read_text())
    doc = json.loads(tracks.read_text())
    arcs = {k: (tuple(v[0]), v[1]) for k, v in res["arcs"].items()}
    by_t = {key(s): s for s in res["shots"] if s.get("kind") == "FG"}
    cap = cv2.VideoCapture(str(ROOT / "backend/sample_data" / film))
    rows = []
    for t in times:
        s = by_t.get(f"{float(t):.1f}")
        if s is None or "take" not in s:
            print("no takeoff for", t)
            continue
        rim = s["rim_at_take"]
        side = "left" if (rim[0] + rim[2]) / 2 < doc["frame_size"][0] / 2 else "right"
        Mi = cv2.invertAffineTransform(T.to_map(rim))
        mx, my = T.ellipse_points(*arcs[side][0], side, k=1500)
        arc_px = list(zip(Mi[0, 0] * mx + Mi[0, 2], Mi[1, 1] * my + Mi[1, 2]))
        x0, y0, x1, y1 = s["shooter_box"]
        cx, cy = int(s["feet"][0]), int(s["feet"][1])
        full = T.read_at(cap, film, s["take"])
        cv2.rectangle(full, (x0, y0), (x1, y1), (0, 255, 0), 3)
        tiles = [cv2.resize(full, (500, 281))]

        def crop(img):   # 640 x 360 around the feet, the feet a third of the way up
            X0, Y0 = min(max(0, cx - 320), img.shape[1] - 640), min(max(0, cy - 240), img.shape[0] - 360)
            return cv2.resize(img[Y0:Y0 + 360, X0:X0 + 640], (500, 281), interpolation=cv2.INTER_AREA)

        for dk, overlay in ((-3, False), (0, False), (0, True)):
            img = T.read_at(cap, film, s["take"] + dk / doc["fps"])
            if overlay:
                for px, py in arc_px:
                    cv2.circle(img, (int(px), int(py)), 0, (255, 0, 255), -1)
                if s.get("line_at"):
                    cv2.circle(img, tuple(int(v) for v in s["line_at"]), 3, (255, 255, 0), -1)
                cv2.circle(img, (cx, cy), 3, (0, 0, 255), -1)
            t_ = crop(img)
            cv2.putText(t_, f"{dk:+d}f" + (" arc" if overlay else ""), (6, 20), 0, 0.6, (0, 255, 255), 2)
            tiles.append(t_)
        row = np.hstack(tiles)
        cv2.putText(row, f"{key(s)} {s['team'][0]} call {s.get('points')} m={s.get('margin')} {str(s.get('arc_source'))[:3]} "
                    f"{side}", (8, 272), 0, 0.6, (0, 255, 255), 2)
        rows.append(row)
    if rows:
        cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
        print("wrote", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="mitty,riordan")
    ap.add_argument("--zoom", help="comma-separated shot times: draw zoomed check sheets instead of running")
    ap.add_argument("--out", type=Path, default=Path("zoom.jpg"))
    ap.add_argument("--cached", action="store_true", help="report the last run without rerunning")
    args = ap.parse_args()
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    if args.zoom:
        zoom_sheet(args.games.split(",")[0], args.zoom.split(","), args.out)
        return
    for game in args.games.split(","):
        if args.cached:
            gid = GAMES[game][0]
            shots = json.loads((ML / f"data/tracks/{gid}.v4.threes_eval.json").read_text())["shots"]
        else:
            shots = run(game)[1]
        report(game, shots, labels)


if __name__ == "__main__":
    main()
