from pathlib import Path
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.clip import Clip
from app.schemas.clip import ClipRead
from app.schemas.game_upload import PlaybackUrl
from app.services import storage
from app.services.clip_stats import hydrate_clip_stats

router = APIRouter(prefix="/teams/{team_id}/clips", tags=["clips"])

ALLOWED_CLIP_TYPES = {"video/mp4", "video/quicktime"}


def _get_clip(db: Session, team_id: int, clip_id: int) -> Clip:
    clip = (
        db.query(Clip)
        .filter(Clip.id == clip_id, Clip.team_id == team_id)
        .first()
    )
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return clip


def _storage_error(exc: Exception) -> HTTPException:
    print(f"[CLIPS] Storage error: {exc}")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Clip storage is unavailable, try again")


def _store_upload(team_id: int, file: UploadFile) -> str:
    if file.content_type not in ALLOWED_CLIP_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clip must be an MP4 or MOV video")
    key = f"teams/{team_id}/clips/{uuid4().hex}{Path(file.filename or '').suffix.lower()}"
    try:
        storage.put_object(key, file.file, file.content_type)
    except (BotoCoreError, ClientError, storage.StorageNotConfigured) as exc:
        raise _storage_error(exc) from exc
    return storage.to_storage_url(key)


@router.get("", response_model=list[ClipRead])
def list_team_clips(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    clips = (
        db.query(Clip)
        .filter(Clip.team_id == team_id)
        .order_by(Clip.uploaded_at.desc())
        .all()
    )
    for clip in clips:
        hydrate_clip_stats(db, clip)
    return clips


@router.get("/{clip_id}", response_model=ClipRead)
def get_clip(
    team_id: int,
    clip_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    clip = _get_clip(db, team_id, clip_id)
    hydrate_clip_stats(db, clip)
    return clip


@router.post("", response_model=ClipRead, status_code=status.HTTP_201_CREATED)
async def upload_team_clip(
    team_id: int,
    file: UploadFile = File(...),
    title: str = Form(...),
    notes: str | None = Form(None),
    game_id: int | None = Form(None),
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    storage_path = _store_upload(team_id, file)
    clip = Clip(
        title=title,
        notes=notes,
        game_id=game_id,
        team_id=team_id,
        uploaded_by_id=current_user.id,
        storage_url=storage_path,
        status="uploaded",
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    hydrate_clip_stats(db, clip)
    return clip


@router.delete("/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team_clip(
    team_id: int,
    clip_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    clip = _get_clip(db, team_id, clip_id)
    if clip.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only delete your own clips")
    # Clips that originate from a game upload share the same file as the raw film.
    # In that case we only remove the database record so the base film continues
    # to exist for other clips.
    key = storage.key_from_storage_url(clip.storage_url)
    if clip.source_upload_id is None and key:
        try:
            storage.delete_object(key)
        except (BotoCoreError, ClientError) as exc:
            raise _storage_error(exc) from exc
    db.delete(clip)
    db.commit()
    return None


@router.get("/{clip_id}/playback", response_model=PlaybackUrl)
def get_clip_playback_url(
    team_id: int,
    clip_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    """Signed link to the clip's video. Clips cut from game film point at the
    full film; the player seeks to source_start_second."""
    clip = _get_clip(db, team_id, clip_id)
    key = storage.key_from_storage_url(clip.storage_url)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip video not found")
    try:
        url = storage.presign_download(key)
    except (BotoCoreError, ClientError, storage.StorageNotConfigured) as exc:
        raise _storage_error(exc) from exc
    return PlaybackUrl(url=url, expires_in=storage.PLAYBACK_URL_TTL_SECONDS)
