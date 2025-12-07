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
from app.models.game_upload import GameUpload
from app.models.team_membership import TeamMembership
from app.models.film_segment import FilmSegment
from app.models.clip import Clip
from app.schemas.game_upload import GameUploadRead
from app.schemas.film_segment import FilmSegmentRead, FilmSegmentCreate
from app.schemas.clip import ClipRead

settings = get_settings()
router = APIRouter(prefix="/teams/{team_id}/film", tags=["film"])
raw_root = Path(settings.media_root) / "raw"
raw_root.mkdir(parents=True, exist_ok=True)


def _require_member(db: Session, team_id: int, user_id: int) -> TeamMembership:
    membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")
    return membership


def _get_upload(db: Session, team_id: int, upload_id: int) -> GameUpload:
    upload = (
        db.query(GameUpload)
        .filter(GameUpload.id == upload_id, GameUpload.team_id == team_id)
        .first()
    )
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return upload


def _save_raw_file(upload: UploadFile) -> str:
    dest = raw_root / f"{uuid4().hex}{Path(upload.filename).suffix}"
    with dest.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return str(dest)


@router.get("", response_model=list[GameUploadRead])
def list_game_uploads(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_member(db, team_id, current_user.id)
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
    current_user=Depends(deps.get_current_user),
):
    _require_member(db, team_id, current_user.id)
    upload = _get_upload(db, team_id, upload_id)
    return upload


@router.post("", response_model=GameUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_game_film(
    team_id: int,
    file: UploadFile = File(...),
    title: str = Form(...),
    notes: str | None = Form(None),
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_member(db, team_id, current_user.id)
    storage_url = _save_raw_file(file)
    upload = GameUpload(
        team_id=team_id,
        uploaded_by_id=current_user.id,
        title=title,
        notes=notes,
        storage_url=storage_url,
        status="uploaded",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game_film(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_member(db, team_id, current_user.id)
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
    try:
        if upload.storage_url and os.path.exists(upload.storage_url):
            os.remove(upload.storage_url)
    except OSError:
        pass
    db.delete(upload)
    db.commit()
    return None


@router.get("/{upload_id}/stream")
def stream_game_film(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_member(db, team_id, current_user.id)
    upload = _get_upload(db, team_id, upload_id)
    file_path = Path(upload.storage_url)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Film file not found")
    content_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        str(file_path),
        media_type=content_type or "video/mp4",
        filename=file_path.name,
    )


@router.get("/{upload_id}/segments", response_model=list[FilmSegmentRead])
def list_segments(
    team_id: int,
    upload_id: int,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    _require_member(db, team_id, current_user.id)
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
):
    _require_member(db, team_id, current_user.id)
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
):
    _require_member(db, team_id, current_user.id)
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
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    return clip
