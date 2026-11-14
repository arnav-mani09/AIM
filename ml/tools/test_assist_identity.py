"""Synthetic adapter checks, not assist labels or verified player identities."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assist_identity import local_hold_evidence, pixel_hold_evidence, shooter_hold_observation


class LocalEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.quick = {"tid": 7, "t0": 2.0, "t1": 2.4}
        self.sample = {**self.quick, "team": "Valley", "sure": True}

    def adapt(self, samples):
        return local_hold_evidence(self.quick, samples, lambda tid: "Opponent")

    def test_exact_local_interval_certifies_only_model_team(self):
        self.assertEqual(self.adapt([self.sample])["team"], "Valley")
        self.assertTrue(self.adapt([self.sample])["sure"])

    def test_other_time_same_track_cannot_certify(self):
        result = self.adapt([{**self.sample, "t0": 10, "t1": 11}])
        self.assertFalse(result["sure"])
        self.assertEqual(result["team"], "Opponent")

    def test_other_track_cannot_certify(self):
        self.assertFalse(self.adapt([{**self.sample, "tid": 8}])["sure"])

    def test_partial_overlap_cannot_certify_whole_hold(self):
        self.assertFalse(self.adapt([{**self.sample, "t1": 2.2}])["sure"])

    def test_containing_sustained_hold_certifies_shorter_quick_hold(self):
        self.assertTrue(self.adapt([{**self.sample, "t0": 1.9, "t1": 2.5}])["sure"])

    def test_conflicting_overlapping_samples_abstain(self):
        result = self.adapt([self.sample, {**self.sample, "team": "Opponent"}])
        self.assertFalse(result["sure"])
        self.assertIsNone(result["team"])

    def test_uncertain_and_unknown_samples_cannot_certify(self):
        for change in ({"sure": False}, {"team": None}):
            self.assertFalse(self.adapt([{**self.sample, **change}])["sure"])

    def test_referee_evidence_is_time_local(self):
        result = self.adapt([{**self.sample, "ref": True}])
        self.assertTrue(result["ref"])
        self.assertFalse(result["sure"])
        self.assertIsNone(result["team"])
        self.assertFalse(self.adapt([{**self.sample, "t0": 10, "t1": 11, "ref": True}])["ref"])

    def test_adapter_does_not_mutate_inputs(self):
        before = copy.deepcopy((self.quick, self.sample))
        self.adapt([self.sample])
        self.assertEqual((self.quick, self.sample), before)

    def test_local_pixels_override_opposing_global_track_vote(self):
        run = {**self.sample, "team": "Opponent", "vote": 0.8, "px": 0.4}
        result = pixel_hold_evidence(run, 0.2, 0.5)
        self.assertEqual(result["team"], "Valley")
        self.assertTrue(result["sure"])
        self.assertEqual(run["team"], "Opponent")

    def test_global_certainty_without_sufficient_local_pixels_is_not_evidence(self):
        for extra in ({}, {"vote": 0.8, "px": 0.1}, {"vote": 0.3, "px": 0.8},
                      {"vote": 0.1, "px": 0.8}):
            self.assertFalse(pixel_hold_evidence({**self.sample, **extra}, 0.2, 0.5)["sure"])

    def test_geometry_does_not_establish_alias(self):
        hold = {"tid": 7, "t0": 2, "t1": 2.4}
        observations = [{"t": 2.2, "players": [{"tid": 7, "box": [0, 0, 20, 100]},
                                                {"tid": 8, "box": [300, 0, 320, 100]}]}]
        result = shooter_hold_observation(8, hold, observations, 3)
        self.assertEqual(result["track_relation"], "separated_covisible_tracks")
        self.assertFalse(result["identity_verified"])
        self.assertAlmostEqual(result["release_to_shot"], 0.6)
        self.assertEqual(shooter_hold_observation(8, hold, [], 3)["track_relation"], "unresolved_tracks")

    def test_camera_translation_preserves_geometry(self):
        hold = {"tid": 7, "t0": 2, "t1": 2.4}
        players = [{"tid": 7, "box": [0, 0, 20, 100]}, {"tid": 8, "box": [300, 0, 320, 100]}]
        first = shooter_hold_observation(8, hold, [{"t": 2.2, "players": players}], 3)
        shifted = [{"tid": player["tid"], "box": [value + 500 for value in player["box"]]} for player in players]
        self.assertEqual(first, shooter_hold_observation(8, hold, [{"t": 2.2, "players": shifted}], 3))


if __name__ == "__main__":
    unittest.main()
