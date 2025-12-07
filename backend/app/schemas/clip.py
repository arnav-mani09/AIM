from datetime import datetime

from pydantic import BaseModel


class ClipBase(BaseModel):
    title: str
    notes: str | None = None
    status: str
    storage_url: str


class ClipRead(ClipBase):
    id: int
    team_id: int | None = None
    game_id: int | None = None
    uploaded_at: datetime
    source_upload_id: int | None = None
    source_start_second: int | None = None
    source_end_second: int | None = None
    uploaded_by_id: int | None = None

    class Config:
        from_attributes = True
