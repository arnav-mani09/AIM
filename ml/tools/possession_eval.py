"""Repeatable check of possession.py on every game that has tracks and a Hudl box score.

Usage:
    ml/.venv/bin/python ml/tools/possession_eval.py [--method v2] [--games mitty,riordan]
    ml/.venv/bin/python ml/tools/possession_eval.py --make-moments [--seed 7 --n 30]  # sample moments to label

Prints, per game and per team, offensive and defensive rebounds, turnovers, steals and assists
next to Hudl, plus the total absolute error per stat. Then scores the team with the ball at a
fixed set of hand-labeled live moments.

The moments are drawn at random from live play (enough players on screen and moving, not in
the 2 s after a shot while the ball is in the air), independent of any method's timeline, so
every version is scored on the same moments. Labels live in
ml/data/labels/possession_moments.json as {game: {time: "Valley" | "Opponent" | "?"}}, made by
looking at the sheets --make-moments writes ("?" means the frame can't tell, and is skipped).
The set so far: seed 7 (30 a game) and seed 8 (20 a game), 61 clear moments over both games.
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import possession as P  # noqa: E402
from shot_split import motion  # noqa: E402

ML = Path(__file__).resolve().parents[1]
ROOT = ML.parent
LABELS = ML / "data/labels/possession_moments.json"
GAMES = {
    "mitty": ("valley-vs-archbishop-mitty", "Valley Christian vs Archbishop Mitty CCS - Tactical.mp4"),
    "riordan": ("valley-vs-archbishop-riordan", "Valley Christian vs Archbishop Riordan - Tactical.mp4"),
}
STATS = ("oreb", "dreb", "to", "stl", "ast")
N_MOMENTS = 30


def tracks_path(game_id):
    return ML / "data/tracks" / f"{game_id}.v4.json"


def sample_moments(res, n=N_MOMENTS, seed=7):
    doc, (start, end), hb = res["doc"], res["window"], res["half_break"]
    shots = [s["t"] for s in res["split"]["shots"]]
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        t = round(rng.uniform(start, end), 1)
        if hb and hb[0] - 5 <= t <= hb[1] + 5:
            continue
        if any(0 <= t - s <= 2.0 or 0 <= s - t <= 0.5 for s in shots):
            continue
        if P.players_around(doc, t - 1, t + 1) < P.MIN_PLAYERS:
            continue
        m = motion(doc, t - 2, t + 1, step=0.5)
        if m is None or m < P.DEAD_MOTION:
            continue
        out.append(t)
    return sorted(out)


def moment_sheets(res, video, moments, stem, tag=""):
    """Five moments per sheet: ball crops 0.5 s before, at and after, and the whole frame."""
    items = [{"t": t, "label": f"t={t}"} for t in moments]
    return P.event_sheets(res["doc"], video, items, ML / "data/tracks" / (stem + f".moments{tag}"), offsets=(-0.5, 0.0, 0.5))


def score_moments(timeline, labels):
    right = wrong = 0
    misses = []
    for t, truth in sorted(labels.items(), key=lambda kv: float(kv[0])):
        if truth not in ("Valley", "Opponent"):
            continue
        got = P.team_at_time(timeline, float(t))
        if got == truth:
            right += 1
        else:
            wrong += 1
            misses.append(f"{float(t):.1f}:{truth[0]}->{(got or '-')[0]}")
    return right, wrong, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="v2")
    ap.add_argument("--games", default="mitty,riordan")
    ap.add_argument("--make-moments", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n", type=int, default=N_MOMENTS)
    ap.add_argument("--quiet", action="store_true", help="only the summary lines")
    args = ap.parse_args()
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    tot_right = tot_n = 0
    for key in args.games.split(","):
        game_id, film = GAMES[key]
        res = P.analyze(tracks_path(game_id), game_id, ROOT / "backend/sample_data" / film, args.method)
        if args.make_moments:
            labels.setdefault(game_id, {})
            moments = [t for t in sample_moments(res, args.n, args.seed) if str(t) not in labels[game_id]]
            for t in moments:
                labels[game_id].setdefault(str(t), "")
            for p in moment_sheets(res, ROOT / "backend/sample_data" / film, moments, f"{game_id}.v4", f"_s{args.seed}_"):
                print("wrote", p)
            continue
        counts = P.count(res["events"])
        truth = P.hudl(game_id)
        err = {k: 0 for k in STATS}
        print(f"{key}: {len(res['timeline'])} possessions, method {args.method}")
        print(f"  {'':9}" + "".join(f"{k:>10}" for k in STATS))
        for team in ("Valley", "Opponent"):
            row = f"  {team:9}"
            for k in STATS:
                row += f"{counts[team][k]:>5} ({truth[team][k]:>2})"
                err[k] += abs(counts[team][k] - truth[team][k])
            print(row)
        print(f"  {'abs err':9}" + "".join(f"{err[k]:>10}" for k in STATS))
        lab = labels.get(game_id, {})
        if lab:
            r, w, misses = score_moments(res["timeline"], lab)
            tot_right, tot_n = tot_right + r, tot_n + r + w
            print(f"  moments right {r}/{r + w}" + ("" if args.quiet else f"  wrong: {' '.join(misses)}"))
    if args.make_moments:
        LABELS.parent.mkdir(parents=True, exist_ok=True)
        LABELS.write_text(json.dumps(labels, indent=1))
        print("wrote", LABELS, "(fill in the labels)")
    elif tot_n:
        print(f"moments right {tot_right}/{tot_n} over both games")


if __name__ == "__main__":
    main()
