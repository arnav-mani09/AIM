"""Focused pilot selection, budget, context and artifact-safety checks."""

import copy
import tempfile
import unittest
from pathlib import Path

import rim_rescan_pilot as pilot


class PilotTests(unittest.TestCase):
    def event(self, identity, time, category="FG", **changes):
        return {"event_id": identity, "t": time, "cohort": "eligible_game", "made": True,
                "triggered": False, "category": category, **changes}

    def test_control_deterministic_tie_and_exclusions(self):
        events = [self.event("z", 9), self.event("a", 11), self.event("near", 10, "FT")]
        self.assertEqual(pilot.select_control(events, 10, set())["event_id"], "a")
        self.assertEqual(pilot.select_control(list(reversed(events)), 10, {"a"})["event_id"], "z")
        self.assertEqual(pilot.select_control(events, 10, {"a", "z"})["event_id"], "near")

    def test_control_failure_not_handpicked(self):
        self.assertIsNone(pilot.select_control([self.event("a", 10, triggered=True),
            self.event("b", 11, made=False), self.event("c", 12, cohort="excluded_warmup")], 10, set()))

    def test_budgets(self):
        pilot.check_budget([{"estimated_frames": 500}], [0] * 500)
        for windows, samples in [([{"estimated_frames": 501}], [0]),
                                 ([{"estimated_frames": 1}] * 7, [0]),
                                 ([{"estimated_frames": 1}], [0] * 501)]:
            with self.assertRaises(ValueError):
                pilot.check_budget(windows, samples)

    def test_context_unknown_not_rejection(self):
        self.assertEqual(pilot.evaluate([], 500)["status"], "missing_records")
        self.assertEqual(pilot.comparison({"decide_result": {"made": True}}, {"status": "missing_initial_context"}), "unknown")
        self.assertEqual(pilot.comparison({"decide_result": {"made": True}}, {"decide_result": {"made": False}}), "changed")

    def test_no_clobber_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            pilot.write_new(path, {"original": True})
            record = pilot.file_record(path)
            pilot.source_rate.checked_record(record)
            with self.assertRaises(FileExistsError):
                pilot.write_new(path, {})
            path.write_text("tampered")
            with self.assertRaises(ValueError):
                pilot.source_rate.checked_record(record)
            with self.assertRaises(ValueError):
                pilot.create_output(Path(directory) / "foreign")

    def test_actual_frozen_cohort(self):
        path = pilot.OUTPUT / "selection.json"
        if not path.exists():
            self.skipTest("Pilot has not frozen yet")
        frozen = pilot.load(path)
        games = {game: pilot.load(pilot.CENSUS / f"{game}.json") for game in pilot.TARGETS}
        for game, targets in pilot.TARGETS.items():
            selected = [case for case in frozen["selected"] if case["game"] == game]
            self.assertEqual([case["event"]["t"] for case in selected if case["stratum"] == "trigger"], list(targets))
            expected = pilot.select_control(games[game]["events"], targets[0], set(frozen["exclusions"][game]["event_ids"]))
            self.assertEqual([case["event"] for case in selected if case["stratum"] == "untriggered_control"], [expected])
        altered = copy.deepcopy(frozen)
        altered["budget_seconds"] = 601
        with self.assertRaises(ValueError):
            pilot.verify(altered)


if __name__ == "__main__":
    unittest.main()
