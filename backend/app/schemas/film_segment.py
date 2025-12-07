from datetime import datetime

from pydantic import BaseModel


class FilmSegmentBase(BaseModel):
    start_second: int
    end_second: int
    label: str | None = None
    confidence: int | None = None
    notes: str | None = None


class FilmSegmentRead(FilmSegmentBase):
    id: int
    upload_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FilmSegmentCreate(BaseModel):
    start_second: int
    end_second: int
    label: str | None = None
    notes: str | None = None
