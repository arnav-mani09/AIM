"""Deterministic exclusion/selection, fixed budget, integrity and context checks."""

import copy
from fractions import Fraction
import sys
import tempfile
import unittest
from pathlib import Path

import rim_rescan_safety as safety


class SafetyTests(unittest.TestCase):
    def fixture(self):
        games, streams = {}, {}
        for game in safety.GAMES:
            events, traces = [], []
            for identity, timestamp, category, triggered in (
                ("fg1", 10, "FG", True), ("fg2", 20, "FG", True),
                ("ft", 30, "FT", True), ("control_z", 9, "FG", False),
                ("control_a", 11, "FG", False)):
                events.append({"event_id": identity, "t": timestamp, "category": category, "made": True,
                               "triggered": triggered, "cohort": "eligible_game", "selected_trace_index": len(traces)})
                traces.append({"path": [[timestamp]], "observed_until": timestamp + 1,
                               "first_under_net": {"point": [timestamp + .2]}})
            games[game] = {"events": events, "traces": traces, "cache": {"first_t": 0, "last_t": 100}}
            streams[game] = {"duration": 100, "avg_frame_rate": "30/1"}
        return games, streams, {game: [] for game in safety.GAMES}, {game: set() for game in safety.GAMES}

    def test_strata_ties_and_reversal(self):
        arguments = self.fixture()
        selected, failures, _ = safety.select(*arguments)
        self.assertFalse(failures)
        self.assertEqual([case["event"]["event_id"] for case in selected[:3]], ["fg1", "ft", "control_a"])
        for game in arguments[0].values():
            game["events"].reverse()
        self.assertEqual(safety.select(*arguments)[0], selected)

    def test_window_overlap_not_only_attempt_and_fallback(self):
        games, streams, intervals, identities = self.fixture()
        intervals["mitty"] = [{"interval": [31, 31.1], "origin": "prior"}]
        selected, failures, audit = safety.select(games, streams, intervals, identities)
        self.assertEqual(selected[1]["event"]["event_id"], "fg2")
        self.assertTrue(selected[1]["fallback"])
        self.assertEqual(failures[0]["requested_stratum"], "FT")
        self.assertEqual(audit["mitty"]["excluded"][0]["event_id"], "ft")
        identities["mitty"].add("fg1")
        with self.assertRaises(ValueError):
            safety.select(games, streams, intervals, identities)

    def test_control_no_ft_substitution(self):
        games, streams, intervals, identities = self.fixture()
        identities["mitty"].update(("control_a", "control_z"))
        selected, failures, _ = safety.select(games, streams, intervals, identities)
        self.assertEqual(len(selected), 5)
        self.assertTrue(any(row["requested_stratum"] == "untriggered_FG_control" for row in failures))

    def test_budget_and_context(self):
        safety.check_budget([{"estimated_frames": 500}], [0] * 500)
        for windows, samples in [([{"estimated_frames": 501}], [0]), ([{"estimated_frames": 1}] * 7, [0]),
                                 ([{"estimated_frames": 1}], [0] * 501), ([{"estimated_frames": 1}], [])]:
            with self.assertRaises(ValueError):
                safety.check_budget(windows, samples)
        self.assertEqual(safety.evaluate([], 500)["status"], "missing_records")
        self.assertEqual(safety.comparison({"decide_result": {"made": True}}, {"status": "missing_initial_context"}), "unknown")

    def test_exact_pts_alignment_has_batch_not_old_experiment_cap(self):
        frames = [{"pts": index, "best_effort_timestamp": index, "pkt_pos": index * 10, "pict_type": "P"} for index in range(79)]
        packets = [{"pts": index, "pos": index * 10} for index in range(79)]
        aligned = safety.align_frames(frames, packets, "1/30", 0, 2.6)
        self.assertEqual(len(aligned), 79)
        self.assertEqual(aligned[-1]["seconds_fraction"], "13/5")
        frames[1]["best_effort_timestamp"] = 0
        with self.assertRaises(ValueError):
            safety.align_frames(frames, packets, "1/30", 0, 2.6)

    def test_integrity_no_clobber_and_no_truth_imports(self):
        self.assertNotIn("makes_eval", sys.modules)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            safety.write_new(path, {"original": True})
            record = safety.file_record(path)
            safety.source.checked_record(record)
            with self.assertRaises(FileExistsError):
                safety.write_new(path, {})
            path.write_text("tampered")
            with self.assertRaises(ValueError):
                safety.source.checked_record(record)
            with self.assertRaises(ValueError):
                safety.create_output(Path(directory))

    def test_actual_frozen_selection_and_context(self):
        if not (safety.OUTPUT / "selection.json").exists():
            self.skipTest("Not frozen yet")
        frozen = safety.load(safety.OUTPUT / "selection.json")
        games = {game: safety.load(safety.CENSUS / f"{game}.json") for game in safety.GAMES}
        intervals, identities = safety.prior_exclusions()
        selected, failures, exclusions = safety.select(games, {game: value["stream"] for game, value in frozen["sources"].items()}, intervals, identities)
        self.assertEqual([case["event"] for case in selected], [case["event"] for case in frozen["selected"]])
        self.assertEqual((failures, exclusions), (frozen["selection_failures"], frozen["exclusions"]))
        altered = copy.deepcopy(frozen)
        altered["budget_seconds"] = 601
        with self.assertRaises(ValueError):
            safety.verify(altered)
        if not (safety.OUTPUT / "analysis.json").exists():
            return
        manifest = safety.load(safety.MANIFEST)
        records = [safety.json.loads(line) for line in (safety.OUTPUT / "detections.jsonl").read_text().splitlines()]
        self.assertEqual([row["sample"] for row in records], manifest["samples"])
        for sample in manifest["samples"]:
            safety.source.checked_record(sample["file"])
            self.assertEqual(Fraction(sample["pts"]) * Fraction(sample["time_base"]), Fraction(sample["seconds_fraction"]))
        for case in safety.load(safety.OUTPUT / "analysis.json")["cases"]:
            self.assertTrue(case["decoded_and_inferred_complete"])
            for trace in [case["dense"], *case["common_context_phases"].values()]:
                if "decide_result" in trace:
                    self.assertEqual(trace["attempt_path_starts_at"], case["shared_prefix_until"])
                    if trace.get("first_under_net"):
                        self.assertTrue(trace["coverage"]["decoded_horizon_complete"])


if __name__ == "__main__":
    unittest.main()
