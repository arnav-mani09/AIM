"""Labeling progress and a quick quality check, straight from Label Studio.

Usage:
    ml/.venv/bin/python ml/tools/label_status.py            # counts + odd frames
    ml/.venv/bin/python ml/tools/label_status.py --score    # also: pre-label boxes vs final labels on test games

Odd frames are worth a look, not always wrong: game 2's gym has side hoops, so 3 rims is normal there.
--score compares the model's pre-labels with your finished labels (IoU 0.5) on the test-only games
in ml/games.yaml. It flatters the model a little, since labels started from its boxes.
"""

import argparse
import collections
import sys
import urllib.parse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from labelstudio_setup import PROJECT_TITLE, URL, login  # noqa: E402

ML = Path(__file__).resolve().parents[1]


def all_tasks(s) -> list[dict]:
    projects = s.get(f"{URL}/api/projects").json()
    projects = projects.get("results", projects)
    project = next(p for p in projects if p["title"] == PROJECT_TITLE)
    tasks, page = [], 1
    while True:
        r = s.get(f"{URL}/api/tasks", params={"project": project["id"], "page": page, "page_size": 500, "fields": "all"})
        batch = r.json().get("tasks", []) if r.status_code == 200 else []
        if not batch:
            return tasks
        tasks += batch
        page += 1


def game_of(task: dict, games: list[str]) -> str:
    image = urllib.parse.unquote(task["data"].get("image", ""))
    return next((g for g in games if f"/{g}/" in image), "?")


def boxes(result: list[dict]) -> list[tuple]:
    out = []
    for x in result:
        if x.get("type") == "rectanglelabels":
            v = x["value"]
            out.append((v["rectanglelabels"][0], v["x"], v["y"], v["x"] + v["width"], v["y"] + v["height"]))
    return out


def iou(a, b) -> float:
    ix = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    iy = max(0, min(a[4], b[4]) - max(a[2], b[2]))
    inter = ix * iy
    union = (a[3] - a[1]) * (a[4] - a[2]) + (b[3] - b[1]) * (b[4] - b[2]) - inter
    return inter / union if union else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()

    games_cfg = yaml.safe_load((ML / "games.yaml").read_text())["games"]
    games = [g["id"] for g in games_cfg]
    test_games = {g["id"] for g in games_cfg if g.get("split") == "eval"}
    tasks = all_tasks(login())

    counts = collections.defaultdict(collections.Counter)
    odd, hit, total, extra, scored = [], collections.Counter(), collections.Counter(), collections.Counter(), 0
    for t in tasks:
        game = game_of(t, games)
        anns = t.get("annotations", [])
        done = [a for a in anns if not a.get("was_cancelled")]
        state = "labeled" if done else ("skipped" if anns else "left")
        counts[game][state] += 1
        if not done:
            continue
        label = boxes(done[-1]["result"])
        n = collections.Counter(b[0] for b in label)
        issues = []
        if n["ball"] > 1:
            issues.append(f"{n['ball']} balls")
        if n["rim"] > 2:
            issues.append(f"{n['rim']} rims")
        if 0 < n["player"] < 3 or n["player"] > 12:
            issues.append(f"{n['player']} players")
        if n["referee"] > 3:
            issues.append(f"{n['referee']} refs")
        if issues:
            odd.append(f"  {t['id']} {game}: {', '.join(issues)}")
        if args.score and game in test_games and t.get("predictions"):
            scored += 1
            guess, used = boxes(t["predictions"][-1]["result"]), set()
            for g in label:
                total[g[0]] += 1
                best = max(((iou(g, q), i) for i, q in enumerate(guess) if q[0] == g[0] and i not in used), default=(0, None))
                if best[0] >= 0.5:
                    hit[g[0]] += 1
                    used.add(best[1])
            for i, q in enumerate(guess):
                extra[q[0]] += i not in used

    for game in games:
        c = counts.get(game, collections.Counter())
        print(f"{game}: {c['labeled']} labeled, {c['skipped']} skipped, {c['left']} left")
    print(f"total: {len(tasks)} frames")
    print(f"odd frames ({len(odd)}):")
    print("\n".join(odd) or "  none")
    if args.score:
        print(f"pre-labels vs labels on test games ({scored} frames):")
        for c in total:
            print(f"  {c}: found {hit[c]}/{total[c]} ({hit[c] / total[c]:.0%}), extra boxes {extra[c]}")


if __name__ == "__main__":
    main()
