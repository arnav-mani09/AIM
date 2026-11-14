"""Read-only cached replay of bounded provisional rim-outcome examples."""

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import shots


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/rim_outcome_audit_20261112"
REVIEW = ROOT / "ml/data/labels/blind_film_review_20261112"
CASES = (
    ("riordan", "R4415-F3", 4422.8, "provisional_rim_rejection"),
    ("riordan", "R850-F6", 866.35, "provisional_physical_make"),
    ("riordan", "R3605-F2", 3613.3, "provisional_physical_make"),
    ("mitty", "M240-F3", 253.1, "provisional_physical_make"),
    ("mitty", "M995-F3", 1015.6, "provisional_physical_make"),
    ("mitty", "M1138-F3", 1150.7, "provisional_physical_make"),
)


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def explain(shot, observed_until, decision=None):
    """Expose current first-under-net predicates; do not propose another classifier."""
    decision = shots.decide if decision is None else decision
    result = decision(copy.deepcopy(shot), observed_until=observed_until)
    points = [shots.rim_units(point) for point in shot["path"]]
    first = next((index for index, point in enumerate(points)
                  if point[2] >= shots.UNDER_NET), None)
    crossing = None
    branch = "no_make"
    if first is not None:
        time, horizontal, vertical = points[first]
        above = [index for index in range(first) if points[index][2] < 0.3]
        crossing = {"index": first, "point": points[first], "last_above": None,
                    "primary_checks": {}, "gap_checks": {}}
        if above:
            last = above[-1]
            previous_time, previous_horizontal, _ = points[last]
            later = points[first + 1:]
            no_pop = not any(point[2] < 0.3 for point in later if point[0] - time <= 0.4)
            no_drift = not any(abs(point[1] - horizontal) > shots.EXIT_DRIFT
                               for point in later if point[0] - time <= 0.3)
            primary = {
                "last_above_over_rim": abs(previous_horizontal) <= shots.OVER_RIM_X,
                "drop_time": time - previous_time <= shots.DROP_TIME,
                "vertical_limit": vertical <= 5.5,
                "intermediate_inside": all(abs(point[1]) <= shots.SIDE_X
                                           for point in points[last + 1:first]),
                "centered_exit": abs(horizontal) <= shots.NET_EXIT_X,
                "no_pop_to_above_rim": no_pop,
                "no_exit_drift": no_drift,
            }
            before = points[first - 1]
            gap = {
                "enabled": bool(shots.LOST_X),
                "gap_length": shots.LOST_GAP <= time - before[0] <= 1.0,
                "previous_vertical": -1.5 <= before[2] <= 1.2,
                "previous_horizontal": abs(before[1]) <= 0.5,
                "exit_horizontal": abs(horizontal) <= shots.LOST_X,
                "vertical_limit": vertical <= 5.5,
                "no_pop_to_above_rim": no_pop,
                "no_exit_drift": no_drift,
            }
            crossing.update(last_above=points[last], primary_checks=primary, gap_checks=gap)
            if all(primary.values()):
                branch = "primary_under_net"
            elif all(gap.values()):
                branch = "gap_under_net"
    if result["made"] and result["evidence"] == 0:
        branch = "net_disappearance"
    if result["made"] != (branch != "no_make"):
        raise ValueError("Diagnostic predicates no longer agree with current shots.decide")
    return {"decide_result": result, "observed_until": observed_until,
            "branch": branch, "first_under_net": crossing,
            "path": shot["path"], "rim_unit_path": points,
            "path_gaps": [{"before": before[0], "after": after[0],
                           "seconds": after[0] - before[0]}
                          for before, after in zip(points, points[1:])
                          if after[0] - before[0] > 1.5 / 10]}


def replay(doc, targets):
    """Replay cached frames with full context, retaining only selected attempts."""
    original = shots.decide
    traces = []

    def capture(shot, observed_until=None):
        if any(abs(shot["t"] - target) < 0.01 for target in targets):
            traces.append(explain(copy.deepcopy(shot), observed_until, decision=original))
        return original(shot, observed_until=observed_until)

    with patch.object(shots, "decide", side_effect=capture):
        final = shots.find_shots(doc)
    for trace in traces:
        trace["final_find_shots_result"] = next(
            (shot for shot in final if shot["t"] == trace["decide_result"]["t"]), None)
    return traces


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite existing private audit: {OUTPUT}")
    review_path = REVIEW / "observations.frozen.json"
    frozen = json.loads(review_path.read_text())
    observations = {item["id"]: item for item in frozen["observations"]}
    report_path = ROOT / "ml/data/labels/points_accuracy_2026_11_12/after-report.json"
    assist_path = ROOT / "ml/data/labels/assist_identity_20261112/riordan_final.json"
    paths = [Path(__file__), ROOT / "ml/tools/shots.py", review_path, report_path, assist_path,
             REVIEW / "provenance.json", REVIEW / "check_evidence.py"]
    records = []
    for game in ("riordan", "mitty"):
        cache_path = ROOT / f"ml/data/tracks/valley-vs-archbishop-{game}.v4.json"
        paths.append(cache_path)
        doc = json.loads(cache_path.read_text())
        cases = [case for case in CASES if case[0] == game]
        traces = replay(doc, [case[2] for case in cases])
        for _, review_id, target, interpretation in cases:
            selected = [trace for trace in traces if abs(trace["decide_result"]["t"] - target) < 0.01]
            if len(selected) != 1:
                raise ValueError(f"Expected one cached decision for {review_id}, got {len(selected)}")
            trace = selected[0]
            observation = observations[review_id]
            paths.extend(ROOT / path for path in observation["evidence_paths"])
            trace.update(game=game, review_id=review_id, provisional_interpretation=interpretation,
                         frozen_observation=observation,
                         cache_metadata={key: doc[key] for key in ("model", "fps", "frame_size")},
                         raw_ball_rim_frames=[
                             [time, [box for box in boxes if box[0] in (0, 3)]]
                             for time, boxes in doc["frames"] if target - 0.5 <= time <= target + 2])
            records.append(trace)
    assist = json.loads(assist_path.read_text())
    payload = {
        "status": "development_diagnostic_not_human_ground_truth",
        "method": "Current find_shots replay on unchanged full cached tracks; bounded output only; no inference/video decoding.",
        "limits": "2D ball/rim boxes cannot certify physical aperture/net traversal or resolve provisional visual disagreement.",
        "inputs_sha256": {str(path.relative_to(ROOT)): digest(path) for path in dict.fromkeys(paths)},
        "cases": records,
        "dependent_assist_events": [event for event in assist["events"] if event.get("shot_t") == 4422.8],
        "assist_cache_status": assist["input_provenance"].get("shot_cache_status"),
    }
    OUTPUT.mkdir(parents=True, exist_ok=False)
    with (OUTPUT / "audit.json").open("x") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(OUTPUT / "audit.json")


if __name__ == "__main__":
    main()
