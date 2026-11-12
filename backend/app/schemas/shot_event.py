from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    # Where the shooter's feet were, in feet on a half court with the rim at (0, 0): x to the right
    # as you face the basket, y out toward half court. Rough (from the film, not a court model), and
    # only for field goals the model drafted with the film read. Coach fixes don't move it.
    x: float | None = None
    y: float | None = None
    zone: str | None = None

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _spot_from_original(cls, data):
        """Read the court spot out of the model's original call (original.detail), so it needs no
        columns of its own."""
        if isinstance(data, dict):
            return data
        detail = ((getattr(data, "original", None) or {}).get("detail")) or {}
        fields = {k: getattr(data, k, None) for k in cls.model_fields if k not in ("x", "y", "zone")}
        return {**fields, "x": detail.get("court_x"), "y": detail.get("court_y"), "zone": detail.get("zone")}


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
