"""Season view: every film whose shots are ready, with each game's box score, the season
totals and all the shots for a season shot chart, in one call instead of one per film.

Team rebounds and turnovers add up only over films that have them (films drafted before they
existed show None until rerun); plays_games says how many films that is."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.models.game_upload import GameUpload
from app.models.shot_event import ShotEvent
from app.schemas.season import SeasonGame, SeasonShot, SeasonSummary
from app.schemas.shot_event import ShotEventRead
from app.services import shot_events

router = APIRouter(prefix="/teams/{team_id}/season", tags=["season"])

LINE_KEYS = ("fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts")
PLAY_KEYS = ("oreb", "dreb", "reb", "to")


@router.get("", response_model=SeasonSummary)
def read_season(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    uploads = (
        db.query(GameUpload)
        .filter(GameUpload.team_id == team_id)
        .order_by(GameUpload.uploaded_at.desc(), GameUpload.id.desc())
        .all()
    )
    ready = [u for u in uploads if shot_events.review_status(u) == "ready"]
    pending = sum(1 for u in uploads if shot_events.review_status(u) == "pending")

    events_by_upload: dict[int, list[ShotEvent]] = {u.id: [] for u in ready}
    if ready:
        rows = (
            db.query(ShotEvent)
            .filter(ShotEvent.upload_id.in_(list(events_by_upload)),
                    ShotEvent.type.in_(shot_events.VISIBLE_TYPES))
            .order_by(ShotEvent.t.asc(), ShotEvent.id.asc())
            .all()
        )
        for e in rows:
            events_by_upload[e.upload_id].append(e)

    totals = {team: {**dict.fromkeys(LINE_KEYS, 0), **dict.fromkeys(PLAY_KEYS)} for team in ("valley", "opponent")}
    games, shots = [], []
    plays_games = 0
    for u in ready:
        events = events_by_upload[u.id]
        plays_known = shot_events.has_plays(u, events)
        plays_games += plays_known
        box = shot_events.box_score(events, plays_known)
        for team, line in box.items():
            for k in LINE_KEYS:
                totals[team][k] += line[k]
            if plays_known:
                for k in PLAY_KEYS:
                    totals[team][k] = (totals[team][k] or 0) + line[k]
        counted = [e for e in events if e.status != "deleted" and e.type == shot_events.SHOT]
        games.append(SeasonGame(
            upload_id=u.id,
            title=u.title,
            uploaded_at=u.uploaded_at,
            game_id=u.game_id,
            game_matchup=u.game.matchup if u.game else None,
            game_scheduled_at=u.game.scheduled_at if u.game else None,
            shots=len(counted),
            reviewed=sum(1 for e in events if e.status != "draft" and e.type == shot_events.SHOT),
            has_plays=plays_known,
            box_score=box,
        ))
        shots.extend(
            SeasonShot(**ShotEventRead.model_validate(e).model_dump(), upload_id=u.id) for e in counted
        )
    return SeasonSummary(games=games, totals=totals, pending=pending, shots=shots, plays_games=plays_games)
