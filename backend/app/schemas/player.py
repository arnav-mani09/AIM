from pydantic import BaseModel


class PlayerCreate(BaseModel):
    name: str
    jersey_number: str


class PlayerRead(BaseModel):
    id: int
    name: str
    jersey_number: str
    team_id: int | None = None

    class Config:
        from_attributes = True
