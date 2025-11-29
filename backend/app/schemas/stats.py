from pydantic import BaseModel


class PossessionSplit(BaseModel):
    team: str
    percentage: int


class PlayerInsight(BaseModel):
    player: str
    label: str
    detail: str


class GameSummary(BaseModel):
    offensive_rating: float
    effective_fg: float
    turnover_rate: float


class GameStats(BaseModel):
    matchup: str
    possession: list[PossessionSplit]
    insights: list[PlayerInsight]
    summary: GameSummary

    class Config:
        from_attributes = True
