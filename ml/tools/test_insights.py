"""Tests for insights.py on made-up shots (no game data needed).

Run: ml/.venv/bin/python -m unittest ml/tools/test_insights.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import insights as I  # noqa: E402

ARCS = {"left": {"ellipse_rim_widths": [1.0, 5.0, 7.0, 2.2, 0.0]},
        "right": {"ellipse_rim_widths": [-1.0, 5.0, 7.0, 2.2, 0.0]}}
RIM = [100, 100, 120, 110]   # rim center (110, 105), 20 px wide


def fg(team, made, value=2, zone="paint", player=None, timing="middle", into=12.0, **kw):
    s = {"t": 0.0, "team": team, "kind": "FG", "made": made, "value": value, "value_known": True,
         "pts": value if made else 0, "player": player, "zone": zone, "timing": timing, "into_poss_s": into}
    s.update(kw)
    return s


def ft(team, made, player=None):
    return {"t": 0.0, "team": team, "kind": "FT", "made": made, "value": 1, "pts": int(made), "player": player}


def game(shots, poss=None):
    return {"game": "test", "shots": shots, "poss": poss, "players_seen": {}}


class ZoneTest(unittest.TestCase):
    def feet(self, dx, dy):   # rim widths from the rim center
        return [110 + 20 * dx, 105 + 20 * dy]

    def test_top_of_key_three(self):
        z = I.zone_of({"feet": self.feet(9, 5), "rim_at_take": RIM, "margin": 2.0, "basket": "left", "points": 3}, ARCS)
        self.assertEqual(z["zone"], "above_break3")
        self.assertEqual(z["dist_ft"], 21.8)

    def test_near_corner_three(self):
        z = I.zone_of({"feet": self.feet(-1, 8), "rim_at_take": RIM, "margin": 1.0, "basket": "left", "points": 3}, ARCS)
        self.assertEqual(z["zone"], "corner3")

    def test_right_basket_mirrors(self):
        z = I.zone_of({"feet": self.feet(-9, 5), "rim_at_take": RIM, "margin": 2.0, "basket": "right", "points": 3}, ARCS)
        self.assertEqual(z["zone"], "above_break3")

    def test_twos_by_distance(self):
        base = {"feet": self.feet(2, 5), "rim_at_take": RIM, "basket": "left", "points": 2}
        self.assertEqual(I.zone_of({**base, "margin": -16.0}, ARCS)["zone"], "rim")
        self.assertEqual(I.zone_of({**base, "margin": -10.0}, ARCS)["zone"], "paint")
        self.assertEqual(I.zone_of({**base, "margin": -3.0}, ARCS)["zone"], "midrange")

    def test_missing_feet_or_wild_distance_is_unknown(self):
        self.assertEqual(I.zone_of({"rim_at_take": RIM, "margin": 1.0, "basket": "left"}, ARCS)["zone"], "unknown")
        z = I.zone_of({"feet": self.feet(9, 5), "rim_at_take": RIM, "margin": 50.0, "basket": "left", "points": 3}, ARCS)
        self.assertEqual(z["zone"], "unknown")


class RatesTest(unittest.TestCase):
    def setUp(self):
        # Made-up game: home 2 of 4 FG (one made 3), 1 of 2 FT = 6 pts.
        self.shots = [fg("Valley", True, 3, "corner3", "7"), fg("Valley", False, 3, "corner3", "7"),
                      fg("Valley", True, 2, "paint", "9", timing="early", into=3.0), fg("Valley", False, 2, "midrange"),
                      ft("Valley", True, "9"), ft("Valley", False, "9"),
                      fg("Opponent", True, 2, "rim", "11")]

    def test_team_rates(self):
        doc = I.build([I.game_counts(game(self.shots))])
        t = doc["teams"]["Valley"]
        self.assertEqual(t["pts"]["value"], 6)
        self.assertEqual(t["fg"]["value"], "2/4")
        self.assertEqual(t["efg_pct"]["value"], 62.5)            # (2 + 0.5) / 4
        self.assertEqual(t["ts_pct"]["value"], round(100 * 6 / (2 * (4 + 0.88)), 1))
        self.assertEqual(t["ft_rate"]["value"], 0.5)
        self.assertEqual(t["fg3a_rate"]["value"], 0.5)
        self.assertEqual(t["shot_mix"]["corner3"]["value"], 50.0)
        self.assertEqual(t["fg_pct"]["trust"], I.SOLID)
        self.assertNotIn("possessions", t)                       # no possession file, no rough stats

    def test_players_and_unknown(self):
        doc = I.build([I.game_counts(game(self.shots))])
        p = doc["players"]["Valley"]
        self.assertEqual(p["7"]["fg3a"], 2)
        self.assertEqual(p["7"]["share_of_team_fga"], 50.0)
        self.assertTrue(p["7"]["small_sample"])
        self.assertEqual(p["7"]["favorite_zones"][0]["zone"], "corner3")
        self.assertEqual(p["unknown"]["fga"], 1)
        self.assertEqual(p["9"]["pts"], 3)

    def test_rollup_sums_counts_not_percentages(self):
        g1 = I.game_counts(game([fg("Valley", True), fg("Valley", True)]))           # 2 of 2
        g2 = I.game_counts(game([fg("Valley", False)] * 8))                          # 0 of 8
        t = I.build([g1, g2])["teams"]["Valley"]
        self.assertEqual(t["fg_pct"]["value"], 20.0)   # 2 of 10, not the 50% average of 100% and 0%
        self.assertEqual(t["games"], 2)

    def test_possession_stats_are_rough(self):
        poss = {"timeline": [[0, 10, "Valley"], [10, 20, "Opponent"], [20, 30, "Valley"]],
                "events": [], "counts": {"Valley": {"oreb": 1, "dreb": 2, "to": 1}, "Opponent": {"oreb": 0, "dreb": 3, "to": 2}}}
        t = I.build([I.game_counts(game(self.shots, poss))])["teams"]["Valley"]
        self.assertEqual(t["possessions"]["value"], 2)
        self.assertEqual(t["off_ppp"]["value"], 3.0)
        self.assertEqual(t["oreb_pct"]["value"], 25.0)   # 1 / (1 + 3)
        self.assertEqual(t["to_pct"]["trust"], I.ROUGH)

    def test_attach_possessions(self):
        poss = {"timeline": [[0, 30, "Valley"], [30.1, 60, "Opponent"]],
                "events": [{"type": "oreb", "team": "Valley", "t": 12.0}, {"type": "to", "team": "Valley", "t": 30.1}]}
        shots = [{"t": 5.0, "team": "Valley", "kind": "FG"}, {"t": 15.0, "team": "Valley", "kind": "FG"},
                 {"t": 33.0, "team": "Opponent", "kind": "FG"}]
        I.attach_possessions(shots, poss)
        self.assertEqual(shots[0]["timing"], "early")
        self.assertFalse(shots[0]["second_chance"])
        self.assertTrue(shots[1]["second_chance"])
        self.assertTrue(shots[2]["off_to"])


class TextTest(unittest.TestCase):
    def test_scouting_text_is_plain(self):
        shots = [fg("Opponent", m, 3, "corner3", "23") for m in (True, False, False, True, False, True, False, False)]
        shots += [fg("Opponent", False, 2, "paint") for _ in range(4)]
        doc = I.build([I.game_counts(game(shots))], team="Opponent")
        text = I.scouting_text(doc, "Opponent", "Test report")
        self.assertIn("#23: 9 pts, takes 67% of the team's shots, FG 3 of 8, 3PT 3 of 8; mostly corner 3s (3 of 8)", text)
        self.assertNotIn(chr(0x2014), text)
        self.assertNotIn("Small sample", text.split("#23")[1].split("\n")[0])


if __name__ == "__main__":
    unittest.main()
