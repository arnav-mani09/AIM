"""Conservative, standard-library source-timeline event evaluation; no inference."""

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path


TYPES = ("point", "rebound", "assist")
STATUSES = ("reviewed_complete", "partially_reviewed", "unreviewed", "unobservable")
LIMIT = 10000
MAX_BYTES = 10_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "expected finite number")
    return value


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "expected nonblank string")
    return value


def bounded_list(value):
    require(isinstance(value, list) and len(value) <= LIMIT, "missing or oversized list")
    return value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    require(Path(path).stat().st_size <= MAX_BYTES, "input exceeds byte limit")
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def validate(document):
    require(document.get("schema_version") == 1, "unsupported schema")
    text(document["game"])
    source = document["source"]
    text(source["path"])
    require(isinstance(source["sha256"], str) and len(source["sha256"]) == 64
            and all(char in "0123456789abcdef" for char in source["sha256"]), "invalid source hash")
    require(source["split_role"] in ("development", "held_out"), "missing source split role")
    start, end = map(number, document["timeline"])
    require(0 <= start < end, "invalid timeline")
    require(type(document["timeline_independently_confirmed"]) is bool, "invalid confirmation")
    if document["timeline_independently_confirmed"]:
        text(document["timeline_evidence"])
    teams = document["teams"]
    require(isinstance(teams, list) and len(teams) == 2 and len(set(map(text, teams))) == 2,
            "expected two distinct teams")
    intervals = bounded_list(document["intervals"])
    previous = start
    interval_ids = set()
    for interval in intervals:
        identifier = text(interval["id"])
        require(identifier not in interval_ids, "duplicate interval id")
        interval_ids.add(identifier)
        left, right = number(interval["start"]), number(interval["end"])
        require(previous <= left < right <= end, "overlapping, unsorted or invalid interval")
        previous = right
        require(interval["status"] in STATUSES, "blank/unknown review status")
        if interval["status"] in ("reviewed_complete", "partially_reviewed"):
            require(interval["independent_of_predictions"] is True, "review must be independent")
            text(interval["evidence"])
            require(interval.get("reviewer_type", "unknown") in ("human", "model", "unknown"),
                    "invalid reviewer type")
            if interval.get("reviewer_type") == "human":
                text(interval["reviewer"])
    starts = [interval["start"] for interval in intervals]

    def locate(time):
        position = bisect.bisect_right(starts, time) - 1
        if position >= 0 and time < intervals[position]["end"]:
            return intervals[position]
        return None

    for key in ("truth_events", "predicted_events"):
        identifiers, truth_keys = set(), set()
        for event in bounded_list(document[key]):
            identifier = text(event["id"])
            require(identifier not in identifiers, "duplicate event id")
            identifiers.add(identifier)
            time = number(event["time"])
            require(start <= time < end, "event outside half-open timeline")
            require(event["type"] in TYPES, "invalid event type")
            require(event["team"] in teams or (key == "predicted_events" and event["team"] is None),
                    "unknown team")
            require(event["player"] is None or bool(text(event["player"])), "invalid player")
            if event["type"] == "point":
                require(type(event["points"]) is int and event["points"] in (1, 2, 3), "invalid points")
            if key == "truth_events":
                interval = locate(time)
                require(interval is not None and interval["status"] in
                        ("reviewed_complete", "partially_reviewed"), "truth outside reviewed interval")
                text(event["evidence"])
                signature = (event["type"], time, event["team"])
                require(signature not in truth_keys, "ambiguous duplicate truth")
                truth_keys.add(signature)
    log_ids = set()
    for entry in bounded_list(document["review_log"]):
        identifier = text(entry["id"])
        require(identifier not in log_ids, "duplicate review log id")
        log_ids.add(identifier)
        text(entry["evidence"])
        text(entry["reviewer_role"])
        require(number(entry["active_seconds"]) >= 0, "negative active time")
        for key in ("reviewed_events", "corrections"):
            require(type(entry[key]) is int and entry[key] >= 0, "invalid logged count")
    return locate


def pair_events(truth, predictions, tolerance, same_team):
    ordered = sorted(truth, key=lambda event: (event["time"], event["id"]))
    times = [event["time"] for event in ordered]
    candidates = {}
    for prediction in predictions:
        left = bisect.bisect_left(times, prediction["time"] - tolerance)
        right = bisect.bisect_right(times, prediction["time"] + tolerance)
        eligible = [event for event in ordered[left:right]
                    if event["type"] == prediction["type"] and
                    (not same_team or event["team"] == prediction["team"])]
        require(len(eligible) <= 1, "ambiguous matching; narrow tolerance or resolve source events")
        if eligible:
            event = eligible[0]
            candidates.setdefault(event["id"], []).append(
                (abs(event["time"] - prediction["time"]), prediction["id"], prediction, event))
    pairs = []
    for options in candidates.values():
        options.sort(key=lambda item: (item[0], item[1]))
        if len(options) > 1 and options[0][0] == options[1][0]:
            first, second = options[0][2], options[1][2]
            require({key: value for key, value in first.items() if key != "id"} ==
                    {key: value for key, value in second.items() if key != "id"},
                    "ambiguous competing predictions")
        pairs.append((options[0][3], options[0][2]))
    return pairs


def ratio(correct, total):
    return correct / total if total else None


def evaluate(document, tolerance=1.0):
    require(0 <= number(tolerance) <= 30, "tolerance must be between 0 and 30 seconds")
    locate = validate(document)
    intervals = document["intervals"]
    complete = [interval for interval in intervals if interval["status"] == "reviewed_complete"]

    def scorable(event):
        interval = locate(event["time"])
        return interval is not None and interval["status"] == "reviewed_complete"

    truth = [event for event in document["truth_events"] if scorable(event)]
    predictions = [event for event in document["predicted_events"] if scorable(event)]
    pairs, diagnostic = [], []
    for interval in complete:
        local_truth = [event for event in truth if locate(event["time"])["id"] == interval["id"]]
        local_predictions = [event for event in predictions if locate(event["time"])["id"] == interval["id"]]
        pairs.extend(pair_events(local_truth, local_predictions, tolerance, True))
        diagnostic.extend(pair_events(local_truth, local_predictions, tolerance, False))
    matched_truth = {event["id"] for event, prediction in pairs}
    matched_predictions = {prediction["id"] for event, prediction in pairs}
    metrics = {}
    for kind in TYPES:
        real = [event for event in truth if event["type"] == kind]
        predicted = [event for event in predictions if event["type"] == kind]
        matched = [(event, prediction) for event, prediction in pairs if event["type"] == kind]
        identified = [(event, prediction) for event, prediction in matched if event["player"] is not None]
        temporal = [(event, prediction) for event, prediction in diagnostic if event["type"] == kind]
        metrics[kind] = {
            "true_events": len(real), "scored_predictions": len(predicted), "matched": len(matched),
            "precision": ratio(len(matched), len(predicted)) if complete else None,
            "recall": ratio(len(matched), len(real)) if complete else None,
            "false_event_ids": [event["id"] for event in predicted if event["id"] not in matched_predictions],
            "missed_event_ids": [event["id"] for event in real if event["id"] not in matched_truth],
            "team_accuracy": ratio(sum(event["team"] == prediction["team"] for event, prediction in temporal), len(temporal)),
            "team_comparisons": len(temporal), "player_comparisons": len(identified),
            "player_accuracy": ratio(sum(event["player"] == prediction["player"] for event, prediction in identified), len(identified)),
            "unknown_truth_player_matches": len(matched) - len(identified),
            "points_value_accuracy": ratio(sum(event["points"] == prediction["points"] for event, prediction in matched), len(matched)) if kind == "point" else None,
        }
    start, end = document["timeline"]
    covered = sum(interval["end"] - interval["start"] for interval in complete)
    timeline_covered = (bool(intervals) and len(complete) == len(intervals)
                        and intervals[0]["start"] == start and intervals[-1]["end"] == end
                        and all(left["end"] == right["start"]
                                for left, right in zip(intervals, intervals[1:])))
    adjudicated = bool(complete) and all(interval.get("reviewer_type") == "human" for interval in complete)
    whole = document["timeline_independently_confirmed"] and timeline_covered and adjudicated
    logs = document["review_log"]
    return {
        "game": document["game"], "source": document["source"], "tolerance_seconds": tolerance,
        "full_game_coverage": whole, "partial": not whole,
        "complete_timeline_coverage": timeline_covered,
        "reference_status": "independent_human" if adjudicated else
                            "provisional_or_unspecified" if complete else "unreviewed",
        "held_out": document["source"]["split_role"] == "held_out",
        "reviewed_complete_seconds": covered, "timeline_seconds": end - start,
        "excluded_seconds": {status: sum(interval["end"] - interval["start"] for interval in intervals if interval["status"] == status) for status in STATUSES if status != "reviewed_complete"},
        "unlisted_seconds": end - start - sum(interval["end"] - interval["start"] for interval in intervals),
        "unscored_prediction_ids": [event["id"] for event in document["predicted_events"] if not scorable(event)],
        "unscored_truth_ids": [event["id"] for event in document["truth_events"] if not scorable(event)],
        "interval_metrics": metrics, "full_game_metrics": metrics if whole else None,
        "review_burden": {"active_seconds": sum(entry["active_seconds"] for entry in logs),
                          "reviewed_events": sum(entry["reviewed_events"] for entry in logs),
                          "corrections": sum(entry["corrections"] for entry in logs),
                          "by_role_active_seconds": {role: sum(entry["active_seconds"] for entry in logs if entry["reviewer_role"] == role) for role in sorted({entry["reviewer_role"] for entry in logs})}} if logs else None,
        "coach_time_gain": None,
    }


def export_template(window_path, game, output, width=120):
    require(0 < number(width) <= 3600, "invalid sampling width")
    window = load(window_path)
    require(window.get("found") is True, "cached window not found")
    start, end = number(window["start"]), number(window["end"])
    require(0 <= start < end and math.ceil((end - start) / width) <= LIMIT, "invalid or oversized window")
    intervals = []
    for index in range(math.ceil((end - start) / width)):
        intervals.append({"id": f"window-{index:04d}", "start": start + index * width,
                          "end": min(end, start + (index + 1) * width), "status": "unreviewed"})
    template = {"schema_version": 1, "game": game,
                "source": {"path": str(Path(window_path).resolve()), "sha256": digest(window_path),
                           "split_role": "development", "kind": "cached_estimated_game_window"},
                "teams": ["Valley", "Opponent"], "timeline": [start, end],
                "timeline_independently_confirmed": False, "timeline_evidence": None,
                "sampling": {"method": "exhaustive_fixed_source_timeline_tiles", "width_seconds": width,
                             "prediction_independent": True, "includes_halftime_and_no_prediction_stretches": True},
                "intervals": intervals, "truth_events": [], "predicted_events": [], "review_log": []}
    validate(template)
    write_new(output, template)
    return template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("window", type=Path)
    export.add_argument("game")
    export.add_argument("output", type=Path)
    export.add_argument("--width", type=float, default=120)
    score = commands.add_parser("evaluate")
    score.add_argument("input", type=Path)
    score.add_argument("output", type=Path)
    score.add_argument("--tolerance", type=float, default=1.0)
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_template(args.window, args.game, args.output, args.width)
        else:
            result = evaluate(load(args.input), args.tolerance)
            result.update(input_sha256=digest(args.input), implementation_sha256=digest(__file__))
            write_new(args.output, result)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
