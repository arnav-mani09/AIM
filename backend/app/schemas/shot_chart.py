from pydantic import BaseModel


class ZoneStats(BaseModel):
    zone: str
    attempts: int
    makes: int
    fg_pct: float | None = None


class ShotChart(BaseModel):
    game_id: int
    team_id: int
    total_attempts: int
    total_makes: int
    overall_fg_pct: float | None = None
    zones: list[ZoneStats]
