"""Team shooting insights: the formulas (same as ml/tools/insights.py), zones, scouting lines and
the API. Runs on an in-memory SQLite database, never the real one.

    cd backend && .venv/bin/python -m unittest tests.test_insights -v
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

import unittest  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api import deps  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GameUpload, ShotEvent, Team, User  # noqa: E402
from app.services import insights, shot_events  # noqa: E402


def s(team, shot_type, made, x=None, y=None, status="confirmed"):
    return {"team": team, "shot_type": shot_type, "made": made, "x": x, "y": y, "status": status}


class ZoneTest(unittest.TestCase):
    def test_zones(self):
        z = insights.zone_of
        self.assertEqual(z(0, 3, False), "rim")
        self.assertEqual(z(8, 9, False), "paint")  # a distance cut, like the offline tool
        self.assertEqual(z(12, 12, False), "midrange")
        self.assertEqual(z(-21, 4, True), "corner3")
        self.assertEqual(z(15, 15, True), "above_break3")
        self.assertEqual(z(None, None, True), "unknown")
        self.assertEqual(z(0, 45, True), "unknown")  # feet found in the wrong place


class FormulaTest(unittest.TestCase):
    def test_rates_match_the_offline_formulas(self):
        shots = [
            s("opponent", "fg3", True, -21, 3), s("opponent", "fg3", False, 21, 2), s("opponent", "fg3", False, 0, 22),
            s("opponent", "fg2", True, 0, 2), s("opponent", "fg2", False, 10, 15),
            s("opponent", "ft", True), s("opponent", "ft", False),
            s("opponent", "fg2", True, 0, 1, status="deleted"),
            s("valley", "fg2", True),
        ]
        t = insights.build(shots, 1)["opponent"]
        self.assertEqual((t["fgm"], t["fga"], t["fg3m"], t["fg3a"], t["ftm"], t["fta"], t["pts"]),
                         (2, 5, 1, 3, 1, 2, 6))
        self.assertEqual(t["efg_pct"], 50.0)            # (2 + 0.5) / 5
        self.assertEqual(t["ts_pct"], round(100 * 6 / (2 * (5 + 0.44 * 2)), 1))
        self.assertEqual((t["ft_rate"], t["fg3a_rate"]), (0.4, 0.6))
        zones = {z["zone"]: z for z in t["zones"]}
        self.assertEqual((zones["corner3"]["attempts"], zones["corner3"]["makes"], zones["corner3"]["points"]),
                         (2, 1, 3))
        self.assertEqual(zones["corner3"]["share"], 40.0)
        self.assertEqual((zones["rim"]["points"], zones["midrange"]["attempts"]), (2, 1))
        self.assertNotIn("unknown", zones)  # no unspotted shots, no row
        self.assertTrue(t["small_sample"])
        self.assertTrue(zones["rim"]["small_sample"])

    def test_scouting_lines(self):
        shots = ([s("opponent", "fg3", i < 4, -21, 3) for i in range(11)]
                 + [s("opponent", "fg3", False, 0, 22) for _ in range(4)]
                 + [s("opponent", "fg2", i < 6, 0, 2) for i in range(10)]
                 + [s("opponent", "fg2", False) for _ in range(1)]
                 + [s("opponent", "ft", True) for _ in range(2)])
        t = insights.build(shots, 2)["opponent"]
        text = " ".join(t["lines"])
        self.assertIn("They take 58% of their shots from 3, mostly corner 3s (4 of 11).", text)
        self.assertIn("a game over 2 games", text)
        self.assertIn("They shoot best at the rim (6 of 10, 60%) and worst corner 3s (4 of 11, 36%).", text)
        self.assertIn("rarely get to the free throw line", text)
        self.assertIn("1 shot had no court spot", text)
        self.assertNotIn("Small sample", text)
        self.assertNotIn("—", text)  # no em dashes

        ours = insights.build([s("valley", "fg2", True, 0, 2)], 1)["valley"]
        self.assertTrue(ours["lines"][0].startswith("We scored 2 points"))
        self.assertIn("Small sample", ours["lines"][-1])
        self.assertEqual(insights.build([], 0)["opponent"]["lines"], ["No shots counted for them yet."])


class PlayRatesTest(unittest.TestCase):
    def test_turnover_and_rebound_rates(self):
        shots = ([s("valley", "fg2", False) for _ in range(10)] + [s("valley", "ft", True) for _ in range(5)]
                 + [s("opponent", "fg2", False) for _ in range(8)])
        plays = ([{"type": "oreb", "team": "valley", "status": "draft"}] * 3
                 + [{"type": "dreb", "team": "valley", "status": "draft"}] * 6
                 + [{"type": "oreb", "team": "opponent", "status": "draft"}] * 2
                 + [{"type": "dreb", "team": "opponent", "status": "draft"}] * 7
                 + [{"type": "to", "team": "valley", "status": "draft"}] * 4
                 + [{"type": "to", "team": "valley", "status": "deleted"}])
        t = insights.build(shots, 1, plays, shots, 1)
        v, o = t["valley"], t["opponent"]
        self.assertEqual((v["oreb"], v["dreb"], v["reb"], v["to"], v["play_games"]), (3, 6, 9, 4, 1))
        self.assertEqual(v["tov_pct"], round(100 * 4 / (10 + 0.44 * 5 - 3 + 4), 1))
        self.assertEqual(v["oreb_pct"], 30.0)   # 3 / (3 + 7)
        self.assertEqual(v["dreb_pct"], 75.0)   # 6 / (6 + 2)
        self.assertEqual(o["to"], 0)
        self.assertIn("turned it over 4 times", " ".join(v["lines"]))
        self.assertEqual(set(insights.QUALITY.values()), {"fair"})

    def test_no_plays_gives_none(self):
        t = insights.build([s("valley", "fg2", True)], 1)["valley"]
        self.assertEqual((t["play_games"], t["oreb"], t["tov_pct"]), (0, None, None))
        self.assertFalse(any("turned it over" in line for line in t["lines"]))


def ev(t, team, shot_type, made, **detail):
    return {"type": "shot", "t": t, "team": team, "shot_type": shot_type, "made": made, "confidence": 0.7,
            "player_number": None, "rim": None, "parts": {}, "detail": detail}


class InsightsApiTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        db = self.Session()
        user = User(email="coach@example.com", hashed_password="x", full_name="Coach")
        team, other = Team(name="Valley"), Team(name="Someone else")
        db.add_all([user, team, other])
        db.flush()

        def film(team_id, title, events=None, **status):
            upload = GameUpload(team_id=team_id, title=title, storage_url=f"r2://aim-film/{title}.mp4", **status)
            db.add(upload)
            db.flush()
            if events:
                shot_events.load_events(db, upload, {"events": events})
            return upload

        done = {"status": "ready", "detection_status": "done", "events_status": "done"}
        one = film(team.id, "Game one", [
            ev(10, "opponent", "fg3", True, court_x=-21.0, court_y=3.0, zone="corner_three_left"),
            ev(20, "opponent", "fg2", False, court_x=0.0, court_y=2.0, zone="restricted_area"),
            ev(30, "valley", "fg2", True, court_x=0.0, court_y=2.0, zone="restricted_area"),
            {"type": "oreb", "t": 31, "team": "valley", "shot_type": "none", "made": False, "confidence": 0.75},
            {"type": "to", "t": 32, "team": "valley", "shot_type": "none", "made": False, "confidence": 0.6},
            {"type": "ast", "t": 29, "team": "valley", "shot_type": "none", "made": False, "confidence": 0.4},
        ], **done)
        two = film(team.id, "Game two", [
            ev(5, "opponent", "fg2", True, court_x=0.0, court_y=2.0),
            ev(15, "opponent", "ft", True),
        ], **done)
        busy = film(team.id, "Still processing", status="processing", detection_status="running")
        theirs = film(other.id, "Other team", [ev(1, "opponent", "fg3", True)], **done)
        db.flush()
        # The coach fixes the restricted area miss into a make: the fix counts.
        fixed = db.query(ShotEvent).filter(ShotEvent.upload_id == one.id, ShotEvent.t == 20).one()
        shot_events.apply_patch(fixed, {"made": True}, user.id)
        db.commit()
        self.team_id, self.other_id, self.user_id = team.id, other.id, user.id
        self.one, self.two, self.busy, self.theirs = one.id, two.id, busy.id, theirs.id
        db.close()

        def get_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        def membership(team_id: int):
            if team_id != self.team_id:
                raise HTTPException(status_code=403, detail="Not a member of this team")
            return True

        app.dependency_overrides[deps.get_db_session] = get_db
        app.dependency_overrides[deps.get_current_user] = lambda: self.Session().get(User, self.user_id)
        app.dependency_overrides[deps.require_team_membership] = membership
        self.client = TestClient(app)
        self.url = f"/api/v1/teams/{self.team_id}/insights"

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_all_ready_films(self):
        body = self.client.get(self.url).json()
        self.assertEqual({g["upload_id"] for g in body["games"]}, {self.one, self.two})
        opp = body["teams"]["opponent"]
        self.assertEqual((opp["games"], opp["fgm"], opp["fga"], opp["pts"]), (2, 3, 3, 8))
        zones = {z["zone"]: z for z in opp["zones"]}
        self.assertEqual((zones["rim"]["makes"], zones["rim"]["attempts"]), (2, 2))
        self.assertEqual(zones["corner3"]["points"], 3)
        self.assertEqual(body["teams"]["valley"]["pts"], 2)
        self.assertIn("Pace", body["coming_soon"])
        self.assertNotIn("Turnover rate", body["coming_soon"])
        self.assertEqual(body["quality"]["tov_pct"], "fair")
        # Only game one has rebounds and turnovers: rates over that game alone.
        val = body["teams"]["valley"]
        self.assertEqual((val["play_games"], val["oreb"], val["to"]), (1, 1, 1))
        self.assertEqual(val["oreb_pct"], 100.0)  # 1 / (1 + opponent's 0 dreb)
        self.assertEqual(val["tov_pct"], round(100 * 1 / (1 + 0 - 1 + 1), 1))
        self.assertIn("1 of 2 games", " ".join(val["lines"]))

    def test_one_game(self):
        body = self.client.get(self.url, params={"upload_ids": [self.two]}).json()
        self.assertEqual([g["upload_id"] for g in body["games"]], [self.two])
        self.assertEqual(body["teams"]["opponent"]["pts"], 3)
        self.assertEqual(body["teams"]["valley"]["fga"], 0)

    def test_picked_games_skip_unready_films(self):
        body = self.client.get(self.url, params={"upload_ids": [self.one, self.busy]}).json()
        self.assertEqual(([g["upload_id"] for g in body["games"]], body["skipped"]), ([self.one], 1))

    def test_other_teams_film_is_not_found(self):
        r = self.client.get(self.url, params={"upload_ids": [self.one, self.theirs]})
        self.assertEqual(r.status_code, 404)

    def test_other_team_is_blocked(self):
        self.assertEqual(self.client.get(f"/api/v1/teams/{self.other_id}/insights").status_code, 403)


if __name__ == "__main__":
    unittest.main()
