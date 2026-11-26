"""Offline import regressions: python -m unittest tests.test_film_import -v."""

import io
import os
import socket
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode

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
from app.models import Base, GameUpload, Team, TeamMembership, User
from app.services import film_import, film_import_download as download


class HudlDownloadLinkTest(unittest.TestCase):
    wrapper = "https://www.hudl.com/notifications-tracking/tracker/BulkDownloadReady-example-123/email/landing"
    target = "https://vtemp.hudl.com/example/game.mp4?v=PRIVATE%2Bsignature&other=1"

    def wrap(self, target):
        return self.wrapper + "?" + urlencode({"forward": target})

    def test_unwraps_once_without_network_and_preserves_signed_target(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("Network forbidden")):
            self.assertEqual(download.normalize_source_url(self.wrap(self.target), "vtemp.hudl.com"), self.target)

    def test_direct_download_remains_unchanged(self):
        self.assertEqual(download.normalize_source_url(self.target, "vtemp.hudl.com"), self.target)

    def test_target_requires_explicit_configured_host(self):
        for hosts in ("", "www.hudl.com", "other.example"):
            with self.subTest(hosts=hosts), self.assertRaises(download.ImportRejected):
                download.normalize_source_url(self.wrap(self.target), hosts)

    def test_rejects_stats_nested_and_unsafe_targets_without_echo(self):
        targets = (
            "/reports/teams/example/download/stats", "https://www.hudl.com/watch/example",
            self.wrap(self.target), "http://vtemp.hudl.com/game.mp4",
            "https://vtemp.hudl.com.evil.example/game.mp4", "https://127.0.0.1/game.mp4",
            "https://user:PRIVATE@vtemp.hudl.com/game.mp4", "https://vtemp.hudl.com:444/game.mp4",
            "https://vtemp.hudl.com/game.mp4#PRIVATE", "https://vtemp.hudl.com/game.m3u8",
            "https://vtemp.hudl.com/game.mp4\n", "//vtemp.hudl.com/game.mp4", "",
        )
        for target in targets:
            with self.subTest(target=target), self.assertRaises(download.ImportRejected) as rejected:
                download.normalize_source_url(self.wrap(target), "vtemp.hudl.com,127.0.0.1")
            self.assertNotIn("PRIVATE", str(rejected.exception))

    def test_rejects_malformed_or_ambiguous_wrappers(self):
        encoded = urlencode({"forward": self.target})
        wrappers = (
            self.wrapper, self.wrapper + "?forward", self.wrapper + "?" + encoded + "&" + encoded,
            self.wrapper + "?" + encoded + "&extra=1", self.wrapper + "?" + encoded + "#fragment",
            self.wrapper.replace("https:", "http:") + "?" + encoded,
            self.wrapper.replace("www.hudl.com", "user@www.hudl.com") + "?" + encoded,
            self.wrapper.replace("BulkDownloadReady", "OtherEvent") + "?" + encoded,
            self.wrapper.replace("/email/landing", "/email/landing/extra") + "?" + encoded,
            self.wrapper + "?" + urlencode({"forward": self.target, "other": "x", "extra": "y"}),
        )
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper), self.assertRaises(download.ImportRejected):
                download.normalize_source_url(wrapper, "vtemp.hudl.com")


class DownloadSecurityTest(unittest.TestCase):
    def setUp(self):
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Live network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_url_policy_rejects_untrusted_or_ambiguous_urls(self):
        for url in (
            "http://cdn.example/game.mp4", "https://user:secret@cdn.example/game.mp4",
            "https://cdn.example:444/game.mp4", "https://127.0.0.1/game.mp4",
            "https://[::1]/game.mp4", "https://cdn.example.evil/game.mp4",
            "https://cdn.example/game.mp4#secret", "https://cdn.example/\\evil",
            "https://cdn.example/game\r\nX: secret", "https://cdn.example./game.mp4",
        ):
            with self.subTest(url=url), self.assertRaises(download.ImportRejected):
                download.validate_source_url(url, "cdn.example,127.0.0.1,::1")
        self.assertEqual(download.validate_source_url("https://cdn.example/signed?token=secret", "cdn.example")[0], "cdn.example")

    def test_dns_rejects_private_reserved_mixed_and_transition_addresses(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "192.0.2.1", "224.0.0.1", "0.0.0.0", "::1", "fc00::1", "fec0::1", "192.88.99.1", "2002:7f00:1::", "::ffff:8.8.8.8"):
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                       (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
            with self.subTest(address=address), patch.object(download.socket, "getaddrinfo", return_value=records), self.assertRaises(download.ImportRejected):
                download.resolve_public("cdn.example")

    def test_redirects_revalidate_host_and_dns(self):
        response = Mock(status=302)
        response.getheader.return_value = "https://internal.example/game.mp4"
        connection = Mock()
        connection.getresponse.return_value = response
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))]
        with patch.object(download.socket, "getaddrinfo", side_effect=[public, private]), patch.object(download, "PinnedHTTPSConnection", return_value=connection) as constructor:
            with self.assertRaises(download.ImportRejected):
                download.open_download("https://cdn.example/video", "cdn.example,internal.example")
            constructor.assert_called_once()
            connection.close.assert_called()

    def test_tls_connects_to_validated_address_with_original_sni(self):
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        connection = download.PinnedHTTPSConnection("cdn.example", address)
        context = Mock()
        connection._context = context
        with patch.object(download.socket, "socket") as factory, patch.object(download.socket, "getaddrinfo", side_effect=AssertionError("Must not resolve again")):
            connection.connect()
            factory.return_value.connect.assert_called_once_with(("8.8.8.8", 443))
            context.wrap_socket.assert_called_once_with(factory.return_value, server_hostname="cdn.example")


class MultipartImportTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "source"
        self.client = Mock()
        self.client.create_multipart_upload.return_value = {"UploadId": "multipart"}
        self.client.upload_part.return_value = {"ETag": "etag"}
        self.connection = Mock()
        self.probe = Mock(return_value={"width": 1920, "height": 1080, "duration": 30})
        self.video = b"\x00\x00\x00\x18ftypisom" + b"0" * 50
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Live network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def run_import(self, data=None, content_type="video/mp4", length=None):
        data = self.video if data is None else data
        response = io.BytesIO(data)
        headers = {"Content-Type": content_type, "Content-Length": length}
        response.getheader = lambda name, default=None: headers.get(name, default)
        with patch.object(download, "open_download", return_value=(self.connection, response)):
            return download.import_to_r2("https://cdn.example/video?token=secret", "cdn.example", self.client, "bucket", "key.mp4", self.path, self.probe)

    def test_streams_uniform_parts_and_hands_off_only_after_probe(self):
        with patch.object(download, "PART_BYTES", 24):
            result = self.run_import(length=str(len(self.video)))
        self.assertEqual(result, {"source_key": "key.mp4", "size_bytes": len(self.video)})
        bodies = [entry.kwargs["Body"] for entry in self.client.upload_part.call_args_list]
        self.assertEqual([len(body) for body in bodies], [24, 24, 14])
        self.assertEqual(b"".join(bodies), self.video)
        self.probe.assert_called_once_with(self.path)
        self.client.complete_multipart_upload.assert_called_once()
        self.client.abort_multipart_upload.assert_not_called()
        self.connection.close.assert_called_once()

    def test_rejects_html_before_multipart(self):
        with self.assertRaises(download.ImportRejected):
            self.run_import(b"<html>watch page</html>", content_type="text/html")
        self.client.create_multipart_upload.assert_not_called()

    def test_rejects_declared_oversize_before_multipart(self):
        with self.assertRaises(download.ImportRejected):
            self.run_import(length=str(download.MAX_BYTES + 1))
        self.client.create_multipart_upload.assert_not_called()

    def test_streamed_limit_and_invalid_magic_abort(self):
        for data, limit in ((self.video, 30), (b"not a video" * 3, 100)):
            with self.subTest(data=data), patch.object(download, "MAX_BYTES", limit), self.assertRaises(download.ImportRejected):
                self.run_import(data)
        self.assertEqual(self.client.abort_multipart_upload.call_count, 2)
        self.client.complete_multipart_upload.assert_not_called()

    def test_incomplete_probe_and_storage_failures_abort(self):
        with self.assertRaises(download.ImportRejected):
            self.run_import(length=str(len(self.video) + 1))
        self.probe.return_value = {"duration": 30}
        with self.assertRaises(download.ImportRejected):
            self.run_import()
        self.client.upload_part.side_effect = RuntimeError("storage unavailable")
        with self.assertRaises(RuntimeError):
            self.run_import()
        self.assertEqual(self.client.abort_multipart_upload.call_count, 3)
        self.client.complete_multipart_upload.assert_not_called()

    def test_failed_abort_does_not_hide_original_error(self):
        self.client.abort_multipart_upload.side_effect = RuntimeError("R2 unavailable")
        with self.assertRaises(download.ImportRejected):
            self.run_import(b"not video" * 10)
        self.connection.close.assert_called_once()

    def test_probe_failure_aborts_without_completing(self):
        self.probe.side_effect = RuntimeError("invalid container")
        with self.assertRaises(RuntimeError):
            self.run_import()
        self.client.abort_multipart_upload.assert_called_once()
        self.client.complete_multipart_upload.assert_not_called()


class ImportEndpointTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.team = Team(name="Valley")
        self.user = User(email="import@example.com", hashed_password="unused", full_name="Coach")
        self.db.add_all([self.team, self.user])
        self.db.flush()
        self.db.add(TeamMembership(team_id=self.team.id, user_id=self.user.id, role="coach"))
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(film.router, prefix="/api/v1")
        self.app.dependency_overrides[deps.get_db_session] = lambda: self.db
        self.app.dependency_overrides[deps.get_current_user] = lambda: self.user
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.url = f"/api/v1/teams/{self.team.id}/film/import"
        self.payload = {"title": "Game", "source_url": "https://cdn.example/video?token=SUPERSECRET", "valley_jersey": "white"}
        self.settings = SimpleNamespace(film_import_enabled=True, film_import_allowed_hosts="cdn.example", modal_film_app="test-film")
        self.patch(patch.object(film_import, "get_settings", return_value=self.settings))
        self.function = Mock()
        self.function.with_options.return_value = self.function
        self.function.spawn.return_value = SimpleNamespace(object_id="import-call")
        self.lookup = self.patch(patch.object(film_import.modal.Function, "from_name", return_value=self.function))
        self.secret = self.patch(patch.object(film_import.modal.Secret, "from_dict", return_value=Mock()))
        self.patch(patch("socket.socket.connect", side_effect=AssertionError("Live network forbidden")))

    def patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def test_returns_importing_without_boxscore_or_plaintext_source(self):
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 202, response.text)
        result = response.json()
        self.assertEqual(result["status"], "importing")
        self.assertIsNone(result["game_id"])
        self.assertIsNone(result["processing_error"])
        self.assertNotIn("SUPERSECRET", response.text)
        upload = self.db.get(GameUpload, result["id"])
        self.assertNotIn("SUPERSECRET", str(upload.__dict__))
        self.assertEqual(upload.import_job_id, "import-call")
        self.assertEqual(upload.valley_jersey, "white")
        self.assertNotIn("SUPERSECRET", str(self.function.spawn.call_args))
        self.assertEqual(self.secret.call_args.args[0]["FILM_IMPORT_SOURCE_URL"], self.payload["source_url"])

    def test_feature_disabled_and_invalid_provider_are_clear(self):
        self.settings.film_import_enabled = False
        self.assertEqual(self.client.post(self.url, json=self.payload).status_code, 503)
        self.settings.film_import_enabled = True
        self.payload["source_url"] = "https://www.hudl.com/watch/123"
        self.assertEqual(self.client.post(self.url, json=self.payload).status_code, 400)
        self.lookup.assert_not_called()
        self.assertEqual(self.db.query(GameUpload).count(), 0)

    def test_hudl_wrapper_dispatches_only_normalized_private_target(self):
        self.settings.film_import_allowed_hosts = "vtemp.hudl.com"
        target = HudlDownloadLinkTest.target
        self.payload["source_url"] = HudlDownloadLinkTest.wrapper + "?" + urlencode({"forward": target})
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.secret.call_args.args[0]["FILM_IMPORT_SOURCE_URL"], target)
        self.assertNotIn("PRIVATE", response.text)
        self.assertNotIn("PRIVATE", str(self.db.query(GameUpload).one().__dict__))
        self.assertNotIn("PRIVATE", str(self.function.spawn.call_args))

    def test_hudl_stats_link_is_rejected_before_row_or_dispatch(self):
        self.settings.film_import_allowed_hosts = "vtemp.hudl.com"
        self.payload["source_url"] = HudlDownloadLinkTest.wrapper + "?" + urlencode({"forward": "/reports/PRIVATE/stats"})
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(self.db.query(GameUpload).count(), 0)
        self.lookup.assert_not_called()

    def test_direct_upload_remains_available_when_import_disabled(self):
        self.settings.film_import_enabled = False
        payload = {"title": "Game", "filename": "game.mov", "content_type": "video/quicktime", "size_bytes": 100}
        with patch.object(film.storage, "create_multipart_upload", return_value="direct-multipart"):
            response = self.client.post(self.url.removesuffix("import") + "uploads", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["upload"]["status"], "uploading")
        self.lookup.assert_not_called()

    def test_validation_never_echoes_signed_source(self):
        del self.payload["title"]
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("SUPERSECRET", response.text)

    def test_import_telemetry_drops_request_body_and_transaction(self):
        event = {"request": {"url": "https://api.example/api/v1/teams/1/film/import", "data": self.payload}}
        self.assertIsNone(film_import.filter_import_telemetry(event, {}))
        event["request"]["url"] += "/?redirected=true"
        self.assertIsNone(film_import.filter_import_telemetry(event, {}))
        other_event = {"request": {"url": "https://api.example/api/v1/teams/1/film"}}
        self.assertIs(film_import.filter_import_telemetry(other_event, {}), other_event)

    def test_unexpected_failure_is_sanitized(self):
        with patch.object(film, "launch_import", side_effect=RuntimeError(self.payload["source_url"])):
            response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SUPERSECRET", response.text)

    def test_membership_and_auth_required(self):
        response = self.client.post("/api/v1/teams/999/film/import", json=self.payload)
        self.assertEqual(response.status_code, 403)
        self.app.dependency_overrides.pop(deps.get_current_user)
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 401)
        self.lookup.assert_not_called()

    def test_unavailable_worker_does_not_leak_exception(self):
        self.function.spawn.side_effect = RuntimeError(self.payload["source_url"])
        response = self.client.post(self.url, json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SUPERSECRET", response.text)
        upload = self.db.query(GameUpload).one()
        self.assertEqual(upload.status, "error")
        self.assertNotIn("SUPERSECRET", upload.processing_error)

    def create_upload(self):
        response = self.client.post(self.url, json=self.payload)
        return self.db.get(GameUpload, response.json()["id"])

    def test_background_poll_hands_off_completed_import(self):
        upload = self.create_upload()
        result = {"source_key": film.storage.key_from_storage_url(upload.storage_url), "size_bytes": 500}
        with patch.object(film_import.modal.FunctionCall, "from_id") as call, patch.object(film.FilmProcessingService, "start") as start:
            call.return_value.get.return_value = result
            film.FilmProcessingService(self.db).refresh_pending()
            start.assert_called_once_with(upload.id)
        self.assertEqual(upload.status, "processing")
        self.assertEqual(upload.size_bytes, 500)
        self.assertIsNone(upload.import_job_id)

    def test_get_poll_keeps_pending_import_and_reports_failures_safely(self):
        upload = self.create_upload()
        url = self.url.removesuffix("import") + str(upload.id)
        with patch.object(film_import.modal.FunctionCall, "from_id") as call:
            call.return_value.get.side_effect = TimeoutError
            self.assertEqual(self.client.get(url).json()["status"], "importing")
            call.return_value.get.side_effect = RuntimeError(self.payload["source_url"])
            response = self.client.get(url)
        self.assertEqual(response.json()["status"], "error")
        self.assertTrue(response.json()["processing_error"])
        self.assertNotIn("SUPERSECRET", response.text)

    def test_orphaned_dispatch_eventually_fails(self):
        upload = self.create_upload()
        upload.import_job_id = None
        upload.import_started_at = datetime.utcnow() - timedelta(hours=3)
        self.db.commit()
        film_import.refresh_pending_imports(self.db)
        self.assertEqual(upload.status, "error")

    def test_expired_import_cancels_and_fails(self):
        upload = self.create_upload()
        upload.import_started_at = datetime.utcnow() - timedelta(hours=3)
        self.db.commit()
        with patch.object(film_import.modal.FunctionCall, "from_id") as call, patch.object(film.FilmProcessingService, "cancel_job") as cancel:
            call.return_value.get.side_effect = TimeoutError
            film_import.refresh_pending_imports(self.db)
            cancel.assert_called_once_with("import-call")
        self.assertEqual(upload.status, "error")

    def test_wrong_worker_key_is_not_processed(self):
        upload = self.create_upload()
        with patch.object(film_import.modal.FunctionCall, "from_id") as call, patch.object(film.FilmProcessingService, "start") as start:
            call.return_value.get.return_value = {"source_key": "someone-elses-key.mp4", "size_bytes": 500}
            film_import.refresh_pending_imports(self.db)
            start.assert_not_called()
        self.assertEqual(upload.status, "error")

    def test_deleting_import_cancels_worker_and_known_object(self):
        upload = self.create_upload()
        with patch.object(film.FilmProcessingService, "cancel_job") as cancel, patch.object(film.storage, "delete_object") as delete:
            response = self.client.delete(self.url.removesuffix("import") + str(upload.id))
            self.assertEqual(response.status_code, 204)
            cancel.assert_called_once_with("import-call")
            delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
