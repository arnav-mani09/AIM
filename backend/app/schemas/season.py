from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.shot_event import BoxScore, PlayCoverage, ShotEventRead


class CategoryCoverageCounts(BaseModel):
    complete: int = 0
    partial: int = 0
    unavailable: int = 0


class SeasonPlayCoverage(BaseModel):
    rebounds: CategoryCoverageCounts = Field(default_factory=CategoryCoverageCounts)
    turnovers: CategoryCoverageCounts = Field(default_factory=CategoryCoverageCounts)


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
    has_plays: bool = False
    play_coverage: PlayCoverage = Field(default_factory=PlayCoverage)
    box_score: BoxScore


class SeasonSummary(BaseModel):
    games: list[SeasonGame]  # newest film first
    totals: BoxScore
    plays_games: int = 0
    play_coverage: SeasonPlayCoverage = Field(default_factory=SeasonPlayCoverage)
    pending: int  # films still being processed, not counted yet
    shots: list[SeasonShot]  # every shot that counts, for the season shot chart
