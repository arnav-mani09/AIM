import re

from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.game_upload import GameUpload


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _combined_upload_text(upload: GameUpload | None, title: str | None = None, notes: str | None = None) -> str:
    if upload is not None:
        return _normalize(f"{upload.title} {upload.notes or ''}")
    return _normalize(f"{title or ''} {notes or ''}")


def find_game_for_upload(db: Session, title: str | None, notes: str | None) -> Game | None:
    combined = _combined_upload_text(None, title=title, notes=notes)
    if not combined:
        return None
    games = db.query(Game).order_by(Game.scheduled_at.desc()).all()
    for game in games:
        matchup = _normalize(game.matchup)
        if matchup and matchup in combined:
            return game
    return None


def link_uploads_to_game(db: Session, game: Game) -> int:
    matchup = _normalize(game.matchup)
    if not matchup:
        return 0
    uploads = (
        db.query(GameUpload)
        .filter(GameUpload.game_id.is_(None))
        .order_by(GameUpload.uploaded_at.desc())
        .all()
    )
    updated = 0
    for upload in uploads:
        combined = _combined_upload_text(upload)
        if matchup in combined:
            upload.game_id = game.id
            updated += 1
    if updated:
        db.commit()
    return updated
