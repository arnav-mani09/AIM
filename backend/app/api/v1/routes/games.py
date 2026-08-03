from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api import deps
from app.models.game import Game
from app.models.player import Player
from app.models.possession import Possession
from app.schemas.game import GameCreate, GameRead
from app.schemas.possession import PossessionCreate, PossessionRead, PossessionUpdate
from app.schemas.shot_chart import ShotChart
from app.services.game_matching import link_uploads_to_game
from app.services.shot_chart import ShotChartService

router = APIRouter(prefix="/teams/{team_id}/games", tags=["games"])


def _get_team_game(db: Session, team_id: int, game_id: int) -> Game:
    game = (
        db.query(Game)
        .filter(
            Game.id == game_id,
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
        )
        .first()
    )
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return game


def _default_label(payload: PossessionCreate) -> str:
    if payload.label:
        return payload.label
    if payload.shot_made is not None:
        result = "Made" if payload.shot_made else "Missed"
        return f"{result} {payload.shot_value}pt ({payload.shot_zone})"
    return "Possession"


@router.post("", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def create_game(
    team_id: int,
    payload: GameCreate,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    game = Game(
        matchup=payload.matchup,
        scheduled_at=payload.scheduled_at,
        location=payload.location,
        home_team_id=team_id,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    link_uploads_to_game(db, game)
    return game


@router.get("", response_model=list[GameRead])
def list_games(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    return (
        db.query(Game)
        .filter(or_(Game.home_team_id == team_id, Game.away_team_id == team_id))
        .order_by(Game.scheduled_at.desc())
        .all()
    )


@router.get("/{game_id}", response_model=GameRead)
def get_game(
    team_id: int,
    game_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    return _get_team_game(db, team_id, game_id)


@router.get("/{game_id}/possessions", response_model=list[PossessionRead])
def list_possessions(
    team_id: int,
    game_id: int,
    review_status: str | None = Query(default=None),
    shot_only: bool = Query(default=False),
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    game = _get_team_game(db, team_id, game_id)
    query = (
        db.query(Possession)
        .join(Player, Possession.player_id == Player.id)
        .filter(Possession.game_id == game.id, Player.team_id == team_id)
    )
    if review_status:
        query = query.filter(Possession.review_status == review_status)
    if shot_only:
        query = query.filter(Possession.shot_made.is_not(None))
    return query.order_by(Possession.created_at.desc()).all()


@router.post("/{game_id}/possessions", response_model=PossessionRead, status_code=status.HTTP_201_CREATED)
def create_possession(
    team_id: int,
    game_id: int,
    payload: PossessionCreate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    _membership=Depends(deps.require_team_membership),
):
    game = _get_team_game(db, team_id, game_id)
    if payload.player_id is not None:
        player = (
            db.query(Player)
            .filter(Player.id == payload.player_id, Player.team_id == team_id)
            .first()
        )
        if not player:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Player is not on this team")

    possession = Possession(
        game_id=game.id,
        player_id=payload.player_id,
        label=_default_label(payload),
        outcome=payload.outcome,
        shot_made=payload.shot_made,
        shot_zone=payload.shot_zone,
        shot_x=payload.shot_x,
        shot_y=payload.shot_y,
        shot_value=payload.shot_value,
        video_start_second=payload.video_start_second,
        video_end_second=payload.video_end_second,
        source="manual",
        review_status="confirmed",
        created_by_id=current_user.id,
    )
    db.add(possession)
    db.commit()
    db.refresh(possession)
    return possession


@router.patch("/{game_id}/possessions/{possession_id}", response_model=PossessionRead)
def update_possession(
    team_id: int,
    game_id: int,
    possession_id: int,
    payload: PossessionUpdate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
    membership=Depends(deps.require_team_membership),
):
    game = _get_team_game(db, team_id, game_id)
    possession = (
        db.query(Possession)
        .join(Player, Possession.player_id == Player.id)
        .filter(
            Possession.id == possession_id,
            Possession.game_id == game.id,
            Player.team_id == team_id,
        )
        .first()
    )
    if not possession:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Possession not found")

    data = payload.model_dump(exclude_unset=True)
    review_status = data.pop("review_status", None)
    if review_status is not None and membership.role not in {"coach", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only coaches can confirm/reject shots")

    for field, value in data.items():
        setattr(possession, field, value)

    if review_status is not None:
        possession.review_status = review_status
        possession.reviewed_by_id = current_user.id
        possession.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(possession)
    return possession


@router.delete("/{game_id}/possessions/{possession_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_possession(
    team_id: int,
    game_id: int,
    possession_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    game = _get_team_game(db, team_id, game_id)
    possession = (
        db.query(Possession)
        .filter(Possession.id == possession_id, Possession.game_id == game.id)
        .first()
    )
    if not possession:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Possession not found")
    db.delete(possession)
    db.commit()
    return None


@router.get("/{game_id}/shot-chart", response_model=ShotChart)
def get_shot_chart(
    team_id: int,
    game_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    _get_team_game(db, team_id, game_id)
    return ShotChartService(db).get_team_shot_chart(team_id, game_id)
