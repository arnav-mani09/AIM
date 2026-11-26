"""Season summary API. Runs on an in-memory SQLite database, never the real one.

    cd backend && .venv/bin/python -m unittest tests.test_season -v
"""

import os

# Before any app import: a throwaway database and no Sentry, whatever backend/.env says.
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
from app.services import shot_events  # noqa: E402


def shot(t, team, shot_type, made, **detail):
    return {"type": "shot", "t": t, "team": team, "shot_type": shot_type, "made": made, "confidence": 0.7,
            "player_number": None, "rim": None, "parts": {}, "detail": detail}


GAME_ONE = {"events": [
    shot(10, "valley", "fg2", True, court_x=1.0, court_y=2.0, zone="restricted_area"),
    shot(20, "valley", "fg3", True, court_x=-20.0, court_y=5.0, zone="corner_three_left"),
    shot(30, "opponent", "fg2", False),
    shot(40, "valley", "ft", True),
    {"type": "oreb", "t": 31, "team": "valley", "shot_type": "none", "made": False, "confidence": 0.75},
    {"type": "dreb", "t": 33, "team": "opponent", "shot_type": "none", "made": False, "confidence": 0.75},
    {"type": "to", "t": 35, "team": "valley", "shot_type": "none", "made": False, "confidence": 0.6},
    {"type": "stl", "t": 35, "team": "opponent", "shot_type": "none", "made": False, "confidence": 0.5, "hidden": True},
], "possession": {"method": "v2", "film_read": True}}
GAME_TWO = {"events": [
    shot(5, "valley", "fg2", False),
    shot(15, "opponent", "fg3", True),
    shot(25, "valley", "fg2", True),  # deleted by the coach below
]}


class SeasonTest(unittest.TestCase):
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
                shot_events.load_events(db, upload, events)
            return upload

        done = {"status": "ready", "detection_status": "done", "events_status": "done"}
        one = film(team.id, "Game one", GAME_ONE, **done)
        two = film(team.id, "Game two", GAME_TWO, **done)
        film(team.id, "Still processing", status="processing", detection_status="running")
        film(team.id, "Broken", status="error")
        film(other.id, "Other team", GAME_ONE, **done)
        db.flush()
        last = db.query(ShotEvent).filter(ShotEvent.upload_id == two.id, ShotEvent.t == 25).one()
        last.status = "deleted"
        db.commit()
        self.team_id, self.other_id, self.user_id = team.id, other.id, user.id
        self.one_id, self.two_id = one.id, two.id
        db.close()

        def get_db():
            s = self.Session()
            try:
                yield s
            finally:
                s.close()

        def membership(team_id: int):
            if team_id != self.team_id:
                raise HTTPException(status_code=403, detail="Not a member of this team")
            return True

        app.dependency_overrides[deps.get_db_session] = get_db
        app.dependency_overrides[deps.get_current_user] = lambda: self.Session().get(User, self.user_id)
        app.dependency_overrides[deps.require_team_membership] = membership
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_games_totals_and_shots(self):
        body = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        self.assertEqual({g["upload_id"] for g in body["games"]}, {self.one_id, self.two_id})
        self.assertEqual(body["pending"], 1)  # the broken film isn't pending or counted
        games = {g["upload_id"]: g for g in body["games"]}
        self.assertEqual(games[self.one_id]["box_score"]["valley"],
                         {"fgm": 2, "fga": 2, "fg3m": 1, "fg3a": 1, "ftm": 1, "fta": 1, "pts": 6,
                          "oreb": 1, "dreb": 0, "reb": 1, "to": 1})
        # Game two was drafted before rebounds and turnovers existed: None, not 0.
        self.assertEqual((games[self.one_id]["has_plays"], games[self.two_id]["has_plays"]), (True, False))
        self.assertIsNone(games[self.two_id]["box_score"]["valley"]["to"])
        self.assertEqual(body["plays_games"], 1)
        self.assertEqual(games[self.two_id]["box_score"]["valley"]["fga"], 1)  # deleted shot left out
        self.assertEqual((games[self.two_id]["shots"], games[self.two_id]["reviewed"]), (2, 1))
        self.assertEqual(body["totals"]["valley"],
                         {"fgm": 2, "fga": 3, "fg3m": 1, "fg3a": 1, "ftm": 1, "fta": 1, "pts": 6,
                          "oreb": 1, "dreb": 0, "reb": 1, "to": 1})
        self.assertEqual(body["totals"]["opponent"],
                         {"fgm": 1, "fga": 2, "fg3m": 1, "fg3a": 1, "ftm": 0, "fta": 0, "pts": 3,
                          "oreb": 0, "dreb": 1, "reb": 1, "to": 0})
        self.assertEqual(len(body["shots"]), 6)
        spot = next(s for s in body["shots"] if s["zone"] == "corner_three_left")
        self.assertEqual((spot["x"], spot["y"], spot["upload_id"]), (-20.0, 5.0, self.one_id))
        self.assertTrue(all(s["status"] != "deleted" for s in body["shots"]))

    def test_other_team_is_blocked(self):
        self.assertEqual(self.client.get(f"/api/v1/teams/{self.other_id}/season").status_code, 403)

    def test_empty_team(self):
        db = self.Session()
        db.query(GameUpload).filter(GameUpload.team_id == self.team_id).delete()
        db.commit()
        db.close()
        body = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        self.assertEqual((body["games"], body["shots"], body["pending"]), ([], [], 0))
        self.assertEqual(body["totals"]["valley"]["pts"], 0)

    def reset_play_data(self):
        db = self.Session()
        db.query(ShotEvent).filter(ShotEvent.upload_id.in_((self.one_id, self.two_id)),
                                   ShotEvent.type != "shot").delete(synchronize_session=False)
        for upload_id in (self.one_id, self.two_id):
            db.get(GameUpload, upload_id).events_info = {}
        return db

    def test_independent_category_totals_and_cohort_counts(self):
        db = self.reset_play_data()
        db.get(GameUpload, self.one_id).events_info = {
            "play_coverage": {"rebounds": "complete", "turnovers": "unavailable"}}
        db.add(ShotEvent(upload_id=self.two_id, type="to", t=30, team="valley", shot_type="none",
                         made=False, confidence=1, status="fixed"))
        db.commit()
        db.close()
        body = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        self.assertEqual(body["play_coverage"], {
            "rebounds": {"complete": 1, "partial": 0, "unavailable": 1},
            "turnovers": {"complete": 0, "partial": 1, "unavailable": 1},
        })
        self.assertEqual((body["totals"]["valley"]["reb"], body["totals"]["valley"]["to"]), (0, 1))
        games = {game["upload_id"]: game for game in body["games"]}
        self.assertIsNone(games[self.one_id]["box_score"]["valley"]["to"])
        self.assertIsNone(games[self.two_id]["box_score"]["valley"]["reb"])
        self.assertEqual(games[self.two_id]["play_coverage"], {"rebounds": "unavailable", "turnovers": "partial"})
        self.assertEqual(body["totals"]["valley"]["pts"], 6)

    def test_deleted_manual_rebound_keeps_observed_zero_not_unknown_turnovers(self):
        db = self.reset_play_data()
        db.add(ShotEvent(upload_id=self.one_id, type="oreb", t=30, team="valley", shot_type="none",
                         made=False, confidence=1, status="deleted"))
        db.commit()
        db.close()
        body = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        self.assertEqual(body["totals"]["valley"]["reb"], 0)
        self.assertIsNone(body["totals"]["valley"]["to"])
        self.assertIsNone(body["totals"]["opponent"]["to"])
        self.assertEqual(body["play_coverage"]["rebounds"], {"complete": 0, "partial": 1, "unavailable": 1})
        self.assertEqual(body["play_coverage"]["turnovers"], {"complete": 0, "partial": 0, "unavailable": 2})

    def test_successful_empty_extraction_keeps_category_zeros(self):
        db = self.reset_play_data()
        db.get(GameUpload, self.one_id).events_info = {
            "play_coverage": {"rebounds": "complete", "turnovers": "complete"}}
        db.commit()
        db.close()
        body = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        self.assertEqual(body["plays_games"], 1)
        for category in ("rebounds", "turnovers"):
            self.assertEqual(body["play_coverage"][category], {"complete": 1, "partial": 0, "unavailable": 1})
        for side in ("valley", "opponent"):
            self.assertEqual([body["totals"][side][key] for key in ("oreb", "dreb", "reb", "to")], [0, 0, 0, 0])

    def test_hidden_events_do_not_establish_category_coverage(self):
        db = self.reset_play_data()
        for kind in ("ast", "stl"):
            db.add(ShotEvent(upload_id=self.one_id, type=kind, t=30, team="valley", shot_type="none",
                             made=False, confidence=1, status="draft"))
        db.commit()
        db.close()
        body = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        self.assertEqual(body["plays_games"], 0)
        for category in ("rebounds", "turnovers"):
            self.assertEqual(body["play_coverage"][category], {"complete": 0, "partial": 0, "unavailable": 2})
        for side in ("valley", "opponent"):
            self.assertTrue(all(body["totals"][side][key] is None for key in ("oreb", "dreb", "reb", "to")))


if __name__ == "__main__":
    unittest.main()
