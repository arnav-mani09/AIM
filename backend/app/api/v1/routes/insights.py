"""Team insights (advanced shooting stats, zones, team rebound and turnover rates, scouting lines)
for Valley and the Opponent, over the films the coach picks (?upload_ids=1&upload_ids=2) or every
ready film."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.game_upload import GameUpload
from app.models.shot_event import ShotEvent
from app.schemas.insights import InsightsGame, InsightsRead
from app.schemas.shot_event import ShotEventRead
from app.services import insights, shot_events

router = APIRouter(prefix="/teams/{team_id}/insights", tags=["insights"])


@router.get("", response_model=InsightsRead)
def read_insights(
    team_id: int,
    upload_ids: list[int] | None = Query(default=None),
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    query = db.query(GameUpload).filter(GameUpload.team_id == team_id)
    if upload_ids:
        wanted = set(upload_ids)
        query = query.filter(GameUpload.id.in_(wanted))
    uploads = query.order_by(GameUpload.uploaded_at.desc(), GameUpload.id.desc()).all()
    if upload_ids and len(uploads) != len(wanted):
        raise HTTPException(status_code=404, detail="Film not found")
    ready = [u for u in uploads if shot_events.review_status(u) == "ready"]

    shots, plays, play_shots, play_games = [], [], [], 0
    if ready:
        rows = (
            db.query(ShotEvent)
            .filter(ShotEvent.upload_id.in_([u.id for u in ready]),
                    ShotEvent.type.in_(shot_events.VISIBLE_TYPES))
            .all()
        )
        by_upload: dict[int, list[ShotEvent]] = {u.id: [] for u in ready}
        for e in rows:
            by_upload[e.upload_id].append(e)
        for u in ready:
            mine = by_upload[u.id]
            game_shots = [ShotEventRead.model_validate(e).model_dump() for e in mine
                          if e.type == shot_events.SHOT and e.status != "deleted"]
            shots += game_shots
            if shot_events.has_plays(u, mine):
                play_games += 1
                play_shots += game_shots
                plays += [{"type": e.type, "team": e.team, "status": e.status} for e in mine if shot_events.is_play(e)]

    games = [
        InsightsGame(
            upload_id=u.id,
            title=u.title,
            uploaded_at=u.uploaded_at,
            game_matchup=u.game.matchup if u.game else None,
            game_scheduled_at=u.game.scheduled_at if u.game else None,
        )
        for u in ready
    ]
    return InsightsRead(
        games=games,
        skipped=len(uploads) - len(ready) if upload_ids else 0,
        teams=insights.build(shots, len(ready), plays, play_shots, play_games),
        coming_soon=insights.COMING_SOON,
        quality=insights.QUALITY,
    )
