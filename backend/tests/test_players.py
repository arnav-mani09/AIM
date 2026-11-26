"""Offline roster API tests: python -m unittest tests.test_players -v."""

import os
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1.routes import players, teams
from app.core.security import create_access_token
from app.models import Base, Game, Player, Possession, Team, TeamMembership, User


class PlayersTest(unittest.TestCase):
    def setUp(self):
        network_guard = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        network_guard.start()
        self.addCleanup(network_guard.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            users = {
                role: User(email=f"{role}@example.com", hashed_password="unused")
                for role in ("owner", "coach", "admin", "member", "outsider")
            }
            db.add_all(users.values())
            db.flush()
            team = Team(name="Roster team", created_by_id=users["owner"].id)
            other = Team(name="Other team", created_by_id=users["outsider"].id)
            db.add_all([team, other])
            db.flush()
            for role in ("owner", "coach", "admin", "member"):
                db.add(TeamMembership(
                    team_id=team.id, user_id=users[role].id, role="member" if role == "owner" else role,
                ))
            db.add(TeamMembership(team_id=other.id, user_id=users["coach"].id, role="coach"))
            first = Player(team_id=team.id, name="Zoe", jersey_number="07")
            second = Player(team_id=team.id, name="Alex", jersey_number="12")
            foreign = Player(team_id=other.id, name="Foreign", jersey_number="23")
            legacy = Player(name="Legacy", jersey_number="99")
            game = Game(matchup="Roster game", scheduled_at=datetime(2026, 1, 1), home_team_id=team.id)
            db.add_all([first, second, foreign, legacy, game])
            db.flush()
            possession = Possession(game_id=game.id, player_id=first.id, label="History", source="manual")
            db.add(possession)
            db.commit()
            self.team_id, self.other_id = team.id, other.id
            self.first_id, self.second_id = first.id, second.id
            self.foreign_id, self.legacy_id = foreign.id, legacy.id
            self.possession_id = possession.id
            self.tokens = {role: create_access_token(str(user.id)) for role, user in users.items()}

        def get_db():
            with self.Session() as db:
                yield db

        self.app = FastAPI()
        self.app.include_router(players.router, prefix="/api/v1")
        self.app.include_router(teams.router, prefix="/api/v1")
        self.app.dependency_overrides[deps.get_db_session] = get_db
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.url = f"/api/v1/teams/{self.team_id}/players"

    def headers(self, role="coach"):
        return {"Authorization": f"Bearer {self.tokens[role]}"}

    def test_team_membership_exposes_authoritative_roster_permission(self):
        for role, expected in (("owner", True), ("coach", True), ("admin", True), ("member", False)):
            with self.subTest(role=role):
                response = self.client.get("/api/v1/teams", headers=self.headers(role))
                self.assertEqual(response.status_code, 200)
                membership = next(row for row in response.json() if row["team"]["id"] == self.team_id)
                self.assertEqual(membership["can_manage_roster"], expected)
                if role == "owner":
                    self.assertEqual(membership["role"], "member")

    def test_create_team_returns_roster_permission_without_exposing_ownership_fields(self):
        response = self.client.post("/api/v1/teams", json={"name": "New roster team"}, headers=self.headers("member"))
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["can_manage_roster"])
        self.assertNotIn("created_by_id", response.json()["team"])
        self.assertNotIn("user_id", response.json())

    def test_null_owner_never_grants_roster_permission_to_a_member(self):
        with self.Session() as db:
            db.get(Team, self.team_id).created_by_id = None
            db.commit()
        membership = next(row for row in self.client.get("/api/v1/teams", headers=self.headers("owner")).json()
                          if row["team"]["id"] == self.team_id)
        self.assertFalse(membership["can_manage_roster"])
        response = self.client.patch(f"{self.url}/{self.first_id}", json={"name": "Denied", "jersey_number": "07"},
                                     headers=self.headers("owner"))
        self.assertEqual(response.status_code, 403)

    def test_member_reads_unchanged_sorted_scoped_list(self):
        response = self.client.get(self.url, headers=self.headers("member"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [
            {"id": self.second_id, "name": "Alex", "jersey_number": "12", "team_id": self.team_id},
            {"id": self.first_id, "name": "Zoe", "jersey_number": "07", "team_id": self.team_id},
        ])

    def test_members_and_nonmembers_cannot_write(self):
        payload = {"name": "Changed", "jersey_number": "33"}
        for role in ("member", "outsider"):
            with self.subTest(role=role):
                self.assertEqual(self.client.post(self.url, json=payload, headers=self.headers(role)).status_code, 403)
                self.assertEqual(self.client.patch(
                    f"{self.url}/{self.first_id}", json=payload, headers=self.headers(role),
                ).status_code, 403)
        self.assertEqual(self.client.get(self.url, headers=self.headers("outsider")).status_code, 403)
        with self.Session() as db:
            self.assertEqual(db.query(Player).count(), 4)
            self.assertEqual(db.get(Player, self.first_id).name, "Zoe")

    def test_unauthenticated_requests_rejected(self):
        payload = {"name": "Changed", "jersey_number": "33"}
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, json=payload).status_code, 401)
        self.assertEqual(self.client.patch(f"{self.url}/{self.first_id}", json=payload).status_code, 401)

    def test_owner_coach_and_admin_create_and_edit(self):
        for index, role in enumerate(("owner", "coach", "admin")):
            with self.subTest(role=role):
                response = self.client.post(
                    self.url, json={"name": f"  New {role}  ", "jersey_number": f"  {index}  "},
                    headers=self.headers(role),
                )
                self.assertEqual(response.status_code, 201, response.text)
                player_id = response.json()["id"]
                self.assertEqual(response.json(), {
                    "id": player_id, "name": f"New {role}", "jersey_number": str(index), "team_id": self.team_id,
                })
                response = self.client.patch(
                    f"{self.url}/{player_id}",
                    json={"name": f"  Edited {role}  ", "jersey_number": f"  0{index}  "},
                    headers=self.headers(role),
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), {
                    "id": player_id, "name": f"Edited {role}", "jersey_number": f"0{index}", "team_id": self.team_id,
                })

    def test_exact_post_is_idempotent_after_trimming(self):
        for payload in (
            {"name": "Zoe", "jersey_number": "07"},
            {"name": " Zoe ", "jersey_number": " 07 "},
        ):
            response = self.client.post(self.url, json=payload, headers=self.headers())
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["id"], self.first_id)
        with self.Session() as db:
            self.assertEqual(db.query(Player).count(), 4)

    def test_same_team_jersey_conflicts_do_not_mutate(self):
        payload = {"name": "Different", "jersey_number": " 12 "}
        created = self.client.post(self.url, json=payload, headers=self.headers())
        edited = self.client.patch(f"{self.url}/{self.first_id}", json=payload, headers=self.headers())
        duplicate = self.client.patch(
            f"{self.url}/{self.first_id}", json={"name": "Alex", "jersey_number": "12"}, headers=self.headers(),
        )
        self.assertEqual(created.status_code, 409)
        self.assertEqual(edited.status_code, 409)
        self.assertEqual(duplicate.status_code, 409)
        with self.Session() as db:
            self.assertEqual(db.query(Player).count(), 4)
            self.assertEqual(db.get(Player, self.first_id).name, "Zoe")
            self.assertEqual(db.get(Player, self.first_id).jersey_number, "07")

    def test_jersey_on_other_team_is_allowed(self):
        response = self.client.post(
            self.url, json={"name": "Foreign", "jersey_number": "23"}, headers=self.headers(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()["id"], self.foreign_id)
        response = self.client.patch(
            f"{self.url}/{self.first_id}", json={"name": "Legacy", "jersey_number": "99"}, headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200)

    def test_edit_in_place_preserves_history_and_allows_unchanged_jersey(self):
        payload = {"name": "Renamed", "jersey_number": "07"}
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.client.patch(f"{self.url}/{self.first_id}", json=payload, headers=self.headers())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["id"], self.first_id)
        with self.Session() as db:
            possession = db.get(Possession, self.possession_id)
            self.assertEqual(possession.player_id, self.first_id)
            self.assertEqual(possession.player.name, "Renamed")
            self.assertEqual(possession.source, "manual")
            self.assertEqual(db.query(Possession).count(), 1)
            self.assertEqual(db.query(Player).count(), 4)

    def test_cross_team_unscoped_and_missing_player_ids_are_not_found(self):
        for player_id in (self.foreign_id, self.legacy_id, 99999):
            with self.subTest(player_id=player_id):
                response = self.client.patch(
                    f"{self.url}/{player_id}", json={"name": "Nope", "jersey_number": "44"},
                    headers=self.headers(),
                )
                self.assertEqual(response.status_code, 404)
        with self.Session() as db:
            self.assertEqual(db.get(Player, self.foreign_id).name, "Foreign")
            self.assertEqual(db.get(Player, self.legacy_id).name, "Legacy")

    def test_invalid_create_and_full_edit_bodies_rejected(self):
        invalid = [
            {}, {"name": "Only name"}, {"jersey_number": "1"},
            {"name": "", "jersey_number": "1"}, {"name": " \t\n", "jersey_number": "1"},
            {"name": "Name", "jersey_number": ""}, {"name": "Name", "jersey_number": " \t\n"},
            {"name": "x" * 101, "jersey_number": "1"}, {"name": "Name", "jersey_number": "1" * 11},
            {"name": None, "jersey_number": "1"}, {"name": "Name", "jersey_number": None},
            {"name": 123, "jersey_number": "1"}, {"name": "Name", "jersey_number": 123},
        ]
        for payload in invalid:
            for method, url in (("post", self.url), ("patch", f"{self.url}/{self.first_id}")):
                with self.subTest(payload=payload, method=method):
                    response = getattr(self.client, method)(url, json=payload, headers=self.headers())
                    self.assertEqual(response.status_code, 422, response.text)
        with self.Session() as db:
            self.assertEqual(db.query(Player).count(), 4)
            self.assertEqual(db.get(Player, self.first_id).name, "Zoe")

    def test_length_boundaries_apply_after_trimming(self):
        payload = {"name": "  " + "x" * 100 + "  ", "jersey_number": "  1234567890  "}
        created = self.client.post(self.url, json=payload, headers=self.headers())
        self.assertEqual(created.status_code, 201, created.text)
        edited = self.client.patch(
            f"{self.url}/{created.json()['id']}", json=payload, headers=self.headers(),
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["name"], "x" * 100)
        self.assertEqual(edited.json()["jersey_number"], "1234567890")

    def test_no_delete_endpoint(self):
        response = self.client.delete(f"{self.url}/{self.first_id}", headers=self.headers())
        self.assertEqual(response.status_code, 405)
        with self.Session() as db:
            self.assertIsNotNone(db.get(Player, self.first_id))
            self.assertIsNotNone(db.get(Possession, self.possession_id))


if __name__ == "__main__":
    unittest.main()
