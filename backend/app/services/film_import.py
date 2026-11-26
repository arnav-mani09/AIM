from datetime import datetime, timedelta

import modal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game_upload import GameUpload
from app.services import storage
from app.services.film_import_download import MAX_BYTES, ImportRejected, normalize_source_url

IMPORT_DEADLINE = timedelta(hours=2, minutes=15)


def filter_import_telemetry(event, hint):
    request_url = str(event.get("request", {}).get("url", ""))
    if request_url.partition("?")[0].rstrip("/").endswith("/film/import"):
        return None
    return event


def check_import_available(source_url: str) -> str:
    settings = get_settings()
    if not settings.film_import_enabled or not settings.film_import_allowed_hosts.strip():
        raise HTTPException(503, "Direct-link film import is not enabled. Upload an MP4 or MOV file instead.")
    if not 1 <= len(source_url) <= 8192:
        raise HTTPException(400, "The direct download URL must be between 1 and 8192 characters.")
    try:
        return normalize_source_url(source_url, settings.film_import_allowed_hosts)
    except ImportRejected as exc:
        raise HTTPException(400, str(exc)) from None


def launch_import(db: Session, upload: GameUpload, source_url: str) -> None:
    settings = get_settings()
    try:
        function = modal.Function.from_name(settings.modal_film_app, "import_film")
        function = function.with_options(secrets=[
            modal.Secret.from_name("aim-r2"),
            modal.Secret.from_dict({
                "FILM_IMPORT_SOURCE_URL": source_url,
                "FILM_IMPORT_ALLOWED_HOSTS": settings.film_import_allowed_hosts,
            }),
        ], retries=0)
        call = function.spawn(storage.key_from_storage_url(upload.storage_url))
        upload.import_job_id = call.object_id
        db.commit()
    except Exception:
        upload.status = "error"
        upload.processing_error = "The import worker is unavailable. Upload a file or try again later."
        db.commit()
        raise HTTPException(503, upload.processing_error) from None


def refresh_import(db: Session, upload_id: int) -> None:
    from app.services.film_processing import FilmProcessingService

    upload = db.query(GameUpload).filter(
        GameUpload.id == upload_id, GameUpload.status == "importing",
    ).with_for_update(skip_locked=True).first()
    if not upload:
        db.rollback()
        return
    expired = upload.import_started_at and datetime.utcnow() - upload.import_started_at > IMPORT_DEADLINE
    if not upload.import_job_id:
        if not expired:
            db.rollback()
            return
        result = {"error": "The import could not be started. Please submit a new authorized download link."}
    else:
        try:
            result = modal.FunctionCall.from_id(upload.import_job_id).get(timeout=0)
        except TimeoutError:
            if not expired:
                db.rollback()
                return
            try:
                FilmProcessingService(db).cancel_job(upload.import_job_id)
            except Exception:
                pass
            result = {"error": "The film import timed out. Please try a new authorized download link."}
        except Exception:
            result = {"error": "The film import failed. Please try a new authorized download link or upload a file."}
    key = storage.key_from_storage_url(upload.storage_url)
    if (
        not isinstance(result, dict) or result.get("source_key") != key
        or type(result.get("size_bytes")) is not int or not 0 < result["size_bytes"] <= MAX_BYTES
    ):
        upload.status = "error"
        upload.processing_error = "The film import failed. Verify this is an authorized MP4/MOV direct download, not a watch page."
        upload.import_job_id = None
        db.commit()
        return
    upload.size_bytes = result["size_bytes"]
    upload.import_job_id = None
    upload.processing_error = None
    upload.status = "processing"
    FilmProcessingService(db).start(upload.id)


def refresh_pending_imports(db: Session) -> None:
    for (upload_id,) in db.query(GameUpload.id).filter(GameUpload.status == "importing").all():
        refresh_import(db, upload_id)
