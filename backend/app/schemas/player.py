from typing import Annotated

from pydantic import BaseModel, StringConstraints


class PlayerCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    jersey_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]


class PlayerUpdate(PlayerCreate):
    pass


class PlayerRead(BaseModel):
    id: int
    name: str
    jersey_number: str
    team_id: int | None = None

    class Config:
        from_attributes = True
