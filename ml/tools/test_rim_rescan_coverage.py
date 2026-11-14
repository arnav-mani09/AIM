import copy
from fractions import Fraction
import unittest
from unittest.mock import patch

import rim_rescan_coverage as coverage


def trace(made=True):
    return {"decide_result": {"made": made}, "first_under_net": {"index": 1, "last_above": [1, 0, 0]},
            "rim_unit_path": [[1, .44, 1.1], [1.1, .2, 3]]}


class CoverageTests(unittest.TestCase):
    def test_duplicate_and_intermediate_calls_are_not_final_makes(self):
        intermediate = {"t": 1, "made": True}
        final = {"t": 1, "made": True}
        links = coverage.resolve([final], [trace(), trace()], [intermediate, final])
        self.assertEqual(links[0]["trace_indices"], [1])
        self.assertTrue(links[0]["triggered"])
        self.assertEqual(len(links), 1)
        self.assertEqual(coverage.resolve([copy.deepcopy(final)], [trace()], [final])[0]["resolution"], "missing")

    def test_final_veto_overrides_pre_veto_acceptance(self):
        final = {"made": False, "dead_ball_make": True}
        self.assertFalse(coverage.resolve([final], [trace()], [final])[0]["triggered"])

    def test_repeated_same_object_uses_last_decision(self):
        final = {"made": True}
        result = coverage.resolve([final], [trace(), trace(False)], [final, final])[0]
        self.assertEqual(result["trace_indices"], [0, 1])
        self.assertEqual(result["selected_trace_index"], 1)
        self.assertFalse(result["triggered"])

    def test_merge_touching_nested_and_disjoint_windows(self):
        windows = [{"start": 1, "end": 2, "event_ids": ["a"]},
                   {"start": 1.2, "end": 1.8, "event_ids": ["b"]},
                   {"start": 2, "end": 3, "event_ids": ["c"]},
                   {"start": 4, "end": 5, "event_ids": ["d"]}]
        merged = coverage.merge_windows(windows, Fraction(30))
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["event_ids"], ["a", "b", "c"])
        self.assertEqual(merged[0]["estimated_frames"], 61)
        self.assertNotIn("seconds", windows[0])

    def test_unknown_context_is_explicit_not_safety(self):
        value = trace()
        value["first_under_net"]["index"] = 0
        self.assertEqual(coverage.context_status(value), "unknown_previous_observation")
        self.assertFalse(coverage.rim_context_eval.trigger(value))
        value["first_under_net"] = None
        self.assertEqual(coverage.context_status(value), "no_under_net_observation")
        value = trace()
        value["first_under_net"]["last_above"] = None
        self.assertEqual(coverage.context_status(value), "unknown_above_rim_context")

    def test_pipeline_exception_restores_functions(self):
        original_decide, original_find = coverage.shots.decide, coverage.shots.find_shots
        with patch.object(coverage.makes_eval, "run_pipeline", side_effect=RuntimeError("test")):
            with self.assertRaisesRegex(RuntimeError, "test"):
                coverage.replay("mitty", {})
        self.assertIs(coverage.shots.decide, original_decide)
        self.assertIs(coverage.shots.find_shots, original_find)


if __name__ == "__main__":
    unittest.main()
