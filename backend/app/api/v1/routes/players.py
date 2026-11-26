from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.player import Player
from app.models.team_membership import TeamMembership
from app.schemas.player import PlayerCreate, PlayerRead, PlayerUpdate

router = APIRouter(prefix="/teams/{team_id}/players", tags=["players"])


def require_roster_manager(
    membership: TeamMembership = Depends(deps.require_team_membership),
) -> TeamMembership:
    if not membership.can_manage_roster:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners, coaches, or admins can manage players",
        )
    return membership


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
    _membership=Depends(require_roster_manager),
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
    conflict = (
        db.query(Player)
        .filter(Player.team_id == team_id, Player.jersey_number == payload.jersey_number)
        .first()
    )
    if conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Jersey number already in use")
    player = Player(name=payload.name, jersey_number=payload.jersey_number, team_id=team_id)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


@router.patch("/{player_id}", response_model=PlayerRead)
def update_player(
    team_id: int,
    player_id: int,
    payload: PlayerUpdate,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(require_roster_manager),
):
    player = db.query(Player).filter(Player.team_id == team_id, Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    conflict = (
        db.query(Player)
        .filter(
            Player.team_id == team_id,
            Player.jersey_number == payload.jersey_number,
            Player.id != player_id,
        )
        .first()
    )
    if conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Jersey number already in use")
    player.name = payload.name
    player.jersey_number = payload.jersey_number
    db.commit()
    db.refresh(player)
    return player
