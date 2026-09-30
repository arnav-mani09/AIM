import math
from pathlib import Path
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import SessionLocal
from app.models.game_upload import GameUpload
from app.models.game import Game
from app.models.film_segment import FilmSegment
from app.models.clip import Clip
from app.schemas.game_upload import (
    FilmUploadStart,
    FilmUploadStarted,
    GameUploadRead,
    PlaybackUrl,
    SignedPart,
    SignPartsRequest,
    UploadedPart,
)
from app.schemas.film_segment import FilmSegmentRead, FilmSegmentCreate
from app.schemas.clip import ClipRead
from app.services import storage
from app.services.film_processing import FilmProcessingService
from app.services.clip_stats import link_clip_to_possessions, hydrate_clip_stats
from app.services.game_matching import find_game_for_upload

router = APIRouter(prefix="/teams/{team_id}/film", tags=["film"])

ALLOWED_FILM_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov"}
MAX_FILM_BYTES = 5 * 1024**3
# R2 needs every part except the last to be the same size. 64 MB keeps a
# 2 GB game at ~35 parts and a retried part cheap to resend.
FILM_PART_BYTES = 64 * 1024**2
MAX_PARTS = 10_000


def _get_upload(db: Session, team_id: int, upload_id: int) -> GameUpload:
    upload = (
        db.query(GameUpload)
        .filter(GameUpload.id == upload_id, GameUpload.team_id == team_id)
        .first()
    )
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return upload


def _get_upload_in_progress(db: Session, team_id: int, upload_id: int) -> tuple[GameUpload, str]:
    upload = _get_upload(db, team_id, upload_id)
    key = storage.key_from_storage_url(upload.storage_url)
    if upload.status != "uploading" or not upload.storage_upload_id or not key:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload is not in progress")
    return upload, key


def _get_game(db: Session, game_id: int) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return game


def _storage_error(exc: Exception) -> HTTPException:
    print(f"[FILM] Storage error: {exc}")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Film storage is unavailable, try again")


def _process_upload_async(upload_id: int) -> None:
    db = SessionLocal()
    try:
        FilmProcessingService(db).process_upload(upload_id)
    finally:
        db.close()


@router.get("", response_model=list[GameUploadRead])
def list_game_uploads(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    uploads = (
        db.query(GameUpload)
        .filter(GameUpload.team_id == team_id)
        .order_by(GameUpload.uploaded_at.desc())
        .all()
    )
    return uploads


@router.get("/{upload_id}", response_model=GameUploadRead)
def get_game_upload(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload = _get_upload(db, team_id, upload_id)
    return upload


@router.post("/uploads", response_model=FilmUploadStarted, status_code=status.HTTP_201_CREATED)
def start_film_upload(
    team_id: int,
    payload: FilmUploadStart,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    """Start a chunked upload straight to R2. The browser then PUTs each part to a signed URL."""
    extension = ALLOWED_FILM_TYPES.get(payload.content_type)
    if not extension:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Film must be an MP4 or MOV video")
    if payload.size_bytes > MAX_FILM_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Film must be 5 GB or smaller")
    game = _get_game(db, payload.game_id) if payload.game_id is not None else find_game_for_upload(db, payload.title, payload.notes)

    key = f"teams/{team_id}/film/{uuid4().hex}{Path(payload.filename).suffix.lower() or extension}"
    try:
        storage_upload_id = storage.create_multipart_upload(key, payload.content_type)
    except (BotoCoreError, ClientError, storage.StorageNotConfigured) as exc:
        raise _storage_error(exc) from exc

    upload = GameUpload(
        team_id=team_id,
        uploaded_by_id=current_user.id,
        title=payload.title,
        notes=payload.notes,
        storage_url=storage.to_storage_url(key),
        storage_upload_id=storage_upload_id,
        size_bytes=payload.size_bytes,
        status="uploading",
        game_id=game.id if game else None,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return FilmUploadStarted(
        upload=upload,
        part_size=FILM_PART_BYTES,
        part_count=math.ceil(payload.size_bytes / FILM_PART_BYTES),
    )


@router.post("/{upload_id}/upload/sign", response_model=list[SignedPart])
def sign_film_upload_parts(
    team_id: int,
    upload_id: int,
    payload: SignPartsRequest,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload, key = _get_upload_in_progress(db, team_id, upload_id)
    part_count = math.ceil((upload.size_bytes or 0) / FILM_PART_BYTES)
    if any(n < 1 or n > min(part_count, MAX_PARTS) for n in payload.part_numbers):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Part number out of range")
    try:
        return [
            SignedPart(part_number=n, url=storage.presign_upload_part(key, upload.storage_upload_id, n))
            for n in payload.part_numbers
        ]
    except (BotoCoreError, ClientError) as exc:
        raise _storage_error(exc) from exc


@router.get("/{upload_id}/upload/parts", response_model=list[UploadedPart])
def list_film_upload_parts(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    """Parts R2 already has, so an interrupted upload can resume."""
    upload, key = _get_upload_in_progress(db, team_id, upload_id)
    try:
        parts = storage.list_parts(key, upload.storage_upload_id)
    except (BotoCoreError, ClientError) as exc:
        raise _storage_error(exc) from exc
    return [UploadedPart(part_number=p["part_number"], size=p["size"]) for p in parts]


@router.post("/{upload_id}/upload/complete", response_model=GameUploadRead)
def complete_film_upload(
    team_id: int,
    upload_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload, key = _get_upload_in_progress(db, team_id, upload_id)
    try:
        # Trust R2's record of the parts, not the browser's.
        parts = storage.list_parts(key, upload.storage_upload_id)
        expected_parts = math.ceil(upload.size_bytes / FILM_PART_BYTES)
        received = sum(p["size"] for p in parts)
        if len(parts) != expected_parts or received != upload.size_bytes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Upload incomplete: {len(parts)} of {expected_parts} parts, {received} of {upload.size_bytes} bytes",
            )
        storage.complete_multipart_upload(key, upload.storage_upload_id, parts)
    except (BotoCoreError, ClientError) as exc:
        raise _storage_error(exc) from exc

    upload.storage_upload_id = None
    upload.status = "processing"
    db.commit()
    db.refresh(upload)
    background_tasks.add_task(_process_upload_async, upload.id)
    return upload


@router.delete("/{upload_id}/upload", status_code=status.HTTP_204_NO_CONTENT)
def abort_film_upload(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload, key = _get_upload_in_progress(db, team_id, upload_id)
    try:
        storage.abort_multipart_upload(key, upload.storage_upload_id)
    except (BotoCoreError, ClientError) as exc:
        raise _storage_error(exc) from exc
    db.delete(upload)
    db.commit()
    return None


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game_film(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload = _get_upload(db, team_id, upload_id)
    # Remove any clips that were published from this upload so nothing points
    # at a file that is about to be deleted.
    linked_clips = (
        db.query(Clip)
        .filter(Clip.source_upload_id == upload.id)
        .all()
    )
    for clip in linked_clips:
        db.delete(clip)
    key = storage.key_from_storage_url(upload.storage_url)
    if key:
        try:
            if upload.storage_upload_id:
                storage.abort_multipart_upload(key, upload.storage_upload_id)
            else:
                storage.delete_object(key)
        except (BotoCoreError, ClientError) as exc:
            raise _storage_error(exc) from exc
    db.delete(upload)
    db.commit()
    return None


@router.get("/{upload_id}/playback", response_model=PlaybackUrl)
def get_film_playback_url(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    """A short-lived signed link the <video> element can load directly from R2."""
    upload = _get_upload(db, team_id, upload_id)
    key = storage.key_from_storage_url(upload.storage_url)
    if not key or upload.status == "uploading":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Film is not available for playback")
    try:
        url = storage.presign_download(key)
    except (BotoCoreError, ClientError, storage.StorageNotConfigured) as exc:
        raise _storage_error(exc) from exc
    return PlaybackUrl(url=url, expires_in=storage.PLAYBACK_URL_TTL_SECONDS)


@router.get("/{upload_id}/segments", response_model=list[FilmSegmentRead])
def list_segments(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    _get_upload(db, team_id, upload_id)
    segments = (
        db.query(FilmSegment)
        .filter(FilmSegment.upload_id == upload_id)
        .order_by(FilmSegment.start_second.asc())
        .all()
    )
    return segments


@router.post("/{upload_id}/segments", response_model=FilmSegmentRead, status_code=status.HTTP_201_CREATED)
def create_segment(
    team_id: int,
    upload_id: int,
    payload: FilmSegmentCreate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    _get_upload(db, team_id, upload_id)
    if payload.end_second <= payload.start_second:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End must be after start")
    segment = FilmSegment(
        upload_id=upload_id,
        start_second=payload.start_second,
        end_second=payload.end_second,
        label=payload.label,
        notes=payload.notes,
        created_by_id=current_user.id,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


@router.post("/{upload_id}/segments/{segment_id}/publish", response_model=ClipRead, status_code=status.HTTP_201_CREATED)
def publish_segment_as_clip(
    team_id: int,
    upload_id: int,
    segment_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    upload = _get_upload(db, team_id, upload_id)
    segment = (
        db.query(FilmSegment)
        .filter(FilmSegment.id == segment_id, FilmSegment.upload_id == upload_id)
        .first()
    )
    if not segment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    clip = Clip(
        team_id=team_id,
        title=segment.label or upload.title,
        notes=segment.notes,
        storage_url=upload.storage_url,
        status="published",
        uploaded_by_id=current_user.id,
        source_upload_id=upload.id,
        source_start_second=segment.start_second,
        source_end_second=segment.end_second,
        game_id=upload.game_id,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    link_clip_to_possessions(db, clip)
    hydrate_clip_stats(db, clip)
    return clip
