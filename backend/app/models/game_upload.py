from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class GameUpload(Base):
    __tablename__ = "game_upload"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    uploaded_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    game_id = Column(Integer, ForeignKey("game.id"), nullable=True)
    title = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now(), default=func.now())

    team = relationship("Team", back_populates="game_uploads")
    uploaded_by = relationship("User")
    game = relationship("Game", back_populates="uploads")
    segments = relationship("FilmSegment", back_populates="upload", cascade="all, delete-orphan")

    @property
    def game_matchup(self) -> str | None:
        return self.game.matchup if self.game else None

    @property
    def game_scheduled_at(self):
        return self.game.scheduled_at if self.game else None
