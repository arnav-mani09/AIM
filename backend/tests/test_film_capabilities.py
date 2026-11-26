import os
import unittest
from types import SimpleNamespace
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
from app.api.v1.routes import film
from app.core.security import create_access_token
from app.models import Base, GameUpload, Team, TeamMembership, User


class FilmCapabilitiesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            member = User(email="member@example.com", hashed_password="unused")
            outsider = User(email="outsider@example.com", hashed_password="unused")
            team = Team(name="Film team")
            other_team = Team(name="Other team")
            db.add_all([member, outsider, team, other_team])
            db.flush()
            db.add(TeamMembership(team_id=team.id, user_id=member.id, role="member"))
            db.commit()
            self.url = f"/api/v1/teams/{team.id}/film/capabilities"
            self.other_url = f"/api/v1/teams/{other_team.id}/film/capabilities"
            self.headers = {"Authorization": f"Bearer {create_access_token(str(member.id))}"}
            self.outsider_headers = {"Authorization": f"Bearer {create_access_token(str(outsider.id))}"}

        def get_db():
            with self.Session() as db:
                yield db

        app = FastAPI()
        app.include_router(film.router, prefix="/api/v1")
        app.dependency_overrides[deps.get_db_session] = get_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        settings_patch = patch.object(film, "get_settings")
        self.settings = settings_patch.start()
        self.addCleanup(settings_patch.stop)
        self.settings.return_value = SimpleNamespace(
            film_import_enabled=False,
            film_import_allowed_hosts="private-cdn.example",
            r2_secret_access_key="never-emit-this-secret",
            database_url="never-emit-this-database-url",
        )
        network_patch = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        network_patch.start()
        self.addCleanup(network_patch.stop)
        modal_patch = patch.object(film, "launch_import", side_effect=AssertionError("Dispatch forbidden"))
        modal_patch.start()
        self.addCleanup(modal_patch.stop)

    def test_disabled_import_keeps_file_guidance_and_limits(self):
        response = self.client.get(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["link_import_enabled"])
        self.assertEqual(body["link_import_status"], "disabled")
        self.assertIn("upload", body["link_import_message"])
        self.assertEqual(body["max_size_bytes"], 5 * 1024**3)
        self.assertEqual(body["content_types"], ["video/mp4", "video/quicktime"])

    def test_enabled_without_provider_is_unconfigured(self):
        self.settings.return_value.film_import_enabled = True
        self.settings.return_value.film_import_allowed_hosts = "  "
        response = self.client.get(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["link_import_status"], "unconfigured")
        self.assertFalse(response.json()["link_import_enabled"])

    def test_configured_is_not_a_worker_or_provider_verification(self):
        self.settings.return_value.film_import_enabled = True
        response = self.client.get(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["link_import_enabled"])
        self.assertEqual(body["link_import_status"], "configured")
        self.assertIn("server validates each download", body["link_import_message"])
        self.assertEqual(set(body), {
            "link_import_enabled", "link_import_status", "link_import_message", "max_size_bytes", "content_types",
        })
        for secret in ("private-cdn.example", "never-emit-this-secret", "never-emit-this-database-url"):
            self.assertNotIn(secret, response.text)
        with self.Session() as db:
            self.assertEqual(db.query(GameUpload).count(), 0)

    def test_authentication_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_nonmember_cannot_read_capabilities(self):
        self.assertEqual(self.client.get(self.url, headers=self.outsider_headers).status_code, 403)

    def test_membership_is_scoped_to_requested_team(self):
        self.assertEqual(self.client.get(self.other_url, headers=self.headers).status_code, 403)


if __name__ == "__main__":
    unittest.main()
