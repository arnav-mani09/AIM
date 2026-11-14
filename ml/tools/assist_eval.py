"""Offline assist candidate export and film-label-only, event-level evaluation.

Example: python ml/tools/assist_eval.py --tracks ml/data/tracks/GAME.v4.json
  --game GAME --out ml/data/labels/assist_GAME_candidates.json
  --template ml/data/labels/assist_GAME_annotations.json
Then human-review the independent label fields before using --annotations.
No film inference, cache writes, site integration, or box-score truth is used.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from assist_sequences import AssistConfig, detect_assists
from assist_identity import local_hold_evidence, pixel_hold_evidence


def input_provenance(tracks):
    """Fingerprint cache inputs and current adapter dependencies without refreshing caches."""
    tracks = Path(tracks)
    tools = Path(__file__).resolve().parent
    paths = [tracks, tracks.with_suffix(".split.json"), tracks.with_suffix(".holders.json")]
    paths += [tools / name for name in ("assist_eval.py", "assist_sequences.py", "assist_identity.py",
                                      "possession.py", "shots.py", "shot_split.py", "track_teams.py")]
    paths.append(tools.parent / "games.yaml")
    files = {str(path): {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "mtime_ns": path.stat().st_mtime_ns} for path in paths}
    return {"files": files, "shot_cache_status": "unverified_cached_split_not_recomputed",
            "split_predates_current_shots_source": tracks.with_suffix(".split.json").stat().st_mtime_ns
            < (tools / "shots.py").stat().st_mtime_ns}


def cached_inputs(tracks, game):
    """Adapt existing cached tracking, without calling analyze or writing its caches."""
    import possession as baseline

    tracks = Path(tracks)
    doc = json.loads(tracks.read_text())
    split = json.loads(tracks.with_suffix(".split.json").read_text())
    cached = json.loads(tracks.with_suffix(".holders.json").read_text())
    if cached.get("window") != split["window"] or not cached.get("pixels"):
        raise ValueError("Matching pixel holder cache required; no film re-inference allowed")
    games = baseline.yaml.safe_load((baseline.ML / "games.yaml").read_text())["games"]
    game_config = next(item for item in games if item["id"] == game)
    groups = baseline.jersey_groups(doc, game_config)
    sustained = cached["runs"]
    baseline.pixel_votes(sustained, {groups[index]: color for index, color in enumerate(doc["group_centers_lab"])})
    track_team = baseline.label_holders(doc, sustained, groups)
    local = [pixel_hold_evidence(run, baseline.VOTE_MIN, baseline.VOTE_SURE) for run in sustained]
    quick = baseline.hold_runs(doc, *split["window"], min_frames=2)
    baseline_runs = []
    certain = {run["tid"] for run in sustained if run.get("sure") is True}
    referees = {run["tid"] for run in sustained if run.get("ref")}
    for run in quick:
        baseline_runs.append({**run, "team": track_team(run["tid"]),
                              "sure": run["tid"] in certain, "ref": run["tid"] in referees})
        run.update(local_hold_evidence(run, local, track_team),
                   contested=baseline.contested_share(doc, run))
    observations, previous = [], None
    for time, boxes in doc["frames"]:
        if not split["window"][0] <= time <= split["window"][1]:
            continue
        ball = baseline.best_ball(boxes, previous[:2] if previous and time - previous[2] <= 0.5 else None)
        point = [(ball[1] + ball[3]) / 2, (ball[2] + ball[4]) / 2] if ball else None
        if point is not None:
            previous = (*point, time)
        observations.append({"t": time, "ball": point,
                             "players": [{"tid": box[6], "box": box[1:5]} for box in baseline.players(boxes)]})
    return split, quick, observations, baseline.assists_v2(split, baseline_runs)


def annotation_template(game, result, baseline_events=()):
    baseline_times = {event["shot_t"] for event in baseline_events}
    rows = []
    for decision in result["decisions"]:
        time = decision["shot_t"]
        rows.append({"shot_t": time, "team": decision["team"], "label": "unreviewed",
                     "passer_track": None, "shooter_track": None, "reviewer": "", "evidence": "",
                     "notes": "", "clip_start": max(0, time - 6), "clip_end": time + 2,
                     "sampling": {"baseline_candidate": time in baseline_times,
                                  "bounded_candidate": decision["status"] == "candidate",
                                  "bounded_reason": decision["reason"]}})
    return {"schema_version": 1, "game": game, "split": "development",
            "instructions": "Review film independently. label: assist, no_assist, uncertain, unreviewed. "
                            "Confirm the made FG/team too; use uncertain if these are not clear. "
                            "Supply reviewer, evidence (film path/time span), and notes for scored labels. "
                            "Track attribution is optional and must be independently verified. "
                            "Sampling metadata is NOT truth. Review all makes, not only predictions.",
            "annotations": rows}


def evaluate(events, annotations, tolerance=0.35):
    """Score only independently reviewed shot opportunities; never treat blanks as negatives.

    Assist detection and optional track attribution are reported separately. Predictions
    outside reviewed opportunities are unscored, NOT false positives. Recall is only
    within labeled made-shot opportunities, not all actual game assists/missed makes.
    """
    if not 0 <= tolerance < float("inf"):
        raise ValueError("Invalid matching tolerance")
    rows = annotations["annotations"]
    counts = Counter(tp=0, fp=0, fn=0, tn=0, uncertain=0, unreviewed=0,
                     attribution_checked=0, attribution_correct=0)
    matched, keys = set(), set()
    for row in rows:
        key = (row["shot_t"], row.get("team"))
        if key in keys:
            raise ValueError("Duplicate annotation opportunity")
        keys.add(key)
        label = row.get("label", "unreviewed")
        if label not in ("assist", "no_assist", "uncertain", "unreviewed"):
            raise ValueError(f"Unknown label: {label}")
        if label in ("uncertain", "unreviewed"):
            counts[label] += 1
            continue
        if not row.get("team") or not all(row.get(field) for field in ("reviewer", "evidence", "notes")):
            raise ValueError("Scored labels require known team, reviewer, evidence and notes")
        candidates = [index for index, event in enumerate(events)
                      if event.get("team") == row["team"] and abs(event["shot_t"] - row["shot_t"]) <= tolerance]
        if len(candidates) > 1 or any(index in matched for index in candidates):
            raise ValueError("Ambiguous/duplicate prediction matching; resolve before scoring")
        predicted = bool(candidates)
        matched.update(candidates)
        counts["tp" if predicted and label == "assist" else "fp" if predicted else "fn" if label == "assist" else "tn"] += 1
        if predicted and label == "assist" and row.get("passer_track") is not None and row.get("shooter_track") is not None:
            event = events[candidates[0]]
            counts["attribution_checked"] += 1
            counts["attribution_correct"] += int(all(event.get(field) == row[field] for field in ("passer_track", "shooter_track")))
    precision_denominator = counts["tp"] + counts["fp"]
    recall_denominator = counts["tp"] + counts["fn"]
    reviewed = sum(counts[key] for key in ("tp", "fp", "fn", "tn"))
    return {**counts, "reviewed_opportunities": reviewed, "predictions_total": len(events),
            "predictions_outside_reviewed": len(events) - len(matched),
            "precision_on_reviewed": counts["tp"] / precision_denominator if precision_denominator else None,
            "recall_on_reviewed": counts["tp"] / recall_denominator if recall_denominator else None,
            "accuracy_on_reviewed": (counts["tp"] + counts["tn"]) / reviewed if reviewed else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tracks", type=Path)
    source.add_argument("--predictions", type=Path)
    parser.add_argument("--game")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args(argv)
    if args.tracks:
        if not args.game:
            parser.error("--tracks requires --game")
        provenance = input_provenance(args.tracks)
        split, runs, observations, baseline = cached_inputs(args.tracks, args.game)
        if provenance != input_provenance(args.tracks):
            raise RuntimeError("Assist replay inputs or source changed during replay; rerun with stable inputs")
        result = {"game": args.game, "split": "development", "config": vars(AssistConfig()),
                  **detect_assists(split, runs, observations), "baseline_events": baseline,
                  "input_provenance": provenance}
    else:
        result = json.loads(args.predictions.read_text())
    for target, payload in ((args.out, result), (args.template, annotation_template(result["game"], result, result.get("baseline_events", [])))):
        if target:
            if target.exists():
                raise FileExistsError(f"Refusing to overwrite {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2) + "\n")
    summary = {"game": result["game"], "baseline_candidates": len(result.get("baseline_events", [])),
               "bounded_candidates": len(result["events"]), "made_fg_opportunities": len(result["decisions"]),
               "decisions": dict(Counter(decision["reason"] for decision in result["decisions"])),
               "accuracy": "not measured; candidate counts are not correctness"}
    if args.annotations:
        annotations = json.loads(args.annotations.read_text())
        if annotations.get("game") != result["game"]:
            raise ValueError("Annotation game does not match predictions")
        summary["bounded_evaluation"] = evaluate(result["events"], annotations)
        summary["baseline_evaluation"] = evaluate(result.get("baseline_events", []), annotations)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
