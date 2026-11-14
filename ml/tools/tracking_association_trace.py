"""Saved-input-only causal trace of the installed supervision 0.26.1 tracker."""

from contextlib import ExitStack, contextmanager
import inspect
import json
from pathlib import Path
import signal
import subprocess
import time
from unittest.mock import patch

import numpy as np
import supervision as sv
from supervision.tracker.byte_tracker import core, matching

import tracking_raw_capture as capture
from tracker_continuity_eval import digest, package_inventory, timeout_handler


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ml/data/labels/tracking_association_trace_20261113"
STAGES = ("high", "low", "unconfirmed")
FOCAL = (29, 30, 31, 90, 91, 92, 151, 152, 153, 212, 213, 214)


def array(value):
    return {"dtype": str(value.dtype), "shape": list(value.shape),
            "values": value.tolist()}


def tracks(values):
    return [{"internal_id": int(track.internal_track_id),
             "external_id": int(track.external_track_id),
             "bbox": track.tlbr.tolist(), "bbox_dtype": str(track.tlbr.dtype),
             "score": float(track.score),
             "state": track.state.name, "activated": bool(track.is_activated),
             "frame_id": int(track.frame_id), "start_frame": int(track.start_frame),
             "tracklet_len": int(track.tracklet_len)} for track in values]


def state(tracker):
    return {name: tracks(getattr(tracker, name)) for name in
            ("tracked_tracks", "lost_tracks", "removed_tracks")}


def check_assignment(event):
    before = np.asarray(event["cost_before"]["values"],
                        dtype=event["cost_before"]["dtype"]).reshape(event["cost_before"]["shape"])
    after = np.asarray(event["cost_after"]["values"], dtype=before.dtype).reshape(before.shape)
    clamped = before.copy()
    clamped[clamped > event["threshold"]] = event["threshold"] + 1e-4
    np.testing.assert_array_equal(after, clamped)
    accepted = event["matches"]
    assert len({pair[0] for pair in accepted}) == len(accepted)
    assert len({pair[1] for pair in accepted}) == len(accepted)
    assert all(before[row, column] <= event["threshold"] for row, column in accepted)
    assert set(event["unmatched_rows"]) == set(range(before.shape[0])) - {p[0] for p in accepted}
    assert set(event["unmatched_columns"]) == set(range(before.shape[1])) - {p[1] for p in accepted}
    return True


class StageTrace:
    def __init__(self, record):
        if sv.__version__ != "0.26.1":
            raise RuntimeError("Requires installed supervision==0.26.1")
        self.record = record
        self.events = []
        self.next_stage = 0
        self.active = None
        self.prediction = None

    def proposal_refs(self, detections):
        result = []
        for detection in detections:
            refs = []
            for index in self.record["player_proposal_indices"]:
                proposal = self.record["proposals"][index]
                box = np.asarray(proposal["xyxy"], dtype=np.float32)
                box[2:] -= box[:2]
                box[2:] += box[:2]
                if float(detection.score) == proposal["score"] and np.array_equal(detection.tlbr, box):
                    refs.append(index)
            if not refs:
                raise AssertionError("Stage detection has no exact float32 source-proposal reference")
            result.append(refs)
        return result

    @contextmanager
    def installed(self):
        original_iou = matching.iou_distance
        original_fuse = matching.fuse_score
        original_assignment = matching.linear_assignment
        original_predict = core.STrack.multi_predict

        def predict(stracks, shared_kalman):
            before = tracks(stracks)
            result = original_predict(stracks, shared_kalman)
            self.prediction = {"before": before, "after": tracks(stracks)}
            return result

        def iou(atracks, btracks):
            caller = inspect.currentframe().f_back.f_code
            result = original_iou(atracks, btracks)
            if caller is core.ByteTrack.update_with_tensors.__code__:
                stage = STAGES[self.next_stage]
                self.next_stage += 1
                event = {"stage": stage, "rows": tracks(atracks), "columns": tracks(btracks),
                         "column_proposals": self.proposal_refs(btracks),
                         "iou_cost": array(result.copy())}
                if stage == "high":
                    event["prediction"] = self.prediction
                self.events.append(event)
                self.active = event
            elif caller is core.remove_duplicate_tracks.__code__:
                self.events.append({"stage": "duplicate_removal", "rows": tracks(atracks),
                                    "columns": tracks(btracks), "iou_cost": array(result.copy()),
                                    "duplicate_if_cost_below": 0.15})
            else:
                raise AssertionError("Unexpected IoU caller")
            return result

        def fuse(cost_matrix, stracks):
            before = cost_matrix.copy()
            result = original_fuse(cost_matrix, stracks)
            np.testing.assert_array_equal(cost_matrix, before)
            expected = 1 - (1 - before) * np.asarray([track.score for track in stracks])[None, :]
            np.testing.assert_array_equal(result, expected)
            self.active["fused_cost"] = array(result.copy())
            return result

        def assignment(cost_matrix, thresh):
            caller = inspect.currentframe().f_back
            if caller.f_code is core.ByteTrack.update_with_detections.__code__:
                event = {"stage": "public_rematch", "rows": [
                    {"proposal_refs": [index], "bbox": self.record["proposals"][index]["xyxy"],
                     "bbox_dtype": str(caller.f_locals["tensors"].dtype),
                     "score": self.record["proposals"][index]["score"]}
                    for index in self.record["player_proposal_indices"]],
                    "columns": tracks(caller.f_locals["tracks"])}
                self.events.append(event)
            elif caller.f_code is core.ByteTrack.update_with_tensors.__code__:
                event = self.active
                assert event["stage"] in STAGES and "matches" not in event
            else:
                raise AssertionError("Unexpected assignment caller")
            before = cost_matrix.copy()
            event.update(threshold=float(thresh), cost_before=array(before))
            result = original_assignment(cost_matrix, thresh)
            matches, unmatched_rows, unmatched_columns = result
            event.update(cost_after=array(cost_matrix.copy()), matches=matches.tolist(),
                         unmatched_rows=list(map(int, unmatched_rows)),
                         unmatched_columns=list(map(int, unmatched_columns)))
            check_assignment(event)
            if before.size:
                boxes_rows = np.asarray([row["bbox"] for row in event["rows"]], dtype=np.result_type(
                    *[np.dtype(row["bbox_dtype"]) for row in event["rows"]]))
                boxes_columns = np.asarray([column["bbox"] for column in event["columns"]], dtype=np.result_type(
                    *[np.dtype(column["bbox_dtype"]) for column in event["columns"]]))
                geometric = 1 - core.box_iou_batch(boxes_rows, boxes_columns)
                np.testing.assert_array_equal(geometric, before if event["stage"] == "public_rematch"
                                              else np.asarray(event["iou_cost"]["values"]))
            if event["stage"] in ("high", "unconfirmed"):
                np.testing.assert_array_equal(before, np.asarray(event["fused_cost"]["values"])
                                              .reshape(before.shape))
            if event["stage"] == "low":
                np.testing.assert_array_equal(before, np.asarray(event["iou_cost"]["values"])
                                              .reshape(before.shape))
            del caller
            return result

        with ExitStack() as stack:
            stack.enter_context(patch.object(matching, "iou_distance", iou))
            stack.enter_context(patch.object(matching, "fuse_score", fuse))
            stack.enter_context(patch.object(matching, "linear_assignment", assignment))
            stack.enter_context(patch.object(core.STrack, "multi_predict", staticmethod(predict)))
            yield self


def replay(inputs, expected, instrument=True):
    assert len(inputs) == len(expected) == 244
    results, outputs = [], []
    tracker, window = None, None
    for record, reference in zip(inputs, expected):
        if record["window"] != window:
            tracker, window = sv.ByteTrack(**capture.TRACKER), record["window"]
        trace = StageTrace(record)
        before = state(tracker)
        detections = capture.unpack_detections(record["detections"])
        if instrument:
            with trace.installed():
                output = tracker.update_with_detections(detections)
            assert [event["stage"] for event in trace.events[:3]] == list(STAGES)
        else:
            output = tracker.update_with_detections(detections)
        packed = {key: record[key] for key in ("sample_index", "window", "pts")}
        packed["detections"] = capture.pack_detections(output)
        assert packed == reference, f"Fresh parity failure at {record['sample_index']}"
        outputs.append(packed)
        results.append({"sample_index": record["sample_index"], "window": window,
                        "pts": record["pts"], "before": before, "after": state(tracker),
                        "events": trace.events, "output": packed["detections"]})
    return results, outputs


def inventory():
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others",
                                     "--exclude-standard"], cwd=ROOT).decode().split("\0")
    owned = {"ml/tools/tracking_association_trace.py", "ml/tools/test_tracking_association_trace.py",
             "ml/docs/tracking_association_trace.md"}
    paths = {ROOT / name for name in names if name and name not in owned}
    for directory in (capture.OUTPUT, ROOT / "ml/data/labels/tracker_continuity_20261113"):
        paths.update(path for path in directory.rglob("*") if path.is_file())
    return {str(path): digest(path) for path in sorted(paths) if path.is_file()}


def save(name, value):
    with (OUTPUT / name).open("x") as handle:
        json.dump(value, handle, allow_nan=False, indent=2)
        handle.write("\n")


def main():
    started_cpu, started_wall = time.process_time(), time.monotonic()
    previous_handler = signal.signal(signal.SIGPROF, timeout_handler)
    previous_timer = signal.setitimer(signal.ITIMER_PROF, 120)
    try:
        OUTPUT.mkdir(exist_ok=True)
        if (OUTPUT / "traces.json").exists():
            raise FileExistsError("Completed trace exists; refusing overwrite")
        before, packages = inventory(), package_inventory()
        for name, value in (("source_inventory_before.json", before),
                            ("package_inventory_before.json", packages)):
            if (OUTPUT / name).exists():
                frozen = json.loads((OUTPUT / name).read_text())
                if name.startswith("package"):
                    assert frozen == value
                else:
                    changes = {path: {"initial": frozen.get(path), "replay_start": value.get(path)}
                               for path in frozen.keys() | value.keys() if frozen.get(path) != value.get(path)}
                    save("concurrent_changes_before_replay.json", changes)
            else:
                save(name, value)
        save("source_inventory_replay_before.json", before)
        manifest = json.loads((capture.OUTPUT / "manifest.json").read_text())
        capture.verify(manifest)
        inputs = capture.read_lines(capture.OUTPUT / "inputs.jsonl")
        expected = capture.read_lines(capture.OUTPUT / "outputs.jsonl")
        assert len(inputs) == len(expected) == len(manifest["samples"]) == 244
        assert sum(len(record["proposals"]) for record in inputs) == 2960
        _, plain = replay(inputs, expected, instrument=False)
        traces, instrumented = replay(inputs, expected)
        assert plain == instrumented == json.loads((capture.OUTPUT / "replayed_outputs.json").read_text())
        save("traces.json", traces)
        save("focal_traces.json", [trace for trace in traces if trace["sample_index"] in FOCAL])
        save("witnesses.json", focal_witnesses(traces, inputs))
        save("installed_primary_source.json", primary_source())
        save("replayed_outputs.json", instrumented)
        after, packages_after = inventory(), package_inventory()
        save("source_inventory_after.json", after)
        save("package_inventory_after.json", packages_after)
        changes = {path: {"before": before.get(path), "after": after.get(path)}
                   for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
        save("concurrent_changes_during_replay.json", changes)
        assert not any("/tracking_raw_capture_20261113/" in path or
                       "/tracker_continuity_20261113/" in path for path in changes), "Frozen input changed"
        assert packages == packages_after, "Installed dependency changed"
        capture.verify(manifest)
        summary = {"frames": 244, "raw_proposals": 2960,
                   "player_inputs": sum(len(record["player_proposal_indices"]) for record in inputs),
                   "emitted": sum(len(row["detections"]["arrays"]["tracker_id"]["values"]) for row in plain),
                   "plain_parity": 244, "instrumented_parity": 244,
                   "assignments_checked": sum("matches" in event for trace in traces for event in trace["events"]),
                   "config": capture.TRACKER,
                   "derived": {"det_thresh": tracker_value("det_thresh"),
                               "max_time_lost": tracker_value("max_time_lost")},
                   "shared_files_unchanged_during_replay": len(before) - len(changes),
                   "concurrent_shared_changes": changes,
                   "package_files_preserved": len(packages["files"]),
                   "cpu_seconds": time.process_time() - started_cpu,
                   "wall_seconds": time.monotonic() - started_wall,
                   "cpu_limit_seconds": 120,
                   "identity_metrics": False, "inference": False}
        save("summary.json", summary)
        print(json.dumps(summary, indent=2))
    finally:
        signal.setitimer(signal.ITIMER_PROF, *previous_timer)
        signal.signal(signal.SIGPROF, previous_handler)


def tracker_value(name):
    return getattr(sv.ByteTrack(**capture.TRACKER), name)


def primary_source():
    functions = {"ByteTrack.update_with_detections": core.ByteTrack.update_with_detections,
                 "ByteTrack.update_with_tensors": core.ByteTrack.update_with_tensors,
                 "remove_duplicate_tracks": core.remove_duplicate_tracks,
                 "STrack.multi_predict": core.STrack.multi_predict,
                 "STrack.activate": core.STrack.activate, "STrack.update": core.STrack.update,
                 "STrack.re_activate": core.STrack.re_activate,
                 "iou_distance": matching.iou_distance, "fuse_score": matching.fuse_score,
                 "linear_assignment": matching.linear_assignment,
                 "indices_to_matches": matching.indices_to_matches}
    return {name: {"path": inspect.getfile(function), "sha256": digest(inspect.getfile(function)),
                   "line": inspect.getsourcelines(function)[1], "source": inspect.getsource(function)}
            for name, function in functions.items()}


def focal_witnesses(rows, inputs):
    queries = ((151, "high", 5, 2), (152, "high", 5, 2),
               (153, "high", 5, 2), (153, "unconfirmed", 32, 2),
               (91, "unconfirmed", 38, 7), (91, "unconfirmed", 38, 8),
               (92, "high", 38, 4), (92, "high", 38, 6), (92, "high", 38, 7),
               (92, "unconfirmed", 40, 4), (92, "unconfirmed", 40, 6),
               (213, "low", 21, 11), (214, "low", 19, 10))
    edges = []
    for sample, stage, track_id, proposal_index in queries:
        event = next(event for event in rows[sample]["events"] if event["stage"] == stage)
        row = next(index for index, value in enumerate(event["rows"]) if value["external_id"] == track_id)
        column = next(index for index, refs in enumerate(event["column_proposals"]) if proposal_index in refs)
        edges.append({"sample": sample, "stage": stage, "external_id": track_id,
                      "proposal_index": proposal_index,
                      "iou": 1 - event["iou_cost"]["values"][row][column],
                      "input_cost": event["cost_before"]["values"][row][column],
                      "clamped_cost": event["cost_after"]["values"][row][column],
                      "threshold": event["threshold"], "accepted": [row, column] in event["matches"]})
    disagreements, agreements, not_emitted = [], 0, []
    for frame in rows:
        internal = {proposal: event["rows"][row]["external_id"] for event in frame["events"]
                    if event["stage"] in STAGES for row, column in event["matches"]
                    for proposal in event["column_proposals"][column]}
        public = {proposal: event["columns"][column]["external_id"] for event in frame["events"]
                  if event["stage"] == "public_rematch" for row, column in event["matches"]
                  for proposal in event["rows"][row]["proposal_refs"]}
        for proposal, track_id in internal.items():
            if proposal not in public:
                not_emitted.append([frame["sample_index"], proposal, track_id])
            elif public[proposal] != track_id:
                disagreements.append([frame["sample_index"], proposal, track_id, public[proposal]])
            else:
                agreements += 1
    controls = []
    for sample in (29, 30, 31):
        event = next(event for event in rows[sample]["events"] if event["stage"] == "public_rematch")
        controls.append({"sample": sample, "inputs": len(inputs[sample]["player_proposal_indices"]),
                         "outputs": len(event["matches"]),
                         "public_winners": [{"proposal": event["rows"][row]["proposal_refs"],
                                             "external_id": event["columns"][column]["external_id"],
                                             "cost": event["cost_before"]["values"][row][column]}
                                            for row, column in event["matches"]]})
    return {"edges": edges, "controls": controls,
            "public_rematch_agrees_with_internal_matched_proposals": agreements,
            "public_rematch_disagreements": disagreements,
            "internally_matched_not_publicly_emitted": not_emitted,
            "meaning": "Exact proposal/track references, not real-person identities"}


if __name__ == "__main__":
    main()
