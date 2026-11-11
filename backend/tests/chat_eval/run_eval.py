"""Chatbot test questions: does the assistant get box score facts right?

The questions and their right answers are worked out from game_events.json (AIM's drafted
shots for one test game, numbers only), loaded into a throwaway in-memory database. Each answer
passes when it contains every required fact (shooting as "5/12" or "5 of 12", points as a
number) and nothing it must not say. Target: 95% of questions pass.

    cd backend
    .venv/bin/python -m tests.chat_eval.run_eval --list     # print questions and answers, no API calls
    .venv/bin/python -m tests.chat_eval.run_eval            # ask the real assistant (needs ANTHROPIC_API_KEY)

A full run asks about 25 questions, each a few model calls at low effort.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "eval-only")

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from collections import defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base_class import Base  # noqa: E402
from app.models import GameUpload, Team  # noqa: E402
from app.services import chat, shot_events  # noqa: E402

# Real game data stays out of the public repo: the fixture lives in the gitignored ml/data folder.
EVENTS_FILE = Path(__file__).resolve().parents[3] / "ml" / "data" / "chat_eval" / "game_events.json"
HERE = Path(__file__).parent
HALFTIME = 2094  # film seconds when the first half ended in this game


def line(events):
    fg = [e for e in events if e["shot_type"] in ("fg2", "fg3")]
    fg3 = [e for e in events if e["shot_type"] == "fg3"]
    fg2 = [e for e in events if e["shot_type"] == "fg2"]
    ft = [e for e in events if e["shot_type"] == "ft"]
    m = lambda xs: sum(1 for e in xs if e["made"])  # noqa: E731
    return {"fg": (m(fg), len(fg)), "fg2": (m(fg2), len(fg2)), "fg3": (m(fg3), len(fg3)), "ft": (m(ft), len(ft)),
            "pts": 2 * m(fg) + m(fg3) + m(ft)}


def frac(pair):
    """Accept "5/12", "5-12", "5 of 12" or "5-for-12"."""
    a, b = pair
    return rf"\b{a}\s*(?:/|-|of|-for-|for)\s*{b}\b"


def num(n):
    return rf"(?<![\d/]){n}(?![\d/])"


def questions(events):
    by_team = {t: [e for e in events if e["team"] == t] for t in ("valley", "opponent")}
    box = {t: line(xs) for t, xs in by_team.items()}
    v, o = box["valley"], box["opponent"]
    qs = [
        ("How many points did Valley score?", [num(v["pts"])]),
        ("How many points did the opponent score?", [num(o["pts"])]),
        ("What was the final score?", [num(v["pts"]), num(o["pts"])]),
        ("How did Valley shoot from the field?", [frac(v["fg"])]),
        ("How did Valley shoot from three?", [frac(v["fg3"])]),
        ("How did Valley do at the free throw line?", [frac(v["ft"])]),
        ("What did the opponent shoot from the field?", [frac(o["fg"])]),
        ("What did the opponent do from three?", [frac(o["fg3"])]),
        ("How were the opponent's free throws?", [frac(o["ft"])]),
        ("How many 2-pointers did Valley make, out of how many?", [frac(v["fg2"])]),
        ("How many threes did the opponent make?", [num(o["fg3"][0])]),
        ("How many free throws did the opponent miss?", [num(o["ft"][1] - o["ft"][0])]),
        ("By how many points did the winner win?", [num(abs(v["pts"] - o["pts"]))]),
        ("How many shots did AIM count in this game, both teams together?", [num(len(events))]),
    ]
    # Halves.
    for team, label in (("valley", "Valley"), ("opponent", "the opponent")):
        first = line([e for e in by_team[team] if e["t"] < HALFTIME])
        second = line([e for e in by_team[team] if e["t"] >= HALFTIME])
        qs.append((f"How did {label} shoot from the field in the first half? The first half ended "
                   f"{HALFTIME // 60} minutes {HALFTIME % 60} seconds into the film.", [frac(first["fg"])]))
        qs.append((f"How many points did {label} score in the second half? The second half started "
                   f"{HALFTIME // 60} minutes {HALFTIME % 60} seconds into the film.", [num(second["pts"])]))
    # Players with a jersey number.
    for team, label in (("valley", "Valley"), ("opponent", "the opponent")):
        players = defaultdict(list)
        for e in by_team[team]:
            if e["player_number"] is not None:
                players[e["player_number"]].append(e)
        lines = {n: line(xs) for n, xs in players.items()}
        best = max(x["pts"] for x in lines.values())
        leaders = [n for n, x in lines.items() if x["pts"] == best]
        qs.append((f"Who scored the most points for {label}? Answer with the jersey number.",
                   [rf"(?:#|number |No\. ?)(?:{'|'.join(str(n) for n in leaders)})\b", num(best)]))
        top = sorted(lines, key=lambda n: (-len(players[n]), n))[:2]
        for n in top:
            qs.append((f"How did {label}'s number {n} shoot from the field?", [frac(lines[n]["fg"])]))
    missing = sum(1 for e in by_team["valley"] if e["player_number"] is None)
    qs.append(("How many of Valley's shots have no jersey number yet?", [num(missing)]))
    # Things the data can't answer: it must say so, not invent.
    qs.append(("How many rebounds did Valley get?", [r"(?i)(?:not|n't|doesn.t|isn.t|no) .{0,40}(?:track|record|count|have)"]))
    qs.append(("How did Valley's number 99 shoot?", [r"(?i)\b(?:no|zero|0|didn.t|did not|not)\b"]))
    return qs


def load_game():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    team = Team(name="Valley")
    db.add(team)
    db.flush()
    upload = GameUpload(team_id=team.id, title="Test game", storage_url="r2://x/test.mp4", status="ready",
                        detection_status="done", events_status="done")
    db.add(upload)
    db.flush()
    events = json.loads(EVENTS_FILE.read_text())["events"]
    shot_events.load_events(db, upload, {"events": events})
    db.commit()
    return db, team.id, upload.id, events


def grade(answer: str, patterns: list[str]) -> bool:
    return all(re.search(p, answer) for p in patterns)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="print the questions and answers only")
    parser.add_argument("--only", type=int, help="ask just the first N questions")
    args = parser.parse_args()
    db, team_id, upload_id, events = load_game()
    qs = questions(events)[: args.only]
    if args.list:
        for i, (q, pats) in enumerate(qs, 1):
            print(f"{i:2}. {q}\n    must match: {pats}")
        print(f"{len(qs)} questions")
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY to ask the real assistant, or use --list.")
    chat.get_settings().anthropic_api_key = os.environ["ANTHROPIC_API_KEY"]
    passed = 0
    for i, (q, pats) in enumerate(qs, 1):
        out = chat.answer(db, team_id, [{"role": "user", "content": q}], upload_id=upload_id)
        ok = grade(out["answer"], pats)
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {i:2}. {q}\n     {out['answer'][:300]!r}")
    print(f"\n{passed}/{len(qs)} passed ({passed / len(qs):.0%}; target 95%)")


if __name__ == "__main__":
    main()
