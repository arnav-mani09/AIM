"""Frozen-input rebound comparison and bounded film review, not a box-score accuracy proxy.

Freeze before editing: rebound_eval.py --freeze mitty --snapshot /tmp/mitty.before.json
Compare: rebound_eval.py --snapshot /tmp/mitty.before.json --output /tmp/mitty.review.json
Optional --video writes at most --limit film review rows. Labels are optional JSON keyed by
shot time, with type/team (or unknown), evidence (an existing image path), and notes.
Both local games are development data. Unlabeled decisions never enter accuracy metrics.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import possession as P


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(event):
    return (event["type"], event["team"]) if event else None


def compare(doc, fixture, labels=None, limit=6):
    before = {event["shot_t"]: event for event in fixture["events"] if event["type"] in ("oreb", "dreb")}
    decisions = P.rebound_decisions_v2(doc, fixture["split"], fixture["window"],
                                    fixture["half_break"], fixture["runs"])
    rows = []
    scores = {"labeled": 0, "unknown": 0, "before_correct": 0, "after_correct": 0}
    labels = labels or {}
    for decision in decisions:
        shot_t = decision["shot_t"]
        old, new = before.get(shot_t), decision["event"]
        row = {**decision, "before": old, "after": new,
               "outcome_changed": signature(old) != signature(new),
               "evidence_changed": (old or {}).get("how") != (new or {}).get("how"),
               "truth": labels.get(str(shot_t), {"type": "unknown"})}
        truth = row["truth"]
        if truth.get("type") in ("oreb", "dreb", "none"):
            if not truth.get("evidence") or not Path(truth["evidence"]).is_file():
                raise ValueError(f"Film evidence required for label {shot_t}")
            if truth["type"] != "none" and truth.get("team") not in ("Valley", "Opponent"):
                raise ValueError(f"Team required for label {shot_t}")
            expected = None if truth["type"] == "none" else (truth["type"], truth["team"])
            scores["labeled"] += 1
            scores["before_correct"] += signature(old) == expected
            scores["after_correct"] += signature(new) == expected
        else:
            scores["unknown"] += 1
        rows.append(row)
    selected = sorted(rows, key=lambda row: (not row["outcome_changed"], row["reason"], row["shot_t"]))[:limit]
    def totals(events):
        return dict(sorted(Counter(f'{event["team"]}:{event["type"]}' for event in events if event).items()))
    return {"game": fixture["game"], "data_role": "development", "scores": scores,
            "before_counts": totals(before.values()), "after_counts": totals(row["after"] for row in rows),
            "categories": dict(Counter(row["reason"] for row in rows)),
            "outcomes_changed": sum(row["outcome_changed"] for row in rows),
            "review_shot_times": [row["shot_t"] for row in selected], "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--freeze", choices=("mitty", "riordan"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--limit", type=int, default=6, choices=range(1, 21))
    args = parser.parse_args()
    if args.freeze:
        if args.snapshot.exists():
            parser.error("refusing to overwrite a frozen snapshot")
        game = "valley-vs-archbishop-" + args.freeze
        tracks = P.ML / "data/tracks" / f"{game}.v4.json"
        cache = tracks.with_suffix(".holders.json")
        if not cache.exists() or not json.loads(cache.read_text()).get("pixels"):
            parser.error("freeze requires existing pixel holder cache; no film inference is run")
        result = P.analyze(tracks, game)
        fixture = {key: result[key] for key in ("split", "window", "half_break", "timeline", "runs")}
        fixture.update(game=game, tracks=str(tracks), tracks_sha256=digest(tracks),
                       events=[event for event in result["events"] if event["type"] in ("oreb", "dreb")])
        args.snapshot.write_text(json.dumps(fixture, indent=1))
        print("frozen", args.snapshot)
        return
    if not args.output:
        parser.error("--output is required for comparison")
    fixture = json.loads(args.snapshot.read_text())
    tracks = Path(fixture.get("tracks", P.ML / "data/tracks" / f'{fixture["game"]}.v4.json'))
    if fixture.get("tracks_sha256") and digest(tracks) != fixture["tracks_sha256"]:
        parser.error("tracks changed since freeze")
    doc = json.loads(tracks.read_text())
    labels = json.loads(args.labels.read_text()) if args.labels else None
    report = compare(doc, fixture, labels, args.limit)
    report.update(snapshot_sha256=digest(args.snapshot), tracks_sha256=digest(tracks),
                  implementation_sha256=digest(P.__file__))
    if args.video:
        items = [{"t": time, "label": f'{fixture["game"]} miss {time}; truth unknown'}
                 for time in report["review_shot_times"]]
        report["review_images"] = [str(path) for path in P.event_sheets(
            doc, args.video, items, args.output.with_suffix(".review"), offsets=(0, 1, 2, 3, 4, 6, 8), per=1)]
    args.output.write_text(json.dumps(report, indent=1))
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
