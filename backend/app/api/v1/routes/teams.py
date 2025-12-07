from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.team import Team
from app.models.team_invite import TeamInvite
from app.models.team_membership import TeamMembership
from app.schemas.team import (
    TeamCreate,
    TeamInviteCreate,
    TeamInviteRead,
    TeamJoinRequest,
    TeamMembershipRead,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def _require_membership(db: Session, team_id: int, user_id: int) -> TeamMembership:
    membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")
    return membership


def _generate_invite_code(db: Session) -> str:
    while True:
        candidate = secrets.token_urlsafe(5).upper()
        exists = db.query(TeamInvite.id).filter(TeamInvite.code == candidate).first()
        if not exists:
            return candidate


@router.post("", response_model=TeamMembershipRead, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    team = Team(
        name=payload.name,
        level=payload.level,
        season_label=payload.season_label,
        created_by_id=current_user.id,
    )
    membership = TeamMembership(team=team, user_id=current_user.id, role="coach")
    db.add(team)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.get("", response_model=list[TeamMembershipRead])
def list_my_teams(
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    memberships = (
        db.query(TeamMembership)
        .join(TeamMembership.team)
        .filter(TeamMembership.user_id == current_user.id)
        .order_by(TeamMembership.joined_at.desc())
        .all()
    )
    return memberships


@router.post("/{team_id}/invites", response_model=TeamInviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(
    team_id: int,
    payload: TeamInviteCreate,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    membership = _require_membership(db, team_id, current_user.id)
    if membership.role not in {"coach", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only coaches can create invites")

    expires_at = None
    if payload.expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=payload.expires_in_hours)

    invite = TeamInvite(
        team_id=team_id,
        code=_generate_invite_code(db),
        role=payload.role or "member",
        expires_at=expires_at,
        max_uses=payload.max_uses,
        created_by_id=current_user.id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@router.post("/join", response_model=TeamMembershipRead, status_code=status.HTTP_201_CREATED)
def join_team_by_code(
    payload: TeamJoinRequest,
    db: Session = Depends(deps.get_db_session),
    current_user=Depends(deps.get_current_user),
):
    invite = (
        db.query(TeamInvite)
        .filter(TeamInvite.code == payload.code, TeamInvite.is_active.is_(True))
        .first()
    )
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite expired")
    if invite.max_uses is not None and invite.uses >= invite.max_uses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already used up")

    existing = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == invite.team_id, TeamMembership.user_id == current_user.id)
        .first()
    )
    if existing:
        return existing

    membership = TeamMembership(team_id=invite.team_id, user_id=current_user.id, role=invite.role)
    invite.uses += 1
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership
