from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Team = Literal["valley", "opponent"]
ShotType = Literal["fg2", "fg3", "ft"]
PlayType = Literal["oreb", "dreb", "to"]  # team offensive / defensive rebound, turnover
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


class PlayEventRead(BaseModel):
    """A team rebound or turnover. Steals and assists are drafted too but never sent."""

    id: int
    type: PlayType
    t: float
    team: Team
    confidence: float
    status: Status

    class Config:
        from_attributes = True


class PlayEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0, allow_inf_nan=False)
    team: Team
    type: PlayType


class ShotEventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    made: bool | None = None
    team: Team | None = None
    shot_type: ShotType | None = None
    player_number: int | None = None
    status: Status | None = None
    t: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _required_values(self):
        for field in self.model_fields_set - {"player_number"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ShotEventCreate(BaseModel):
    t: float = Field(ge=0, allow_inf_nan=False)
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
    # Team rebounds and turnovers. None for a film drafted before they existed (rerun to add them).
    oreb: int | None = None
    dreb: int | None = None
    reb: int | None = None
    to: int | None = None


class BoxScore(BaseModel):
    valley: TeamLine
    opponent: TeamLine


class ShotEventsRead(BaseModel):
    status: Literal["pending", "ready", "failed"]
    events: list[ShotEventRead]  # shots only
    plays: list[PlayEventRead] = []  # team rebounds and turnovers
    # False for a film drafted before rebounds and turnovers existed: rerun to add them.
    has_plays: bool = False
    box_score: BoxScore
    # Extra to the review screen's contract: true when the jersey colors weren't given, so
    # Valley and Opponent may be swapped (POST .../events/swap-teams fixes it in one call).
    teams_guessed: bool = False
