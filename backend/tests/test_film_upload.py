import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1.routes import film
from app.models import Base, GameUpload, Team


class FilmUploadCompletionTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.db.close)
        team = Team(name="Valley")
        self.db.add(team)
        self.db.flush()
        self.upload = GameUpload(
            team_id=team.id, title="Game", storage_url="r2://aim-film/game.mp4",
            storage_upload_id="multipart-1", size_bytes=film.FILM_PART_BYTES + 10, status="uploading",
        )
        self.db.add(self.upload)
        self.db.commit()
        app = FastAPI()
        app.include_router(film.router, prefix="/api/v1")
        app.dependency_overrides[deps.get_db_session] = lambda: self.db
        app.dependency_overrides[deps.require_team_membership] = lambda: object()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = f"/api/v1/teams/{team.id}/film/{self.upload.id}/upload/complete"
        self.parts = self.mock(patch.object(film.storage, "list_parts", return_value=[
            {"part_number": 1, "size": film.FILM_PART_BYTES, "etag": "first"},
            {"part_number": 2, "size": 10, "etag": "last"},
        ]))
        self.complete = self.mock(patch.object(film.storage, "complete_multipart_upload"))
        self.head = self.mock(patch.object(film.storage, "object_size", return_value=self.upload.size_bytes))
        self.process = self.mock(patch.object(film, "_process_upload_async"))
        self.mock(patch("socket.socket.connect", side_effect=AssertionError("Live network forbidden")))

    def mock(self, patcher):
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def missing_multipart(self):
        return ClientError({"Error": {"Code": "NoSuchUpload", "Message": "missing"}}, "ListParts")

    def test_complete_uses_storage_record_and_starts_processing_once(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "processing")
        self.complete.assert_called_once_with("game.mp4", "multipart-1", self.parts.return_value)
        self.process.assert_called_once_with(self.upload.id)
        self.assertIsNone(self.upload.storage_upload_id)

    def test_retry_after_lost_response_is_idempotent(self):
        self.assertEqual(self.client.post(self.url).status_code, 200)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        self.parts.assert_called_once()
        self.complete.assert_called_once()
        self.process.assert_called_once()

    def test_finished_upload_retries_preserve_existing_status(self):
        for status in ("ready", "error"):
            with self.subTest(status=status):
                self.upload.status = status
                self.upload.storage_upload_id = None
                self.db.commit()
                response = self.client.post(self.url)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["status"], status)
        self.parts.assert_not_called()
        self.process.assert_not_called()

    def test_recovers_storage_completion_before_database_commit(self):
        self.parts.side_effect = self.missing_multipart()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        self.head.assert_called_once_with("game.mp4")
        self.complete.assert_not_called()
        self.process.assert_called_once_with(self.upload.id)

    def test_recovers_ambiguous_storage_completion_response(self):
        self.complete.side_effect = self.missing_multipart()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        self.head.assert_called_once_with("game.mp4")
        self.process.assert_called_once()

    def test_missing_multipart_is_not_success_without_matching_object(self):
        self.parts.side_effect = self.missing_multipart()
        self.head.return_value = self.upload.size_bytes - 1
        self.assertEqual(self.client.post(self.url).status_code, 409)
        self.assertEqual(self.upload.status, "uploading")
        self.process.assert_not_called()

    def test_missing_object_keeps_upload_retryable(self):
        self.parts.side_effect = self.missing_multipart()
        self.head.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        self.assertEqual(self.client.post(self.url).status_code, 502)
        self.assertEqual(self.upload.status, "uploading")
        self.process.assert_not_called()

    def test_incomplete_parts_never_complete(self):
        self.parts.return_value = self.parts.return_value[:1]
        self.assertEqual(self.client.post(self.url).status_code, 409)
        self.complete.assert_not_called()
        self.head.assert_not_called()

    def test_part_numbers_and_each_size_must_match_upload_layout(self):
        invalid = (
            [(1, film.FILM_PART_BYTES), (1, 10)],
            [(1, film.FILM_PART_BYTES), (3, 10)],
            [(1, 10), (2, film.FILM_PART_BYTES)],
            [(1, film.FILM_PART_BYTES - 1), (2, 11)],
        )
        for parts in invalid:
            with self.subTest(parts=parts):
                self.parts.return_value = [
                    {"part_number": number, "size": size, "etag": "part"} for number, size in parts
                ]
                self.assertEqual(self.client.post(self.url).status_code, 409)
                self.complete.assert_not_called()
        self.head.assert_not_called()

    def test_out_of_order_storage_parts_are_normalized(self):
        self.parts.return_value.reverse()
        self.assertEqual(self.client.post(self.url).status_code, 200)

    def test_unrelated_storage_errors_do_not_use_recovery(self):
        self.parts.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "ListParts")
        self.assertEqual(self.client.post(self.url).status_code, 502)
        self.head.assert_not_called()
        self.process.assert_not_called()

    def test_cross_team_and_missing_uploads_are_not_found(self):
        self.assertEqual(self.client.post(self.url.replace(f"/teams/{self.upload.team_id}/", "/teams/9999/")).status_code, 404)
        self.assertEqual(self.client.post(self.url.replace(f"/film/{self.upload.id}/", "/film/9999/")).status_code, 404)
        self.parts.assert_not_called()

    def test_importing_and_unfinished_states_cannot_be_completed(self):
        for status in ("importing", "pending", "processing"):
            with self.subTest(status=status):
                self.upload.status = status
                self.db.commit()
                self.assertEqual(self.client.post(self.url).status_code, 409)
        self.process.assert_not_called()
