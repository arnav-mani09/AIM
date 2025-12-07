from datetime import datetime

from pydantic import BaseModel


class TeamBase(BaseModel):
    name: str
    level: str | None = None
    season_label: str | None = None


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class TeamMembershipRead(BaseModel):
    id: int
    role: str
    joined_at: datetime
    team: TeamRead

    class Config:
        from_attributes = True


class TeamInviteCreate(BaseModel):
    role: str | None = None
    expires_in_hours: int | None = None
    max_uses: int | None = None


class TeamInviteRead(BaseModel):
    id: int
    code: str
    role: str
    expires_at: datetime | None = None
    max_uses: int | None = None
    uses: int

    class Config:
        from_attributes = True


class TeamJoinRequest(BaseModel):
    code: str
