from collections import Counter
from typing import List

from sqlalchemy.orm import Session

from app.models.clip import Clip
from app.models.clip_possession_link import ClipPossessionLink
from app.models.player import Player
from app.models.possession import Possession
from app.models.team import Team


def link_clip_to_possessions(db: Session, clip: Clip) -> None:
    """Attach clip-to-possession links based on overlapping time ranges."""
    if clip.source_start_second is None or clip.source_end_second is None:
        return

    matches: List[Possession] = (
        db.query(Possession)
        .filter(Possession.video_start_second.isnot(None))
        .filter(Possession.video_end_second.isnot(None))
        .filter(Possession.video_end_second > clip.source_start_second)
        .filter(Possession.video_start_second < clip.source_end_second)
        .all()
    )

    if not matches:
        return

    db.query(ClipPossessionLink).filter(ClipPossessionLink.clip_id == clip.id).delete()
    for possession in matches:
        db.add(ClipPossessionLink(clip_id=clip.id, possession_id=possession.id))
    db.commit()


def hydrate_clip_stats(db: Session, clip: Clip) -> Clip:
    """Populate lightweight stats context on a clip ORM object."""
    rows = (
        db.query(
            ClipPossessionLink.possession_id,
            Possession.label,
            Possession.outcome,
            Possession.video_start_second,
            Possession.video_end_second,
            Player.name.label("player_name"),
            Player.jersey_number,
            Team.name.label("team_name"),
        )
        .join(Possession, ClipPossessionLink.possession_id == Possession.id)
        .outerjoin(Player, Possession.player_id == Player.id)
        .outerjoin(Team, Player.team_id == Team.id)
        .filter(ClipPossessionLink.clip_id == clip.id)
        .all()
    )

    contexts = []
    player_counts: Counter[str] = Counter()
    for row in rows:
        player_name = row.player_name
        contexts.append(
            {
                "possession_id": row.possession_id,
                "label": row.label,
                "outcome": row.outcome,
                "player": player_name,
                "team": row.team_name,
                "start_second": row.video_start_second,
                "end_second": row.video_end_second,
            }
        )
        if player_name:
            player_counts[player_name] += 1

    clip.possession_context = contexts
    if contexts:
        clip.stats_summary = {
            "total_possessions": len(contexts),
            "players": [
                {"player": name, "touches": count}
                for name, count in player_counts.most_common(4)
            ],
        }
    else:
        clip.stats_summary = None

    return clip
