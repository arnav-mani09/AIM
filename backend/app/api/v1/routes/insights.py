"""Team insights (advanced shooting stats, zones, team rebound and turnover rates, scouting lines)
for Valley and the Opponent, over the films the coach picks (?upload_ids=1&upload_ids=2) or every
ready film."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.game_upload import GameUpload
from app.models.shot_event import ShotEvent
from app.schemas.insights import InsightsGame, InsightsRead
from app.schemas.shot_event import ShotEventRead
from app.services import insights, shot_events

router = APIRouter(prefix="/teams/{team_id}/insights", tags=["insights"])


def _covered_insights(shots, ready, by_upload):
    reports = insights.build(shots, len(ready))
    coverage = {upload.id: shot_events.play_coverage(upload, by_upload[upload.id]) for upload in ready}
    known = {category: {upload_id for upload_id, states in coverage.items()
                        if states[category] != "unavailable"} for category in ("rebounds", "turnovers")}
    counts = {}
    for category, upload_ids in known.items():
        kinds = ("oreb", "dreb") if category == "rebounds" else ("to",)
        counts[category] = {
            team: insights.count_plays([event for upload_id in upload_ids for event in by_upload[upload_id]
                                       if event.team == team and event.type in kinds])
            for team in insights.TEAMS
        }
    rebound_complete = bool(known["rebounds"]) and all(
        coverage[upload_id]["rebounds"] == "complete" for upload_id in known["rebounds"])
    matched_complete = rebound_complete and known["rebounds"] == known["turnovers"] and all(
        coverage[upload_id]["turnovers"] == "complete" for upload_id in known["turnovers"])
    for team, report in reports.items():
        other = "opponent" if team == "valley" else "valley"
        rebounds = counts["rebounds"][team]
        theirs = counts["rebounds"][other]
        turnovers = counts["turnovers"][team]
        report["play_games"] = len(known["rebounds"] | known["turnovers"])
        report["rebound_games"] = len(known["rebounds"])
        report["turnover_games"] = len(known["turnovers"])
        if known["rebounds"]:
            report.update(oreb=rebounds["oreb"], dreb=rebounds["dreb"], reb=rebounds["oreb"] + rebounds["dreb"])
        if known["turnovers"]:
            report["to"] = turnovers["to"]
        if rebound_complete:
            report["oreb_pct"] = insights.pct(rebounds["oreb"], rebounds["oreb"] + theirs["dreb"])
            report["dreb_pct"] = insights.pct(rebounds["dreb"], rebounds["dreb"] + theirs["oreb"])
        if matched_complete:
            cohort_shots = [ShotEventRead.model_validate(event).model_dump()
                            for upload_id in known["turnovers"] for event in by_upload[upload_id]
                            if event.type == shot_events.SHOT and event.team == team]
            shot_counts = insights.count_shots(cohort_shots)
            possessions = shot_counts["fga"] + 0.44 * shot_counts["fta"] - rebounds["oreb"] + turnovers["to"]
            report["tov_pct"] = insights.pct(turnovers["to"], possessions) if possessions > 0 else None
        report["lines"] += insights.play_lines({**report, "games": report["play_games"]}, team)
        for category in ("rebounds", "turnovers"):
            complete = sum(states[category] == "complete" for states in coverage.values())
            partial = sum(states[category] == "partial" for states in coverage.values())
            if partial or complete < len(ready):
                report["lines"].append(
                    f"{category.capitalize()}: {complete} complete, {partial} partial, "
                    f"{len(ready) - complete - partial} unavailable games. Partial counts are observations, not full-game totals.")
    return reports


@router.get("", response_model=InsightsRead)
def read_insights(
    team_id: int,
    upload_ids: list[int] | None = Query(default=None),
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    query = db.query(GameUpload).filter(GameUpload.team_id == team_id)
    if upload_ids:
        wanted = set(upload_ids)
        query = query.filter(GameUpload.id.in_(wanted))
    uploads = query.order_by(GameUpload.uploaded_at.desc(), GameUpload.id.desc()).all()
    if upload_ids and len(uploads) != len(wanted):
        raise HTTPException(status_code=404, detail="Film not found")
    ready = [u for u in uploads if shot_events.review_status(u) == "ready"]

    shots = []
    by_upload: dict[int, list[ShotEvent]] = {u.id: [] for u in ready}
    if ready:
        rows = (
            db.query(ShotEvent)
            .filter(ShotEvent.upload_id.in_([u.id for u in ready]),
                    ShotEvent.type.in_(shot_events.VISIBLE_TYPES))
            .all()
        )
        for e in rows:
            by_upload[e.upload_id].append(e)
        for u in ready:
            mine = by_upload[u.id]
            game_shots = [ShotEventRead.model_validate(e).model_dump() for e in mine
                          if e.type == shot_events.SHOT and e.status != "deleted"]
            shots += game_shots

    games = [
        InsightsGame(
            upload_id=u.id,
            title=u.title,
            uploaded_at=u.uploaded_at,
            game_matchup=u.game.matchup if u.game else None,
            game_scheduled_at=u.game.scheduled_at if u.game else None,
        )
        for u in ready
    ]
    return InsightsRead(
        games=games,
        skipped=len(uploads) - len(ready) if upload_ids else 0,
        teams=_covered_insights(shots, ready, by_upload),
        coming_soon=insights.COMING_SOON,
        quality=insights.QUALITY,
    )
