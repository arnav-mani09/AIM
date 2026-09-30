import math
import subprocess
from typing import List

import httpx
import modal
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.film_segment import FilmSegment
from app.models.game_upload import GameUpload
from app.services import storage


class FilmProcessingService:
    """Turns a finished upload into playable, segmented film.

    The Modal worker (worker/film_worker.py) makes the 720p proxy, thumbnail
    and exact duration. `start` launches it; `refresh` collects the result and
    runs from both page polls and the background poller in app.main, so a
    finished job is picked up even when nobody has the page open.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def start(self, upload_id: int) -> None:
        upload = self.db.query(GameUpload).filter(GameUpload.id == upload_id).first()
        key = storage.key_from_storage_url(upload.storage_url) if upload else None
        if not upload or not key:
            return
        try:
            make_proxy = modal.Function.from_name(self.settings.modal_film_app, "make_proxy")
            call = make_proxy.spawn(key)
        except Exception as exc:  # Modal down or not configured: keep film usable without a proxy.
            print(f"[FILM] Could not start the Modal worker for upload {upload.id}: {exc}")
            self.process_without_worker(upload.id)
            return
        upload.status = "processing"
        upload.processing_job_id = call.object_id
        upload.processing_error = None
        self.db.commit()

    def refresh(self, upload_id: int) -> None:
        """Collect a finished worker job, if there is one. Cheap when nothing is pending."""
        # skip_locked: a page poll and the background poller may race; one wins.
        upload = (
            self.db.query(GameUpload)
            .filter(GameUpload.id == upload_id, GameUpload.status == "processing", GameUpload.processing_job_id.isnot(None))
            .with_for_update(skip_locked=True)
            .first()
        )
        if not upload:
            self.db.rollback()
            return
        try:
            result = modal.FunctionCall.from_id(upload.processing_job_id).get(timeout=0)
        except TimeoutError:
            self.db.rollback()
            return
        except Exception as exc:
            print(f"[FILM] Worker failed for upload {upload.id}: {exc}")
            upload.status = "error"
            upload.processing_error = str(exc)[:1000] or exc.__class__.__name__
            upload.processing_job_id = None
            self.db.commit()
            return

        upload.proxy_url = storage.to_storage_url(result["proxy_key"])
        upload.thumbnail_url = storage.to_storage_url(result["thumbnail_key"])
        upload.processing_job_id = None
        self._finish(upload, result["duration_seconds"])
        print(f"[FILM] Upload {upload.id} processed: {result.get('timings_seconds')}")

    def refresh_pending(self) -> None:
        pending = (
            self.db.query(GameUpload.id)
            .filter(GameUpload.status == "processing", GameUpload.processing_job_id.isnot(None))
            .all()
        )
        for (upload_id,) in pending:
            self.refresh(upload_id)

    def process_without_worker(self, upload_id: int) -> None:
        """Fallback when the worker can't run: duration via ffprobe, no proxy."""
        upload = self.db.query(GameUpload).filter(GameUpload.id == upload_id).first()
        if not upload or not upload.storage_url:
            return
        upload.status = "processing"
        self.db.commit()
        self._finish(upload, self._probe_duration(upload.storage_url))

    def _finish(self, upload: GameUpload, duration: float | None) -> None:
        try:
            if duration is not None:
                upload.duration_seconds = int(duration)
            existing_segments = (
                self.db.query(FilmSegment)
                .filter(FilmSegment.upload_id == upload.id)
                .count()
            )
            if existing_segments == 0 and duration and duration > 0:
                segments = self._fetch_model_segments(upload) or self._suggest_segments(duration)
                for segment in segments:
                    self.db.add(
                        FilmSegment(
                            upload_id=upload.id,
                            start_second=segment["start"],
                            end_second=segment["end"],
                            label=segment.get("label"),
                            notes=segment.get("notes"),
                        )
                    )
            upload.status = "ready"
        except Exception as exc:
            upload.status = "error"
            upload.processing_error = str(exc)[:1000]
            raise
        finally:
            self.db.commit()

    def _fetch_model_segments(self, upload: GameUpload) -> List[dict]:
        """Try to fetch model-generated segments from a gateway. Returns [] on failure."""
        if not self.settings.model_gateway_url:
            return []
        payload = {
            "upload_id": upload.id,
            "storage_url": upload.storage_url,
            "duration_seconds": upload.duration_seconds,
            "game_id": upload.game_id,
            "title": upload.title,
        }
        headers = {}
        if self.settings.model_gateway_token:
            headers["Authorization"] = f"Bearer {self.settings.model_gateway_token}"
        try:
            response = httpx.post(
                self.settings.model_gateway_url,
                json=payload,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            print(f"[FILM] Model gateway failed: {exc}")
            return []
        segments = data.get("segments", [])
        normalized = []
        for segment in segments:
            start = int(segment.get("start_second", segment.get("start", 0)))
            end = int(segment.get("end_second", segment.get("end", 0)))
            if end <= start:
                continue
            normalized.append(
                {
                    "start": start,
                    "end": end,
                    "label": segment.get("label"),
                    "notes": segment.get("notes"),
                }
            )
        return normalized

    def _probe_duration(self, storage_url: str) -> float | None:
        """Read the video duration with ffprobe, straight from R2 via a signed link.

        Only used when the Modal worker can't run. Returns None when ffprobe
        is missing (as on Render) or the file can't be read.
        """
        key = storage.key_from_storage_url(storage_url)
        if not key:
            return None
        try:
            source = storage.presign_download(key, ttl_seconds=15 * 60)
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    source,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            return float(result.stdout.strip())
        except FileNotFoundError:
            print("[FILM] ffprobe is not installed; duration unknown")
            return None
        except (subprocess.SubprocessError, ValueError) as exc:
            print(f"[FILM] ffprobe failed: {exc}")
            return None

    def _suggest_segments(self, duration: float) -> List[dict]:
        """Create evenly spaced placeholder segments."""
        if duration <= 0:
            return []
        if duration < 8:
            total_segments = 1
        elif duration < 24:
            total_segments = 2
        elif duration < 60:
            total_segments = 3
        else:
            total_segments = min(6, math.ceil(duration / 25))
        segment_length = duration / total_segments
        segment_length = max(5, min(segment_length, 25))

        suggestions = []
        current = 0.0
        index = 1
        while current < duration and index <= total_segments:
            end = min(duration, current + segment_length)
            if end - current < 2:
                break
            suggestions.append(
                {
                    "start": int(current),
                    "end": int(end),
                    "label": f"Suggested segment {index}",
                    "notes": "Auto-generated by AIM.",
                }
            )
            current = end
            index += 1
        return suggestions
