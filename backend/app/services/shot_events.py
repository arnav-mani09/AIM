"""Drafted shot events: loading the model's calls, applying coach fixes, and the box score."""

from sqlalchemy.orm import Session

from app.models.game_upload import GameUpload
from app.models.shot_event import ShotEvent

CALL_FIELDS = ("made", "team", "shot_type", "player_number", "t")


def box_score(events) -> dict:
    """Team totals from events that aren't deleted. Works on rows or dicts."""
    get = (lambda e, k: e[k]) if events and isinstance(events[0], dict) else getattr
    out = {}
    for team in ("valley", "opponent"):
        mine = [e for e in events if get(e, "team") == team and get(e, "status") != "deleted"]
        fg = [e for e in mine if get(e, "shot_type") in ("fg2", "fg3")]
        fg3 = [e for e in mine if get(e, "shot_type") == "fg3"]
        ft = [e for e in mine if get(e, "shot_type") == "ft"]
        fgm, fg3m, ftm = (sum(1 for e in xs if get(e, "made")) for xs in (fg, fg3, ft))
        out[team] = {"fgm": fgm, "fga": len(fg), "fg3m": fg3m, "fg3a": len(fg3),
                     "ftm": ftm, "fta": len(ft), "pts": 2 * fgm + fg3m + ftm}
    return out


def review_status(upload: GameUpload) -> str:
    if upload.events_status == "done":
        return "ready"
    if upload.events_status == "error" or upload.detection_status == "error" or upload.status == "error":
        return "failed"
    return "pending"


def load_events(db: Session, upload: GameUpload, result: dict) -> int:
    """Store the worker's drafted events. If the coach already reviewed some, keep everything
    as is: a rerun must never throw away their work. Returns how many were stored."""
    existing = db.query(ShotEvent).filter(ShotEvent.upload_id == upload.id)
    if existing.filter(ShotEvent.status != "draft").count():
        return 0
    existing.delete(synchronize_session=False)
    for e in result.get("events", []):
        call = {k: e.get(k) for k in ("type", "t", "team", "shot_type", "made", "confidence", "player_number")}
        db.add(ShotEvent(
            upload_id=upload.id, type=e.get("type", "shot"), t=e["t"], team=e["team"], shot_type=e["shot_type"],
            made=e["made"], confidence=e["confidence"], player_number=e.get("player_number"), status="draft",
            original={**call, "parts": e.get("parts"), "detail": e.get("detail"), "version": result.get("version")},
            rim=e.get("rim"),
        ))
    upload.events_info = {k: result.get(k) for k in ("version", "window", "teams_guessed", "valley_basket_first_half",
                                                      "votes", "dropped", "three_point")}
    return len(result.get("events", []))


def apply_patch(event: ShotEvent, patch: dict, user_id: int | None) -> ShotEvent:
    """Changing any part of the call makes it "fixed"; a status on its own is taken as sent
    (confirm, delete, restore). Deleting always wins."""
    changed = False
    for k in CALL_FIELDS:
        if k in patch and getattr(event, k) != patch[k]:
            setattr(event, k, patch[k])
            changed = True
    status = patch.get("status")
    if status == "deleted":
        event.status = "deleted"
    elif changed:
        event.status = "fixed"
    elif status:
        event.status = status
    event.updated_by_id = user_id
    return event


def swap_teams(db: Session, upload: GameUpload, user_id: int | None) -> None:
    """Flip Valley and Opponent on every shot (the colors were guessed wrong)."""
    for e in db.query(ShotEvent).filter(ShotEvent.upload_id == upload.id):
        e.team = "opponent" if e.team == "valley" else "valley"
        e.updated_by_id = user_id
        if e.status == "draft":  # the model's call was wrong, so it's a fix
            e.status = "fixed"
    info = dict(upload.events_info or {})
    info["teams_guessed"] = False
    info["teams_swapped"] = not info.get("teams_swapped", False)
    upload.events_info = info
