from datetime import datetime

from pydantic import BaseModel

from app.schemas.shot_event import BoxScore, ShotEventRead


class SeasonShot(ShotEventRead):
    """A shot from one of the season's films, tagged with the film it came from."""

    upload_id: int


class SeasonGame(BaseModel):
    upload_id: int
    title: str
    uploaded_at: datetime
    game_id: int | None = None
    game_matchup: str | None = None
    game_scheduled_at: datetime | None = None
    shots: int  # shots that count (not deleted)
    reviewed: int  # shots a coach confirmed, fixed or deleted
    has_plays: bool = False  # team rebounds and turnovers drafted for this film
    box_score: BoxScore


class SeasonSummary(BaseModel):
    games: list[SeasonGame]  # newest film first
    totals: BoxScore  # the games' box scores added up (rebounds and turnovers over plays_games films)
    plays_games: int = 0  # films with team rebounds and turnovers
    pending: int  # films still being processed, not counted yet
    shots: list[SeasonShot]  # every shot that counts, for the season shot chart
