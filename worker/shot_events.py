"""Turn a tracks file into drafted shot events and a team box score.

Runs on Modal after detection (film_worker.make_events), and locally for checks:
    ml/.venv/bin/python worker/shot_events.py ml/data/tracks/valley-vs-archbishop-mitty.v4.json \
        --valley-jersey "light blue" --opponent-jersey white \
        --video "backend/sample_data/Valley Christian vs Archbishop Mitty CCS - Tactical.mp4"

Steps 1 to 3 use the tracks alone; step 4 also needs the film:
1. Game window and halftime: ml/tools/game_window.py.
2. Shot attempts and makes: ml/tools/shots.py.
3. Team and free throw vs field goal: ml/tools/shot_split.py. Warmup and dead-ball shots are
   dropped. Which color group is Valley comes from the jersey colors the coach gave; without
   them it's a guess the coach can flip with one click (teams_guessed).
4. 2s and 3s: ml/tools/three_point.py, from the shooter's feet and the 3-point arc it finds in
   the film. It reads only the frames at each shot's takeoff (seeking, not the whole film), so
   the film can be a signed R2 link. Without film every field goal is "fg2" with a low
   shot-type confidence kept out of the call's confidence, so it doesn't flatten the review order.
5. Team rebounds and turnovers: worker/possession_events.py (ml/tools/possession.py version 2),
   from who holds the ball, with each holder's jersey read from the film (front to back, about
   2 minutes; best with a local file). Steals and assists come out too but are marked hidden.

Every event gets one confidence from 0 to 1: the weakest of its parts (attempt, make, team,
free throw, and 2 or 3 when the film was read). The parts are kept in the event's "parts" so the review screen can say why.
These are rough rules, not calibrated probabilities.
"""

import sys
from pathlib import Path

# On Modal the tools sit next to this file; locally they're in ml/tools.
_here = Path(__file__).resolve().parent
for p in (_here, _here.parent / "ml" / "tools"):
    if (p / "shots.py").exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import game_window  # noqa: E402
import shot_split  # noqa: E402
import shots as shot_rules  # noqa: E402

# Jersey colors a coach can pick, as BGR. Kept here (not in track_teams.py) so this step
# doesn't need torch or YOLOX.
JERSEY_BGR = {
    "white": (235, 235, 235),
    "black": (35, 35, 35),
    "gray": (140, 140, 140),
    "light blue": (225, 190, 140),
    "royal blue": (170, 70, 30),
    "navy": (80, 40, 20),
    "red": (40, 40, 200),
    "maroon": (40, 25, 110),
    "orange": (30, 120, 240),
    "gold": (40, 180, 230),
    "green": (50, 130, 30),
    "purple": (120, 40, 100),
}

EVENTS_VERSION = 4   # 2: field goals labeled 2 or 3 from the film. 3: court spot and zone per field goal.
                     # 4: team rebounds and turnovers (steals and assists hidden)
PLAY_TYPES = ("oreb", "dreb", "to")  # non-shot events the site shows and counts


def _lab(bgr):
    import cv2
    import numpy as np

    return cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)


def group_names(doc: dict, valley_jersey: str | None, opponent_jersey: str | None) -> tuple[dict, bool]:
    """Which tracker color group is Valley. Same matching as shot_split.jersey_groups, with a
    wider color list. Returns (names, guessed)."""
    import numpy as np

    centers = doc.get("group_centers_lab")
    if not centers or valley_jersey not in JERSEY_BGR or opponent_jersey not in JERSEY_BGR:
        return {0: "Valley", 1: "Opponent"}, True

    def feat(v):  # brightness counts for half, as in track_teams.feature
        return np.array([0.5 * v[0], v[1], v[2]])

    c0, c1 = (feat(c) for c in centers)
    v, o = feat(_lab(JERSEY_BGR[valley_jersey])), feat(_lab(JERSEY_BGR[opponent_jersey]))
    keep = np.linalg.norm(c0 - v) + np.linalg.norm(c1 - o) <= np.linalg.norm(c0 - o) + np.linalg.norm(c1 - v)
    return ({0: "Valley", 1: "Opponent"} if keep else {0: "Opponent", 1: "Valley"}), False


def confidence_parts(s: dict, team_sure: float, guessed: bool) -> dict:
    """Rough confidence for each part of one call, 0 to 1."""
    attempt = min(1.0, 0.6 * s.get("ball_score", 0.5) + 0.4 * s.get("rim_score", 0.5))
    if s["made"]:
        # evidence counts the frames that back the make; 0 means the ball was lost in the net.
        make = 0.9 if s.get("evidence", 0) >= 2 else 0.75 if s.get("evidence", 0) == 1 else 0.5
    else:
        make = 0.8  # the hand check found about 1 in 9 called misses were makes
    # The team comes from the whole game's basket vote, so it's as sure as that vote. A shooter
    # seen in the other team's jersey is often a crowd mix-up, but worth a look.
    team = 0.5 if guessed else team_sure
    if not guessed and s.get("shooter_jersey") not in (None, "unsure") and s["shooter_jersey"] != s["team"]:
        team = min(team, 0.75)
    still = s.get("stillness")
    if still is None:
        kind = 0.5
    elif s["kind"] == "FT":
        kind = 0.9 if still < 0.06 else 0.65
    else:
        kind = 0.95 if still > 0.2 else 0.6
    return {k: round(v, 2) for k, v in
            {"attempt": attempt, "make": make, "team": team, "free_throw": kind}.items()}


def shot_type_confidence(s: dict) -> float | None:
    """How sure the 2 or 3 call is, from how far the feet were from the line. None when there was
    no call (no takeoff found, so it stays a 2 by default)."""
    if s.get("points") is None:
        return None
    margin = s.get("margin")
    if margin is None:   # feet behind the basket, where no arc runs: a 2, but an odd spot
        return 0.6
    # Right on the line is a coin flip; 3 ft or more either side is clear.
    sure = 0.55 + 0.4 * min(1.0, abs(margin) / 3.0)
    if s.get("arc_source") != "own frame":   # line not seen in this frame, so the game's average arc
        sure = min(sure, 0.85)
    return round(sure, 2)


def box_score(events: list[dict], plays_known: bool = True) -> dict:
    """Team totals from events that aren't deleted or hidden. Same shape the API returns."""
    out = {}
    for team in ("valley", "opponent"):
        mine = [e for e in events if e["team"] == team and e.get("status") != "deleted" and not e.get("hidden")]
        shots = [e for e in mine if e.get("type", "shot") == "shot"]
        fg = [e for e in shots if e["shot_type"] in ("fg2", "fg3")]
        fg3 = [e for e in shots if e["shot_type"] == "fg3"]
        ft = [e for e in shots if e["shot_type"] == "ft"]
        made = lambda xs: sum(1 for e in xs if e["made"])  # noqa: E731
        fgm, fg3m, ftm = made(fg), made(fg3), made(ft)
        plays = {k: sum(1 for e in mine if e.get("type") == k) for k in PLAY_TYPES}
        out[team] = {"fgm": fgm, "fga": len(fg), "fg3m": fg3m, "fg3a": len(fg3),
                     "ftm": ftm, "fta": len(ft), "pts": 2 * fgm + fg3m + ftm,
                     "oreb": plays["oreb"], "dreb": plays["dreb"], "reb": plays["oreb"] + plays["dreb"],
                     "to": plays["to"]}
        if not plays_known:
            out[team].update(oreb=None, dreb=None, reb=None, to=None)
    return out


def build_events(doc: dict, valley_jersey: str | None = None, opponent_jersey: str | None = None,
                 video: str | None = None, possession: bool = True) -> dict:
    """video: the film (a path or a link) for 2s and 3s and for holders' jerseys. Without it field
    goals stay "fg2" and rebounds and turnovers use the tracker's team split (lower confidence).
    possession=False skips rebounds and turnovers."""
    window = game_window.find_window(doc)
    span = (window["start"], window["end"]) if window.get("found") else (0.0, doc["frames"][-1][0])
    half_break = window.get("halftime") if window.get("found") else None

    found = shot_rules.find_shots(doc)
    names, guessed = group_names(doc, valley_jersey, opponent_jersey)
    # shot_split names the color groups from ml/games.yaml colors; hand it ours instead.
    original_groups = shot_split.jersey_groups
    shot_split.jersey_groups = lambda _doc, _game: names
    try:
        labeled, info = shot_split.split(doc, found, {}, span, half_break)
    finally:
        shot_split.jersey_groups = original_groups

    # How clear the basket vote is: the gap between the two answers in standard deviations.
    # 72 to 33 (Mitty) is about 3.8, which is about as sure as this gets.
    three_point = "not run"
    if video:
        import three_point as threes

        try:
            threes.classify(doc, labeled, video)
            fg = [s for s in labeled if s["kind"] == "FG"]
            three_point = f"ran: {sum(s.get('points') is None for s in fg)} of {len(fg)} field goals without a takeoff"
        except Exception as exc:  # a bad film link shouldn't lose the shots; they stay 2s
            three_point = f"failed: {exc}"[:200]
            for s in labeled:
                s.pop("points", None)

    a, b = info["votes"].values()
    z = abs(a - b) / max(1.0, (a + b) ** 0.5)
    team_sure = min(0.95, 0.5 + 0.12 * z)
    events = []
    for s in labeled:
        if s["kind"] not in ("FG", "FT"):
            continue  # warmup or dead ball
        parts = confidence_parts(s, team_sure, guessed)
        if s["kind"] == "FT":
            shot_type, type_sure = "ft", 1.0
        else:
            type_sure = shot_type_confidence(s)
            shot_type = "fg3" if s.get("points") == 3 else "fg2"
            if type_sure is None and three_point.startswith("ran"):
                type_sure = 0.5   # film read but no shooter found: a 2 by default, worth a look
            if type_sure is not None:
                parts["shot_type"] = type_sure   # counts toward the call's confidence
        events.append({
            "type": "shot",
            "t": round(float(s["t"]), 2),
            "team": s["team"].lower(),
            "shot_type": shot_type,
            "made": bool(s["made"]),
            "confidence": min(parts.values()),
            "player_number": None,
            "rim": s.get("rim"),
            "parts": {**parts, "shot_type": type_sure if type_sure is not None else 0.3},
            "detail": {k: s.get(k) for k in ("make_t", "evidence", "stillness", "ft_pair", "basket", "half",
                                             "shooter_track", "shooter_jersey", "ball_score", "rim_score",
                                             "margin", "arc_source", "take", "court_x", "court_y", "zone")},
        })
    possession_info = None
    if possession:
        try:
            import possession_events

            got = possession_events.build_possession(doc, labeled, info, span, half_break, names, video)
            events += got["events"]
            possession_info = got["info"]
        except Exception as exc:  # rebounds and turnovers failing shouldn't lose the shots
            possession_info = {"error": f"{exc}"[:300]}
        events.sort(key=lambda e: e["t"])
    return {
        "version": EVENTS_VERSION,
        "window": {"start": span[0], "end": span[1], "found": bool(window.get("found")),
                   "halftime": half_break, "quarter_breaks": window.get("quarter_breaks", [])},
        "teams_guessed": guessed,
        "valley_basket_first_half": info["valley_basket_first_half"],
        "votes": info["votes"],
        "dropped": {"warmup": info["warmup_dropped"], "dead_ball": info["dead_ball_dropped"]},
        "three_point": three_point,
        "possession": possession_info,
        "events": events,
        "box_score": box_score(events, bool(possession_info) and not possession_info.get("error")),
    }


def main() -> None:
    import argparse
    import gzip
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--valley-jersey")
    parser.add_argument("--opponent-jersey")
    parser.add_argument("--video", help="film path or link, for 2s and 3s")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--no-possession", action="store_true", help="skip rebounds and turnovers")
    args = parser.parse_args()
    opener = gzip.open if args.tracks.suffix == ".gz" else open
    with opener(args.tracks, "rt") as f:
        doc = json.load(f)
    result = build_events(doc, args.valley_jersey, args.opponent_jersey, args.video, not args.no_possession)
    print(f"3-point: {result['three_point']}")
    print(f"window {result['window']['start']} to {result['window']['end']}, halftime {result['window']['halftime']}, "
          f"teams guessed: {result['teams_guessed']}, {len(result['events'])} events")
    for team, row in result["box_score"].items():
        print(f"  {team:9} FG {row['fgm']}/{row['fga']}  3PT {row['fg3m']}/{row['fg3a']}  "
              f"FT {row['ftm']}/{row['fta']}  PTS {row['pts']}  OREB {row['oreb']}  DREB {row['dreb']}  "
              f"REB {row['reb']}  TO {row['to']}")
    if result.get("possession"):
        print(f"possession: {result['possession']}")
        hidden = [e for e in result["events"] if e.get("hidden")]
        for team in ("valley", "opponent"):
            print(f"  hidden {team:9} STL {sum(e['type'] == 'stl' and e['team'] == team for e in hidden)}  "
                  f"AST {sum(e['type'] == 'ast' and e['team'] == team for e in hidden)}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=1))
        print("wrote", args.out)


if __name__ == "__main__":
    main()
