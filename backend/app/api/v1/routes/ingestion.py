from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api import deps
from app.services.ingestion import StatsIngestionService

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/possessions")
def ingest_possessions(
    matchup: str = Form(...),
    scheduled_at: datetime = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db_session),
):
    temp_path = Path("/tmp") / file.filename
    temp_path.write_bytes(file.file.read())
    service = StatsIngestionService(db)
    game = service.ingest_possession_csv(temp_path, matchup, scheduled_at)
    temp_path.unlink(missing_ok=True)
    return {"game_id": game.id, "matchup": game.matchup}
