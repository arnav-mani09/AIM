from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.shot_zones import ZONE_LABELS

PossessionSource = Literal["manual", "csv", "ai"]
ReviewStatus = Literal["pending", "confirmed", "rejected"]


def _validate_zone(value: str | None) -> str | None:
    if value is not None and value not in ZONE_LABELS:
        raise ValueError(f"shot_zone must be one of {ZONE_LABELS}")
    return value


class PossessionCreate(BaseModel):
    player_id: int | None = None
    label: str | None = None
    outcome: str | None = None
    shot_made: bool | None = None
    shot_zone: str | None = None
    shot_x: float | None = Field(default=None, ge=0, le=1)
    shot_y: float | None = Field(default=None, ge=0, le=1)
    shot_value: Literal[2, 3] | None = None
    video_start_second: int | None = None
    video_end_second: int | None = None

    _validate_shot_zone = field_validator("shot_zone")(_validate_zone)

    @model_validator(mode="after")
    def _validate_shot_fields(self):
        if self.shot_made is not None:
            if self.shot_value is None:
                raise ValueError("shot_value is required when logging a shot attempt")
            if self.shot_zone is None:
                raise ValueError("shot_zone is required when logging a shot attempt")
            if self.player_id is None:
                # A shot's team is derived from its player (see ShotChartService's
                # join on Player.team_id) — an unassigned shot can't be attributed
                # to a team, so it would silently vanish from every team-scoped
                # list/chart query. Every shot needs a shooter; other possession
                # types (e.g. team-level turnovers) may still omit a player.
                raise ValueError("player_id is required when logging a shot attempt")
        return self


class PossessionUpdate(BaseModel):
    label: str | None = None
    outcome: str | None = None
    player_id: int | None = None
    shot_made: bool | None = None
    shot_zone: str | None = None
    shot_x: float | None = Field(default=None, ge=0, le=1)
    shot_y: float | None = Field(default=None, ge=0, le=1)
    shot_value: Literal[2, 3] | None = None
    video_start_second: int | None = None
    video_end_second: int | None = None
    review_status: ReviewStatus | None = None

    _validate_shot_zone = field_validator("shot_zone")(_validate_zone)


class PossessionRead(BaseModel):
    id: int
    game_id: int
    player_id: int | None = None
    player_name: str | None = None
    label: str
    outcome: str | None = None
    shot_made: bool | None = None
    shot_zone: str | None = None
    shot_x: float | None = None
    shot_y: float | None = None
    shot_value: int | None = None
    video_start_second: int | None = None
    video_end_second: int | None = None
    source: str
    review_status: str
    created_by_id: int | None = None
    reviewed_by_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
