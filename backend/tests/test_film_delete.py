"""Offline deletion regressions: python -m unittest tests.test_film_delete -v."""

import os
import unittest
from unittest.mock import call, patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1.routes import film
from app.models import Base, Clip, FilmSegment, GameUpload, ShotEvent, Team


class FilmDeleteTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        team = Team(name="Valley")
        self.db.add(team)
        self.db.flush()
        self.key = f"teams/{team.id}/film/{'a' * 32}.mp4"
        self.tracks_key = self.key[:-4] + ".tracks-v1.json.gz"
        self.events_key = self.key[:-4] + ".tracks-v1.events.json"
        self.upload = GameUpload(
            team_id=team.id, title="Game", storage_url=film.storage.to_storage_url(self.key), status="ready",
            proxy_url=film.storage.to_storage_url(self.key + ".proxy.mp4"),
            thumbnail_url=film.storage.to_storage_url(self.key + ".thumb.jpg"),
            tracks_url=film.storage.to_storage_url(self.tracks_key),
            events_url=film.storage.to_storage_url(self.events_key),
            processing_job_id="processing", detection_job_id="detection", events_job_id="events",
        )
        self.db.add(self.upload)
        self.db.commit()
        self.upload_id = self.upload.id
        self.team_id = team.id
        self.app = FastAPI()
        self.app.include_router(film.router, prefix="/api/v1")

        def get_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.rollback()
                session.close()

        self.app.dependency_overrides[deps.get_db_session] = get_db
        self.app.dependency_overrides[deps.require_team_membership] = lambda: True
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.url = f"/api/v1/teams/{self.team_id}/film/{self.upload_id}"
        self.cancel_patch = patch.object(film.FilmProcessingService, "cancel_job")
        self.cancel = self.cancel_patch.start()
        self.addCleanup(self.cancel_patch.stop)
        self.delete = self.start_patch(patch.object(film.storage, "delete_object"))
        self.abort = self.start_patch(patch.object(film.storage, "abort_multipart_upload"))
        self.capture = self.start_patch(patch.object(film.sentry_sdk, "capture_exception"))
        self.start_patch(patch.object(film.storage, "_client", side_effect=AssertionError("Live storage forbidden")))
        self.start_patch(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))

    def start_patch(self, patcher):
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def delete_film(self):
        self.db.commit()
        return self.client.delete(self.url)

    def assert_upload_exists(self, exists):
        self.db.expire_all()
        self.assertEqual(self.db.get(GameUpload, self.upload_id) is not None, exists)

    def test_cancels_all_jobs_before_storage_and_deletes_owned_objects(self):
        operations = []
        self.cancel.side_effect = lambda job_id: operations.append(("cancel", job_id))
        self.delete.side_effect = lambda key: operations.append(("delete", key))
        response = self.delete_film()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(operations[:3], [("cancel", "processing"), ("cancel", "detection"), ("cancel", "events")])
        self.assertEqual(self.delete.call_args_list, [call(key) for key in (
            self.key, self.key + ".proxy.mp4", self.key + ".thumb.jpg", self.tracks_key, self.events_key,
        )])
        self.abort.assert_not_called()
        self.assert_upload_exists(False)

    def test_job_ids_are_deduplicated_and_not_gated_by_status(self):
        self.upload.processing_job_id = self.upload.detection_job_id = self.upload.events_job_id = "same"
        self.upload.detection_status = self.upload.events_status = "done"
        self.assertEqual(self.delete_film().status_code, 204)
        self.cancel.assert_called_once_with("same")

    def test_missing_job_ids_are_skipped(self):
        self.upload.processing_job_id = None
        self.upload.detection_job_id = ""
        self.assertEqual(self.delete_film().status_code, 204)
        self.cancel.assert_called_once_with("events")

    def test_unexpected_cancel_failure_does_not_skip_other_jobs_or_deletion(self):
        failure = RuntimeError("cancel unavailable")
        self.cancel.side_effect = [failure, None, None]
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.cancel.call_args_list, [call("processing"), call("detection"), call("events")])
        self.capture.assert_called_once_with(failure)
        self.assert_upload_exists(False)

    def test_real_cancel_service_keeps_best_effort_failure_contract(self):
        self.cancel_patch.stop()
        failure = RuntimeError("Modal unavailable")
        with patch("app.services.film_processing.modal.FunctionCall.from_id", side_effect=failure) as from_id:
            self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(from_id.call_args_list, [call("processing"), call("detection"), call("events")])
        self.assertEqual(self.capture.call_count, 3)
        self.assert_upload_exists(False)

    def test_real_cancel_service_requests_container_termination(self):
        self.cancel_patch.stop()
        with patch("app.services.film_processing.modal.FunctionCall.from_id") as from_id:
            self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(from_id.call_count, 3)
        self.assertEqual(from_id.return_value.cancel.call_args_list, [call(terminate_containers=True)] * 3)

    def test_duplicate_media_keys_are_deleted_once(self):
        self.upload.thumbnail_url = self.upload.proxy_url
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.delete.call_count, 4)
        self.assertEqual(self.delete.call_args_list.count(call(self.key + ".proxy.mp4")), 1)

    def test_multipart_full_delete_cancels_jobs_and_aborts_without_object_deletion(self):
        self.upload.storage_upload_id = "multipart"
        self.upload.status = "uploading"
        self.assertEqual(self.delete_film().status_code, 204)
        self.abort.assert_called_once_with(self.key, "multipart")
        self.assertEqual(self.cancel.call_count, 3)
        self.delete.assert_not_called()
        self.assert_upload_exists(False)

    def test_abort_endpoint_remains_upload_only(self):
        self.upload.storage_upload_id = "multipart"
        self.upload.status = "uploading"
        self.db.commit()
        self.assertEqual(self.client.delete(self.url + "/upload").status_code, 204)
        self.abort.assert_called_once_with(self.key, "multipart")
        self.cancel.assert_not_called()
        self.delete.assert_not_called()

    def test_abort_endpoint_rejects_completed_upload(self):
        self.assertEqual(self.client.delete(self.url + "/upload").status_code, 409)
        self.cancel.assert_not_called()
        self.abort.assert_not_called()
        self.assert_upload_exists(True)

    def test_storage_failure_returns_502_and_preserves_rows(self):
        self.db.add(Clip(team_id=self.team_id, title="Published", storage_url=self.upload.storage_url,
                         source_upload_id=self.upload_id))
        self.delete.side_effect = ClientError({"Error": {"Code": "Unavailable"}}, "DeleteObject")
        self.assertEqual(self.delete_film().status_code, 502)
        self.assertEqual(self.cancel.call_count, 3)
        self.assert_upload_exists(True)
        self.assertEqual(self.db.query(Clip).count(), 1)

    def test_abort_failure_returns_502_and_preserves_upload(self):
        self.upload.storage_upload_id = "multipart"
        self.abort.side_effect = BotoCoreError()
        self.assertEqual(self.delete_film().status_code, 502)
        self.delete.assert_not_called()
        self.assert_upload_exists(True)

    def test_foreign_bucket_and_unrelated_analysis_urls_are_not_deleted(self):
        self.upload.tracks_url = "r2://another-bucket/" + self.tracks_key
        self.upload.events_url = film.storage.to_storage_url("shared/events.json")
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.delete.call_count, 3)

    def test_external_or_missing_analysis_urls_are_not_deleted(self):
        self.upload.tracks_url = "https://example.invalid/tracks.json.gz"
        self.upload.events_url = None
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.delete.call_count, 3)

    def test_noncanonical_original_does_not_authorize_analysis_cleanup(self):
        self.upload.storage_url = film.storage.to_storage_url("legacy/game.mp4")
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.delete.call_count, 3)

    def test_foreign_bucket_original_does_not_authorize_analysis_cleanup(self):
        self.upload.storage_url = "r2://another-bucket/" + self.key
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.delete.call_count, 3)

    def test_other_upload_reference_protects_analysis_object(self):
        self.db.add(GameUpload(team_id=self.team_id, title="Other", storage_url="local.mp4",
                               proxy_url=self.upload.tracks_url))
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertNotIn(call(self.tracks_key), self.delete.call_args_list)
        self.assertIn(call(self.events_key), self.delete.call_args_list)

    def test_shared_source_protects_both_analysis_objects(self):
        self.db.add(GameUpload(team_id=self.team_id, title="Other", storage_url=self.upload.storage_url))
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertEqual(self.delete.call_count, 3)

    def test_unlinked_clip_reference_protects_analysis_object(self):
        clip = Clip(team_id=self.team_id, title="Independent", storage_url=self.upload.events_url)
        self.db.add(clip)
        self.db.flush()
        clip_id = clip.id
        self.assertEqual(self.delete_film().status_code, 204)
        self.assertNotIn(call(self.events_key), self.delete.call_args_list)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Clip, clip_id))

    def test_linked_clips_segments_and_all_event_types_are_deleted(self):
        self.db.add(Clip(team_id=self.team_id, title="Published", storage_url=self.upload.storage_url,
                         source_upload_id=self.upload_id))
        self.db.add(FilmSegment(upload_id=self.upload_id, start_second=1, end_second=10))
        for kind in ("shot", "stl", "ast"):
            self.db.add(ShotEvent(upload_id=self.upload_id, type=kind, t=2, team="valley", shot_type="fg2",
                                  made=False, confidence=0.5))
        self.assertEqual(self.delete_film().status_code, 204)
        for model in (Clip, FilmSegment, ShotEvent):
            self.assertEqual(self.db.query(model).count(), 0)

    def test_wrong_team_or_missing_upload_never_touches_external_services(self):
        for url in (self.url.replace(f"teams/{self.team_id}/", "teams/999/"), self.url + "999"):
            self.assertEqual(self.client.delete(url).status_code, 404)
        self.cancel.assert_not_called()
        self.delete.assert_not_called()
        self.abort.assert_not_called()
        self.assert_upload_exists(True)

    def test_membership_is_required(self):
        def forbidden():
            raise HTTPException(status_code=403, detail="Not a member of this team")

        self.app.dependency_overrides[deps.require_team_membership] = forbidden
        self.assertEqual(self.delete_film().status_code, 403)
        self.cancel.assert_not_called()
        self.delete.assert_not_called()
        self.assert_upload_exists(True)


if __name__ == "__main__":
    unittest.main()
