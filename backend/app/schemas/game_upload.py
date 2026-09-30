from datetime import datetime

from pydantic import BaseModel, Field


class GameUploadRead(BaseModel):
  id: int
  title: str
  notes: str | None = None
  status: str
  storage_url: str
  uploaded_at: datetime
  size_bytes: int | None = None
  has_proxy: bool = False
  processing_error: str | None = None
  duration_seconds: int | None = None
  game_id: int | None = None
  game_matchup: str | None = None
  game_scheduled_at: datetime | None = None

  class Config:
    from_attributes = True


class FilmUploadStart(BaseModel):
  title: str = Field(min_length=1, max_length=200)
  notes: str | None = None
  game_id: int | None = None
  filename: str = Field(min_length=1, max_length=255)
  content_type: str
  size_bytes: int = Field(gt=0)


class FilmUploadStarted(BaseModel):
  upload: GameUploadRead
  part_size: int
  part_count: int


class SignPartsRequest(BaseModel):
  part_numbers: list[int] = Field(min_length=1, max_length=100)


class SignedPart(BaseModel):
  part_number: int
  url: str


class UploadedPart(BaseModel):
  part_number: int
  size: int


class PlaybackUrl(BaseModel):
  url: str
  expires_in: int
