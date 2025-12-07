from datetime import datetime

from pydantic import BaseModel


class GameUploadCreate(BaseModel):
  title: str
  notes: str | None = None


class GameUploadRead(BaseModel):
  id: int
  title: str
  notes: str | None = None
  status: str
  storage_url: str
  uploaded_at: datetime
  duration_seconds: int | None = None

  class Config:
    from_attributes = True
