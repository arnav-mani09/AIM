"""Shot event API and box score. Runs on an in-memory SQLite database, never the real one.

    cd backend && .venv/bin/python -m unittest tests.test_shot_events -v
"""

import os

# Before any app import: a throwaway database and no Sentry, whatever backend/.env says.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

import unittest  # noqa: E402
from copy import deepcopy  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api import deps  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GameUpload, ShotEvent, Team, User  # noqa: E402
from app.services import chat, shot_events  # noqa: E402

DRAFT = {
    "version": 1, "teams_guessed": True, "window": {"start": 10, "end": 100},
    "events": [
        {"type": "shot", "t": 12.5, "team": "valley", "shot_type": "fg2", "made": True, "confidence": 0.8,
         "player_number": None, "rim": [1, 2, 3, 4], "parts": {"attempt": 0.8},
         "detail": {"evidence": 2, "court_x": -6.5, "court_y": 12.0, "zone": "mid_range_left"}},
        {"type": "shot", "t": 30.0, "team": "opponent", "shot_type": "ft", "made": False, "confidence": 0.6,
         "player_number": None, "rim": [1, 2, 3, 4], "parts": {"attempt": 0.6}, "detail": {}},
        {"type": "shot", "t": 44.0, "team": "valley", "shot_type": "fg2", "made": False, "confidence": 0.5,
         "player_number": None, "rim": None, "parts": {}, "detail": {}},
    ],
}


SHOOTING = ("fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts")


def play(kind, t, team, confidence=0.75, hidden=False):
    return {"type": kind, "t": t, "team": team, "shot_type": "none", "made": False, "confidence": confidence,
            "player_number": None, "rim": None, "hidden": hidden, "parts": {"event": confidence},
            "detail": {"how": "hold", "film_read": True}}


# The same film after the event step learned rebounds and turnovers (steals and assists hidden).
DRAFT_PLAYS = {
    **DRAFT, "version": 4, "possession": {"method": "v2", "film_read": True},
    "events": DRAFT["events"] + [
        play("dreb", 45.0, "opponent"), play("oreb", 50.0, "valley"), play("to", 60.0, "valley"),
        play("to", 70.0, "opponent"), play("stl", 60.0, "opponent", 0.5, True), play("ast", 12.0, "valley", 0.4, True),
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
                                                  "player_number", "status", "x", "y", "zone"})
        self.assertEqual((body["events"][0]["x"], body["events"][0]["y"], body["events"][0]["zone"]),
                         (-6.5, 12.0, "mid_range_left"))
        self.assertIsNone(body["events"][1]["x"])
        self.assertEqual(body["box_score"]["valley"], {"fgm": 1, "fga": 2, "fg3m": 0, "fg3a": 0, "ftm": 0, "fta": 0, "pts": 2,
                                                       "oreb": None, "dreb": None, "reb": None, "to": None})
        self.assertEqual((body["plays"], body["has_plays"]), ([], False))  # drafted before plays existed
        self.assertEqual(body["box_score"]["opponent"]["fta"], 1)

    def test_fix_confirm_delete(self):
        ids = [e["id"] for e in self.client.get(self.base).json()["events"]]
        # Changing the call makes it fixed and keeps the model's original.
        fixed = self.client.patch(f"{self.base}/{ids[0]}", json={"shot_type": "fg3"}).json()
        self.assertEqual((fixed["shot_type"], fixed["status"]), ("fg3", "fixed"))
        self.assertEqual((fixed["x"], fixed["y"]), (-6.5, 12.0))   # a fix doesn't move the shot
        # Status alone is taken as sent.
        self.assertEqual(self.client.patch(f"{self.base}/{ids[1]}", json={"status": "confirmed"}).json()["status"], "confirmed")
        self.assertEqual(self.client.patch(f"{self.base}/{ids[2]}", json={"status": "deleted"}).json()["status"], "deleted")
        box = self.client.get(self.base).json()["box_score"]["valley"]
        self.assertEqual({k: box[k] for k in SHOOTING}, {"fgm": 1, "fga": 1, "fg3m": 1, "fg3a": 1, "ftm": 0, "fta": 0, "pts": 3})
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

    def _rerun_with_plays(self):
        db = self.Session()
        upload = db.get(GameUpload, self.upload_id)
        stored = shot_events.load_events(db, upload, DRAFT_PLAYS)
        db.commit()
        db.close()
        return stored

    def _load_result(self, result):
        db = self.Session()
        upload = db.get(GameUpload, self.upload_id)
        stored = shot_events.load_events(db, upload, result)
        db.commit()
        db.close()
        return stored

    def _assert_totals_across_views(self, expected):
        film = self.client.get(self.base).json()
        season = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        scouting = self.client.get(f"/api/v1/teams/{self.team_id}/insights").json()
        db = self.Session()
        box = chat._box(db, db.get(GameUpload, self.upload_id))
        db.close()
        for team in ("valley", "opponent"):
            for key, made_key, attempts_key in (("fg", "fgm", "fga"), ("fg3", "fg3m", "fg3a"),
                                                 ("ft", "ftm", "fta")):
                made, attempts = map(int, box[team][key].split("/"))
                box[team].update({made_key: made, attempts_key: attempts})
        for team, values in expected.items():
            for key, value in values.items():
                with self.subTest(team=team, key=key):
                    self.assertEqual(film["box_score"][team][key], value)
                    self.assertEqual(season["totals"][team][key], value)
                    self.assertEqual(scouting["teams"][team][key], value)
                    self.assertEqual(box[team][key], value)
        return film

    def test_automatic_shot_corrections_refresh_all_views_with_reviewed_plays(self):
        self._rerun_with_plays()
        play_event = self.client.get(self.base).json()["plays"][0]
        self.client.patch(f"{self.base}/{play_event['id']}", json={"t": 46.5})
        corrected = deepcopy(DRAFT_PLAYS)
        corrected["events"][:3] = [
            {**DRAFT["events"][0], "shot_type": "fg3"},
            {**DRAFT["events"][1], "made": True, "team": "valley"},
            {**DRAFT["events"][2], "made": True, "team": "opponent"},
        ]
        corrected["box_score"] = {"valley": {"pts": 999}}
        for _ in range(3):
            self.assertEqual(self._load_result(corrected), 3)
            film = self._assert_totals_across_views({
                "valley": {"fgm": 1, "fga": 1, "fg3m": 1, "fg3a": 1,
                           "ftm": 1, "fta": 1, "pts": 4, "reb": 1, "to": 1},
                "opponent": {"fgm": 1, "fga": 1, "fg3m": 0, "fg3a": 0,
                             "ftm": 0, "fta": 0, "pts": 2, "reb": 1, "to": 1},
            })
            saved = next(p for p in film["plays"] if p["id"] == play_event["id"])
            self.assertEqual((saved["t"], saved["status"]), (46.5, "fixed"))
            self.assertEqual(len(film["events"]), 3)
            self.assertTrue(all(e["status"] == "draft" and e["player_number"] is None
                                for e in film["events"]))

    def test_repeated_automatic_replacement_removes_old_events_without_accumulating(self):
        self._rerun_with_plays()
        corrected = deepcopy(DRAFT_PLAYS)
        corrected["events"] = [
            {**DRAFT["events"][0], "shot_type": "fg3", "team": "opponent"},
            play("dreb", 80, "valley", confidence=0.35),
            play("to", 85, "opponent"),
            play("stl", 85, "valley", hidden=True),
            play("ast", 12.5, "opponent", hidden=True),
        ]
        for _ in range(3):
            self.assertEqual(self._load_result(corrected), 5)
            film = self._assert_totals_across_views({
                "valley": {"pts": 0, "fga": 0, "oreb": 0, "dreb": 1, "reb": 1, "to": 0},
                "opponent": {"pts": 3, "fga": 1, "oreb": 0, "dreb": 0, "reb": 0, "to": 1},
            })
            self.assertEqual(len(film["events"]), 1)
            self.assertEqual(len(film["plays"]), 2)
            self.assertTrue(all(p["status"] == "draft" for p in film["plays"]))
            db = self.Session()
            self.assertEqual(db.query(ShotEvent).count(), 5)
            db.close()

    def test_failed_or_skipped_rerun_removes_previous_automatic_play_totals(self):
        for info in (None, {"error": "failed"}):
            with self.subTest(info=info):
                self._rerun_with_plays()
                self._load_result({**DRAFT, "possession": info})
                film = self._assert_totals_across_views({
                    team: {"reb": None, "oreb": None, "dreb": None, "to": None}
                    for team in ("valley", "opponent")
                })
                self.assertFalse(film["has_plays"])
                self.assertEqual(film["plays"], [])
                self._load_result({**DRAFT, "possession": {"method": "v2"}})
                self._assert_totals_across_views({
                    team: {"reb": 0, "oreb": 0, "dreb": 0, "to": 0}
                    for team in ("valley", "opponent")
                })

    def test_shot_changes_do_not_rewrite_independent_rebound_evidence(self):
        result = deepcopy(DRAFT_PLAYS)
        result["events"][3]["detail"]["shot_t"] = 44.0
        self._load_result(result)
        before = self.client.get(self.base).json()
        shot = next(e for e in before["events"] if e["t"] == 44.0)
        self.client.patch(f"{self.base}/{shot['id']}",
                          json={"made": True, "team": "opponent", "shot_type": "fg3"})
        after = self._assert_totals_across_views({
            "valley": {"pts": 2, "oreb": 1, "dreb": 0},
            "opponent": {"pts": 3, "oreb": 0, "dreb": 1},
        })
        self.assertEqual(after["plays"], before["plays"])

    def test_coincident_events_are_independent_and_cross_upload_refs_are_rejected(self):
        result = deepcopy(DRAFT_PLAYS)
        result["events"][3]["t"] = 12.5
        result["events"][4]["t"] = 12.5
        for _ in range(2):
            self.assertEqual(self._load_result(result), len(result["events"]))
        before = self.client.get(self.base).json()
        self.assertEqual(len([e for e in before["events"] + before["plays"] if e["t"] == 12.5]), 3)
        db = self.Session()
        other = GameUpload(team_id=self.team_id, title="Other", storage_url="r2://aim-film/other.mp4",
                           status="ready", detection_status="done", events_status="done")
        db.add(other)
        db.flush()
        shot_events.load_events(db, other, DRAFT_PLAYS)
        db.flush()
        foreign = db.query(ShotEvent).filter(ShotEvent.upload_id == other.id, ShotEvent.type == "dreb").one()
        foreign_id = foreign.id
        db.commit()
        db.close()
        for event_id in (foreign_id, 999999):
            self.assertEqual(self.client.patch(f"{self.base}/{event_id}", json={"team": "valley"}).status_code,
                             404)
        self.assertEqual(self.client.get(self.base).json(), before)

    def test_plays_in_box_score_and_list(self):
        self._rerun_with_plays()
        body = self.client.get(self.base).json()
        self.assertTrue(body["has_plays"])
        self.assertEqual([e["t"] for e in body["events"]], [12.5, 30.0, 44.0])  # shots only
        self.assertEqual([(p["type"], p["team"]) for p in body["plays"]],
                         [("dreb", "opponent"), ("oreb", "valley"), ("to", "valley"), ("to", "opponent")])
        self.assertEqual(set(body["plays"][0]), {"id", "type", "t", "team", "confidence", "status"})
        v, o = body["box_score"]["valley"], body["box_score"]["opponent"]
        self.assertEqual((v["oreb"], v["dreb"], v["reb"], v["to"]), (1, 0, 1, 1))
        self.assertEqual((o["oreb"], o["dreb"], o["reb"], o["to"]), (0, 1, 1, 1))

    def test_steals_and_assists_never_shown_or_editable(self):
        self._rerun_with_plays()
        body = self.client.get(self.base).json()
        self.assertFalse(any(p["type"] in ("stl", "ast") for p in body["plays"] + body["events"]))
        db = self.Session()
        hidden = db.query(ShotEvent).filter(ShotEvent.type.in_(("stl", "ast"))).all()
        self.assertEqual(len(hidden), 2)  # stored for training
        hidden_id = hidden[0].id
        db.close()
        self.assertEqual(self.client.patch(f"{self.base}/{hidden_id}", json={"status": "confirmed"}).status_code, 404)

    def test_flip_rebound_team_switches_kind(self):
        self._rerun_with_plays()
        plays = self.client.get(self.base).json()["plays"]
        dreb = next(p for p in plays if p["type"] == "dreb")
        got = self.client.patch(f"{self.base}/{dreb['id']}", json={"team": "valley"}).json()
        self.assertEqual((got["type"], got["team"], got["status"]), ("oreb", "valley", "fixed"))
        to = next(p for p in plays if p["type"] == "to" and p["team"] == "valley")
        got = self.client.patch(f"{self.base}/{to['id']}", json={"team": "opponent"}).json()
        self.assertEqual((got["type"], got["team"]), ("to", "opponent"))
        self.assertEqual(self.client.patch(f"{self.base}/{to['id']}", json={"made": True}).status_code, 422)
        self.assertEqual(self.client.patch(f"{self.base}/{to['id']}", json={"status": "deleted"}).json()["status"], "deleted")
        box = self.client.get(self.base).json()["box_score"]
        self.assertEqual((box["valley"]["oreb"], box["valley"]["to"], box["opponent"]["to"]), (2, 0, 1))

    def test_add_play(self):
        r = self.client.post(f"/api/v1/teams/{self.team_id}/film/{self.upload_id}/plays",
                             json={"t": 80, "team": "opponent", "type": "to"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.json()["type"], r.json()["status"], r.json()["confidence"]), ("to", "fixed", 1.0))
        body = self.client.get(self.base).json()
        self.assertTrue(body["has_plays"])  # a coach-added play counts as having them
        self.assertEqual(body["box_score"]["opponent"]["to"], 1)
        bad = self.client.post(f"/api/v1/teams/{self.team_id}/film/{self.upload_id}/plays",
                               json={"t": 80, "team": "opponent", "type": "stl"})
        self.assertEqual(bad.status_code, 422)

    def test_rerun_adds_plays_and_keeps_reviewed_shots(self):
        eid = self.client.get(self.base).json()["events"][0]["id"]
        self.client.patch(f"{self.base}/{eid}", json={"made": False})
        self.assertEqual(self._rerun_with_plays(), 6)  # 4 plays and 2 hidden; the 3 shots stay
        body = self.client.get(self.base).json()
        self.assertEqual(len(body["events"]), 3)
        self.assertEqual(next(e for e in body["events"] if e["id"] == eid)["made"], False)
        self.assertEqual(len(body["plays"]), 4)
        # A second rerun with untouched plays redrafts them; once one is reviewed they're kept too.
        self.assertEqual(self._rerun_with_plays(), 6)
        pid = self.client.get(self.base).json()["plays"][0]["id"]
        self.client.patch(f"{self.base}/{pid}", json={"status": "confirmed"})
        self.assertEqual(self._rerun_with_plays(), 0)

    def test_rerun_after_swap_flips_new_plays(self):
        self.client.post(f"{self.base}/swap-teams")
        self._rerun_with_plays()
        body = self.client.get(self.base).json()
        self.assertEqual(body["events"][0]["team"], "opponent")  # swapped shot kept
        self.assertEqual(next(p for p in body["plays"] if p["type"] == "dreb")["team"], "valley")
        self.assertFalse(body["teams_guessed"])

    def test_swap_teams_flips_plays_but_keeps_kind(self):
        self._rerun_with_plays()
        body = self.client.post(f"{self.base}/swap-teams").json()
        self.assertEqual([(p["type"], p["team"]) for p in body["plays"]],
                         [("dreb", "valley"), ("oreb", "opponent"), ("to", "opponent"), ("to", "valley")])

    def test_swap_before_shots_exist_orients_later_drafts(self):
        db = self.Session()
        db.query(ShotEvent).delete()
        db.commit()
        db.close()
        self.client.post(f"{self.base}/swap-teams")
        self._rerun_with_plays()
        self._rerun_with_plays()
        body = self.client.get(self.base).json()
        self.assertEqual(body["events"][0]["team"], "opponent")
        self.assertEqual(body["plays"][0]["team"], "valley")
        self.assertFalse(body["teams_guessed"])

    def test_play_validation_rejects_null_extra_and_nonfinite_values(self):
        self._rerun_with_plays()
        pid = self.client.get(self.base).json()["plays"][0]["id"]
        for patch in ({"team": None}, {"t": None}, {"status": None}, {"t": "Infinity"},
                      {"t": "NaN"}, {"t": -1}, {"type": "stl"}, {"made": False}):
            with self.subTest(patch=patch):
                self.assertEqual(self.client.patch(f"{self.base}/{pid}", json=patch).status_code, 422)
        for values in ({"t": "Infinity"}, {"t": "NaN"}, {"t": -1}, {"made": True}):
            with self.subTest(values=values):
                response = self.client.post(f"/api/v1/teams/{self.team_id}/film/{self.upload_id}/plays",
                                            json={"type": "to", "team": "valley", "t": 10, **values})
                self.assertEqual(response.status_code, 422)

    def test_play_corrections_survive_reload_and_rerun(self):
        self._rerun_with_plays()
        play = self.client.get(self.base).json()["plays"][0]
        path = f"{self.base}/{play['id']}"
        self.client.patch(path, json={"team": "valley", "t": 46.5})
        self.client.patch(path, json={"status": "deleted"})
        self._rerun_with_plays()
        saved = next(p for p in self.client.get(self.base).json()["plays"] if p["id"] == play["id"])
        self.assertEqual((saved["type"], saved["team"], saved["t"], saved["status"]),
                         ("oreb", "valley", 46.5, "deleted"))
        self.client.patch(path, json={"status": "fixed"})
        self.assertEqual(self.client.get(self.base).json()["box_score"]["valley"]["oreb"], 2)
        season = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        scouting = self.client.get(f"/api/v1/teams/{self.team_id}/insights").json()
        self.assertEqual(season["totals"]["valley"]["oreb"], 2)
        self.assertEqual(scouting["teams"]["valley"]["oreb"], 2)
        db = self.Session()
        row = db.get(ShotEvent, play["id"])
        self.assertEqual((row.original["type"], row.original["team"], row.updated_by_id),
                         ("dreb", "opponent", self.user_id))
        db.close()

    def test_missing_failed_and_empty_play_data_are_distinct(self):
        for info, expected in ((None, None), ({"error": "failed"}, None), ({"method": "v2"}, 0)):
            with self.subTest(info=info):
                db = self.Session()
                upload = db.get(GameUpload, self.upload_id)
                shot_events.load_events(db, upload, {**DRAFT, "possession": info})
                db.commit()
                db.close()
                body = self.client.get(self.base).json()
                self.assertEqual(body["has_plays"], expected is not None)
                self.assertEqual(body["box_score"]["valley"]["to"], expected)
                season = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
                scouting = self.client.get(f"/api/v1/teams/{self.team_id}/insights").json()
                self.assertEqual(season["totals"]["valley"]["to"], expected)
                self.assertEqual(scouting["teams"]["valley"]["to"], expected)

    def test_deleted_manual_play_stays_known_across_views(self):
        created = self.client.post(f"/api/v1/teams/{self.team_id}/film/{self.upload_id}/plays",
                                   json={"t": 50, "type": "to", "team": "valley"}).json()
        self.client.patch(f"{self.base}/{created['id']}", json={"status": "deleted"})
        film = self.client.get(self.base).json()
        season = self.client.get(f"/api/v1/teams/{self.team_id}/season").json()
        scouting = self.client.get(f"/api/v1/teams/{self.team_id}/insights").json()
        self.assertEqual(film["box_score"]["valley"]["to"], 0)
        self.assertEqual(season["totals"]["valley"]["to"], 0)
        self.assertEqual(scouting["teams"]["valley"]["to"], 0)
        self.assertEqual(scouting["teams"]["valley"]["play_games"], 1)
        db = self.Session()
        box = chat._box(db, db.get(GameUpload, self.upload_id))
        self.assertEqual(box["valley"]["to"], 0)
        db.close()

    def test_pending_until_events_done(self):
        db = self.Session()
        db.get(GameUpload, self.upload_id).events_status = "running"
        db.commit()
        db.close()
        self.assertEqual(self.client.get(self.base).json()["status"], "pending")


if __name__ == "__main__":
    unittest.main()
