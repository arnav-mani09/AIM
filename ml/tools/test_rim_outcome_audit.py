import copy
import unittest
from unittest.mock import patch

import rim_outcome_audit as audit
import shots


def attempt(points):
    return {"t": points[0][0], "rim": [100, 100, 120, 110],
            "ball_score": 0.85, "rim_score": 0.8,
            "path": [(time, 110 + 20 * horizontal, 100 + 10 * vertical,
                      100, 100, 120, 110) for time, horizontal, vertical in points]}


class RimOutcomeAuditTest(unittest.TestCase):
    def test_actual_rejection_uses_primary_not_missing_ball_fallback(self):
        path = [
            (4422.8, 1382, 114.55, 1293.1, 182.9, 1356.9, 211.1),
            (4422.9, 1368, 161.85, 1294.7, 184.6, 1355.3, 210.9),
            (4423.0, 1353, 217.5, 1296.2, 186.6, 1355.8, 214.2),
            (4423.1, 1337, 278.5, 1291.3, 187, 1356.7, 216.8),
            (4423.2, 1324, 342, 1289.9, 190.1, 1352.1, 216.9),
            (4423.6, 1311, 323.75, 1291.8, 188.3, 1350.2, 215.2),
            (4423.7, 1319, 280, 1292.5, 184.8, 1355.5, 213.2),
            (4423.8, 1338, 269.5, 1296.8, 183.6, 1359.2, 212.2),
            (4424.2, 1428, 317, 1356, 181.4, 1422, 210.1),
            (4424.3, 1453, 298.5, 1366.7, 181, 1433.3, 211),
            (4424.4, 1478, 291.25, 1376.4, 181.9, 1441.6, 210.3),
        ]
        shot = {"t": 4422.8, "rim": [1293, 183, 1357, 211], "ball_score": 0.856,
                "rim_score": 0.804, "path": path}
        original = copy.deepcopy(shot)
        result = audit.explain(shot, 4424.4)
        self.assertEqual(shot, original)
        self.assertEqual(result["branch"], "primary_under_net")
        self.assertEqual(result["decide_result"]["make_t"], 4423.1)
        self.assertEqual(result["decide_result"]["evidence"], 2)
        self.assertTrue(all(result["first_under_net"]["primary_checks"].values()))
        self.assertFalse(result["first_under_net"]["gap_checks"]["gap_length"])
        self.assertAlmostEqual(result["rim_unit_path"][2][1], 0.4530201)
        before, after = path[2:4]
        synthetic_point = tuple(start + (end - start) / 3 for start, end in zip(before, after))
        synthetic_shot = copy.deepcopy(shot)
        synthetic_shot["path"].insert(3, synthetic_point)
        synthetic_result = audit.explain(synthetic_shot, 4424.4)
        self.assertEqual(synthetic_result["branch"], "no_make")
        self.assertFalse(synthetic_result["first_under_net"]["primary_checks"]["centered_exit"])
        self.assertEqual(shot, original)

    def test_centered_projection_is_not_a_physical_outcome_label(self):
        shot = attempt([(0, 0.7, -1), (0.1, 0.45, 1.1), (0.2, 0.2, 3), (0.3, 0, 5)])
        result = audit.explain(shot, 1.6)
        self.assertEqual(result["branch"], "primary_under_net")
        self.assertNotIn("physical_outcome", result)

    def test_post_exit_drift_can_reject_positive_control_shape(self):
        shot = attempt([(0, 0, -0.5), (0.1, 0.22, 1.42), (0.2, 0.24, 2.47),
                        (0.3, 0.59, 2.47), (0.4, 1.02, 3.32)])
        result = audit.explain(shot, 1.6)
        self.assertEqual(result["branch"], "no_make")
        self.assertFalse(result["first_under_net"]["primary_checks"]["no_exit_drift"])

    def test_gap_fallback_is_distinct_from_primary(self):
        result = audit.explain(attempt([(0, 0, -0.5), (0.4, 0.5, 2)]), 1.6)
        self.assertEqual(result["branch"], "gap_under_net")
        self.assertFalse(result["first_under_net"]["primary_checks"]["centered_exit"])

    def test_disappearance_needs_observation_horizon(self):
        shot = attempt([(0, 0, -0.5), (0.1, 0, 0.9)])
        self.assertEqual(audit.explain(shot, 0.2)["branch"], "no_make")
        self.assertEqual(audit.explain(shot, 1)["branch"], "net_disappearance")

    def test_first_under_net_is_not_retried_after_side_exit(self):
        result = audit.explain(attempt([(0, 0, -0.5), (0.1, 0.8, 2), (0.2, 0, 3)]), 1.6)
        self.assertEqual(result["first_under_net"]["index"], 1)
        self.assertEqual(result["branch"], "no_make")

    def test_replay_preserves_inputs_and_restores_production_function(self):
        shot = attempt([(0, 0, -0.5), (0.1, 0, 1), (0.2, 0, 2)])
        frames = [(time, [[3, 100, 100, 120, 110, 0.9],
                          [0, horizontal - 2, vertical - 2, horizontal + 2, vertical + 2, 0.9]])
                  for time, horizontal, vertical, *_ in shot["path"]]
        doc = {"fps": 10, "frame_size": [1000, 500], "frames": frames}
        original_doc, original_decide = copy.deepcopy(doc), shots.decide
        with patch.object(shots, "dead_ball_make", return_value=False):
            result = audit.replay(doc, [0])
        self.assertEqual(doc, original_doc)
        self.assertIs(shots.decide, original_decide)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["final_find_shots_result"]["made"])

    def test_empty_path_is_not_a_make(self):
        shot = {"t": 0, "rim": [100, 100, 120, 110], "ball_score": 0.8,
                "rim_score": 0.8, "path": []}
        result = audit.explain(shot, 1.6)
        self.assertEqual(result["branch"], "no_make")
        self.assertIsNone(result["first_under_net"])


if __name__ == "__main__":
    unittest.main()
