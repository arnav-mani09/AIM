from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.possession import Possession
from app.schemas.shot_chart import ShotChart, ZoneStats
from app.services.shot_zones import ZONE_LABELS


class ShotChartService:
    def __init__(self, db: Session):
        self.db = db

    def get_team_shot_chart(self, team_id: int, game_id: int) -> ShotChart:
        rows = (
            self.db.query(Possession)
            .join(Player, Possession.player_id == Player.id)
            .filter(
                Possession.game_id == game_id,
                Player.team_id == team_id,
                Possession.shot_made.is_not(None),
                Possession.review_status == "confirmed",
            )
            .all()
        )

        buckets = {zone: [0, 0] for zone in ZONE_LABELS}
        makes = 0
        attempts = 0
        for possession in rows:
            zone = possession.shot_zone
            if zone not in buckets:
                continue
            buckets[zone][1] += 1
            attempts += 1
            if possession.shot_made:
                buckets[zone][0] += 1
                makes += 1

        zones = [
            ZoneStats(
                zone=zone,
                makes=zone_makes,
                attempts=zone_attempts,
                fg_pct=round(zone_makes / zone_attempts * 100, 1) if zone_attempts else None,
            )
            for zone, (zone_makes, zone_attempts) in buckets.items()
        ]

        return ShotChart(
            game_id=game_id,
            team_id=team_id,
            total_attempts=attempts,
            total_makes=makes,
            overall_fg_pct=round(makes / attempts * 100, 1) if attempts else None,
            zones=zones,
        )
