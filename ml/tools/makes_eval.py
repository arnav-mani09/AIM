"""Check every made and missed call against the score bug: the true time of each score change.

Usage:
    ml/.venv/bin/python ml/tools/makes_eval.py [--games mitty] [--no-film] [--list]
    ml/.venv/bin/python ml/tools/makes_eval.py --build-truth --games mitty   # reread the score bug (7 min a game)
    ml/.venv/bin/python ml/tools/makes_eval.py --games mitty --zoom 1234.5   # sheet of rim crops around a time

Truth. The game film has a score overlay in the bottom left corner. --build-truth reads both scores
4 times a second (digit templates matched to labeled examples, ml/data/labels/score_digits.npz), keeps
values that hold for at least a second, and writes every change (team, +1/+2/+3, when the old score
was last seen and the new one first seen) to ml/data/labels/score_changes.json. A change that is undone
right after (an operator's correction) is dropped. On Mitty and Riordan the changes add up to the
Hudl box score exactly: every made field goal (2s and 3s) and free throw for both teams. The overlay
is truth only: many gyms have none, so the shot rules never read it.

Matching. The operator updates the score 1.5 to 3.5 s after the ball goes through (median 2.2 s).
An AIM make matches a score change of the same team when its make time is between 10 s before the
change was first seen and 0.3 s after (or inside the stretch the overlay was hidden). One to one,
with maximum one-to-one coverage, preferring the usual lag when exploring matches.
Then each score change falls in one bucket:
    found       AIM called a make for that team (kind noted: FG or FT, and 2 or 3)
    called miss AIM has an attempt of that team there but called it a miss
    wrong team  AIM's make there went to the other team
    dropped     AIM found the attempt but left it out (warmup, dead ball, fouled)
    not found   no attempt at all
and every AIM make left over is a false make.

Prints FGM/FGA/FTM/FTA/points per team for AIM, the score bug and Hudl (attempts only from Hudl).
Runs the same steps as worker/shot_events.py (window, shots, split, 2s and 3s).
Defaults to the development game, Mitty; Riordan requires explicit --games riordan.
Both games have influenced development; neither is a globally untouched holdout.
Score changes label makes only, so this is event precision/recall, not miss accuracy.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ML = Path(__file__).resolve().parents[1]
ROOT = ML.parent
sys.path.insert(0, str(ROOT / "worker"))

TRUTH = ML / "data/labels/score_changes.json"
DIGITS = ML / "data/labels/score_digits.npz"
HUDL = ML / "data/stats/2026-27-hudl-box-scores.yaml"
# id, film, score boxes in the bottom left 330 x 190 corner (x0, y0, x1, y1) and whose score each is.
GAMES = {
    "mitty": ("valley-vs-archbishop-mitty", "Valley Christian vs Archbishop Mitty CCS - Tactical.mp4",
              {"Opponent": (66, 70, 142, 106), "Valley": (186, 70, 262, 106)}),
    "riordan": ("valley-vs-archbishop-riordan", "Valley Christian vs Archbishop Riordan - Tactical.mp4",
                {"Opponent": (66, 55, 160, 100), "Valley": (222, 58, 328, 97)}),
}
JERSEYS = ("light blue", "white")
LAG = 2.2                 # usual seconds from the make to the score bug changing
WINDOW = (-10.0, 0.3)     # make time relative to the change being first seen
NEAR = 8.0                # an attempt this close before the change explains it (called miss, dropped)


# ---------- truth from the score bug ----------

def read_digits(box, reps, labels):
    """The number in one score box, or None when it doesn't read cleanly."""
    import cv2
    import numpy as np

    n, lab, st, _ = cv2.connectedComponentsWithStats((box > 200).astype(np.uint8), 8)
    h = box.shape[0]
    comps = sorted((st[i][0], st[i][2], (lab[st[i][1]:st[i][1] + st[i][3], st[i][0]:st[i][0] + st[i][2]] == i))
                   for i in range(1, n) if 0.55 * h <= st[i][3] < 0.98 * h and st[i][4] > 30)
    parts = []
    for _x, w, m in comps:
        m = m.astype(np.uint8) * 255
        parts += [m[:, :w // 2], m[:, w // 2:]] if w > 0.95 * m.shape[0] else [m]   # two digits touching
    if not 1 <= len(parts) <= 2:
        return None
    val = 0
    for m in parts:
        d = cv2.resize(m, (16, 24), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        dist = np.abs(reps - d).mean(axis=(1, 2))
        j = int(dist.argmin())
        if dist[j] > 0.15:
            return None
        val = val * 10 + int(labels[j])
    return val


def segments(times, vals, min_n=4):
    """Runs of one value (at least min_n reads), blips dropped, kept non-decreasing unless a lower
    value holds 30 s (a real correction)."""
    segs = []
    for t, v in zip(times, vals):
        if v is None:
            continue
        if segs and segs[-1]["v"] == v:
            segs[-1]["end"], segs[-1]["n"] = t, segs[-1]["n"] + 1
        else:
            segs.append({"v": v, "start": t, "end": t, "n": 1})
    out = []
    for s in (s for s in segs if s["n"] >= min_n):
        if out and (out[-1]["v"] == s["v"] or (s["v"] < out[-1]["v"] and s["n"] < 120)):
            if out[-1]["v"] == s["v"]:
                out[-1]["end"] = s["end"]
            continue
        out.append(dict(s))
    return out


def changes(times, vals, team):
    segs = segments(times, vals)
    ev = [{"team": team, "delta": b["v"] - a["v"], "score": b["v"], "seen_old": round(a["end"], 2),
           "seen_new": round(b["start"], 2)} for a, b in zip(segs, segs[1:])]
    # A change undone within 30 s is the operator fixing a mistake: drop both.
    keep = []
    for e in ev:
        if keep and e["delta"] < 0 and keep[-1]["delta"] == -e["delta"] and e["seen_new"] - keep[-1]["seen_new"] < 30:
            keep.pop()
            continue
        keep.append(e)
    return keep


def build_truth(game):
    import cv2
    import numpy as np

    gid, film, boxes = GAMES[game]
    z = np.load(DIGITS)
    reps, labels = z[game + "_reps"], z[game + "_digits"]
    cap = cv2.VideoCapture(str(ROOT / "backend/sample_data" / film))
    step = int(round(cap.get(cv2.CAP_PROP_FPS) / 4))
    times, vals, i = [], {k: [] for k in boxes}, 0
    while cap.grab():
        if i % step == 0:
            ok, img = cap.retrieve()
            g = cv2.cvtColor(img[880:1070, 0:330], cv2.COLOR_BGR2GRAY)
            times.append(i / cap.get(cv2.CAP_PROP_FPS))
            for team, (x0, y0, x1, y1) in boxes.items():
                vals[team].append(read_digits(g[y0:y1, x0:x1], reps, labels))
        i += 1
    ev = sorted((e for team in boxes for e in changes(times, vals[team], team)), key=lambda e: e["seen_new"])
    data = json.loads(TRUTH.read_text()) if TRUTH.exists() else {}
    data[game] = ev
    TRUTH.write_text(json.dumps(data, indent=0))
    print(f"{game}: {len(ev)} score changes, final " + ", ".join(
        f"{team} {max([e['score'] for e in ev if e['team'] == team] or [0])}" for team in boxes))


# ---------- AIM's calls ----------

def run_pipeline(game, film=True):
    """Same steps as worker/shot_events.build_events; returns every attempt (dropped ones too)."""
    import game_window
    import shot_events
    import shot_split
    import shots as shot_rules

    gid, video, _ = GAMES[game]
    doc = json.loads((ML / f"data/tracks/{gid}.v4.json").read_text())
    window = game_window.find_window(doc)
    span = (window["start"], window["end"]) if window.get("found") else (0.0, doc["frames"][-1][0])
    found = shot_rules.find_shots(doc)
    names, _ = shot_events.group_names(doc, *JERSEYS)
    original = shot_split.jersey_groups
    shot_split.jersey_groups = lambda _doc, _game: names
    try:
        labeled, _info = shot_split.split(doc, found, {}, span, window.get("halftime") if window.get("found") else None)
    finally:
        shot_split.jersey_groups = original
    if film:
        import three_point
        three_point.classify(doc, labeled, str(ROOT / "backend/sample_data" / video))
    return doc, labeled


def box(shots):
    out = {}
    for team in ("Valley", "Opponent"):
        fg = [s for s in shots if s.get("team") == team and s["kind"] == "FG"]
        ft = [s for s in shots if s.get("team") == team and s["kind"] == "FT"]
        fgm, ftm = sum(s["made"] for s in fg), sum(s["made"] for s in ft)
        fg3m = sum(s["made"] for s in fg if s.get("points") == 3)
        out[team] = {"FGM": fgm, "FGA": len(fg), "FTM": ftm, "FTA": len(ft), "3PM": fg3m,
                     "PTS": 2 * fgm + fg3m + ftm}
    return out


def hudl(gid):
    text = HUDL.read_text()
    game = re.search(r"(?m)^  - id: " + re.escape(gid) + r"\s*$([\s\S]*?)(?=^  - id: |\Z)", text)
    if game is None:
        raise ValueError(f"No Hudl totals for {gid}")
    out = {}
    for team in ("valley", "opponent"):
        totals = re.search(team + r":\s*\{([^}]*)\}", game.group(1))
        if totals is None:
            raise ValueError(f"No Hudl {team} totals for {gid}")
        seg = totals.group(1)
        f2, f3, ft = (tuple(map(int, re.search(k + r":\s*(\d+)/(\d+)", seg).groups())) for k in ("fg2", "fg3", "ft"))
        out[team.capitalize()] = {"FGM": f2[0] + f3[0], "FGA": f2[1] + f3[1], "FTM": ft[0], "FTA": ft[1],
                                  "3PM": f3[0], "PTS": 2 * (f2[0] + f3[0]) + f3[0] + ft[0]}
    return out


def make_time(s):
    return s["t"] if s.get("make_t") is None else s["make_t"]


def validate_truth(truth, totals):
    """Reject incomplete or invalid cached score changes before reporting event metrics."""
    for change in truth:
        if (change["team"] not in totals or change["delta"] not in (1, 2, 3)
                or change["seen_old"] > change["seen_new"]):
            raise ValueError(f"Invalid score change: {change}")
    for team, expected in totals.items():
        changes = [change for change in truth if change["team"] == team]
        actual = {"FGM": sum(change["delta"] in (2, 3) for change in changes),
                  "FTM": sum(change["delta"] == 1 for change in changes),
                  "3PM": sum(change["delta"] == 3 for change in changes),
                  "PTS": sum(change["delta"] for change in changes)}
        if any(actual[key] != expected[key] for key in actual):
            raise ValueError(f"Score changes disagree with Hudl for {team}: {actual}")


def match(truth, shots):
    """Pairs score changes with AIM makes (see the module docstring). Returns (buckets, false makes)."""
    makes = [s for s in shots if s["made"] and s["kind"] in ("FG", "FT")]
    pairs = []
    for i, c in enumerate(truth):
        lo = min(c["seen_old"], c["seen_new"] + WINDOW[0])
        for j, s in enumerate(makes):
            mt = make_time(s)
            if s["team"] == c["team"] and lo <= mt <= c["seen_new"] + WINDOW[1]:
                pairs.append((abs(c["seen_new"] - mt - LAG), i, j))
    candidates = {index: [] for index in range(len(truth))}
    for _distance, truth_index, shot_index in sorted(pairs):
        candidates[truth_index].append(shot_index)
    owners = {}

    def assign(truth_index, visited):
        for shot_index in candidates[truth_index]:
            if shot_index in visited:
                continue
            visited.add(shot_index)
            if shot_index not in owners or assign(owners[shot_index], visited):
                owners[shot_index] = truth_index
                return True
        return False

    for truth_index in sorted(candidates, key=lambda index: (len(candidates[index]), index)):
        assign(truth_index, set())
    got = {truth_index: makes[shot_index] for shot_index, truth_index in owners.items()}
    buckets = []
    for i, c in enumerate(truth):
        lo, hi = min(c["seen_old"], c["seen_new"] - NEAR - 2), c["seen_new"] + WINDOW[1]
        near = [s for s in shots if lo <= s["t"] <= hi]
        if i in got:
            s = got[i]
            kind = "FT" if c["delta"] == 1 else "FG"
            note = "" if s["kind"] == kind else f"called {s['kind']}"
            if kind == "FG" and s["kind"] == "FG" and s.get("points") in (2, 3) and s["points"] != c["delta"]:
                note = f"called {s.get('points') or 2}"
            buckets.append(("found", c, s, note))
            continue
        mine = [s for s in near if not s["made"] and s.get("team") == c["team"] and s.get("kind") in ("FG", "FT")]
        other = [s for s in near if s.get("team") not in (None, c["team"]) and s["made"] and s.get("kind") in ("FG", "FT")]
        drop = [s for s in near if s.get("kind") in ("warmup", "dead_ball", "fouled")]
        if mine:
            buckets.append(("called miss", c, mine[-1], ""))
        elif other:
            buckets.append(("wrong team", c, other[-1], ""))
        elif drop:
            buckets.append(("dropped", c, drop[-1], drop[-1]["kind"]))
        else:
            buckets.append(("not found", c, None, ""))
    false = [s for j, s in enumerate(makes) if j not in owners]
    return buckets, false


def clock(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def event_report(truth, predictions):
    """Serializable event audit; unmatched makes are not independently labeled misses."""
    buckets, false = match(truth, predictions)
    found = sum(bucket == "found" for bucket, *_rest in buckets)
    count = found + len(false)
    return {"matched": found, "scores": len(truth), "unmatched_makes": len(false),
            "precision": found / count if count else None,
            "recall": found / len(truth) if truth else None,
            "events": [{"bucket": bucket, "truth": change, "prediction": shot, "note": note}
                       for bucket, change, shot, note in buckets],
            "false_makes": false, "predictions": predictions}


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def zoom(game, times, out, span=(-0.6, 2.6), step=0.2):
    """Rim crops every `step` s around each time (0.6 s before to 2.6 s after), the ball circled
    in yellow, two rows of tiles per time."""
    import cv2
    import numpy as np

    gid, video, _ = GAMES[game]
    doc = json.loads((ML / f"data/tracks/{gid}.v4.json").read_text())
    cap = cv2.VideoCapture(str(ROOT / "backend/sample_data" / video))
    rows = []
    for t0 in times:
        tiles, last = [], None
        n = int(round((span[1] - span[0]) / step)) + 1
        for k in range(n):
            t = t0 + span[0] + step * k
            i = int(round(t * doc["fps"]))
            rims = [b for b in doc["frames"][i][1] if b[0] == 3 and b[5] >= 0.5]
            if rims:
                r = max(rims, key=lambda b: b[3] - b[1])
                if last is None or abs((r[1] + r[3]) / 2 - (last[1] + last[3]) / 2) < 3 * (last[3] - last[1]):
                    last = r
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, img = cap.read()
            if not ok:
                continue
            if last is not None:
                w = max(20, int(last[3] - last[1]))
                cx, cy = int((last[1] + last[3]) / 2), int(last[2])
                x0, y0 = max(0, cx - 2 * w), max(0, cy - 2 * w)
                crop = img[y0:cy + 3 * w, x0:cx + 2 * w].copy()
                sx, sy = 160 / max(1, crop.shape[1]), 200 / max(1, crop.shape[0])
                crop = cv2.resize(crop, (160, 200))
                for b in doc["frames"][i][1]:
                    if b[0] == 0 and b[5] >= 0.2:
                        bx, by = ((b[1] + b[3]) / 2 - x0) * sx, ((b[2] + b[4]) / 2 - y0) * sy
                        cv2.circle(crop, (int(bx), int(by)), 9, (0, 255, 255), 1)
            else:
                crop = cv2.resize(img, (160, 200))
            cv2.putText(crop, f"{t:.1f}", (2, 14), 0, 0.45, (0, 255, 0), 1)
            tiles.append(crop)
        tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % 8)
        rows += [np.hstack(tiles[j:j + 8]) for j in range(0, len(tiles), 8)]
    cv2.imwrite(str(out), np.vstack(rows))
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="mitty", help="development: mitty; additional development fixture: riordan (explicit opt-in)")
    ap.add_argument("--build-truth", action="store_true")
    ap.add_argument("--no-film", action="store_true", help="skip 2s and 3s (faster; predicted points are unavailable)")
    ap.add_argument("--list", action="store_true", help="print every miss and false make")
    ap.add_argument("--report-json", type=Path, help="save frozen predictions, event audit and input/source fingerprints")
    ap.add_argument("--zoom", help="comma separated times for a rim crop sheet")
    ap.add_argument("--out", type=Path, default=Path("zoom.jpg"))
    args = ap.parse_args()
    games = args.games.split(",")
    if any(game not in GAMES for game in games):
        ap.error("--games must contain only mitty and/or riordan")
    if args.build_truth:
        for g in games:
            build_truth(g)
        return
    if args.zoom:
        zoom(games[0], [float(x) for x in args.zoom.split(",")], args.out)
        return
    truth_all = json.loads(TRUTH.read_text())
    reports = {"film": not args.no_film, "truth_sha256": fingerprint(TRUTH), "games": {},
               "source_sha256": {str(path.relative_to(ROOT)): fingerprint(path)
                                 for path in (Path(__file__), ML / "tools/shots.py", ML / "tools/shot_split.py",
                                              ML / "tools/game_window.py", ROOT / "worker/shot_events.py",
                                              ML / "tools/three_point.py")}}
    for g in games:
        gid = GAMES[g][0]
        truth = truth_all[g]
        hd = hudl(gid)
        validate_truth(truth, hd)
        _doc, shots = run_pipeline(g, film=not args.no_film)
        report = event_report(truth, shots)
        report["tracks_sha256"] = fingerprint(ML / f"data/tracks/{gid}.v4.json")
        reports["games"][g] = report
        aim = box(shots)
        print(f"== {g}")
        for team in ("Valley", "Opponent"):
            tr = [c for c in truth if c["team"] == team]
            bug = {"FGM": sum(c["delta"] in (2, 3) for c in tr), "FTM": sum(c["delta"] == 1 for c in tr),
                   "3PM": sum(c["delta"] == 3 for c in tr), "PTS": sum(c["delta"] for c in tr)}
            a, h = aim[team], hd[team]
            predicted_points = "3PM n/a PTS n/a" if args.no_film else f"3PM {a['3PM']:2} PTS {a['PTS']:3}"
            difference = "n/a" if args.no_film else f"{a['PTS'] - h['PTS']:+d}"
            print(f"  {team:8} AIM  FG {a['FGM']:2}/{a['FGA']:2} FT {a['FTM']:2}/{a['FTA']:2} {predicted_points}"
                  f"   bug FGM {bug['FGM']:2} 3PM {bug['3PM']:2} FTM {bug['FTM']:2} PTS {bug['PTS']:3}"
                  f"   Hudl FG {h['FGM']:2}/{h['FGA']:2} FT {h['FTM']:2}/{h['FTA']:2} PTS {h['PTS']:3}   diff {difference}")
        buckets, false = match(truth, shots)
        counts = {}
        for b, c, _s, note in buckets:
            k = (b, "FT" if c["delta"] == 1 else "FG")
            counts[k] = counts.get(k, 0) + 1
        fk = {"FG": sum(s["kind"] == "FG" for s in false), "FT": sum(s["kind"] == "FT" for s in false)}
        print("  score changes: " + ", ".join(f"{b} {k} {n}" for (b, k), n in sorted(counts.items())))
        print(f"  false makes: FG {fk['FG']}, FT {fk['FT']}")
        found = sum(bucket == "found" for bucket, *_rest in buckets)
        precision = f"{found / (found + len(false)):.1%}" if found + len(false) else "n/a"
        recall = f"{found / len(truth):.1%}" if truth else "n/a"
        print(f"  event precision {precision}, recall {recall} ({found}/{len(truth)} scores matched); miss accuracy unavailable")
        notes = [f"{clock(c['seen_new'])} {note}" for b, c, s, note in buckets if b == "found" and note]
        print("  found but kind or points wrong: " + ", ".join(notes))
        if args.list:
            for b, c, s, note in buckets:
                if b != "found":
                    st = f"shot t {s['t']:.1f} {s.get('kind')} {s.get('team')} made={s['made']} ev={s.get('evidence')}" if s else ""
                    print(f"    {b:11} {c['team']:8} +{c['delta']} seen {c['seen_new']:.1f} (old {c['seen_old']:.1f})  {st} {note}")
            for s in false:
                print(f"    false make {s['team']:8} {s['kind']} t {s['t']:.1f} make_t {make_time(s):.1f} ev {s.get('evidence')}"
                      f" rescued={bool(s.get('rescued'))}")
    if args.report_json:
        args.report_json.write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    main()
