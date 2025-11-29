from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.schemas.stats import GameStats
from app.services.stats import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/game", response_model=GameStats)
def read_game_stats(
    matchup: str | None = Query(default=None),
    stats_service: StatsService = Depends(StatsService.as_dependency),
):
    return stats_service.get_stats(matchup)
