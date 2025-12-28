import math
import subprocess
from pathlib import Path
from typing import List

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.film_segment import FilmSegment
from app.models.game_upload import GameUpload


class FilmProcessingService:
    """Extracts basic metadata from uploads and creates placeholder segments."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def process_upload(self, upload_id: int) -> None:
        upload = (
            self.db.query(GameUpload)
            .filter(GameUpload.id == upload_id)
            .first()
        )
        if not upload or not upload.storage_url:
            return

        upload.status = "processing"
        self.db.commit()

        status = "ready"
        duration = self._probe_duration(Path(upload.storage_url))
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
                    film_segment = FilmSegment(
                        upload_id=upload.id,
                        start_second=segment["start"],
                        end_second=segment["end"],
                        label=segment.get("label"),
                        notes=segment.get("notes"),
                    )
                    self.db.add(film_segment)
        except Exception:
            status = "error"
            raise
        finally:
            upload.status = status
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

    def _probe_duration(self, path: Path) -> float | None:
        """Use ffprobe if available to detect duration of the uploaded video."""
        if not path.exists():
            return None
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(result.stdout.strip())
        except FileNotFoundError:
            return path.stat().st_size / 4_000_000 if path.stat().st_size else None
        except (subprocess.SubprocessError, ValueError):
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
