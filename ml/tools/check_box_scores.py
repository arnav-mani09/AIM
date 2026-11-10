"""Check a transcribed box score file: player rows must add up to the team totals.

Usage:
    ml/.venv/bin/python ml/tools/check_box_scores.py ml/data/stats/2026-27-hudl-box-scores.yaml

For each team it checks field goals, threes, free throws, and that each player's points equal
2*FG + 3PT + FT. Prints the final score so it can be compared with the scoreboard.
"""

import argparse
from pathlib import Path

import yaml


def split(s: str) -> tuple[int, int]:
    made, att = s.split("/")
    return int(made), int(att)


def check_team(label: str, rows: list, totals: dict) -> tuple[int, list[str]]:
    problems, fg, fg3, ft, pts = [], [0, 0], [0, 0], (0, 0), 0
    for row in rows:
        number, name, p, f, f3, t = row[:6]
        (fm, fa), (tm, ta), (xm, xa) = split(f), split(f3), split(t)
        if 2 * fm + tm + xm != p:
            problems.append(f"{label} #{number} {name}: points {p} but shots give {2 * fm + tm + xm}")
        for acc, (m, a) in ((fg, (fm, fa)), (fg3, (tm, ta))):
            acc[0] += m
            acc[1] += a
        ft = (ft[0] + xm, ft[1] + xa)
        pts += p
    two, three, free = split(totals["fg2"]), split(totals["fg3"]), split(totals["ft"])
    want_fg = (two[0] + three[0], two[1] + three[1])
    for what, got, want in (("FG", tuple(fg), want_fg), ("3PT", tuple(fg3), three), ("FT", ft, free)):
        if got != want:
            problems.append(f"{label} {what}: players add to {got[0]}/{got[1]}, team total is {want[0]}/{want[1]}")
    team_pts = 2 * want_fg[0] + three[0] + free[0]
    if pts != team_pts:
        problems.append(f"{label} points: players add to {pts}, team totals give {team_pts}")
    return team_pts, problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    for game in yaml.safe_load(args.path.read_text())["games"]:
        valley, p1 = check_team("Valley", game["valley_players"], game["team_totals"]["valley"])
        if "opponent_players" in game:
            opp, p2 = check_team("Opponent", game["opponent_players"], game["team_totals"]["opponent"])
        else:
            t = game["team_totals"]["opponent"]
            two, three, free = split(t["fg2"]), split(t["fg3"]), split(t["ft"])
            opp, p2 = 2 * (two[0] + three[0]) + three[0] + free[0], ["Opponent players: partial table, not checked"]
        print(f"{game['id']}: Valley {valley}, {game['opponent']} {opp}")
        for p in p1 + p2:
            print("   ", p)
        if not p1 + p2:
            print("    all rows add up")


if __name__ == "__main__":
    main()
