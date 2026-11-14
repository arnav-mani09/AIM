import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SENTRY_DSN"] = ""
os.environ.setdefault("SECRET_KEY", "test-only")

import threading
import unittest
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models import GameUpload, Team
from app.services.film_processing import FilmProcessingService


class EventLaunchTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = create_engine(
            f"sqlite:///{self.directory.name}/processing.db",
            connect_args={"check_same_thread": False, "timeout": 5},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        team = Team(name="Valley")
        self.db.add(team)
        self.db.flush()
        upload = GameUpload(
            team_id=team.id, title="Game", storage_url="r2://aim-film/game.mp4",
            status="ready", tracks_url="r2://aim-film/game.tracks.json",
            detection_status="done", valley_jersey="white", opponent_jersey="blue",
            events_status="done", events_url="r2://aim-film/old.events.json",
            events_info={"teams_swapped": True},
        )
        self.db.add(upload)
        self.db.commit()
        self.upload_id = upload.id
        self.function = Mock()
        self.function.spawn.return_value = SimpleNamespace(object_id="new-call")
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch(
            "app.services.film_processing.modal.Function.from_name", return_value=self.function,
        ))
        patches.enter_context(patch("app.services.film_processing.sentry_sdk.capture_exception"))
        patches.enter_context(patch("app.services.film_processing.deployment_environment", return_value="development"))

    def service(self, db=None):
        service = FilmProcessingService(db or self.db)
        service.settings = SimpleNamespace(modal_film_app="test-film")
        return service

    def test_repeated_start_retains_original_job(self):
        self.service().start_events(self.upload_id)
        started = self.db.get(GameUpload, self.upload_id).events_started_at
        self.service().start_events(self.upload_id)
        self.function.spawn.assert_called_once_with(
            "game.tracks.json", "white", "blue", environment="development",
        )
        upload = self.db.get(GameUpload, self.upload_id)
        self.assertEqual(upload.events_job_id, "new-call")
        self.assertEqual(upload.events_started_at, started)

    def test_done_upload_can_rerun_without_erasing_results(self):
        self.service().start_events(self.upload_id)
        upload = self.db.get(GameUpload, self.upload_id)
        self.assertEqual(upload.events_status, "running")
        self.assertEqual(upload.events_url, "r2://aim-film/old.events.json")
        self.assertEqual(upload.events_info, {"teams_swapped": True})
        self.assertIsNone(upload.events_error)
        self.assertIsNotNone(upload.events_started_at)

    def test_running_without_job_is_not_implicitly_relaunched(self):
        upload = self.db.get(GameUpload, self.upload_id)
        upload.events_status = "running"
        self.db.commit()
        self.service().start_events(self.upload_id)
        self.function.spawn.assert_not_called()

    def test_never_started_and_failed_uploads_can_start(self):
        for previous in (None, "error"):
            with self.subTest(previous=previous):
                upload = self.db.get(GameUpload, self.upload_id)
                upload.events_status = previous
                upload.events_error = "previous failure"
                self.db.commit()
                self.service().start_events(self.upload_id)
                self.assertEqual(upload.events_status, "running")
                self.assertIsNone(upload.events_error)
        self.assertEqual(self.function.spawn.call_count, 2)

    def test_missing_upload_and_invalid_tracks_do_not_spawn(self):
        self.service().start_events(self.upload_id + 1)
        for tracks_url in (None, "https://example.invalid/tracks.json"):
            with self.subTest(tracks_url=tracks_url):
                upload = self.db.get(GameUpload, self.upload_id)
                upload.tracks_url = tracks_url
                self.db.commit()
                self.service().start_events(self.upload_id)
                self.assertEqual(upload.events_status, "done")
        self.function.spawn.assert_not_called()

    def test_spawn_failure_allows_retry(self):
        self.function.spawn.side_effect = RuntimeError("worker unavailable")
        self.service().start_events(self.upload_id)
        upload = self.db.get(GameUpload, self.upload_id)
        self.assertEqual(upload.events_status, "error")
        self.assertIn("worker unavailable", upload.events_error)
        self.function.spawn.side_effect = None
        self.service().start_events(self.upload_id)
        self.assertEqual(upload.events_status, "running")
        self.assertEqual(upload.events_job_id, "new-call")

    def test_stale_session_cannot_replace_running_job(self):
        stale = self.Session()
        self.addCleanup(stale.close)
        cached = stale.get(GameUpload, self.upload_id)
        self.assertEqual(cached.events_status, "done")
        self.service().start_events(self.upload_id)
        self.service(stale).start_events(self.upload_id)
        self.assertEqual(cached.events_status, "running")
        self.function.spawn.assert_called_once()

    def test_concurrent_starts_spawn_once(self):
        spawning = threading.Event()
        release_spawn = threading.Event()
        second_claim = threading.Event()
        errors = []

        def spawn(*args, **kwargs):
            spawning.set()
            if not release_spawn.wait(5):
                raise RuntimeError("test did not release spawn")
            return SimpleNamespace(object_id="concurrent-call")

        def before_execute(connection, cursor, statement, parameters, context, executemany):
            if threading.current_thread().name == "second-start" and statement.startswith("UPDATE"):
                second_claim.set()

        def start():
            with self.Session() as db:
                try:
                    self.service(db).start_events(self.upload_id)
                except Exception as exc:
                    errors.append(exc)

        self.function.spawn.side_effect = spawn
        event.listen(self.engine, "before_cursor_execute", before_execute)
        first = threading.Thread(target=start, name="first-start")
        second = threading.Thread(target=start, name="second-start")
        try:
            first.start()
            self.assertTrue(spawning.wait(5))
            second.start()
            self.assertTrue(second_claim.wait(5))
        finally:
            release_spawn.set()
            first.join(10)
            if second.ident is not None:
                second.join(10)
            event.remove(self.engine, "before_cursor_execute", before_execute)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.function.spawn.assert_called_once()
        self.db.expire_all()
        self.assertEqual(self.db.get(GameUpload, self.upload_id).events_job_id, "concurrent-call")
