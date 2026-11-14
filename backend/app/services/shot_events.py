"""Drafted events: loading the model's calls, applying coach fixes, and the box score.

The shot_event table holds every kind of drafted event, told apart by `type`:
- "shot": a shot (shot_type fg2, fg3 or ft, made).
- "oreb", "dreb", "to": team offensive and defensive rebounds and turnovers ("plays"). They use
  shot_type "none" and made false.
- "stl", "ast": steals and assists. Drafted and stored for training, but not accurate yet, so
  they are never shown, counted or editable on the site.
"""

from sqlalchemy.orm import Session

from app.models.game_upload import GameUpload
from app.models.shot_event import ShotEvent

CALL_FIELDS = ("made", "team", "shot_type", "player_number", "t")
PLAY_FIELDS = ("team", "t")
SHOT = "shot"
PLAY_TYPES = ("oreb", "dreb", "to")
HIDDEN_TYPES = ("stl", "ast")
VISIBLE_TYPES = (SHOT, *PLAY_TYPES)
PLAY_SHOT_TYPE = "none"


def _get(e, k, default=None):
    return e.get(k, default) if isinstance(e, dict) else getattr(e, k, default)


def is_play(e) -> bool:
    return _get(e, "type") in PLAY_TYPES


def box_score(events, plays_known: bool = True) -> dict:
    """Team totals from events that aren't deleted. Works on rows or dicts. Hidden types
    (steals, assists) never count. plays_known=False (a film drafted before rebounds and
    turnovers existed, not rerun yet) leaves those at None instead of a made-up 0."""
    out = {}
    for team in ("valley", "opponent"):
        mine = [e for e in events if _get(e, "team") == team and _get(e, "status") != "deleted"]
        shots = [e for e in mine if (_get(e, "type") or SHOT) == SHOT]
        fg = [e for e in shots if _get(e, "shot_type") in ("fg2", "fg3")]
        fg3 = [e for e in shots if _get(e, "shot_type") == "fg3"]
        ft = [e for e in shots if _get(e, "shot_type") == "ft"]
        fgm, fg3m, ftm = (sum(1 for e in xs if _get(e, "made")) for xs in (fg, fg3, ft))
        line = {"fgm": fgm, "fga": len(fg), "fg3m": fg3m, "fg3a": len(fg3),
                "ftm": ftm, "fta": len(ft), "pts": 2 * fgm + fg3m + ftm}
        if plays_known:
            n = {k: sum(1 for e in mine if _get(e, "type") == k) for k in PLAY_TYPES}
            line.update(oreb=n["oreb"], dreb=n["dreb"], reb=n["oreb"] + n["dreb"], to=n["to"])
        else:
            line.update(oreb=None, dreb=None, reb=None, to=None)
        out[team] = line
    return out


def has_plays(upload: GameUpload, events=()) -> bool:
    """True when this film's rebounds and turnovers were drafted (the event step ran with them
    and didn't fail on them), or a coach added one by hand."""
    info = (upload.events_info or {}).get("possession")
    if info and not info.get("error"):
        return True
    return any(is_play(e) for e in events)


def review_status(upload: GameUpload) -> str:
    if upload.events_status == "done":
        return "ready"
    if upload.events_status == "error" or upload.detection_status == "error" or upload.status == "error":
        return "failed"
    return "pending"


def _row(upload: GameUpload, e: dict, version) -> ShotEvent:
    kind = e.get("type", SHOT)
    call = {k: e.get(k) for k in ("type", "t", "team", "shot_type", "made", "confidence", "player_number")}
    return ShotEvent(
        upload_id=upload.id, type=kind, t=e["t"], team=e["team"],
        shot_type=e.get("shot_type") or PLAY_SHOT_TYPE, made=bool(e.get("made", False)),
        confidence=e["confidence"], player_number=e.get("player_number"), status="draft",
        original={**call, "parts": e.get("parts"), "detail": e.get("detail"), "version": version},
        rim=e.get("rim"),
    )


def load_events(db: Session, upload: GameUpload, result: dict) -> int:
    """Store the worker's drafted events. Shots and plays (rebounds and turnovers, with the
    hidden steals and assists) are handled apart: a group the coach already reviewed any of is
    kept exactly as is, since a rerun must never throw away their work; a group with only
    model drafts is replaced. So a rerun adds rebounds and turnovers to a film whose shots were
    reviewed before they existed. Returns how many events were stored."""
    old = db.query(ShotEvent).filter(ShotEvent.upload_id == upload.id).all()
    old_shots = [e for e in old if e.type == SHOT]
    old_plays = [e for e in old if e.type != SHOT]
    keep_shots = any(e.status != "draft" for e in old_shots)
    keep_plays = any(e.status != "draft" for e in old_plays if e.type in PLAY_TYPES)
    new = result.get("events", [])
    new_shots = [e for e in new if e.get("type", SHOT) == SHOT]
    new_plays = [e for e in new if e.get("type", SHOT) in PLAY_TYPES + HIDDEN_TYPES]
    old_info = dict(upload.events_info or {})
    flip = bool(old_info.get("teams_swapped"))
    version = result.get("version")
    stored = 0
    for keep, olds, news in ((keep_shots, old_shots, new_shots), (keep_plays, old_plays, new_plays)):
        if keep:
            continue
        for e in olds:
            db.delete(e)
        for e in news:
            row = _row(upload, e, version)
            if flip:
                row.team = "opponent" if row.team == "valley" else "valley"
            db.add(row)
            stored += 1
    info = {k: result.get(k) for k in ("version", "window", "teams_guessed", "valley_basket_first_half",
                                       "votes", "dropped", "three_point")}
    if keep_shots or keep_plays or flip:
        for k in ("teams_guessed", "teams_swapped", "valley_basket_first_half", "votes"):
            if k in old_info:
                info[k] = old_info[k]
    if keep_plays and old_info.get("possession"):
        info["possession"] = old_info["possession"]
    else:
        info["possession"] = result.get("possession")
    upload.events_info = info
    return stored


def apply_patch(event: ShotEvent, patch: dict, user_id: int | None) -> ShotEvent:
    """Changing any part of the call makes it "fixed"; a status on its own is taken as sent
    (confirm, delete, restore). Deleting always wins. For a rebound, switching the team also
    switches offensive and defensive: the shooting team didn't change."""
    changed = False
    fields = PLAY_FIELDS if is_play(event) else CALL_FIELDS
    for k in fields:
        if k in patch and getattr(event, k) != patch[k]:
            if k == "team" and event.type in ("oreb", "dreb"):
                event.type = "dreb" if event.type == "oreb" else "oreb"
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
    """Flip Valley and Opponent on every event (the colors were guessed wrong). A rebound stays
    offensive or defensive: the shooting team flips with it."""
    for e in db.query(ShotEvent).filter(ShotEvent.upload_id == upload.id):
        e.team = "opponent" if e.team == "valley" else "valley"
        e.updated_by_id = user_id
        if e.status == "draft" and e.type in VISIBLE_TYPES:  # the model's call was wrong, so it's a fix
            e.status = "fixed"
    info = dict(upload.events_info or {})
    info["teams_guessed"] = False
    info["teams_swapped"] = not info.get("teams_swapped", False)
    upload.events_info = info
