import math
import re
from pathlib import Path
from uuid import uuid4

import sentry_sdk
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import or_
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
from app.schemas.shot_event import (
    PlayEventCreate,
    PlayEventRead,
    ShotEventCreate,
    ShotEventPatch,
    ShotEventRead,
    ShotEventsRead,
)
from app.models.shot_event import ShotEvent
from app.services import shot_events
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
    sentry_sdk.capture_exception(exc)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Film storage is unavailable, try again")


def _process_upload_async(upload_id: int) -> None:
    db = SessionLocal()
    try:
        FilmProcessingService(db).start(upload_id)
    finally:
        db.close()


def _refresh_processing(db: Session, uploads: list[GameUpload]) -> None:
    """Pick up finished worker jobs so the page sees them on its next poll."""
    service = FilmProcessingService(db)
    for upload in uploads:
        if upload.status == "processing" and upload.processing_job_id:
            service.refresh(upload.id)
            db.refresh(upload)


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
    _refresh_processing(db, uploads)
    return uploads


@router.get("/{upload_id}", response_model=GameUploadRead)
def get_game_upload(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload = _get_upload(db, team_id, upload_id)
    _refresh_processing(db, [upload])
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
        valley_jersey=payload.valley_jersey,
        opponent_jersey=payload.opponent_jersey,
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


def _owned_analysis_keys(db: Session, upload: GameUpload) -> list[str]:
    key = storage.key_from_storage_url(upload.storage_url)
    if (
        not key
        or storage.to_storage_url(key) != upload.storage_url
        or not re.fullmatch(rf"teams/{upload.team_id}/film/[0-9a-f]{{32}}\.(mp4|mov)", key)
    ):
        return []
    stem = re.escape(key.rsplit(".", 1)[0])
    keys = []
    for url, suffix in ((upload.tracks_url, r"\.json\.gz"), (upload.events_url, r"\.events\.json")):
        candidate = storage.key_from_storage_url(url)
        if (
            not candidate
            or storage.to_storage_url(candidate) != url
            or not re.fullmatch(stem + r"\.tracks-[^/]+" + suffix, candidate)
        ):
            continue
        shared_upload = db.query(GameUpload.id).filter(
            GameUpload.id != upload.id,
            or_(
                GameUpload.storage_url.in_([upload.storage_url, url]),
                GameUpload.proxy_url == url,
                GameUpload.thumbnail_url == url,
                GameUpload.tracks_url == url,
                GameUpload.events_url == url,
            ),
        ).first()
        shared_clip = db.query(Clip.id).filter(
            or_(Clip.source_upload_id.is_(None), Clip.source_upload_id != upload.id),
            Clip.storage_url == url,
        ).first()
        if not shared_upload and not shared_clip:
            keys.append(candidate)
    return keys


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game_film(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    upload = _get_upload(db, team_id, upload_id)
    service = FilmProcessingService(db)
    job_ids = dict.fromkeys(
        job_id for job_id in (upload.processing_job_id, upload.detection_job_id, upload.events_job_id)
        if job_id
    )
    for job_id in job_ids:
        try:
            service.cancel_job(job_id)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
    analysis_keys = _owned_analysis_keys(db, upload) if not upload.storage_upload_id else []
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
    derived = [storage.key_from_storage_url(u) for u in (upload.proxy_url, upload.thumbnail_url)]
    try:
        if key and upload.storage_upload_id:
            storage.abort_multipart_upload(key, upload.storage_upload_id)
        for object_key in dict.fromkeys([key, *derived, *analysis_keys]):
            if object_key and not upload.storage_upload_id:
                storage.delete_object(object_key)
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
    """A short-lived signed link the <video> element can load directly from R2.
    Plays the 720p proxy once the worker has made it, the original until then."""
    upload = _get_upload(db, team_id, upload_id)
    key = storage.key_from_storage_url(upload.proxy_url) or storage.key_from_storage_url(upload.storage_url)
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


# --- Drafted shot events (the coach review screen) ---------------------------------


def _events_response(db: Session, upload: GameUpload) -> ShotEventsRead:
    events = (
        db.query(ShotEvent)
        .filter(ShotEvent.upload_id == upload.id, ShotEvent.type.in_(shot_events.VISIBLE_TYPES))
        .order_by(ShotEvent.t.asc(), ShotEvent.id.asc())
        .all()
    )
    plays_known = shot_events.has_plays(upload, events)
    return ShotEventsRead(
        status=shot_events.review_status(upload),
        events=[e for e in events if e.type == shot_events.SHOT],
        plays=[e for e in events if shot_events.is_play(e)],
        has_plays=plays_known,
        box_score=shot_events.box_score(events, plays_known),
        teams_guessed=bool((upload.events_info or {}).get("teams_guessed")),
    )


def _get_event(db: Session, upload_id: int, event_id: int) -> ShotEvent:
    """A shot or play on this film. Hidden types (steals, assists) are never reachable."""
    event = (
        db.query(ShotEvent)
        .filter(ShotEvent.id == event_id, ShotEvent.upload_id == upload_id,
                ShotEvent.type.in_(shot_events.VISIBLE_TYPES))
        .first()
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _event_read(event: ShotEvent) -> ShotEventRead | PlayEventRead:
    return PlayEventRead.model_validate(event) if shot_events.is_play(event) else ShotEventRead.model_validate(event)


@router.get("/{upload_id}/events", response_model=ShotEventsRead)
def list_shot_events(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    """AIM's drafted shots, team rebounds and turnovers for this film and the box score they add up to."""
    upload = _get_upload(db, team_id, upload_id)
    if upload.events_status == "running" and upload.events_job_id:
        FilmProcessingService(db).refresh_events(upload.id)
        db.refresh(upload)
    return _events_response(db, upload)


@router.patch("/{upload_id}/events/{event_id}", response_model=ShotEventRead | PlayEventRead)
def update_shot_event(
    team_id: int,
    upload_id: int,
    event_id: int,
    payload: ShotEventPatch,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    """Fix a shot, or a rebound or turnover (team, time or status only; switching a rebound's
    team also switches offensive and defensive)."""
    _get_upload(db, team_id, upload_id)
    event = _get_event(db, upload_id, event_id)
    patch = payload.model_dump(exclude_unset=True)
    if shot_events.is_play(event) and set(patch) - {"team", "t", "status"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="A rebound or turnover can only change its team, time or status")
    shot_events.apply_patch(event, patch, current_user.id)
    db.commit()
    db.refresh(event)
    return _event_read(event)


@router.post("/{upload_id}/events", response_model=ShotEventRead, status_code=status.HTTP_201_CREATED)
def add_shot_event(
    team_id: int,
    upload_id: int,
    payload: ShotEventCreate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    """A shot the model missed, added by the coach."""
    _get_upload(db, team_id, upload_id)
    event = ShotEvent(upload_id=upload_id, type="shot", confidence=1.0, status="fixed", original=None,
                      updated_by_id=current_user.id, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.post("/{upload_id}/plays", response_model=PlayEventRead, status_code=status.HTTP_201_CREATED)
def add_play_event(
    team_id: int,
    upload_id: int,
    payload: PlayEventCreate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    """A team rebound or turnover the model missed, added by the coach."""
    _get_upload(db, team_id, upload_id)
    event = ShotEvent(upload_id=upload_id, type=payload.type, t=payload.t, team=payload.team,
                      shot_type=shot_events.PLAY_SHOT_TYPE, made=False, confidence=1.0, status="fixed",
                      original=None, updated_by_id=current_user.id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.post("/{upload_id}/events/swap-teams", response_model=ShotEventsRead)
def swap_shot_event_teams(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    """Flip Valley and Opponent on every shot, rebound and turnover, for when the jersey colors were guessed wrong."""
    upload = _get_upload(db, team_id, upload_id)
    shot_events.swap_teams(db, upload, current_user.id)
    db.commit()
    return _events_response(db, upload)


@router.post("/{upload_id}/events/rerun", response_model=ShotEventsRead, status_code=status.HTTP_202_ACCEPTED)
def rerun_shot_events(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    """Draft the shots, rebounds and turnovers again from this film's tracks (after the rules
    improve, or for films drafted before a step existed). If a coach reviewed any shot, all the
    shots are kept as they are, and the same for rebounds and turnovers; the rest is redrafted."""
    upload = _get_upload(db, team_id, upload_id)
    if upload.detection_status != "done" or not upload.tracks_url:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Player detection hasn't finished for this film")
    if upload.events_status == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shots are already being drafted")
    FilmProcessingService(db).start_events(upload.id)
    db.refresh(upload)
    return _events_response(db, upload)
