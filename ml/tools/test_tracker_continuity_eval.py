"""Actual pinned ByteTrack tests; synthetic truth does not label cached people."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tracker_continuity_eval import (CONFIGS, actual_dependencies, continuity_summary,
                                     observation, run_tracker, synthetic_inputs,
                                     threshold_probe)


class ActualByteTrackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.np, cls.sv = actual_dependencies()

    def test_only_buffer_changes_and_runtime_semantics(self):
        first, second = CONFIGS["current"], CONFIGS["buffer_3s"]
        self.assertEqual([key for key in first if first[key] != second[key]], ["lost_track_buffer"])
        self.assertEqual(self.sv.ByteTrack(**first).max_time_lost, 10)
        self.assertEqual(self.sv.ByteTrack(**second).max_time_lost, 30)
        self.assertEqual(self.sv.ByteTrack(**first).det_thresh, 0.6)

    def measure(self, case, config):
        frames = synthetic_inputs()[case]
        return continuity_summary(frames, run_tracker(frames, CONFIGS[config]), synthetic=True)

    def test_short_gap_preserved_both_long_gap_only_extended(self):
        for config in CONFIGS:
            self.assertEqual(self.measure("occlusion_5_frames", config)["known_identity_fragments"], 0)
        self.assertEqual(self.measure("occlusion_18_frames", "current")["known_identity_fragments"], 1)
        self.assertEqual(self.measure("occlusion_18_frames", "buffer_3s")["known_identity_fragments"], 0)
        for config in CONFIGS:
            self.assertEqual(self.measure("occlusion_35_frames", config)["known_identity_fragments"], 1)

    def test_extended_buffer_can_contaminate_both_team_relations(self):
        for relation in ("same_team", "opposing_team"):
            case = f"stale_replacement_{relation}"
            self.assertEqual(self.measure(case, "current")["contaminated_replay_ids"], 0)
            self.assertEqual(self.measure(case, "buffer_3s")["contaminated_replay_ids"], 1)

    def test_team_tags_do_not_enter_tracker(self):
        cases = synthetic_inputs()
        for config in CONFIGS.values():
            self.assertEqual(run_tracker(cases["crossing_same_team"], config),
                             run_tracker(cases["crossing_opposing_team"], config))

    def test_threshold_boundaries_without_changing_configuration(self):
        probe = threshold_probe()
        for score, by_config in probe.items():
            self.assertEqual(by_config["current"], by_config["buffer_3s"])
            result = by_config["current"]
            self.assertEqual(result["fresh_output_by_frame"], [int(float(score) >= 0.6)] * 4)
            expected = 0.1 < float(score) < 0.5 or float(score) > 0.5
            self.assertEqual(result["ongoing_probe_output_by_frame"][0], int(expected))
            self.assertEqual(result["lost_track_probe_output"], int(float(score) > 0.5))

    def test_camera_translation_and_crossings_are_deterministic(self):
        for case in ("camera_translation_smooth", "camera_translation_abrupt",
                     "crossing_same_team", "crossing_opposing_team"):
            frames = synthetic_inputs()[case]
            for config in CONFIGS.values():
                self.assertEqual(run_tracker(frames, config), run_tracker(frames, config))

    def test_no_alias_for_covisible_different_players(self):
        frames = [[observation("person_A"), observation("person_B", x=300)] for _ in range(5)]
        for config in CONFIGS.values():
            outputs = run_tracker(frames, config)
            self.assertTrue(all(len({row["track_id"] for row in rows}) == 2 for rows in outputs))
            self.assertEqual(continuity_summary(frames, outputs, True)["contaminated_replay_ids"], 0)

    def test_cached_diagnostics_never_emit_real_identity_metrics(self):
        frames = [[observation("cache_1")], [observation("cache_2")]]
        summary = continuity_summary(frames, run_tracker(frames, CONFIGS["current"]))
        self.assertNotIn("known_identity_id_changes", summary)
        self.assertNotIn("contaminated_replay_ids", summary)
        self.assertEqual(summary["replay_ids_spanning_multiple_input_keys"], {"1": ["cache_1", "cache_2"]})


if __name__ == "__main__":
    unittest.main()
