from datetime import datetime

from pydantic import BaseModel


class ClipBase(BaseModel):
    title: str
    notes: str | None = None
    status: str
    storage_url: str


class ClipPlayerTouch(BaseModel):
    player: str
    touches: int


class ClipStatSummary(BaseModel):
    total_possessions: int
    players: list[ClipPlayerTouch]


class ClipPossessionContext(BaseModel):
    possession_id: int
    label: str
    outcome: str | None = None
    player: str | None = None
    team: str | None = None
    start_second: int | None = None
    end_second: int | None = None


class ClipRead(ClipBase):
    id: int
    team_id: int | None = None
    game_id: int | None = None
    uploaded_at: datetime
    source_upload_id: int | None = None
    source_start_second: int | None = None
    source_end_second: int | None = None
    uploaded_by_id: int | None = None
    game_matchup: str | None = None
    game_scheduled_at: datetime | None = None
    stats_summary: ClipStatSummary | None = None
    possession_context: list[ClipPossessionContext] = []

    class Config:
        from_attributes = True
