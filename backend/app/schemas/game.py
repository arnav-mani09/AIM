from datetime import datetime

from pydantic import BaseModel


class GameCreate(BaseModel):
    matchup: str
    scheduled_at: datetime
    location: str | None = None


class GameRead(BaseModel):
    id: int
    matchup: str
    scheduled_at: datetime
    location: str | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    primary_upload_id: int | None = None

    class Config:
        from_attributes = True
