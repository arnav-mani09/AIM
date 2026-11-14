from datetime import datetime

from pydantic import BaseModel


class ZoneRow(BaseModel):
    zone: str  # rim, paint, midrange, corner3, above_break3, unknown (same names as ml/tools/insights.py)
    label: str
    attempts: int
    makes: int
    fg_pct: float | None = None
    share: float | None = None  # percent of the team's field goal tries
    points: int
    small_sample: bool


class TeamInsights(BaseModel):
    games: int
    pts: int
    fgm: int
    fga: int
    fg2m: int
    fg2a: int
    fg3m: int
    fg3a: int
    ftm: int
    fta: int
    pts_per_game: float | None = None
    fg_pct: float | None = None
    fg3_pct: float | None = None
    ft_pct: float | None = None
    efg_pct: float | None = None  # (FGM + 0.5 x 3PM) / FGA
    ts_pct: float | None = None  # PTS / (2 x (FGA + 0.44 x FTA))
    ft_rate: float | None = None  # FTA / FGA
    fg3a_rate: float | None = None  # 3PA / FGA
    small_sample: bool
    # Team rebounds and turnovers, over the films that have them (play_games); None without any.
    # Rated "fair" (see InsightsRead.quality).
    play_games: int = 0
    oreb: int | None = None
    dreb: int | None = None
    reb: int | None = None
    to: int | None = None
    tov_pct: float | None = None  # TO / (FGA + 0.44 x FTA - OREB + TO)
    oreb_pct: float | None = None  # OREB / (OREB + other team's DREB)
    dreb_pct: float | None = None  # DREB / (DREB + other team's OREB)
    zones: list[ZoneRow]
    lines: list[str]  # plain-language scouting lines


class InsightsGame(BaseModel):
    upload_id: int
    title: str
    uploaded_at: datetime
    game_matchup: str | None = None
    game_scheduled_at: datetime | None = None


class TeamsInsights(BaseModel):
    valley: TeamInsights
    opponent: TeamInsights


class InsightsRead(BaseModel):
    games: list[InsightsGame]  # the films counted, newest first
    skipped: int  # asked-for films whose shots aren't ready yet
    teams: TeamsInsights
    coming_soon: list[str]  # stats not shown yet
    quality: dict[str, str] = {}  # stat name -> "fair" for stats to read as rough (rebounds, turnovers)
