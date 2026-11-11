"""Give each shot to a player (team and jersey number), then build a per-player box score.

Usage:
    ml/.venv/bin/python ml/tools/player_stats.py ml/data/tracks/valley-vs-archbishop-mitty.v4.json [--check]

Inputs, all next to the tracks file unless noted:
- <game>.v4.split.json and <game>.v4.threes.json: the shots, with team, FT vs FG, 2 vs 3, made,
  and the shooter's track at the gather when three_point.py could follow the ball back.
- ml/data/jerseys/<game>.v4.players-all.json: tracks grouped into players by team and number
  (jersey_model.py players).
- <game>.v4.stitch_map.json (optional): broken tracks joined by stitch_tracks.py.

How a shot gets its player, in order (each step is tried only when the one before fails):
1. Shooter track. The track three_point.py found holding the ball at the gather, if its jersey
   color agrees with the shooting team. Otherwise the player box of the shooting team nearest the
   ball just before release. Free throws use the second rule.
2. The track's own number, from the players file.
3. A neighbour: a track of the same team that ends just before this one starts (or starts just
   after it ends), near the same spot, and has a number. Tracks often break right at a shot
   because the shooter jumps and overlaps a defender.
4. Who else could it be: the team's numbered players seen in the 30 s around the shot, minus any
   player on screen somewhere else at that moment. A team has at most 5 on the floor, so this is
   usually a short list. The one seen closest in time and place wins if it is clearly ahead.
5. Otherwise "unknown".
Each attribution carries a confidence and the step that made it.

Writes <game>.v4.player_stats.json. With --check, compares against the Hudl box score and
writes zoomed crops of 20 random attributions for a hand check.
"""

import argparse
import json
import math
import random
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from shot_split import jersey_groups  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GAMES = ROOT / "ml" / "games.yaml"
STATS = ROOT / "ml" / "data" / "stats" / "2026-27-hudl-box-scores.yaml"
JERSEYS = ROOT / "ml" / "data" / "jerseys"

NEIGHBOUR_GAP = 2.0      # seconds between a track ending and the next starting
NEIGHBOUR_DIST = 1.5     # box heights between the end of one and the start of the next
ON_COURT_WINDOW = 30.0   # seconds around the shot to list the team's players
CLEAR_LEAD = 1.5         # the best candidate's score must beat the runner-up by this factor


class Game:
    """Tracks file plus quick lookups by time and by track."""

    def __init__(self, path: Path):
        self.doc = json.loads(path.read_text())
        self.frames = self.doc["frames"]
        self.times = [f[0] for f in self.frames]
        self.tracks = self.doc["tracks"]
        # First and last box of each player track, for neighbour matching.
        self.first, self.last = {}, {}
        for t, boxes in self.frames:
            for b in boxes:
                if b[0] == 1 and b[6] >= 0:
                    k = str(b[6])
                    self.first.setdefault(k, (t, b))
                    self.last[k] = (t, b)
        self.starts = sorted((v[0], k) for k, v in self.first.items())

    def window(self, t0, t1):
        i, j = bisect_left(self.times, t0), bisect_right(self.times, t1)
        return self.frames[i:j]


def best_ball(boxes):
    balls = [b for b in boxes if b[0] == 0 and b[5] >= 0.2]
    return max(balls, key=lambda b: b[5]) if balls else None


def box_dist(ball, box):
    """Distance from the ball center to a player box, in box heights (0 when inside)."""
    bx, by = (ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2
    dx = max(box[1] - bx, 0, bx - box[3])
    dy = max(box[2] - by, 0, by - box[4])
    return math.hypot(dx, dy) / max(1.0, box[4] - box[2])


def nearest_to_ball(g: Game, t0, t1, team_group, top=3):
    """Tracks of the shooting team closest to the ball over [t0, t1], best first."""
    score = Counter()
    for _, boxes in g.window(t0, t1):
        ball = best_ball(boxes)
        if ball is None:
            continue
        for b in boxes:
            if b[0] != 1 or b[6] < 0:
                continue
            grp = g.tracks.get(str(b[6]), {}).get("group")
            # A track's overall color is a weak hint: about 1 in 7 is "unsure" and some carry the
            # other team's color after an ID switch (a Valley free-throw shooter whose track was
            # grouped white). So the other color only lowers the weight; the color check at the
            # shot itself makes the call.
            weight = 1.0 if grp == team_group else 0.7 if grp == "unsure" else 0.35
            d = box_dist(ball, b)
            if d < 1.0:
                # Sharp: holding the ball (inside the box) beats standing next to it.
                score[str(b[6])] += math.exp(-d / 0.12) * weight
    return [tid for tid, _ in score.most_common(top)]


class ColorCheck:
    """Reads the film at the shot to check the shooter's jersey color in that very frame.
    Tracks sometimes switch to another player right at a shot (two players overlap at the rim),
    so the track's overall color can be the wrong team's at the moment that matters."""

    def __init__(self, video: Path, doc: dict):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        self.cap = cv2.VideoCapture(str(video))
        # Same feature as shot_split.jersey_groups: brightness counts for half.
        self.centers = [np.array([0.5 * c[0], c[1], c[2]]) for c in doc["group_centers_lab"]]

    def group(self, t, box):
        """0 or 1 when the torso clearly matches one group's color, else None."""
        cv2, np = self.cv2, self.np
        self.cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = self.cap.read()
        if not ok:
            return None
        x0, y0, x1, y1 = (int(v) for v in box[1:5])
        w, h = x1 - x0, y1 - y0
        torso = img[max(0, y0 + int(0.15 * h)):y0 + int(0.5 * h), max(0, x0 + int(0.25 * w)):x1 - int(0.25 * w)]
        if torso.size == 0:
            return None
        lab = cv2.cvtColor(torso, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
        m = np.median(lab, axis=0)
        f = np.array([0.5 * m[0], m[1], m[2]])
        d0, d1 = (np.linalg.norm(f - c) for c in self.centers)
        if min(d0, d1) * 1.2 > max(d0, d1):
            return None  # too close to call (shadow, two players in one box)
        return 0 if d0 < d1 else 1


def find_shooter(g: Game, shot, three, team_group, check=None):
    """Returns (track id, how, box time, box). Candidates in order: the track three_point.py
    found holding the ball at the gather (if its color fits the shooting team), then the
    shooting team's tracks nearest the ball. With a ColorCheck, a candidate whose jersey is
    clearly the other team's at that moment is skipped."""
    cands = []
    tid = three.get("shooter_track") if three else None
    if tid is not None and three.get("shooter_from") == "ball at the gather":
        grp = g.tracks.get(str(tid), {}).get("group")
        if grp == team_group or grp == "unsure" or check is not None:
            cands.append((str(tid), "gather"))
    if shot["kind"] == "FT":
        # Free throws: the shooter holds the ball at the line for a second or more before the
        # release. The ball reaches the rim zone about 0.6 to 1 s after release, so look earlier;
        # later windows pick up players in the lane under the ball's flight.
        t0, t1 = shot["t"] - 3.5, shot["t"] - 0.8
    else:
        take = three.get("take") if three else None
        t0, t1 = (take - 0.5, take + 0.2) if take else (shot["t"] - 1.8, shot["t"] - 0.6)
    for t in nearest_to_ball(g, t0, t1, team_group):
        if all(t != c for c, _ in cands):
            cands.append((t, "nearest to ball"))
    when = (three.get("take") or shot["t"] - 1.0) if shot["kind"] == "FG" else shot["t"] - 1.6
    for tid, how in cands:
        box_t, box = track_box_near(g, tid, when)
        if check is not None and box is not None:
            seen = check.group(box_t, box)
            if seen is not None and seen != team_group:
                continue
            # Color unclear in this frame and the track is the other team's color overall:
            # most often a box covering an attacker and a defender. Skip it.
            if seen is None and g.tracks.get(tid, {}).get("group") not in (team_group, "unsure"):
                continue
        return tid, how, box_t, box
    return None, "no shooter", None, None


def player_index(players: dict):
    track_player = {}
    for key, p in players.items():
        for t in p["tracks"]:
            track_player[str(t)] = key
    return track_player


def neighbour_player(g: Game, tid, team_group, track_player):
    """Number from a track of the same team that hands off to or from this one."""
    if tid not in g.first:
        return None
    s_t, s_b = g.first[tid]
    e_t, e_b = g.last[tid]
    cands = []
    # Numbered tracks that end shortly before this one starts, or start shortly after it ends.
    for k in track_player:
        if k not in g.last or k == tid:
            continue
        grp = g.tracks.get(k, {}).get("group")
        if grp in (0, 1) and grp != team_group:
            continue
        lt, lb = g.last[k]
        ft, fb = g.first[k]
        if 0 <= s_t - lt <= NEIGHBOUR_GAP:
            d = math.hypot((lb[1] + lb[3] - s_b[1] - s_b[3]) / 2, lb[4] - s_b[4]) / max(1.0, s_b[4] - s_b[2])
            if d <= NEIGHBOUR_DIST:
                cands.append((d + (s_t - lt), k))
        if 0 <= ft - e_t <= NEIGHBOUR_GAP:
            d = math.hypot((fb[1] + fb[3] - e_b[1] - e_b[3]) / 2, fb[4] - e_b[4]) / max(1.0, e_b[4] - e_b[2])
            if d <= NEIGHBOUR_DIST:
                cands.append((d + (ft - e_t), k))
    if not cands:
        return None
    cands.sort()
    best_key = track_player[cands[0][1]]
    # Two different players next to each other at the hand-off: too close to call.
    if len(cands) > 1 and track_player[cands[1][1]] != best_key and cands[1][0] < 1.3 * cands[0][0]:
        return None
    return best_key


def on_court_player(g: Game, shot_t, shooter_box, team_group, team_players, track_player):
    """Most likely numbered player of the team: seen near the shot, not on screen elsewhere."""
    visible_now = set()
    for _, boxes in g.window(shot_t - 0.3, shot_t + 0.3):
        for b in boxes:
            if b[0] == 1 and b[6] >= 0 and str(b[6]) in track_player:
                visible_now.add(track_player[str(b[6])])
    scores = {}
    for key, p in team_players.items():
        if key in visible_now:
            continue  # on screen as someone else right now
        best = None
        for t in p["tracks"]:
            t = str(t)
            if t not in g.first:
                continue
            ft, fb = g.first[t]
            lt, lb = g.last[t]
            for when, box in ((ft, fb), (lt, lb)):
                dt = abs(when - shot_t)
                if dt > ON_COURT_WINDOW:
                    continue
                dist = 0.0
                if shooter_box is not None:
                    dist = math.hypot((box[1] + box[3] - shooter_box[1] - shooter_box[3]) / 2,
                                      box[4] - shooter_box[4]) / max(1.0, shooter_box[4] - shooter_box[2])
                cost = dt / 5.0 + dist / 3.0
                best = cost if best is None or cost < best else best
        if best is not None:
            scores[key] = 1.0 / (0.2 + best)
    if not scores:
        return None, 0.0, 0
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    if len(ranked) > 1 and ranked[0][1] < CLEAR_LEAD * ranked[1][1]:
        return None, 0.0, len(ranked)
    return ranked[0][0], ranked[0][1], len(ranked)


def track_box_near(g: Game, tid, t):
    """The track's box in the frame closest to t (within 1 s), and that frame's time."""
    if tid is None:
        return None, None
    best = None
    for ft, boxes in g.window(t - 1.0, t + 1.0):
        for b in boxes:
            if b[0] == 1 and str(b[6]) == tid and (best is None or abs(ft - t) < abs(best[0] - t)):
                best = (ft, b)
    return best if best else (None, None)


def attribute(tracks_path: Path, video: Path | None = None):
    stem = tracks_path.name.replace(".json", "")          # <game>.v4
    game_id = stem.split(".")[0]
    g = Game(tracks_path)
    games = {x["id"]: x for x in yaml.safe_load(GAMES.read_text())["games"]}
    names = jersey_groups(g.doc, games[game_id])           # {group: "Valley"/"Opponent"}
    group_of_team = {v: k for k, v in names.items()}
    split = json.loads(tracks_path.with_name(stem + ".split.json").read_text())["shots"]
    threes_path = tracks_path.with_name(stem + ".threes.json")
    threes = json.loads(threes_path.read_text())["shots"] if threes_path.exists() else []
    by_t = {round(s["t"], 2): s for s in threes}
    players = json.loads((JERSEYS / f"{stem}.players-all.json").read_text())
    track_player = player_index(players)
    check = ColorCheck(video, g.doc) if video else None

    out = []
    for shot in split:
        if shot["kind"] not in ("FG", "FT"):
            continue
        three = by_t.get(round(shot["t"], 2), {})
        team_group = group_of_team[shot["team"]]
        team_players = {k: p for k, p in players.items() if p["team"] == team_group}
        tid, how, box_t, box = find_shooter(g, shot, three, team_group, check)
        when = box_t if box_t is not None else shot["t"] - 1.0
        player, step, conf = None, "unknown", 0.0
        if tid and tid in track_player and players[track_player[tid]]["team"] == team_group:
            player, step, conf = track_player[tid], "own number", 0.85
        elif tid:
            nb = neighbour_player(g, tid, team_group, track_player)
            if nb and players[nb]["team"] == team_group:
                player, step, conf = nb, "neighbour track", 0.6
        if player is None:
            cand, score, n = on_court_player(g, when, box, team_group, team_players, track_player)
            if cand:
                player, step, conf = cand, f"on court ({n} candidates)", round(min(0.5, 0.15 + 0.35 / max(1, n - 1)), 2)
        if how == "nearest to ball":
            conf *= 0.85
        pts = 0
        if shot["made"]:
            pts = 1 if shot["kind"] == "FT" else (three.get("points") or 2)
        out.append({
            "t": shot["t"], "team": shot["team"], "kind": shot["kind"], "made": shot["made"],
            "points_value": 1 if shot["kind"] == "FT" else (three.get("points") or 2),
            "pts": pts, "shooter_track": tid, "shooter_from": how,
            "player": players[player]["number"] if player else None, "player_key": player,
            "step": step, "confidence": round(conf, 2), "box": [round(v) for v in box[1:5]] if box else None,
            "box_t": box_t if box_t is not None else when,
        })
    return out


def box_score(attrs):
    table = defaultdict(lambda: Counter())
    for a in attrs:
        row = table[(a["team"], a["player"] or "unknown")]
        if a["kind"] == "FT":
            row["fta"] += 1
            row["ftm"] += a["made"]
        else:
            row["fga"] += 1
            row["fgm"] += a["made"]
            if a["points_value"] == 3:
                row["fg3a"] += 1
                row["fg3m"] += a["made"]
        row["pts"] += a["pts"]
    return table


def split_ma(s):
    m, a = s.split("/")
    return int(m), int(a)


def hudl_rows(game_id):
    games = {x["id"]: x for x in yaml.safe_load(STATS.read_text())["games"]}
    g = games[game_id]
    out = {}
    for team, key in (("Valley", "valley_players"), ("Opponent", "opponent_players")):
        rows = defaultdict(Counter)
        for r in g[key]:
            num = str(r[0]) if r[0] is not None else "unknown"
            fg, fg3, ft = split_ma(r[3]), split_ma(r[4]), split_ma(r[5])
            rows[num]["fga"] += fg[1]
            rows[num]["fgm"] += fg[0]
            rows[num]["fg3a"] += fg3[1]
            rows[num]["fta"] += ft[1]
            rows[num]["pts"] += r[2]
        out[team] = rows
    return out


def compare(attrs, game_id):
    ours, theirs = box_score(attrs), hudl_rows(game_id)
    report = {}
    for team in ("Opponent", "Valley"):
        truth = theirs[team]
        known_truth = {n for n in truth if n != "unknown"}
        mine = {n: c for (tm, n), c in ours.items() if tm == team}
        att = sum(c["fga"] + c["fta"] for c in mine.values())
        named = sum(c["fga"] + c["fta"] for n, c in mine.items() if n != "unknown")
        # Attempts given to a number that Hudl lists for this team.
        on_roster = sum(c["fga"] + c["fta"] for n, c in mine.items() if n in known_truth)
        # Best case of right numbers: per number, the overlap of our FGA and Hudl's.
        overlap = sum(min(mine.get(n, Counter())["fga"], truth[n]["fga"]) for n in known_truth)
        hudl_known_fga = sum(truth[n]["fga"] for n in known_truth)
        err = {n: mine.get(n, Counter())["fga"] - truth[n]["fga"] for n in sorted(known_truth, key=lambda x: int(x))}
        extra = {n: c["fga"] for n, c in mine.items() if n not in known_truth and n != "unknown" and c["fga"]}
        report[team] = {
            "attempts": att, "named": named, "named_share": round(named / max(1, att), 2),
            "on_hudl_numbers": on_roster, "fga_overlap": overlap, "hudl_numbered_fga": hudl_known_fga,
            "fga_error_by_number": err, "fga_to_numbers_not_on_hudl": extra,
            "abs_fga_error": sum(abs(v) for v in err.values()),
        }
    return report


def crops(attrs, video: Path, out: Path, n=20, seed=0):
    """Zoomed crops of random named attributions: the shooter box 2.5x, label on top."""
    import cv2
    import numpy as np

    random.seed(seed)
    named = [a for a in attrs if a["player"] and a["box"]]
    pick = sorted(random.sample(named, min(n, len(named))), key=lambda a: a["t"])
    cap = cv2.VideoCapture(str(video))
    tiles = []
    for i, a in enumerate(pick):
        cap.set(cv2.CAP_PROP_POS_MSEC, a["box_t"] * 1000)
        ok, img = cap.read()
        if not ok:
            continue
        x0, y0, x1, y1 = a["box"]
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        half = int(max(w, h) * 0.9)
        crop = img[max(0, cy - half):cy + half, max(0, cx - half):cx + half].copy()
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, (300, 300))
        bx0 = int((x0 - max(0, cx - half)) * 300 / max(1, 2 * half))
        by0 = int((y0 - max(0, cy - half)) * 300 / max(1, 2 * half))
        bx1 = int((x1 - max(0, cx - half)) * 300 / max(1, 2 * half))
        by1 = int((y1 - max(0, cy - half)) * 300 / max(1, 2 * half))
        cv2.rectangle(crop, (bx0, by0), (bx1, by1), (0, 255, 255), 1)
        m, s = divmod(int(a["t"]), 60)
        label = f"{i} {a['team'][:3]} #{a['player']} {a['kind']} {m}:{s:02d}"
        cv2.rectangle(crop, (0, 0), (300, 26), (0, 0, 0), -1)
        cv2.putText(crop, label, (4, 19), 0, 0.55, (255, 255, 255), 1)
        cv2.putText(crop, a["step"][:24], (4, 292), 0, 0.45, (0, 255, 0), 1)
        tiles.append(crop)
    if not tiles:
        return pick
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 5)
    rows = [np.hstack(tiles[i:i + 5]) for i in range(0, len(tiles), 5)]
    cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return pick


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", type=Path)
    ap.add_argument("--check", action="store_true", help="compare with Hudl and write hand-check crops")
    ap.add_argument("--video", type=Path, help="film, for the jersey color check at each shot and the crops")
    args = ap.parse_args()
    attrs = attribute(args.tracks, args.video)
    stem = args.tracks.name.replace(".json", "")
    game_id = stem.split(".")[0]
    out = args.tracks.with_name(stem + ".player_stats.json")
    table = box_score(attrs)
    zero = dict.fromkeys(("fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts"), 0)
    rows = [{"team": tm, "number": n, **zero, **c} for (tm, n), c in sorted(table.items())]
    out.write_text(json.dumps({"shots": attrs, "box_score": rows}, indent=1))
    steps = Counter(a["step"].split(" (")[0] for a in attrs)
    print(f"{len(attrs)} shots; by step: {dict(steps)}")
    for r in rows:
        print(f"  {r['team']:8} #{r['number']:>7}: FG {r['fgm']}/{r['fga']}  3PT {r['fg3m']}/{r['fg3a']}"
              f"  FT {r['ftm']}/{r['fta']}  PTS {r['pts']}")
    print("wrote", out)
    if args.check:
        rep = compare(attrs, game_id)
        print(json.dumps(rep, indent=1))
        if args.video:
            sheet = args.tracks.with_name(stem + ".player_check.jpg")
            pick = crops(attrs, args.video, sheet)
            for i, a in enumerate(pick):
                print(f"  check {i}: t={a['t']} {a['team']} #{a['player']} {a['kind']} via {a['step']} conf {a['confidence']}")
            print("wrote", sheet)


if __name__ == "__main__":
    main()
