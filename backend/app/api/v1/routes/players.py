from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.player import Player
from app.schemas.player import PlayerCreate, PlayerRead

router = APIRouter(prefix="/teams/{team_id}/players", tags=["players"])


@router.get("", response_model=list[PlayerRead])
def list_players(
    team_id: int,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    return db.query(Player).filter(Player.team_id == team_id).order_by(Player.name).all()


@router.post("", response_model=PlayerRead, status_code=status.HTTP_201_CREATED)
def create_player(
    team_id: int,
    payload: PlayerCreate,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    existing = (
        db.query(Player)
        .filter(
            Player.team_id == team_id,
            Player.name == payload.name,
            Player.jersey_number == payload.jersey_number,
        )
        .first()
    )
    if existing:
        return existing
    player = Player(name=payload.name, jersey_number=payload.jersey_number, team_id=team_id)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player
