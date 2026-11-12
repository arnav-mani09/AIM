"""Team shooting insights from the shots on the site: advanced shooting stats, a zone table and
plain-language scouting lines, for Valley and the Opponent separately.

Mirrors ml/tools/insights.py so the site and the offline tool agree:
- Counts first, rates last. Any pile of games is the sum of its shots' counts, and every
  percentage is computed from those sums (never an average of per-game percentages).
- Same formulas: eFG% = (FGM + 0.5 x 3PM) / FGA, TS% = PTS / (2 x (FGA + 0.44 x FTA)),
  FT rate = FTA / FGA, 3PA rate = 3PA / FGA.
- Same zone names: rim, paint, midrange, corner3, above_break3 and unknown (no court spot).
  2s split by distance only (rim within 4.5 ft, paint within free throw line distance, then
  midrange), because the side-to-side spot inside the arc is rough from one camera. 3s split into
  corner and above the break. The offline tool reads the corner from the painted arc's ellipse;
  the site only has the court spot (x, y in feet, rim at 0, 0), so here a 3 is a corner 3 when the
  feet were within 8 ft of the baseline line through the rim, the rule three_point.zone_of uses.
- The zone follows the coach's current call: a shot fixed from a 2 to a 3 moves to a 3-point zone.

Only stats that hold up today are here (shots, makes, 2 vs 3, court zone). Possession stats
(pace, points per possession, rebound and turnover rates) are listed as coming soon.
"""

from __future__ import annotations

import math
from collections import Counter

TEAMS = ("valley", "opponent")

RIM_FT = 4.5            # within this of the basket: at the rim
PAINT_FT = 13.75        # free throw line distance (a distance cut, not the lane width)
CORNER_Y_FT = 8.0       # a 3 with the feet this close to the baseline line is a corner 3
MAX_SHOT_FT = 40.0      # farther than this: the feet were found in the wrong place

ZONES = ("rim", "paint", "midrange", "corner3", "above_break3", "unknown")
ZONE_NAMES = {"rim": "at the rim", "paint": "in the paint", "midrange": "midrange",
              "corner3": "corner 3s", "above_break3": "above-the-break 3s", "unknown": "unknown spot"}
ZONE_TITLES = {"rim": "At the rim", "paint": "Paint", "midrange": "Midrange", "corner3": "Corner 3",
               "above_break3": "Above-the-break 3", "unknown": "No spot"}

TEAM_SMALL_SAMPLE = 20  # fewer field goal tries than this: treat the numbers as hints
ZONE_SMALL_SAMPLE = 5   # fewer tries than this in a zone: small sample
ZONE_MENTION = 4        # a zone needs this many tries to be named in a scouting line

COMING_SOON = ["Pace", "Points per possession", "Rebound rates", "Turnover rate"]


def _get(e, k):
    return e[k] if isinstance(e, dict) else getattr(e, k)


def zone_of(x: float | None, y: float | None, three: bool) -> str:
    if x is None or y is None:
        return "unknown"
    dist = math.hypot(x, y)
    if dist > MAX_SHOT_FT:
        return "unknown"
    if three:
        return "corner3" if y <= CORNER_Y_FT else "above_break3"
    if dist <= RIM_FT:
        return "rim"
    if dist <= PAINT_FT:
        return "paint"
    return "midrange"


def count_shots(shots) -> Counter:
    """Raw counts for one team's shots. Each shot is a dict (or row) with shot_type, made, x, y
    and status; deleted shots are skipped."""
    c = Counter()
    for s in shots:
        if _get(s, "status") == "deleted":
            continue
        made = int(bool(_get(s, "made")))
        kind = _get(s, "shot_type")
        if kind == "ft":
            c["fta"] += 1
            c["ftm"] += made
            c["pts"] += made
            continue
        three = kind == "fg3"
        value = 3 if three else 2
        c["fga"] += 1
        c["fgm"] += made
        c["fg3a" if three else "fg2a"] += 1
        c["fg3m" if three else "fg2m"] += made
        c["pts"] += value * made
        z = zone_of(_get(s, "x"), _get(s, "y"), three)
        c[f"z_{z}_a"] += 1
        c[f"z_{z}_m"] += made
        c[f"z_{z}_pts"] += value * made
    return c


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def ratio(a, b, nd=2):
    return round(a / b, nd) if b else None


def team_report(c: Counter, games: int, side: str) -> dict:
    fga, fta = c["fga"], c["fta"]
    zones = []
    for z in ZONES:
        a, m = c[f"z_{z}_a"], c[f"z_{z}_m"]
        if z == "unknown" and not a:
            continue
        zones.append({"zone": z, "label": ZONE_TITLES[z], "attempts": a, "makes": m, "fg_pct": pct(m, a),
                      "share": pct(a, fga), "points": c[f"z_{z}_pts"], "small_sample": 0 < a < ZONE_SMALL_SAMPLE})
    r = {
        "games": games,
        "pts": c["pts"], "fgm": c["fgm"], "fga": fga, "fg2m": c["fg2m"], "fg2a": c["fg2a"],
        "fg3m": c["fg3m"], "fg3a": c["fg3a"], "ftm": c["ftm"], "fta": fta,
        "pts_per_game": round(c["pts"] / games, 1) if games else None,
        "fg_pct": pct(c["fgm"], fga),
        "fg3_pct": pct(c["fg3m"], c["fg3a"]),
        "ft_pct": pct(c["ftm"], fta),
        "efg_pct": pct(c["fgm"] + 0.5 * c["fg3m"], fga),
        "ts_pct": pct(c["pts"], 2 * (fga + 0.44 * fta)),
        "ft_rate": ratio(fta, fga),
        "fg3a_rate": ratio(c["fg3a"], fga),
        "small_sample": fga < TEAM_SMALL_SAMPLE,
        "zones": zones,
    }
    r["lines"] = scouting_lines(r, side)
    return r


def _w(x) -> str:
    return "?" if x is None else f"{round(x)}"


def scouting_lines(r: dict, side: str) -> list[str]:
    """Short plain-language lines built from the numbers. "We" for Valley, "They" for the opponent."""
    we = side == "valley"
    subj, their = ("We", "our") if we else ("They", "their")
    if not r["fga"] and not r["fta"]:
        return [f"No shots counted for {'us' if we else 'them'} yet."]
    lines = []
    games = r["games"]
    per = f", {r['pts_per_game']:g} a game over {games} games" if games > 1 else ""
    lines.append(f"{subj} scored {r['pts']} points{per}: {r['fgm']} of {r['fga']} from the field "
                 f"({_w(r['fg_pct'])}%), {r['fg3m']} of {r['fg3a']} from 3 and {r['ftm']} of {r['fta']} "
                 "at the free throw line.")

    zones = {z["zone"]: z for z in r["zones"]}
    if r["fga"]:
        share3 = _w(100 * (r["fg3a_rate"] or 0))
        threes = [zones[z] for z in ("corner3", "above_break3") if z in zones and zones[z]["attempts"]]
        top3 = max(threes, key=lambda z: z["attempts"], default=None)
        line = f"{subj} take {share3}% of {their} shots from 3"
        if top3 and r["fg3a"] >= ZONE_MENTION and top3["attempts"] * 2 > r["fg3a"]:
            line += f", mostly {ZONE_NAMES[top3['zone']]} ({top3['makes']} of {top3['attempts']})"
        lines.append(line + ".")

        spotted = [z for z in r["zones"] if z["zone"] != "unknown" and z["attempts"]]
        if spotted:
            top = max(spotted, key=lambda z: z["attempts"])
            if top["attempts"] >= ZONE_MENTION:
                lines.append(f"{'Our' if we else 'Their'} most common shot is {ZONE_NAMES[top['zone']]}: "
                             f"{_w(top['share'])}% of {their} shots, {top['makes']} of {top['attempts']} made.")
            sized = [z for z in spotted if z["attempts"] >= ZONE_SMALL_SAMPLE]
            if len(sized) >= 2:
                best = max(sized, key=lambda z: (z["fg_pct"], z["attempts"]))
                worst = min(sized, key=lambda z: (z["fg_pct"], -z["attempts"]))
                if best["fg_pct"] - worst["fg_pct"] >= 15:
                    lines.append(f"{subj} shoot best {ZONE_NAMES[best['zone']]} ({best['makes']} of "
                                 f"{best['attempts']}, {_w(best['fg_pct'])}%) and worst {ZONE_NAMES[worst['zone']]} "
                                 f"({worst['makes']} of {worst['attempts']}, {_w(worst['fg_pct'])}%).")
            rim_paint = sum(zones[z]["points"] for z in ("rim", "paint") if z in zones)
            fg_pts = 2 * r["fg2m"] + 3 * r["fg3m"]
            if fg_pts >= 10:
                lines.append(f"{_w(pct(rim_paint, fg_pts))}% of {their} field goal points come at the rim "
                             f"or in the paint ({rim_paint} of {fg_pts}).")

        if r["fga"] >= 10 and r["ft_rate"] is not None:
            per10 = round(10 * r["ft_rate"])
            if r["ft_rate"] >= 0.35:
                lines.append(f"{subj} get to the free throw line a lot: about {per10} free throws for every "
                             "10 shots.")
            elif r["ft_rate"] <= 0.15:
                lines.append(f"{subj} rarely get to the free throw line: about {per10} free throws for every "
                             "10 shots.")

        unknown = zones.get("unknown")
        if unknown and unknown["attempts"]:
            n = unknown["attempts"]
            lines.append(f"{n} shot{'s' if n != 1 else ''} had no court spot, so the zones leave "
                         f"{'them' if n != 1 else 'it'} out.")
    if r["small_sample"]:
        lines.append(f"Small sample: only {r['fga']} shots so far, so treat these as hints, not habits.")
    return lines


def build(shots, games: int) -> dict:
    """Insights for both teams from a pile of shots (one or more games)."""
    return {side: team_report(count_shots([s for s in shots if _get(s, "team") == side]), games, side)
            for side in TEAMS}
