from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    upload_id: int | None = None  # the game the coach is looking at, if any
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatCitation(BaseModel):
    event_id: int
    upload_id: int
    t: float  # seconds into the film


class ChatResponse(BaseModel):
    answer: str  # may contain [[event:ID]] markers, one per citation
    citations: list[ChatCitation]
