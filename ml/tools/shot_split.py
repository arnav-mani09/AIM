"""Label each shot attempt with the shooting team (Valley or Opponent) and free throw or field goal.

Usage:
    ml/.venv/bin/python ml/tools/shot_split.py ml/data/tracks/valley-vs-archbishop-mitty.v4.json \
        --game valley-vs-archbishop-mitty [--video "backend/sample_data/<game>.mp4"]

Reads <tracks>.json and <tracks>.shots.json (from shots.py) and writes the team and kind into
<tracks>.split.json. Takes the game window and jersey colors from ml/games.yaml, and prints the
totals next to the Hudl box score when the game has one.

How it decides:
- Team. A team only ever shoots at the basket it attacks, and the teams swap baskets at halftime.
  So the team comes from the basket (left or right of the frame center, since the camera pans
  but never past a baseline) and the half (halftime is the longest gap between attempts in the
  middle of the game). Which team attacks which basket comes from a vote: for each shot, the
  player holding the ball just before it's in the air is the shooter, and his track's jersey
  group votes. One vote per shot is noisy (the ball is often hidden in a crowd); the whole
  game's vote is not. Overtime keeps the second-half baskets.
- Free throw. On a free throw everyone but the shooter stands still along the lane for several
  seconds, and the camera holds. So: the players' median movement over the 3.5 s before the
  shot, after removing camera pans, measured in body heights per second. Live play is around
  0.3 to 0.7; a free throw is under 0.1. Between 0.1 and 0.15 the hand check (Nov 10) found
  mostly live play (a jump shot, scrambles under the rim) and one real free throw, so the
  cutoff stays at 0.1. A pair partner (another still attempt at the same basket within 25 s)
  is saved as ft_pair but doesn't change the call: a putback right after a free throw has one.
- Not game shots, left out of the totals:
  - "warmup": during halftime warmups both teams shoot several balls at once. Any attempt
    where the 30 s around it averages 1.8 or more balls per frame. Live play stays under 1.5.
  - "dead_ball": during quarter breaks and timeouts, people (kids, staff) shoot around with
    the players at the benches. Any attempt with fewer than 5 players on screen (median over
    the 4 s before). Live play always had 7 or more in both test games.
These are rules, not a model; the Hudl totals are the check.
"""

import argparse
import json
import random
import statistics as st
from pathlib import Path

import yaml

ML = Path(__file__).resolve().parents[1]
STILL = 0.10        # players' movement below this before a shot means a free-throw lineup
MOTION_BEFORE = (4.0, 0.5)  # look from 4 s to 0.5 s before the ball reaches the rim zone
SHOOTER_LOOKBACK = 2.0
WARMUP_BALLS = 1.8  # average balls per frame over 30 s that means a warmup, not a game
MIN_PLAYERS = 5     # fewer players on screen than this before a shot means a dead ball


def frame_at(doc, t):
    i = int(round(t * doc["fps"]))
    return doc["frames"][i][1] if 0 <= i < len(doc["frames"]) else []


def players(boxes):
    return [b for b in boxes if b[0] == 1 and b[5] >= 0.4]


def motion(doc, t0, t1, step=0.5):
    """Median player movement relative to the camera, in body heights per second."""
    vals, t = [], t0
    while t < t1:
        p0 = {b[6]: b for b in players(frame_at(doc, t))}
        p1 = {b[6]: b for b in players(frame_at(doc, t + step))}
        common = [k for k in p0 if k in p1]
        t += step
        if len(common) < 3:
            continue
        moves = [((p1[k][1] + p1[k][3] - p0[k][1] - p0[k][3]) / 2, p1[k][4] - p0[k][4], p0[k][4] - p0[k][2])
                 for k in common]
        # A camera pan shifts everyone the same way, so subtract the median shift.
        mx, my = st.median(m[0] for m in moves), st.median(m[1] for m in moves)
        vals.append(st.median(((m[0] - mx) ** 2 + (m[1] - my) ** 2) ** 0.5 / m[2] / step for m in moves))
    return st.median(vals) if vals else None


def balls_per_frame(doc, t, half_width=15.0):
    fps = doc["fps"]
    frames = doc["frames"][max(0, int((t - half_width) * fps)):int((t + half_width) * fps)]
    if not frames:
        return 0.0
    return sum(sum(1 for b in boxes if b[0] == 0 and b[5] >= 0.3) for _, boxes in frames) / len(frames)


def players_on_screen(doc, t, before=4.0):
    fps = doc["fps"]
    counts = [len(players(frame_at(doc, t - k / fps))) for k in range(1, int(before * fps) + 1)]
    return st.median(counts) if counts else 0


def shooter(doc, t):
    """Track id of the player who had the ball last before it reached the rim zone at time t.
    Walks back from t following the ball; the first frame where the ball sits inside a player's
    box (upper two thirds, where hands are on a shot) is the release."""
    fps, prev = doc["fps"], None
    for k in range(int(SHOOTER_LOOKBACK * fps) + 1):
        boxes = frame_at(doc, t - k / fps)
        balls = [b for b in boxes if b[0] == 0 and b[5] >= 0.2]
        if not balls:
            continue
        if prev:
            ball = min(balls, key=lambda b: abs((b[1] + b[3]) / 2 - prev[0]) + abs((b[2] + b[4]) / 2 - prev[1]))
        else:
            ball = max(balls, key=lambda b: b[5])
        bx, by = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
        if prev and abs(bx - prev[0]) + abs(by - prev[1]) > 300:
            continue  # jumped to another ball
        prev = (bx, by)
        holders = []
        for p in players(boxes):
            x0, y0, x1, y1 = p[1:5]
            h = y1 - y0
            if x0 - 0.15 * (x1 - x0) <= bx <= x1 + 0.15 * (x1 - x0) and y0 - 0.25 * h <= by <= y0 + 0.66 * h:
                holders.append((abs(bx - (x0 + x1) / 2), p[6]))
        if holders:
            return min(holders)[1]
    return None


def halftime(times, start, end):
    """Middle of the longest gap between attempts in the middle 60% of the game."""
    lo, hi = start + 0.2 * (end - start), start + 0.8 * (end - start)
    gaps = [(times[i + 1] - times[i], (times[i] + times[i + 1]) / 2)
            for i in range(len(times) - 1) if lo <= times[i] <= hi]
    return max(gaps)[1] if gaps else (start + end) / 2


def jersey_groups(doc, game):
    """Which of the tracker's two color groups is Valley: the pairing of groups to the two
    teams' reference colors that is closest overall (same rule as track_teams.assign_teams)."""
    import cv2
    import numpy as np

    from track_teams import JERSEY_BGR

    def lab(bgr):
        return cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)

    def feat(v):  # brightness counts for half, as in track_teams.feature
        return np.array([0.5 * v[0], v[1], v[2]])

    c0, c1 = (feat(c) for c in doc["group_centers_lab"])
    v, o = feat(lab(JERSEY_BGR[game["valley_jersey"]])), feat(lab(JERSEY_BGR[game["opponent_jersey"]]))
    keep = np.linalg.norm(c0 - v) + np.linalg.norm(c1 - o) <= np.linalg.norm(c0 - o) + np.linalg.norm(c1 - v)
    return {0: "Valley", 1: "Opponent"} if keep else {0: "Opponent", 1: "Valley"}


def split(doc, shots, game, window):
    start, end = window
    shots = [s for s in shots if start <= s["t"] <= end]
    dropped = []
    for s in shots:
        if balls_per_frame(doc, s["t"]) >= WARMUP_BALLS:
            s["kind"] = "warmup"
        elif players_on_screen(doc, s["t"]) < MIN_PLAYERS:
            s["kind"] = "dead_ball"
        else:
            continue
        dropped.append(s)
    shots = [s for s in shots if s not in dropped]
    times = [s["t"] for s in shots]
    half_t = halftime(times, start, end)
    names = jersey_groups(doc, game)
    tracks = doc["tracks"]

    for s in shots:
        s["basket"] = "left" if (s["rim"][0] + s["rim"][2]) / 2 < doc["frame_size"][0] / 2 else "right"
        s["half"] = 1 if s["t"] < half_t else 2
        m = motion(doc, s["t"] - MOTION_BEFORE[0], s["t"] - MOTION_BEFORE[1])
        s["stillness"] = None if m is None else round(m, 3)
        tid = shooter(doc, s["t"])
        group = tracks.get(str(tid), {}).get("group") if tid is not None else None
        s["shooter_track"] = tid
        s["shooter_jersey"] = names.get(group, "unsure") if group in (0, 1) else "unsure"

    # Free throws: still players. ft_pair is kept for the review screen, not used in the call.
    for i, s in enumerate(shots):
        still = s["stillness"] is not None and s["stillness"] < STILL
        partner = any(j != i and o["basket"] == s["basket"] and abs(o["t"] - s["t"]) <= 25
                      and o["stillness"] is not None and o["stillness"] < STILL for j, o in enumerate(shots))
        s["kind"] = "FT" if still else "FG"
        s["ft_pair"] = still and partner

    # Basket vote. "Valley attacks left in the first half" is the same claim as "Valley attacks
    # right in the second", so every vote counts toward one of two answers.
    votes = {"valley_left_first": 0, "valley_right_first": 0}
    for s in shots:
        if s["shooter_jersey"] == "unsure":
            continue
        valley_side_first = s["basket"] if s["half"] == 1 else ("right" if s["basket"] == "left" else "left")
        if s["shooter_jersey"] == "Opponent":
            valley_side_first = "right" if valley_side_first == "left" else "left"
        votes[f"valley_{valley_side_first}_first"] += 1
    valley_first = "left" if votes["valley_left_first"] >= votes["valley_right_first"] else "right"
    for s in shots:
        valley_side = valley_first if s["half"] == 1 else ("right" if valley_first == "left" else "left")
        s["team"] = "Valley" if s["basket"] == valley_side else "Opponent"
    info = {"halftime": round(half_t, 1), "valley_basket_first_half": valley_first, "votes": votes,
            "shooter_agrees": sum(s["shooter_jersey"] == s["team"] for s in shots),
            "shooter_known": sum(s["shooter_jersey"] != "unsure" for s in shots),
            "warmup_dropped": sum(s["kind"] == "warmup" for s in dropped),
            "dead_ball_dropped": sum(s["kind"] == "dead_ball" for s in dropped)}
    return sorted(shots + dropped, key=lambda s: s["t"]), info


def hudl_totals(game_id):
    path = ML / "data" / "stats" / "2026-27-hudl-box-scores.yaml"
    if not path.exists():
        return None
    for g in yaml.safe_load(path.read_text())["games"]:
        if g["id"] == game_id:
            out = {}
            for team, key in (("Valley", "valley"), ("Opponent", "opponent")):
                t = g["team_totals"][key]
                f2, f3, ft = (tuple(map(int, t[k].split("/"))) for k in ("fg2", "fg3", "ft"))
                out[team] = {"FG": (f2[0] + f3[0], f2[1] + f3[1]), "FT": ft}
            return out
    return None


def sheet(video, shots, out, title):
    """Wide frames 1 s before each shot (the lineup, or the play), labeled with time and call."""
    import cv2
    import numpy as np

    cap, tiles = cv2.VideoCapture(str(video)), []
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_MSEC, (s["t"] - 1) * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        img = cv2.resize(img, (480, 270))
        m, sec = divmod(int(s["t"]), 60)
        label = f"{m}:{sec:02d} {s['team'][:3]} {s['kind']} {s['basket'][0].upper()}"
        cv2.putText(img, label, (6, 26), 0, 0.7, (0, 255, 255), 2)
        tiles.append(img)
    if not tiles:
        return
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 4)
    img = np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)])
    cv2.putText(img, title, (8, img.shape[0] - 10), 0, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--game", required=True, help="game id in ml/games.yaml")
    parser.add_argument("--video", type=Path)
    args = parser.parse_args()
    doc = json.loads(args.tracks.read_text())
    shots = json.loads(args.tracks.with_suffix(".shots.json").read_text())
    game = next(g for g in yaml.safe_load((ML / "games.yaml").read_text())["games"] if g["id"] == args.game)
    window = game.get("game_window", [0.0, doc["frames"][-1][0]])
    shots, info = split(doc, shots, game, window)
    print(f"halftime at {info['halftime']} s; Valley shoots at the {info['valley_basket_first_half']} basket "
          f"in the first half (votes {info['votes']}); dropped {info['warmup_dropped']} warmup and {info['dead_ball_dropped']} dead-ball attempts; shooter jersey agrees on "
          f"{info['shooter_agrees']} of {info['shooter_known']} shots where it was seen")
    hudl = hudl_totals(args.game)
    print(f"{'':10}{'AIM FG':>10}{'Hudl FG':>10}{'AIM FT':>10}{'Hudl FT':>10}")
    for team in ("Valley", "Opponent"):
        row = []
        for kind in ("FG", "FT"):
            got = [s for s in shots if s.get("team") == team and s["kind"] == kind]
            row.append(f"{sum(s['made'] for s in got)}/{len(got)}")
            row.append("{}/{}".format(*hudl[team][kind]) if hudl else "-")
        print(f"{team:10}" + "".join(f"{c:>10}" for c in row))
    out = args.tracks.with_suffix(".split.json")
    out.write_text(json.dumps({"window": window, **info, "shots": shots}, indent=1))
    print("wrote", out)
    if args.video:
        random.seed(0)
        for kind in ("FT", "FG"):
            group = [s for s in shots if s["kind"] == kind]
            pick = sorted(random.sample(group, min(12, len(group))), key=lambda s: s["t"])
            path = args.tracks.with_name(args.tracks.stem + f".{kind.lower()}.jpg")
            sheet(args.video, pick, path, f"12 random {kind}")
            print("wrote", path)


if __name__ == "__main__":
    main()
