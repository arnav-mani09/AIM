from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Clip(Base):
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("game.id"), nullable=True)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    title = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    shared_with = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now(), default=func.now())
    source_upload_id = Column(Integer, ForeignKey("game_upload.id"), nullable=True)
    source_start_second = Column(Integer, nullable=True)
    source_end_second = Column(Integer, nullable=True)

    game = relationship("Game", back_populates="clips")
    team = relationship("Team", back_populates="clips")
    uploaded_by = relationship("User")
    source_upload = relationship("GameUpload", foreign_keys=[source_upload_id])
    possessions = relationship(
        "ClipPossessionLink",
        cascade="all, delete-orphan",
        backref="clip",
    )

    @property
    def game_matchup(self) -> str | None:
        return self.game.matchup if self.game else None

    @property
    def game_scheduled_at(self):
        return self.game.scheduled_at if self.game else None
