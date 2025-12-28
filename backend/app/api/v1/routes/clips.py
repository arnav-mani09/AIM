from pathlib import Path
from uuid import uuid4
import mimetypes
import os
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import get_settings
from app.models.clip import Clip
from app.models.team_membership import TeamMembership
from app.schemas.clip import ClipRead
from app.services.clip_stats import hydrate_clip_stats

router = APIRouter(prefix="/teams/{team_id}/clips", tags=["clips"])
settings = get_settings()
media_root = Path(settings.media_root)
media_root.mkdir(parents=True, exist_ok=True)


def _require_membership(db: Session, team_id: int, user_id: int) -> TeamMembership:
    membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")
    return membership


def _get_clip(db: Session, team_id: int, clip_id: int) -> Clip:
    clip = (
        db.query(Clip)
        .filter(Clip.id == clip_id, Clip.team_id == team_id)
        .first()
    )
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return clip


def _store_upload(file: UploadFile) -> str:
    suffix = Path(file.filename).suffix
    destination = media_root / f"{uuid4().hex}{suffix}"
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return str(destination)


@router.get("", response_model=list[ClipRead])
def list_team_clips(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_membership(db, team_id, current_user.id)
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
    current_user=Depends(deps.get_current_user),
):
    _require_membership(db, team_id, current_user.id)
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
):
    _require_membership(db, team_id, current_user.id)
    storage_path = _store_upload(file)
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
):
    _require_membership(db, team_id, current_user.id)
    clip = _get_clip(db, team_id, clip_id)
    if clip.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only delete your own clips")
    # Clips that originate from a game upload share the same file as the raw film.
    # In that case we only remove the database record so the base film continues
    # to exist for other clips.
    should_remove_file = clip.source_upload_id is None
    try:
        if should_remove_file and clip.storage_url and os.path.exists(clip.storage_url):
            os.remove(clip.storage_url)
    except OSError:
        pass
    db.delete(clip)
    db.commit()
    return None


@router.get("/{clip_id}/stream")
def stream_clip(
    team_id: int,
    clip_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_membership(db, team_id, current_user.id)
    clip = _get_clip(db, team_id, clip_id)
    file_path = Path(clip.storage_url)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file not found")
    content_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        str(file_path),
        media_type=content_type or "video/mp4",
        filename=file_path.name,
    )
