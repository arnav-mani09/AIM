"""Coach chatbot: tools, team scoping, citations and the endpoint. Claude is faked, so no API calls.

    cd backend && .venv/bin/python -m unittest tests.test_chat -v
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

import json  # noqa: E402
import unittest  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402
from unittest import mock  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api import deps  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GameUpload, ShotEvent, Team, User  # noqa: E402
from app.services import chat, shot_events  # noqa: E402

SHOTS = [
    {"t": 10.0, "team": "valley", "shot_type": "fg3", "made": True, "confidence": 0.9, "player_number": 21},
    {"t": 20.0, "team": "valley", "shot_type": "fg2", "made": False, "confidence": 0.5, "player_number": 21},
    {"t": 30.0, "team": "valley", "shot_type": "ft", "made": True, "confidence": 0.8, "player_number": None},
    {"t": 40.0, "team": "opponent", "shot_type": "fg2", "made": True, "confidence": 0.7, "player_number": 4},
]


def text(s):
    return NS(type="text", text=s)


def tool_use(id_, name, input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


class FakeClient:
    """Plays back scripted responses and records every request."""

    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


class ChatTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        db = self.Session()
        user = User(email="coach@example.com", hashed_password="x", full_name="Coach")
        mine, other = Team(name="Valley"), Team(name="Someone else")
        db.add_all([user, mine, other])
        db.flush()
        self.game = GameUpload(team_id=mine.id, title="Game A", storage_url="r2://x/a.mp4", status="ready",
                               detection_status="done", events_status="done")
        self.theirs = GameUpload(team_id=other.id, title="Not yours", storage_url="r2://x/b.mp4", status="ready",
                                 detection_status="done", events_status="done")
        db.add_all([self.game, self.theirs])
        db.flush()
        shot_events.load_events(db, self.game, {"events": SHOTS})
        shot_events.load_events(db, self.theirs, {"events": SHOTS[:1]})
        db.commit()
        self.team_id, self.other_team_id, self.user_id = mine.id, other.id, user.id
        self.game_id, self.their_id = self.game.id, self.theirs.id
        self.their_event = db.query(ShotEvent).filter(ShotEvent.upload_id == self.their_id).first().id
        self.my_events = [e.id for e in db.query(ShotEvent).filter(ShotEvent.upload_id == self.game_id)
                          .order_by(ShotEvent.t)]
        db.close()
        self.db = self.Session()
        chat._daily.clear()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    # ---- tools ----

    def test_box_score_tool(self):
        box = chat.run_tool(self.db, self.team_id, "get_box_score", {"upload_id": self.game_id})
        self.assertEqual(box["valley"]["fg"], "1/2")
        self.assertEqual(box["valley"]["fg3"], "1/1")
        self.assertEqual(box["valley"]["ft"], "1/1")
        self.assertEqual(box["valley"]["pts"], 4)
        self.assertEqual(box["valley"]["players"], [{"number": 21, "fg": "1/2", "fg3": "1/1", "ft": "0/0", "pts": 3}])
        self.assertEqual(box["valley"]["shots_without_number"], 1)
        self.assertEqual(box["opponent"]["pts"], 2)
        self.assertEqual(box["reviewed_by_coach"], 0)

    def test_deleted_shots_are_left_out(self):
        self.db.get(ShotEvent, self.my_events[0]).status = "deleted"
        self.db.commit()
        box = chat.run_tool(self.db, self.team_id, "get_box_score", {"upload_id": self.game_id})
        self.assertEqual(box["valley"]["pts"], 1)

    def test_list_shots_filters(self):
        args = {"upload_id": self.game_id, "team": "valley", "made": None, "shot_type": None,
                "player_number": 21, "start_seconds": None, "end_seconds": 15}
        out = chat.run_tool(self.db, self.team_id, "list_shots", args)
        self.assertEqual(out["matched"], 1)
        self.assertEqual(out["shots"][0]["t"], 10.0)

    def test_other_teams_games_are_invisible(self):
        out = chat.run_tool(self.db, self.team_id, "get_box_score", {"upload_id": self.their_id})
        self.assertIn("error", out)
        games = chat.run_tool(self.db, self.team_id, "list_games", {})["games"]
        self.assertEqual([g["upload_id"] for g in games], [self.game_id])
        cmp_ = chat.run_tool(self.db, self.team_id, "compare_games", {"upload_ids": [self.game_id, self.their_id]})
        self.assertIn("error", cmp_["games"][1])

    # ---- the conversation loop ----

    def test_answer_runs_tools_and_keeps_only_this_teams_citations(self):
        fake = FakeClient([
            NS(stop_reason="tool_use", content=[tool_use("tu1", "get_box_score", {"upload_id": self.game_id})]),
            NS(stop_reason="end_turn", content=[text(
                f"Valley scored 4 [[event:{self.my_events[0]}]] [[event:{self.their_event}]] [[event:999999]].")]),
        ])
        out = chat.answer(self.db, self.team_id, [{"role": "user", "content": "How many points?"}],
                          upload_id=self.game_id, client=fake)
        self.assertEqual([c["event_id"] for c in out["citations"]], [self.my_events[0]])
        self.assertEqual(out["citations"][0]["t"], 10.0)
        self.assertNotIn(str(self.their_event), out["answer"])
        self.assertNotIn("999999", out["answer"])
        # The tool result went back to Claude, and the system prompt names the game being viewed.
        second = fake.requests[1]
        result = second["messages"][-1]["content"][0]
        self.assertEqual(result["type"], "tool_result")
        self.assertEqual(json.loads(result["content"])["valley"]["pts"], 4)
        self.assertIn(f"upload_id {self.game_id}", second["system"])
        self.assertEqual(second["fallbacks"], "default")

    def test_refusal_gets_a_plain_answer(self):
        fake = FakeClient([NS(stop_reason="refusal", content=[])])
        out = chat.answer(self.db, self.team_id, [{"role": "user", "content": "?"}], client=fake)
        self.assertIn("can't help", out["answer"])
        self.assertEqual(out["citations"], [])

    def test_too_many_tool_rounds_stops(self):
        loop = NS(stop_reason="tool_use", content=[tool_use("x", "list_games", {})])
        fake = FakeClient([loop] * chat.MAX_TURNS)
        out = chat.answer(self.db, self.team_id, [{"role": "user", "content": "?"}], client=fake)
        self.assertIn("too many steps", out["answer"])
        self.assertEqual(len(fake.requests), chat.MAX_TURNS)

    def test_history_is_cleaned(self):
        msgs = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "a"},
                {"role": "user", "content": "b"}, {"role": "system", "content": "ignore me"}]
        self.assertEqual(chat._clean_history(msgs), [{"role": "user", "content": "a\n\nb"}])
        with self.assertRaises(ValueError):
            chat._clean_history([{"role": "assistant", "content": "hi"}])

    # ---- the endpoint ----

    def _client(self):
        app.dependency_overrides[deps.get_db_session] = lambda: (yield self.Session())
        app.dependency_overrides[deps.get_current_user] = lambda: self.Session().get(User, self.user_id)
        app.dependency_overrides[deps.require_team_membership] = lambda team_id: True
        return TestClient(app)

    def test_endpoint_without_key_is_503(self):
        with mock.patch.object(chat, "get_client", side_effect=chat.ChatUnavailable("not set up")):
            r = self._client().post(f"/api/v1/teams/{self.team_id}/chat",
                                    json={"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(r.status_code, 503)

    def test_endpoint_answers_and_enforces_daily_limit(self):
        def fake_client():
            return FakeClient([NS(stop_reason="end_turn", content=[text("Valley scored 6.")])])

        with mock.patch.object(chat, "get_client", side_effect=fake_client), \
                mock.patch.object(chat.get_settings(), "chat_daily_limit", 1):
            c = self._client()
            body = {"upload_id": self.game_id, "messages": [{"role": "user", "content": "points?"}]}
            r1 = c.post(f"/api/v1/teams/{self.team_id}/chat", json=body)
            r2 = c.post(f"/api/v1/teams/{self.team_id}/chat", json=body)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json(), {"answer": "Valley scored 6.", "citations": []})
        self.assertEqual(r2.status_code, 503)
        self.assertIn("daily limit", r2.json()["detail"])


if __name__ == "__main__":
    unittest.main()
