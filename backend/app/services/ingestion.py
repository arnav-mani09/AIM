import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.player import Player
from app.models.possession import Possession
from app.models.team import Team


class StatsIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def ingest_possession_csv(self, file_path: Path, matchup: str, scheduled_at: datetime) -> Game:
        game = Game(matchup=matchup, scheduled_at=scheduled_at)
        self.db.add(game)
        self.db.flush()

        with file_path.open() as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                player = self._get_or_create_player(row["player"], row["jersey"], row.get("team"))
                possession = Possession(
                    game_id=game.id,
                    player_id=player.id,
                    label=row["label"],
                    outcome=row.get("outcome"),
                )
                self.db.add(possession)
        self.db.commit()
        self.db.refresh(game)
        return game

    def _get_or_create_team(self, team_name: str) -> Team:
        team = self.db.query(Team).filter(Team.name == team_name).first()
        if team:
            return team
        team = Team(name=team_name)
        self.db.add(team)
        self.db.flush()
        return team

    def _get_or_create_player(self, name: str, jersey: str, team_name: str | None) -> Player:
        player = (
            self.db.query(Player)
            .filter(Player.name == name, Player.jersey_number == jersey)
            .first()
        )
        if player:
            return player
        team_id = None
        if team_name:
            team = self._get_or_create_team(team_name)
            team_id = team.id
        player = Player(name=name, jersey_number=jersey, team_id=team_id)
        self.db.add(player)
        self.db.flush()
        return player
