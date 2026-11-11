"""Coach chatbot: answers questions about a team's games from AIM's own data.

Claude never sees the database. It calls the tools below, which only read the asking team's
uploads, and it's told to state only numbers that came back from a tool. When it talks about
a specific shot it writes [[event:ID]]; the API keeps only ids that belong to the team and
returns them as citations, so the page can turn each one into a clickable film time.
"""

import re
from collections import defaultdict
from datetime import date

import anthropic
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game_upload import GameUpload
from app.models.shot_event import ShotEvent
from app.services import shot_events

MAX_TURNS = 6  # tool rounds per question
MAX_HISTORY = 20  # messages kept from the conversation
MAX_CHARS = 4000  # per message from the page
SHOT_LIMIT = 60  # rows list_shots returns at most

CITE = re.compile(r"\[\[event:(\d+)\]\]")

SYSTEM = """You are AIM's assistant for high school basketball coaches. Coaches ask about their own games.

Facts you must keep straight:
- "Valley" is the coach's team. The other team is always "Opponent".
- Stats come from AIM's drafted shots: made or missed, team, 2-pointer (fg2), 3-pointer (fg3) or free throw (ft), \
the time in the film, and sometimes the shooter's jersey number. A coach may have reviewed and fixed them.
- Field goals (FG) include both 2s and 3s. Points = 2 per made 2, 3 per made 3, 1 per made free throw.
- AIM doesn't track rebounds, assists, turnovers, steals or fouls yet.

Rules:
- Use the tools to get every number. Never guess, estimate or round a stat, and never use outside knowledge about these teams or players.
- If the data can't answer the question (for example, most shots have no jersey number yet), say so plainly and give what you do have.
- If shots are still drafts that no coach has reviewed, say once that the numbers may change after review.
- When you point to specific shots, cite each one as [[event:ID]] using the id from the tools, right after the words about it. Cite at most 8.
- Answer in plain, short sentences a busy coach can read in a few seconds. Show shooting as made/attempted, like 5/12.
- Don't use em dashes."""

TOOLS = [
    {
        "name": "list_games",
        "description": "List this team's uploaded games, newest first, with each game's id, title, upload date, "
                       "whether its shots are ready, and the score from AIM's shots. Use it to find a game id.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "get_box_score",
        "description": "Box score for one game: shooting and points for Valley and Opponent, per-player lines for "
                       "shots that have a jersey number, how many shots have no number, and how many shots a "
                       "coach has reviewed.",
        "input_schema": {
            "type": "object",
            "properties": {"upload_id": {"type": "integer", "description": "Game id from list_games"}},
            "required": ["upload_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "list_shots",
        "description": "Individual shots in one game, oldest first, matching the filters. Each has an id (for "
                       "citing), film time in seconds, team, shot type, made, jersey number (null if unknown) and "
                       f"review status. Returns at most {SHOT_LIMIT} shots plus the total that matched.",
        "input_schema": {
            "type": "object",
            "properties": {
                "upload_id": {"type": "integer"},
                "team": {"type": ["string", "null"], "description": "\"valley\", \"opponent\", or null for both"},
                "made": {"type": ["boolean", "null"]},
                "shot_type": {"type": ["string", "null"], "description": "\"fg2\", \"fg3\", \"ft\", or null for all"},
                "player_number": {"type": ["integer", "null"]},
                "start_seconds": {"type": ["number", "null"], "description": "Film time from, in seconds"},
                "end_seconds": {"type": ["number", "null"], "description": "Film time to, in seconds"},
            },
            "required": ["upload_id", "team", "made", "shot_type", "player_number", "start_seconds", "end_seconds"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "compare_games",
        "description": "Box scores for several games side by side (2 to 10 game ids).",
        "input_schema": {
            "type": "object",
            "properties": {"upload_ids": {"type": "array", "items": {"type": "integer"}}},
            "required": ["upload_ids"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class ChatUnavailable(Exception):
    """No API key configured, or the daily limit is reached. The message is safe to show."""


# Questions asked per team per day. In memory: one Render instance, and a restart only resets
# the count early, which is fine for a cost guard.
_daily = defaultdict(int)


def take_daily_slot(team_id: int) -> None:
    limit = get_settings().chat_daily_limit
    key = (team_id, date.today().isoformat())
    if _daily[key] >= limit:
        raise ChatUnavailable(f"Your team has asked {limit} questions today, the daily limit. It resets tomorrow.")
    _daily[key] += 1


def get_client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise ChatUnavailable("The chat assistant isn't set up yet.")
    return anthropic.Anthropic(api_key=key)


# ---- Tools: every read is limited to the asking team's uploads ----

def _upload(db: Session, team_id: int, upload_id) -> GameUpload | None:
    if not isinstance(upload_id, int):
        return None
    return db.query(GameUpload).filter(GameUpload.id == upload_id, GameUpload.team_id == team_id).first()


def _live_events(db: Session, upload_id: int) -> list[ShotEvent]:
    return (db.query(ShotEvent)
            .filter(ShotEvent.upload_id == upload_id, ShotEvent.status != "deleted")
            .order_by(ShotEvent.t.asc(), ShotEvent.id.asc()).all())


def _line(events) -> dict:
    fg = [e for e in events if e.shot_type in ("fg2", "fg3")]
    fg3 = [e for e in events if e.shot_type == "fg3"]
    ft = [e for e in events if e.shot_type == "ft"]
    fgm, fg3m, ftm = (sum(1 for e in xs if e.made) for xs in (fg, fg3, ft))
    return {"fg": f"{fgm}/{len(fg)}", "fg3": f"{fg3m}/{len(fg3)}", "ft": f"{ftm}/{len(ft)}",
            "pts": 2 * fgm + fg3m + ftm}


def _box(db: Session, upload: GameUpload) -> dict:
    events = _live_events(db, upload.id)
    teams = {}
    for team in ("valley", "opponent"):
        mine = [e for e in events if e.team == team]
        players = defaultdict(list)
        for e in mine:
            if e.player_number is not None:
                players[e.player_number].append(e)
        teams[team] = {
            **_line(mine),
            "players": [{"number": n, **_line(xs)} for n, xs in sorted(players.items())],
            "shots_without_number": sum(1 for e in mine if e.player_number is None),
        }
    return {
        "upload_id": upload.id, "title": upload.title,
        "shots_status": shot_events.review_status(upload),
        "shots": len(events),
        "reviewed_by_coach": sum(1 for e in events if e.status in ("confirmed", "fixed")),
        "valley": teams["valley"], "opponent": teams["opponent"],
    }


def run_tool(db: Session, team_id: int, name: str, args: dict) -> dict:
    if name == "list_games":
        uploads = (db.query(GameUpload).filter(GameUpload.team_id == team_id)
                   .order_by(GameUpload.uploaded_at.desc()).limit(50).all())
        games = []
        for u in uploads:
            score = shot_events.box_score(_live_events(db, u.id))
            games.append({"upload_id": u.id, "title": u.title,
                          "uploaded": u.uploaded_at.date().isoformat() if u.uploaded_at else None,
                          "shots_status": shot_events.review_status(u),
                          "valley_pts": score["valley"]["pts"], "opponent_pts": score["opponent"]["pts"]})
        return {"games": games}

    if name == "get_box_score":
        upload = _upload(db, team_id, args.get("upload_id"))
        return _box(db, upload) if upload else {"error": "No game with that id for this team."}

    if name == "list_shots":
        upload = _upload(db, team_id, args.get("upload_id"))
        if not upload:
            return {"error": "No game with that id for this team."}
        rows = _live_events(db, upload.id)
        filters = {k: args.get(k) for k in ("team", "made", "shot_type", "player_number")}
        for key, want in filters.items():
            if want is not None:
                rows = [e for e in rows if getattr(e, key) == want]
        if args.get("start_seconds") is not None:
            rows = [e for e in rows if e.t >= args["start_seconds"]]
        if args.get("end_seconds") is not None:
            rows = [e for e in rows if e.t <= args["end_seconds"]]
        return {"matched": len(rows), "shots": [
            {"id": e.id, "t": round(e.t, 1), "team": e.team, "shot_type": e.shot_type, "made": e.made,
             "player_number": e.player_number, "status": e.status} for e in rows[:SHOT_LIMIT]]}

    if name == "compare_games":
        ids = args.get("upload_ids") or []
        if not 2 <= len(ids) <= 10:
            return {"error": "Give 2 to 10 game ids."}
        out = []
        for i in ids:
            upload = _upload(db, team_id, i)
            out.append(_box(db, upload) if upload else {"upload_id": i, "error": "No game with that id for this team."})
        return {"games": out}

    return {"error": f"Unknown tool {name}"}


# ---- The conversation ----

def _clean_history(messages: list[dict]) -> list[dict]:
    """Plain text turns from the page, alternating, ending with the coach's question."""
    out = []
    for m in messages[-MAX_HISTORY:]:
        role, text = m.get("role"), str(m.get("content") or "").strip()[:MAX_CHARS]
        if role not in ("user", "assistant") or not text:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    if not out or out[-1]["role"] != "user":
        raise ValueError("The last message must be the coach's question.")
    return out


def answer(db: Session, team_id: int, messages: list[dict], upload_id: int | None = None, client=None) -> dict:
    """Run one question through Claude and the tools. Returns the answer text (with [[event:ID]]
    markers) and the citations the page can link to the film."""
    import json

    history = _clean_history(messages)
    client = client or get_client()
    system = SYSTEM
    if upload_id is not None:
        upload = _upload(db, team_id, upload_id)
        if upload:
            system += f'\n\nThe coach is looking at the game "{upload.title}" (upload_id {upload.id}). ' \
                      "Questions without another game named are about this one."

    convo = list(history)
    response = None
    for _ in range(MAX_TURNS):
        response = client.beta.messages.create(
            model=get_settings().chat_model,
            max_tokens=4000,
            system=system,
            tools=TOOLS,
            messages=convo,
            output_config={"effort": "low"},
            # If a safety check declines the question, Anthropic retries it on its recommended model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason != "tool_use":
            break
        convo.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = run_tool(db, team_id, block.name, dict(block.input or {}))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            except Exception as exc:  # a broken tool shouldn't sink the whole answer
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": f"Tool failed: {type(exc).__name__}"})
        convo.append({"role": "user", "content": results})

    if response is None or response.stop_reason == "refusal":
        return {"answer": "Sorry, I can't help with that one. Try asking about shooting or points in a game.",
                "citations": []}
    text = "\n\n".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "tool_use" or not text:
        return {"answer": "Sorry, that question took too many steps. Try asking it in a simpler way.",
                "citations": []}
    cited = citations(db, team_id, text)
    known = {c["event_id"] for c in cited}
    # Drop markers for shots that aren't this team's (or don't exist), so the page never shows a dead link.
    text = CITE.sub(lambda m: m.group(0) if int(m.group(1)) in known else "", text)
    return {"answer": text, "citations": cited}


def citations(db: Session, team_id: int, text: str) -> list[dict]:
    """Shots cited in the answer that belong to this team, in the order they appear."""
    ids = list(dict.fromkeys(int(i) for i in CITE.findall(text)))
    if not ids:
        return []
    rows = (db.query(ShotEvent).join(GameUpload, GameUpload.id == ShotEvent.upload_id)
            .filter(ShotEvent.id.in_(ids), GameUpload.team_id == team_id).all())
    found = {e.id: e for e in rows}
    return [{"event_id": i, "upload_id": found[i].upload_id, "t": found[i].t} for i in ids if i in found]
