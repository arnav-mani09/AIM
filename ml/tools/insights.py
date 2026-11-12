"""Advanced stats, player insights and scouting reports from what the pipeline already writes.

Usage:
    ml/.venv/bin/python ml/tools/insights.py game valley-vs-archbishop-mitty [more games] [--hudl]
    ml/.venv/bin/python ml/tools/insights.py scout --team Opponent --games <game> [<game> ...]
    ml/.venv/bin/python ml/tools/insights.py scout --team Valley --games <game> <game>

Inputs per game, all in ml/data/tracks unless noted (no film, no GPU, a second or two per game):
- <game>.v4.threes.json: every shot with team, FG/FT/warmup, made, 2 vs 3, shooter feet in the
  frame, the rim box at takeoff and the game's 3-point arcs (three_point.py, on top of
  shot_split.py's split.json).
- <game>.v4.player_stats.json: shot to jersey number with a confidence (player_stats.py).
- <game>.v4.possession.json: who has the ball over time, rebounds, turnovers, steals, assists
  (possession.py). Still being tuned, so everything built on it is marked "rough".
- ml/data/jerseys/<game>.v4.players.json: numbers seen per team and for how long.
- ml/data/stats/2026-27-hudl-box-scores.yaml: Hudl team totals, only for the --hudl check.

Writes ml/data/insights/<game>.insights.json (game), or <team>-<games>.scout.json and .txt
(scout). Both stay local: ml/data is never committed.

How the numbers are built:
- Counts first, rates second. A game (or a pile of games) is a set of counts per team and per
  player; every percentage is computed from summed counts, so a multi-game rollup is just the
  sum of the games' counts with the rates recomputed (never an average of percentages).
- Every stat carries "source" (which files it comes from) and "trust":
    solid: shot attempts, makes and free throws (shot_split, checked against Hudl).
    fair:  anything that needs 2 vs 3 (eFG%, TS%, 3PA rate) or a jersey number.
    rough: zones inside the arc (rim / paint / midrange need the feet's distance, which is
           rough geometry) and everything from possession.json (possessions, ratings,
           rebound and turnover rates, shot timing, second chance and transition points).
- Zones. three_point.py measures how far past the arc the feet were in rough feet ("margin");
  the shot distance is 19.75 ft plus that margin. The direction comes from the feet's spot
  around the arc's own ellipse (the painted arc as the camera sees it): 3s past the ellipse's
  widest point toward the baseline are corner 3s, the rest above the break (set by eye on the
  check sheets). Inside the arc the direction is too rough to trust, so 2s split by distance
  only: rim (within 4.5 ft), paint (within free throw line distance, so a short wing shot counts
  as paint) and midrange. Shots with no feet found are "unknown".
- Players. A shot counts for a number only when player_stats' confidence is at least
  PLAYER_CONF (own number, a neighbour track, or a short on-court list); the rest go to
  "unknown player". Under SMALL_SAMPLE field goal attempts a player is flagged small sample.
- Shot timing. Seconds from the start of the team's possession (possession.json timeline) to
  the shot: early (under EARLY_S), middle, late (over LATE_S). Over MAX_POSS_S means the
  timeline probably swallowed a dead ball, so the timing is unknown.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACKS = ROOT / "ml" / "data" / "tracks"
JERSEYS = ROOT / "ml" / "data" / "jerseys"
STATS = ROOT / "ml" / "data" / "stats" / "2026-27-hudl-box-scores.yaml"
OUT = ROOT / "ml" / "data" / "insights"

TEAMS = ("Valley", "Opponent")
GAME_MINUTES = 32           # high school: 4 quarters of 8 minutes
PLAYER_CONF = 0.5           # minimum player_stats confidence to give a shot to a number
SMALL_SAMPLE = 8            # fewer field goal attempts than this: small sample
EARLY_S, LATE_S = 8.0, 20.0
MAX_POSS_S = 45.0           # longer than the 35 s shot clock plus slack: the timeline is off
TRANSITION_S = 6.0          # a first-chance shot this early in a possession counts as transition

# Court geometry (rough feet; three_point.py's margin is feet past the 19 ft 9 in arc).
ARC_FT = 19.75
RIM_FT = 4.5                # within this of the basket: at the rim
PAINT_FT = 13.75            # free throw line distance; the side-to-side direction inside the arc is
                            # too rough to test the 12 ft lane width, so this is a distance cut
MAX_SHOT_FT = 40.0          # farther than this means the feet were found in the wrong place
CORNER_NEAR_DEG = 90        # 3s past the arc ellipse's widest point toward the baseline are corner
CORNER_FAR_DEG = 65         # the far half of the arc is foreshortened, so its corners start earlier

ZONES = ("rim", "paint", "midrange", "corner3", "above_break3", "unknown")
ZONE_NAMES = {"rim": "at the rim", "paint": "in the paint", "midrange": "midrange",
              "corner3": "corner 3s", "above_break3": "above-the-break 3s", "unknown": "unknown spot"}
TIMING = ("early", "middle", "late", "unknown")

SOLID, FAIR, ROUGH = "solid", "fair", "rough"
SRC_SHOTS = "shots + split"
SRC_THREES = "shots + split + threes"
SRC_POSS = "possession (being improved, counts less trusted)"
SRC_PLAYER = "player_stats (confident numbers only)"


# ---------------------------------------------------------------- loading

def load_game(game: str) -> dict:
    """The game's live shots (FG and FT) with zone, player and possession context attached."""
    stem = TRACKS / f"{game}.v4"
    threes = json.loads(Path(f"{stem}.threes.json").read_text())
    arcs = threes.get("arcs", {})
    ps_path = Path(f"{stem}.player_stats.json")
    by_t = {}
    if ps_path.exists():
        by_t = {round(a["t"], 2): a for a in json.loads(ps_path.read_text())["shots"]}
    poss_path = Path(f"{stem}.possession.json")
    poss = json.loads(poss_path.read_text()) if poss_path.exists() else None
    shots = []
    for s in threes["shots"]:
        if s.get("kind") not in ("FG", "FT") or s.get("team") not in TEAMS:
            continue
        a = by_t.get(round(s["t"], 2), {})
        conf = a.get("confidence", 0.0)
        player = a.get("player") if a.get("player") and conf >= PLAYER_CONF else None
        shot = {"t": s["t"], "team": s["team"], "kind": s["kind"], "made": bool(s["made"]),
                "player": player, "player_conf": conf}
        if s["kind"] == "FG":
            shot["value"] = s.get("points") or 2
            shot["value_known"] = s.get("points") is not None
            shot.update(zone_of(s, arcs))
        else:
            shot["value"] = 1
        shot["pts"] = shot["value"] if shot["made"] else 0
        shots.append(shot)
    shots.sort(key=lambda x: x["t"])
    if poss:
        attach_possessions(shots, poss)
    players_seen = {}
    pj = JERSEYS / f"{game}.v4.players.json"
    if pj.exists():
        # Team group (0/1) to Valley/Opponent, learned from player_stats' keys like "1#25".
        group_team = {}
        for a in by_t.values():
            if a.get("player_key"):
                group_team[a["player_key"].split("#")[0]] = a["team"]
        for key, p in json.loads(pj.read_text()).items():
            team = group_team.get(str(p["team"]))
            if team:
                players_seen[(team, p["number"])] = round(p.get("seconds", 0.0))
    return {"game": game, "shots": shots, "poss": poss, "players_seen": players_seen}


def zone_of(s: dict, arcs: dict) -> dict:
    """Shot distance (rough feet), side angle and zone, from the shooter's feet."""
    feet, rim, margin = s.get("feet"), s.get("rim_at_take"), s.get("margin")
    side = s.get("basket")
    if not feet or not rim or margin is None or side not in arcs:
        return {"zone": "unknown"}
    dist = max(0.0, ARC_FT + margin)
    if dist > MAX_SHOT_FT:
        return {"zone": "unknown"}
    # Angle around the arc's own ellipse: 0 points at the top of the key, +-90 at the ellipse's
    # widest point toward the near (+) or far (-) sideline, beyond that toward the baseline.
    rw = rim[2] - rim[0]
    cx, cy, a, b, th = arcs[side]["ellipse_rim_widths"]
    dx = (feet[0] - (rim[0] + rim[2]) / 2) / rw - cx
    dy = (feet[1] - (rim[1] + rim[3]) / 2) / rw - cy
    th = math.radians(th)
    u = (dx * math.cos(th) + dy * math.sin(th)) / a
    v = (-dx * math.sin(th) + dy * math.cos(th)) / b
    ang = math.degrees(math.atan2(v, u if side == "left" else -u))
    if s.get("points") == 3:
        zone = "corner3" if ang >= CORNER_NEAR_DEG or ang <= -CORNER_FAR_DEG else "above_break3"
    elif dist <= RIM_FT:
        zone = "rim"
    elif dist <= PAINT_FT:
        zone = "paint"
    else:
        zone = "midrange"
    return {"zone": zone, "dist_ft": round(dist, 1), "arc_angle": round(ang)}


def attach_possessions(shots: list, poss: dict) -> None:
    """Seconds into the possession, second chance (after an offensive rebound) and off a turnover."""
    segs = poss["timeline"]
    orebs = {tm: sorted(e["t"] for e in poss["events"] if e["type"] == "oreb" and e["team"] == tm) for tm in TEAMS}
    tos = [e for e in poss["events"] if e["type"] == "to"]
    for s in shots:
        seg = next((g for g in segs if g[0] - 0.5 <= s["t"] <= g[1] + 0.5 and g[2] == s["team"]), None)
        if seg is None:
            s["timing"] = "unknown"
            continue
        s["second_chance"] = any(seg[0] <= t < s["t"] for t in orebs[s["team"]])
        s["off_to"] = any(e["team"] != s["team"] and abs(e["t"] - seg[0]) <= 1.0 for e in tos)
        into = s["t"] - seg[0]
        if s["kind"] == "FT" or into > MAX_POSS_S:
            s["timing"] = "unknown"
        else:
            s["into_poss_s"] = round(into, 1)
            s["timing"] = "early" if into < EARLY_S else "late" if into > LATE_S else "middle"


# ---------------------------------------------------------------- counting

def count_shots(shots: list) -> Counter:
    """Raw counts for any group of shots (a team, a player, a pile of games)."""
    c = Counter()
    for s in shots:
        m = int(s["made"])
        c["pts"] += s["pts"]
        if s["kind"] == "FT":
            c["fta"] += 1
            c["ftm"] += m
            if s.get("second_chance"):
                c["pts_second_chance"] += s["pts"]
            if s.get("off_to"):
                c["pts_off_to"] += s["pts"]
            continue
        c["fga"] += 1
        c["fgm"] += m
        k = "fg3" if s["value"] == 3 else "fg2"
        c[k + "a"] += 1
        c[k + "m"] += m
        c["fga_value_unknown"] += 0 if s.get("value_known", True) else 1
        z = s.get("zone", "unknown")
        c[f"z_{z}_a"] += 1
        c[f"z_{z}_m"] += m
        c[f"z_{z}_pts"] += s["pts"]
        tm = s.get("timing", "unknown")
        c[f"tm_{tm}_a"] += 1
        c[f"tm_{tm}_m"] += m
        if s.get("second_chance"):
            c["pts_second_chance"] += s["pts"]
        elif s.get("timing") == "early" and s.get("into_poss_s", 99) <= TRANSITION_S:
            c["pts_transition"] += s["pts"]
        if s.get("off_to"):
            c["pts_off_to"] += s["pts"]
    return c


def count_possession(poss: dict | None) -> dict:
    """Per team: possessions on the timeline and the event counts."""
    out = {tm: Counter() for tm in TEAMS}
    if not poss:
        return out
    for _, _, tm in poss["timeline"]:
        if tm in out:
            out[tm]["poss_tracked"] += 1
    for tm in TEAMS:
        for k, v in poss.get("counts", {}).get(tm, {}).items():
            out[tm][k] += v
    return out


def game_counts(g: dict) -> dict:
    """Counts per team and per (team, number) for one game."""
    pc = count_possession(g["poss"])
    teams, players = {}, {}
    for tm in TEAMS:
        mine = [s for s in g["shots"] if s["team"] == tm]
        c = count_shots(mine)
        c.update(pc[tm])
        c["games"] = 1
        c["has_poss"] = 1 if g["poss"] else 0
        teams[tm] = c
        for num in sorted({s["player"] or "unknown" for s in mine}, key=num_key):
            pcount = count_shots([s for s in mine if (s["player"] or "unknown") == num])
            pcount["games"] = 1
            pcount["seen_s"] = g["players_seen"].get((tm, num), 0)
            players[(tm, num)] = pcount
    return {"teams": teams, "players": players}


def num_key(n: str):
    return (1, 0) if n == "unknown" else (0, int(n)) if n.isdigit() else (0, 999)


# ---------------------------------------------------------------- rates

def stat(value, source, trust, note=None):
    d = {"value": value, "source": source, "trust": trust}
    if note:
        d["note"] = note
    return d


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def ratio(a, b, nd=2):
    return round(a / b, nd) if b else None


def team_report(c: Counter, opp: Counter) -> dict:
    """Advanced stats for a team from its counts and its opponent's (same games)."""
    fga, fta = c["fga"], c["fta"]
    games = max(1, c["games"])
    r = {
        "games": c["games"],
        "pts": stat(c["pts"], SRC_THREES, SOLID, "points need 2 vs 3, which is close to Hudl"),
        "fg": stat(f"{c['fgm']}/{fga}", SRC_SHOTS, SOLID),
        "fg2": stat(f"{c['fg2m']}/{c['fg2a']}", SRC_THREES, FAIR),
        "fg3": stat(f"{c['fg3m']}/{c['fg3a']}", SRC_THREES, FAIR),
        "ft": stat(f"{c['ftm']}/{fta}", SRC_SHOTS, SOLID),
        "fg_pct": stat(pct(c["fgm"], fga), SRC_SHOTS, SOLID),
        "efg_pct": stat(pct(c["fgm"] + 0.5 * c["fg3m"], fga), SRC_THREES, FAIR),
        "ts_pct": stat(pct(c["pts"], 2 * (fga + 0.44 * fta)), SRC_THREES, FAIR),
        "ft_rate": stat(ratio(fta, fga), SRC_SHOTS, SOLID, "FTA per FGA"),
        "fg3a_rate": stat(ratio(c["fg3a"], fga), SRC_THREES, FAIR, "share of FGA that are 3s"),
        "shot_mix": {}, "points_by_zone": {}, "fg_pct_by_zone": {},
    }
    for z in ZONES:
        a = c[f"z_{z}_a"]
        trust = FAIR if z in ("corner3", "above_break3") else ROUGH
        r["shot_mix"][z] = stat(pct(a, fga), SRC_THREES + " (feet position)", trust, f"{a} FGA")
        r["points_by_zone"][z] = stat(c[f"z_{z}_pts"], SRC_THREES + " (feet position)", trust)
        r["fg_pct_by_zone"][z] = stat(pct(c[f"z_{z}_m"], a), SRC_THREES + " (feet position)", trust,
                                      f"{c[f'z_{z}_m']} of {a}")
    if c["has_poss"] and opp["has_poss"]:
        poss = c["poss_tracked"]
        est = fga - c["oreb"] + c["to"] + 0.44 * fta
        r.update({
            "possessions": stat(poss, SRC_POSS, ROUGH, "team-with-ball changes on the timeline"),
            "possessions_formula": stat(round(est, 1), SRC_SHOTS + " + " + SRC_POSS, ROUGH,
                                        "FGA - OREB + TO + 0.44 FTA"),
            "pace": stat(round((poss + opp["poss_tracked"]) / 2 / games, 1), SRC_POSS, ROUGH,
                         f"possessions per team per {GAME_MINUTES} minutes"),
            "off_ppp": stat(ratio(c["pts"], poss), SRC_THREES + " + " + SRC_POSS, ROUGH, "points per possession"),
            "def_ppp": stat(ratio(opp["pts"], opp["poss_tracked"]), SRC_THREES + " + " + SRC_POSS, ROUGH,
                            "opponent points per opponent possession"),
            "oreb": stat(c["oreb"], SRC_POSS, ROUGH), "dreb": stat(c["dreb"], SRC_POSS, ROUGH),
            "to": stat(c["to"], SRC_POSS, ROUGH), "stl": stat(c["stl"], SRC_POSS, ROUGH),
            "ast": stat(c["ast"], SRC_POSS, ROUGH),
            "oreb_pct": stat(pct(c["oreb"], c["oreb"] + opp["dreb"]), SRC_POSS, ROUGH),
            "dreb_pct": stat(pct(c["dreb"], c["dreb"] + opp["oreb"]), SRC_POSS, ROUGH),
            "to_pct": stat(pct(c["to"], poss), SRC_POSS, ROUGH, "turnovers per possession"),
            "pts_second_chance": stat(c["pts_second_chance"], SRC_THREES + " + " + SRC_POSS, ROUGH),
            "pts_transition": stat(c["pts_transition"], SRC_THREES + " + " + SRC_POSS, ROUGH,
                                   f"first-chance FG points within {TRANSITION_S:.0f} s of getting the ball"),
            "pts_off_to": stat(c["pts_off_to"], SRC_THREES + " + " + SRC_POSS, ROUGH),
            "shot_timing": {t: stat(pct(c[f"tm_{t}_a"], fga), SRC_POSS, ROUGH, f"{c[f'tm_{t}_a']} FGA")
                            for t in TIMING},
        })
    return r


def player_report(c: Counter, team_fga: int) -> dict:
    fga = c["fga"]
    zones = sorted(((z, c[f"z_{z}_a"]) for z in ZONES if c[f"z_{z}_a"] and z != "unknown"), key=lambda x: -x[1])
    timed = sum(c[f"tm_{t}_a"] for t in TIMING if t != "unknown")
    return {
        "games": c["games"], "fga": fga, "fgm": c["fgm"], "fg3a": c["fg3a"], "fg3m": c["fg3m"],
        "fta": c["fta"], "ftm": c["ftm"], "pts": c["pts"],
        "fg_pct": pct(c["fgm"], fga), "share_of_team_fga": pct(fga, team_fga),
        "small_sample": fga < SMALL_SAMPLE,
        "favorite_zones": [{"zone": z, "fga": a, "share": pct(a, fga)} for z, a in zones[:3]],
        "by_zone": {z: {"fga": c[f"z_{z}_a"], "fgm": c[f"z_{z}_m"], "fg_pct": pct(c[f"z_{z}_m"], c[f"z_{z}_a"])}
                    for z in ZONES if c[f"z_{z}_a"]},
        "timing": ({t: {"fga": c[f"tm_{t}_a"], "share": pct(c[f"tm_{t}_a"], timed)} for t in TIMING if t != "unknown"}
                   if timed else None),
        "seen_on_film_s": c["seen_s"] or None,
        "source": SRC_PLAYER, "trust": FAIR,
    }


def build(counts_list: list, team: str | None = None) -> dict:
    """Sum the counts of one or more games and turn them into the insights document."""
    teams = {tm: Counter() for tm in TEAMS}
    players = {}
    for gc in counts_list:
        for tm in TEAMS:
            teams[tm].update(gc["teams"][tm])
        for k, v in gc["players"].items():
            players.setdefault(k, Counter()).update(v)
    # has_poss only counts if every game had possession data
    for tm in TEAMS:
        teams[tm]["has_poss"] = int(teams[tm]["has_poss"] == len(counts_list))
    out = {"teams": {}, "players": {}}
    for tm in ([team] if team else TEAMS):
        opp = teams[TEAMS[1 - TEAMS.index(tm)]]
        out["teams"][tm] = team_report(teams[tm], opp)
        out["players"][tm] = {num: player_report(c, teams[tm]["fga"])
                              for (t, num), c in sorted(players.items(), key=lambda x: num_key(x[0][1])) if t == tm}
    out["trust_levels"] = {SOLID: "shot attempts, makes and free throws; close to Hudl",
                           FAIR: "needs 2 vs 3 or a jersey number; mostly right, check odd ones",
                           ROUGH: "needs feet distance or possession tracking; a direction, not a number to quote"}
    return out


# ---------------------------------------------------------------- scouting text

def fmt_zone_line(p: dict) -> str:
    if not p["favorite_zones"]:
        return ""
    top = p["favorite_zones"][0]
    bz = p["by_zone"][top["zone"]]
    mostly = "mostly " if top["share"] >= 50 else "most often "
    s = f"{mostly}{ZONE_NAMES[top['zone']]} ({bz['fgm']} of {bz['fga']})"
    if len(p["favorite_zones"]) > 1:
        z2 = p["favorite_zones"][1]
        b2 = p["by_zone"][z2["zone"]]
        s += f", then {ZONE_NAMES[z2['zone']]} ({b2['fgm']} of {b2['fga']})"
    return s


def whole(x) -> str:
    return "?" if x is None else f"{round(x)}"


def pts_word(n: int) -> str:
    return f"{n} pt" if n == 1 else f"{n} pts"


def scouting_text(doc: dict, team: str, title: str) -> str:
    t = doc["teams"][team]
    v = lambda k: t[k]["value"]  # noqa: E731
    games = t["games"]
    per = f" over {games} games" if games > 1 else ""
    lines = [title, ""]
    lines.append(f"Team shooting{per}: {v('pts')} points, FG {v('fg')} ({whole(v('fg_pct'))}%), 3PT {v('fg3')}, "
                 f"FT {v('ft')}. Effective FG {whole(v('efg_pct'))}%, true shooting {whole(v('ts_pct'))}%.")
    lines.append(f"{whole(100 * (v('fg3a_rate') or 0))}% of their shots are 3s. They get {v('ft_rate')} free throw "
                 f"tries per field goal try.")
    mix = sorted(((z, t["shot_mix"][z]) for z in ZONES if z != "unknown"), key=lambda x: -(x[1]["value"] or 0))
    parts = [f"{ZONE_NAMES[z]} {whole(m['value'])}% ({t['fg_pct_by_zone'][z]['note']})" for z, m in mix if m["value"]]
    lines.append("Where they shoot from (share of shots, makes): " + "; ".join(parts) + ".")
    if "possessions" in t:
        lines.append(f"Rough, from possession tracking: about {whole(v('pace'))} possessions a game, "
                     f"{v('off_ppp')} points per possession, turnovers on {whole(v('to_pct'))}% of possessions, "
                     f"offensive rebound rate {whole(v('oreb_pct'))}%.")
        tm = t["shot_timing"]
        if tm["early"]["value"] is not None:
            lines.append(f"Rough shot timing: {whole(tm['early']['value'])}% of shots come in the first "
                         f"{EARLY_S:.0f} s of a possession, {whole(tm['late']['value'])}% after {LATE_S:.0f} s.")
    lines += ["", "Players (by jersey number, only where the number read was confident):"]
    players = doc["players"][team]
    ranked = sorted(((n, p) for n, p in players.items() if n != "unknown"), key=lambda x: (-x[1]["fga"], -x[1]["pts"]))
    for num, p in ranked:
        if not p["fga"] and not p["fta"]:
            continue
        s = f"#{num}: {pts_word(p['pts'])}"
        if p["fga"]:
            s += f", takes {whole(p['share_of_team_fga'])}% of the team's shots, FG {p['fgm']} of {p['fga']}"
        if p["fg3a"]:
            s += f", 3PT {p['fg3m']} of {p['fg3a']}"
        if p["fta"]:
            s += f", FT {p['ftm']} of {p['fta']}"
        if p["fga"] >= 4:
            zl = fmt_zone_line(p)
            if zl:
                s += f"; {zl}"
        if p["timing"] and not p["small_sample"]:
            e, lt = p["timing"]["early"]["share"], p["timing"]["late"]["share"]
            if e is not None and e >= 40:
                s += f"; shoots early ({whole(e)}% in the first {EARLY_S:.0f} s, rough)"
            elif lt is not None and lt >= 40:
                s += f"; shoots late ({whole(lt)}% after {LATE_S:.0f} s, rough)"
        lines.append(s + "." + (" Small sample." if p["small_sample"] else ""))
    unk = players.get("unknown")
    if unk:
        lines.append(f"Unknown player (number not read confidently): {unk['fga']} FGA, {unk['fta']} FTA, "
                     f"{pts_word(unk['pts'])} ({whole(unk['share_of_team_fga'])}% of shots).")
    lines += ["", "Shot counts and makes are solid. 2 vs 3 and jersey numbers are mostly right. Zones inside the arc "
              "and anything from possession tracking are rough."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- Hudl check

def hudl_totals(game: str) -> dict | None:
    import yaml
    if not STATS.exists():
        return None
    g = {x["id"]: x for x in yaml.safe_load(STATS.read_text())["games"]}.get(game)
    if not g:
        return None
    out = {}
    for tm, key in (("Valley", "valley"), ("Opponent", "opponent")):
        t = g["team_totals"][key]
        c = Counter()
        for k in ("fg2", "fg3", "ft"):
            m, a = map(int, t[k].split("/"))
            c[k + "m"], c[k + "a"] = m, a
        c["fgm"], c["fga"] = c["fg2m"] + c["fg3m"], c["fg2a"] + c["fg3a"]
        c["pts"] = 2 * c["fg2m"] + 3 * c["fg3m"] + c["ftm"]
        for k in ("oreb", "dreb", "to", "stl", "ast", "paint_pts", "second_chance_pts", "transition_pts", "pts_off_to"):
            c[k] = t.get(k, 0)
        out[tm] = c
    return out


def hudl_compare(game: str, gc: dict) -> list:
    """Rows of (team, stat, AIM, Hudl) for every stat Hudl has."""
    h = hudl_totals(game)
    if not h:
        return []
    rows = []
    for tm in TEAMS:
        a, b = gc["teams"][tm], h[tm]
        oa, ob = gc["teams"][TEAMS[1 - TEAMS.index(tm)]], h[TEAMS[1 - TEAMS.index(tm)]]

        def adv(c, o, poss=None):
            fga, fta = c["fga"], c["fta"]
            p = poss if poss is not None else fga - c["oreb"] + c["to"] + 0.44 * fta
            return {"eFG%": pct(c["fgm"] + 0.5 * c["fg3m"], fga), "TS%": pct(c["pts"], 2 * (fga + 0.44 * fta)),
                    "FT rate": ratio(fta, fga), "3PA rate": ratio(c["fg3a"], fga),
                    "poss (formula)": round(p, 1), "pts/poss": ratio(c["pts"], p),
                    "OREB%": pct(c["oreb"], c["oreb"] + o["dreb"]), "TO%": pct(c["to"], p)}
        aa, ab = adv(a, oa), adv(b, ob)
        for k, label in (("fg", "FG"), ("fg2", "2PT"), ("fg3", "3PT"), ("ft", "FT")):
            rows.append((tm, label, f"{a[k + 'm']}/{a[k + 'a']}", f"{b[k + 'm']}/{b[k + 'a']}"))
        rows.append((tm, "PTS", a["pts"], b["pts"]))
        for k in ("eFG%", "TS%", "FT rate", "3PA rate"):
            rows.append((tm, k, aa[k], ab[k]))
        if a["has_poss"]:
            for k in ("oreb", "dreb", "to", "stl", "ast"):
                rows.append((tm, k.upper() + " (rough)", a[k], b[k]))
            for k in ("poss (formula)", "pts/poss", "OREB%", "TO%"):
                rows.append((tm, k + " (rough)", aa[k], ab[k]))
            rows.append((tm, "poss (timeline, rough)", a["poss_tracked"], "-"))
            rows.append((tm, "2nd chance pts (rough)", a["pts_second_chance"], b["second_chance_pts"]))
            rows.append((tm, "transition pts (rough)", a["pts_transition"], b["transition_pts"]))
            rows.append((tm, "pts off TO (rough)", a["pts_off_to"], b["pts_off_to"]))
        rows.append((tm, "paint pts (rim+paint, rough)", a["z_rim_pts"] + a["z_paint_pts"], b["paint_pts"]))
    return rows


def print_rows(game: str, rows: list) -> None:
    print(f"\n{game}: AIM vs Hudl")
    print(f"  {'team':9} {'stat':30} {'AIM':>8} {'Hudl':>8}")
    for tm, k, a, b in rows:
        print(f"  {tm:9} {k:30} {str(a):>8} {str(b):>8}")


# ---------------------------------------------------------------- main

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("game", help="per-game insights JSON, plus the Hudl check")
    g.add_argument("games", nargs="+")
    g.add_argument("--hudl", action="store_true", help="print team totals next to Hudl")
    s = sub.add_parser("scout", help="scouting report for one team over one or more games")
    s.add_argument("--team", choices=TEAMS, required=True)
    s.add_argument("--games", nargs="+", required=True)
    s.add_argument("--title", default=None)
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    if args.cmd == "game":
        for game in args.games:
            gc = game_counts(load_game(game))
            doc = {"game": game, **build([gc])}
            out = OUT / f"{game}.insights.json"
            out.write_text(json.dumps(doc, indent=1))
            print("wrote", out.relative_to(ROOT))
            if args.hudl:
                print_rows(game, hudl_compare(game, gc))
        return

    counts = [game_counts(load_game(gm)) for gm in args.games]
    doc = {"team": args.team, "games": args.games, **build(counts, team=args.team)}
    title = args.title or f"Scouting report: {args.team}, {len(args.games)} game(s): {', '.join(args.games)}"
    text = scouting_text(doc, args.team, title)
    doc["text"] = text
    base = OUT / f"{slug(args.team)}-{slug('-'.join(args.games))[:80]}.scout"
    Path(f"{base}.json").write_text(json.dumps(doc, indent=1))
    Path(f"{base}.txt").write_text(text)
    print(text)
    print("wrote", Path(f"{base}.json").relative_to(ROOT), "and .txt")


if __name__ == "__main__":
    sys.exit(main())
