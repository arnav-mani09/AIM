from typing import Literal

from pydantic import BaseModel, Field

Team = Literal["valley", "opponent"]
ShotType = Literal["fg2", "fg3", "ft"]
Status = Literal["draft", "confirmed", "fixed", "deleted"]


class ShotEventRead(BaseModel):
    id: int
    type: str
    t: float
    team: Team
    shot_type: ShotType
    made: bool
    confidence: float
    player_number: int | None = None
    status: Status

    class Config:
        from_attributes = True


class ShotEventPatch(BaseModel):
    made: bool | None = None
    team: Team | None = None
    shot_type: ShotType | None = None
    player_number: int | None = None
    status: Status | None = None
    t: float | None = Field(default=None, ge=0)


class ShotEventCreate(BaseModel):
    t: float = Field(ge=0)
    team: Team
    shot_type: ShotType
    made: bool
    player_number: int | None = None


class TeamLine(BaseModel):
    fgm: int
    fga: int
    fg3m: int
    fg3a: int
    ftm: int
    fta: int
    pts: int


class BoxScore(BaseModel):
    valley: TeamLine
    opponent: TeamLine


class ShotEventsRead(BaseModel):
    status: Literal["pending", "ready", "failed"]
    events: list[ShotEventRead]
    box_score: BoxScore
    # Extra to the review screen's contract: true when the jersey colors weren't given, so
    # Valley and Opponent may be swapped (POST .../events/swap-teams fixes it in one call).
    teams_guessed: bool = False
