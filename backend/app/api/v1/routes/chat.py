import anthropic
import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat

router = APIRouter(prefix="/teams/{team_id}/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def ask(
    team_id: int,
    payload: ChatRequest,
    db: Session = Depends(deps.get_db_session),
    _membership=Depends(deps.require_team_membership),
):
    """Answer a coach's question from this team's AIM data."""
    try:
        client = chat.get_client()
        chat.take_daily_slot(team_id)
        return chat.answer(db, team_id, [m.model_dump() for m in payload.messages], payload.upload_id, client=client)
    except chat.ChatUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except anthropic.RateLimitError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The assistant is busy right now. Try again in a minute.")
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        sentry_sdk.capture_exception(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="The assistant couldn't answer just now. Try again.")
