from collections import Counter

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.game import Game
from app.models.possession import Possession
from app.schemas.stats import GameStats, GameSummary, PlayerInsight, PossessionSplit


class StatsService:
    def __init__(self, db: Session):
        self.db = db

    def get_stats(self, matchup: str | None = None) -> GameStats:
        query = self.db.query(Game).order_by(Game.scheduled_at.desc())
        if matchup:
            query = query.filter(Game.matchup == matchup)
        game = query.first()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")

        possessions = (
            self.db.query(Possession)
            .filter(Possession.game_id == game.id)
            .all()
        )
        total_possessions = len(possessions) or 1

        team_counts: Counter[str] = Counter()
        player_counts: Counter[str] = Counter()
        for poss in possessions:
            team_name = (
                poss.player.team.name
                if poss.player and poss.player.team
                else "Unassigned"
            )
            team_counts[team_name] += 1
            if poss.player:
                player_counts[poss.player.name] += 1

        possession_split = [
            PossessionSplit(team=team, percentage=int(count / total_possessions * 100))
            for team, count in team_counts.items()
        ] or [PossessionSplit(team="Unassigned", percentage=100)]

        insights = [
            PlayerInsight(
                player=name,
                label="High usage",
                detail=f"Involved in {count} possessions",
            )
            for name, count in player_counts.most_common(4)
        ]

        summary = GameSummary(
            offensive_rating=float(total_possessions * 2),
            effective_fg=55.0,
            turnover_rate=12.5,
        )

        return GameStats(
            matchup=game.matchup,
            possession=possession_split,
            insights=insights,
            summary=summary,
        )

    @staticmethod
    def as_dependency(db: Session = Depends(get_db_session)):
        return StatsService(db)
