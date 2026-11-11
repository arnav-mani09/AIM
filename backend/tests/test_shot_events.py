"""Shot event API and box score. Runs on an in-memory SQLite database, never the real one.

    cd backend && .venv/bin/python -m unittest tests.test_shot_events -v
"""

import os

# Before any app import: a throwaway database and no Sentry, whatever backend/.env says.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

import unittest  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api import deps  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GameUpload, ShotEvent, Team, User  # noqa: E402
from app.services import shot_events  # noqa: E402

DRAFT = {
    "version": 1, "teams_guessed": True, "window": {"start": 10, "end": 100},
    "events": [
        {"type": "shot", "t": 12.5, "team": "valley", "shot_type": "fg2", "made": True, "confidence": 0.8,
         "player_number": None, "rim": [1, 2, 3, 4], "parts": {"attempt": 0.8}, "detail": {"evidence": 2}},
        {"type": "shot", "t": 30.0, "team": "opponent", "shot_type": "ft", "made": False, "confidence": 0.6,
         "player_number": None, "rim": [1, 2, 3, 4], "parts": {"attempt": 0.6}, "detail": {}},
        {"type": "shot", "t": 44.0, "team": "valley", "shot_type": "fg2", "made": False, "confidence": 0.5,
         "player_number": None, "rim": None, "parts": {}, "detail": {}},
    ],
}


class ShotEventsTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        db = self.Session()
        user = User(email="coach@example.com", hashed_password="x", full_name="Coach")
        team = Team(name="Valley")
        db.add_all([user, team])
        db.flush()
        upload = GameUpload(team_id=team.id, title="Game", storage_url="r2://aim-film/teams/1/film/a.mp4",
                            status="ready", detection_status="done", events_status="done")
        db.add(upload)
        db.flush()
        shot_events.load_events(db, upload, DRAFT)
        db.commit()
        self.team_id, self.upload_id, self.user_id = team.id, upload.id, user.id
        db.close()

        def get_db():
            s = self.Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[deps.get_db_session] = get_db
        app.dependency_overrides[deps.get_current_user] = lambda: self.Session().get(User, self.user_id)
        app.dependency_overrides[deps.require_team_membership] = lambda team_id: True
        # Not used as a context manager, so the background Modal poller never starts.
        self.client = TestClient(app)
        self.base = f"/api/v1/teams/{self.team_id}/film/{self.upload_id}/events"

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_list_has_events_and_box_score(self):
        body = self.client.get(self.base).json()
        self.assertEqual(body["status"], "ready")
        self.assertTrue(body["teams_guessed"])
        self.assertEqual([e["t"] for e in body["events"]], [12.5, 30.0, 44.0])
        self.assertEqual(set(body["events"][0]), {"id", "type", "t", "team", "shot_type", "made", "confidence",
                                                  "player_number", "status"})
        self.assertEqual(body["box_score"]["valley"], {"fgm": 1, "fga": 2, "fg3m": 0, "fg3a": 0, "ftm": 0, "fta": 0, "pts": 2})
        self.assertEqual(body["box_score"]["opponent"]["fta"], 1)

    def test_fix_confirm_delete(self):
        ids = [e["id"] for e in self.client.get(self.base).json()["events"]]
        # Changing the call makes it fixed and keeps the model's original.
        fixed = self.client.patch(f"{self.base}/{ids[0]}", json={"shot_type": "fg3"}).json()
        self.assertEqual((fixed["shot_type"], fixed["status"]), ("fg3", "fixed"))
        # Status alone is taken as sent.
        self.assertEqual(self.client.patch(f"{self.base}/{ids[1]}", json={"status": "confirmed"}).json()["status"], "confirmed")
        self.assertEqual(self.client.patch(f"{self.base}/{ids[2]}", json={"status": "deleted"}).json()["status"], "deleted")
        box = self.client.get(self.base).json()["box_score"]["valley"]
        self.assertEqual(box, {"fgm": 1, "fga": 1, "fg3m": 1, "fg3a": 1, "ftm": 0, "fta": 0, "pts": 3})
        db = self.Session()
        self.assertEqual(db.get(ShotEvent, ids[0]).original["shot_type"], "fg2")
        self.assertEqual(db.get(ShotEvent, ids[0]).updated_by_id, self.user_id)
        db.close()

    def test_add_missed_shot(self):
        r = self.client.post(self.base, json={"t": 50, "team": "opponent", "shot_type": "fg2", "made": True})
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.json()["status"], r.json()["confidence"]), ("fixed", 1.0))
        self.assertEqual(self.client.get(self.base).json()["box_score"]["opponent"]["pts"], 2)

    def test_bad_values_rejected(self):
        eid = self.client.get(self.base).json()["events"][0]["id"]
        self.assertEqual(self.client.patch(f"{self.base}/{eid}", json={"team": "home"}).status_code, 422)
        self.assertEqual(self.client.patch(f"{self.base}/99999", json={"made": True}).status_code, 404)

    def test_swap_teams(self):
        body = self.client.post(f"{self.base}/swap-teams").json()
        self.assertFalse(body["teams_guessed"])
        self.assertEqual(body["box_score"]["opponent"]["fga"], 2)
        self.assertTrue(all(e["status"] == "fixed" for e in body["events"]))

    def test_rerun_keeps_reviewed_shots(self):
        eid = self.client.get(self.base).json()["events"][0]["id"]
        self.client.patch(f"{self.base}/{eid}", json={"made": False})
        db = self.Session()
        upload = db.get(GameUpload, self.upload_id)
        self.assertEqual(shot_events.load_events(db, upload, {"events": []}), 0)
        db.commit()
        self.assertEqual(db.query(ShotEvent).count(), 3)
        db.close()

    def test_pending_until_events_done(self):
        db = self.Session()
        db.get(GameUpload, self.upload_id).events_status = "running"
        db.commit()
        db.close()
        self.assertEqual(self.client.get(self.base).json()["status"], "pending")


if __name__ == "__main__":
    unittest.main()
