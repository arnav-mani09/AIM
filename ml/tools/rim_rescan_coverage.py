"""Read-only whole-cache trigger census; no film access, inference, or outcome override."""

import copy
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from unittest.mock import patch

import makes_eval
import rim_context_eval
import rim_outcome_audit
import shots


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/rim_rescan_coverage_20261112"
PROVENANCE = ROOT / "ml/data/labels/blind_film_review_20261112/provenance.json"
EXPERIMENT = ROOT / "ml/data/labels/rim_source_rate_20261112"


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def write_new(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def snapshot(paths):
    return {str(path.relative_to(ROOT)): {"sha256": digest(path), "size_bytes": path.stat().st_size}
            for path in sorted(set(paths))}


def context_status(trace):
    crossing = trace.get("first_under_net")
    if not crossing:
        return "no_under_net_observation"
    if crossing["index"] == 0:
        return "unknown_previous_observation"
    if crossing.get("last_above") is None:
        return "unknown_above_rim_context"
    return "observed_previous_and_above"


def resolve(finals, traces, returned):
    links = []
    for final in finals:
        candidates = [index for index, result in enumerate(returned) if result is final]
        selected = candidates[-1] if candidates else None
        links.append({"trace_indices": candidates, "selected_trace_index": selected,
                      "resolution": "last_return_by_identity" if candidates else "missing",
                      "triggered": bool(final["made"] and selected is not None
                                        and rim_context_eval.trigger(traces[selected]))})
    return links


def merge_windows(windows, rate):
    merged = []
    for window in sorted(windows, key=lambda item: (item["start"], item["end"])):
        if merged and window["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], window["end"])
            merged[-1]["event_ids"] = sorted(set(merged[-1]["event_ids"] + window["event_ids"]))
        else:
            merged.append(copy.deepcopy(window))
    for window in merged:
        window["seconds"] = window["end"] - window["start"]
        window["estimated_frames"] = math.ceil(Fraction(str(window["seconds"])) * rate) + 1
    return merged


def workload(events, traces, lower, upper, rate):
    windows = []
    for event in events:
        if not event["triggered"]:
            continue
        trace = traces[event["selected_trace_index"]]
        path = trace["path"]
        crossing_time = trace["first_under_net"]["point"][0]
        start = max(lower, min(event["t"], path[0][0]) - 0.5)
        end = min(upper, max(event["t"] + shots.MAKE_WINDOW, path[-1][0],
                             trace["observed_until"], crossing_time + 0.4) + 0.5)
        windows.append({"start": start, "end": end, "event_ids": [event["event_id"]]})
    merged = merge_windows(windows, rate)
    return {"requested_windows": windows, "merged_windows": merged,
            "window_count": len(merged), "seconds": sum(item["seconds"] for item in merged),
            "estimated_frames": sum(item["estimated_frames"] for item in merged)}


def summary(events):
    return {"attempts": len(events), "final_accepted_makes": sum(event["made"] for event in events),
            "triggered_makes": sum(event["triggered"] for event in events),
            "categories": {kind: {"attempts": sum(event["category"] == kind for event in events),
                                   "makes": sum(event["category"] == kind and event["made"] for event in events),
                                   "triggered": sum(event["category"] == kind and event["triggered"] for event in events)}
                           for kind in ("FG", "FT", "unknown")},
            "context_status": dict(Counter(event["context_status"] for event in events)),
            "triggered_event_ids": [event["event_id"] for event in events if event["triggered"]]}


def replay(game, source):
    original_decide, original_find = shots.decide, shots.find_shots
    traces, returned, final_refs, finals = [], [], [], []

    def capture_decide(shot, observed_until=None):
        trace = rim_outcome_audit.explain(copy.deepcopy(shot), observed_until, decision=original_decide)
        trace["trace_index"] = len(traces)
        trace["caller"] = sys._getframe(1).f_code.co_name
        result = original_decide(shot, observed_until=observed_until)
        if result != trace["decide_result"]:
            raise ValueError("Diagnostic and runtime decision disagree")
        traces.append(trace)
        returned.append(result)
        return result

    def capture_find(doc):
        result = original_find(doc)
        final_refs.extend(result)
        finals.extend(copy.deepcopy(result))
        return result

    started = time.monotonic()
    with patch.object(shots, "decide", capture_decide), patch.object(shots, "find_shots", capture_find):
        doc, labeled = makes_eval.run_pipeline(game, film=False)
    if shots.decide is not original_decide or shots.find_shots is not original_find:
        raise ValueError("Runtime functions not restored")
    plain_doc, plain_labeled = makes_eval.run_pipeline(game, film=False)
    plain_final = original_find(plain_doc)
    if finals != plain_final or labeled != plain_labeled:
        raise ValueError("Instrumented final output differs from unchanged uninstrumented replay")
    links = resolve(final_refs, traces, returned)
    labeled_by_identity = {id(shot): shot for shot in labeled}
    if len(labeled_by_identity) != len(labeled) or any(not any(shot is final for final in final_refs) for shot in labeled):
        raise ValueError("Unexpected split copy/duplicate: explicit identity linking requires revision")
    events = []
    for index, (final, reference, link) in enumerate(zip(finals, final_refs, links)):
        label = labeled_by_identity.get(id(reference))
        kind = label.get("kind") if label else None
        trace_index = link["selected_trace_index"]
        event_id = f"{game}:cache:{index:04d}:t={final['t']:.2f}"
        trace = traces[trace_index] if trace_index is not None else None
        event = {"event_id": event_id, "t": final["t"], "make_t": final.get("make_t"),
                 "made": final["made"], "rescued": bool(final.get("rescued")),
                 "dead_ball_make": bool(final.get("dead_ball_make")),
                 "runtime_kind": kind, "category": kind if kind in ("FG", "FT") else "unknown",
                 "cohort": "eligible_game" if kind in ("FG", "FT") else
                           ("outside_runtime_window" if label is None else f"excluded_{kind}"),
                 "team": label.get("team") if label else None,
                 "context_status": context_status(trace) if trace else "unknown_missing_trace",
                 "final_find_shots_result": final, "runtime_result": copy.deepcopy(label), **link}
        events.append(event)
        for candidate in link["trace_indices"]:
            traces[candidate]["final_event_id"] = event_id
    for trace in traces:
        trace.setdefault("final_event_id", None)
        trace["raw_trigger"] = rim_context_eval.trigger(trace)
        trace["context_status"] = context_status(trace)
    missing = [event["event_id"] for event in events if event["selected_trace_index"] is None]
    if missing:
        raise ValueError(f"Final attempts lack traces; do not interpret as untriggered: {missing}")
    video_stream = next(stream for stream in source["ffprobe"]["streams"] if stream["codec_type"] == "video")
    rate = Fraction(video_stream["avg_frame_rate"])
    eligible = [event for event in events if event["cohort"] == "eligible_game"]
    lower, upper = max(0, doc["frames"][0][0]), min(float(video_stream["duration"]), doc["frames"][-1][0])
    groups = {}
    for trace in traces:
        key = json.dumps({"result": trace["decide_result"], "observed_until": trace["observed_until"]}, sort_keys=True)
        groups.setdefault(key, []).append(trace["trace_index"])
    return {"game": game, "replay_wall_seconds": time.monotonic() - started,
            "cache": {"fps": doc["fps"], "frames": len(doc["frames"]), "first_t": lower, "last_t": upper,
                      "model": doc.get("model"), "frame_size": doc["frame_size"]},
            "source_rate": {"avg_frame_rate": str(rate), "r_frame_rate": video_stream["r_frame_rate"],
                            "source_recorded_sha256": source["sha256"], "source_not_opened": True,
                            "provenance": str(PROVENANCE.relative_to(ROOT))},
            "all_cache": summary(events), "eligible_game": summary(eligible),
            "excluded_cohorts": dict(Counter(event["cohort"] for event in events if event not in eligible)),
            "uninstrumented_parity": {"post_veto_find_shots": True, "runtime_labeled_output": True},
            "trace_resolution": {"calls": len(traces), "accepted_decide_calls": sum(trace["decide_result"]["made"] for trace in traces),
                                 "raw_trigger_calls": sum(trace["raw_trigger"] for trace in traces),
                                 "unlinked_calls": sum(trace["final_event_id"] is None for trace in traces),
                                 "unlinked_accepted_calls": sum(trace["final_event_id"] is None and trace["decide_result"]["made"] for trace in traces),
                                 "missing_final_traces": missing,
                                 "multiple_identity_links": [event["event_id"] for event in events if len(event["trace_indices"]) > 1],
                                 "exact_duplicate_trace_groups": [indices for indices in groups.values() if len(indices) > 1],
                                 "same_attempt_time_trace_groups": [indices for timestamp in sorted({trace["decide_result"]["t"] for trace in traces})
                                                                    if len(indices := [trace["trace_index"] for trace in traces if trace["decide_result"]["t"] == timestamp]) > 1],
                                 "same_time_final_groups": [ids for timestamp in sorted({event["t"] for event in events})
                                                            if len(ids := [event["event_id"] for event in events if event["t"] == timestamp]) > 1],
                                 "post_veto_makes_removed": sum(event["dead_ball_make"] for event in events)},
            "all_cache_workload": workload(events, traces, lower, upper, rate),
            "eligible_game_workload": workload(eligible, traces, lower, upper, rate),
            "events": events, "traces": traces}


def input_paths():
    paths = [PROVENANCE, ROOT / "ml/docs/rim_context_eval.md"]
    for directory in (ROOT / "ml/tools", ROOT / "worker"):
        paths.extend(directory.glob("*.py"))
    for directory in ("rim_context_20261112", "rim_source_rate_20261112", "rim_outcome_audit_20261112"):
        paths.extend(path for path in (ROOT / "ml/data/labels" / directory).rglob("*") if path.is_file())
    paths.extend(ROOT / f"ml/data/tracks/{makes_eval.GAMES[game][0]}.v4.json" for game in ("mitty", "riordan"))
    return paths


def main():
    OUTPUT.mkdir(mode=0o700, exist_ok=False)
    paths = input_paths()
    before = snapshot(paths)
    write_new(OUTPUT / "inputs_before.json", before)
    provenance = json.loads(PROVENANCE.read_text())
    manifest = json.loads((EXPERIMENT / "manifest.json").read_text())
    inference = json.loads((EXPERIMENT / "inference.json").read_text())
    budget = json.loads((EXPERIMENT / "budget.json").read_text())
    if inference["manifest_sha256"] != digest(EXPERIMENT / "manifest.json"):
        raise ValueError("Prior timing manifest identity mismatch")
    games = {game: replay(game, provenance["sources"][game]) for game in ("mitty", "riordan")}
    timing = {"label": "Explicit linear extrapolation, NOT a measured deployment latency or guarantee",
              "measured_experiment": str(EXPERIMENT.relative_to(ROOT)),
              "measured_frames": len(manifest["samples"]), "input_size": manifest["protocol"]["input_size"],
              "protocol": manifest["protocol"], "loop_including_final_verification_seconds": inference["inference_seconds"],
              "child_wall_including_startup_seconds": budget["wall_seconds"], "projection": {}}
    for game, report in games.items():
        timing["projection"][game] = {}
        for cohort in ("all_cache", "eligible_game"):
            frames = report[f"{cohort}_workload"]["estimated_frames"]
            timing["projection"][game][cohort] = {
                "loop_linear_seconds": frames * inference["inference_seconds"] / len(manifest["samples"]),
                "wall_linear_seconds": frames * budget["wall_seconds"] / len(manifest["samples"])}
        write_new(OUTPUT / f"{game}.json", report)
        print(game, json.dumps({key: report[key] for key in ("all_cache", "eligible_game", "trace_resolution")}), flush=True)
    after = snapshot(input_paths())
    write_new(OUTPUT / "inputs_after.json", after)
    if before != after:
        raise ValueError("Source/input inventory or bytes changed during census")
    write_new(OUTPUT / "summary.json", {"status": "complete_read_only_cache_census", "inputs_unchanged": True,
              "trigger": rim_context_eval.TRIGGER, "score_truth_read": False,
              "window_policy": "min(attempt t, first path t)-0.5 through max(t+MAKE_WINDOW, last path t, observed_until, first_under_net+0.4)+0.5; clipped to cache/source extent; union overlaps/touching per game",
              "frame_estimate": "ceil(union duration * recorded actual source avg_frame_rate)+1 per merged window; not an exact PTS/sample schedule",
              "cohort_policy": "makes_eval.run_pipeline(game, film=False); eligible iff returned kind FG/FT, exactly worker shot-event emission filter; all-cache includes out-of-window and non-game attempts",
              "timing_extrapolation": timing,
              "games": {game: {key: value for key, value in report.items() if key not in ("events", "traces")}
                        for game, report in games.items()}})
    write_new(OUTPUT / "integrity.json", {"files": snapshot(path for path in OUTPUT.iterdir() if path.is_file())})


if __name__ == "__main__":
    main()
