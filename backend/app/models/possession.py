from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Possession(Base):
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("game.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("player.id"), nullable=True)
    label = Column(String, nullable=False)
    outcome = Column(String, nullable=True)
    video_start_second = Column(Integer, nullable=True)
    video_end_second = Column(Integer, nullable=True)

    shot_made = Column(Boolean, nullable=True)
    shot_zone = Column(String, nullable=True)
    shot_x = Column(Float, nullable=True)
    shot_y = Column(Float, nullable=True)
    shot_value = Column(Integer, nullable=True)

    source = Column(String, nullable=False, server_default="manual")
    review_status = Column(String, nullable=False, server_default="confirmed")
    created_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    game = relationship("Game", back_populates="possessions")
    player = relationship("Player", back_populates="possessions")
    created_by = relationship("User", foreign_keys=[created_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])

    @property
    def player_name(self) -> str | None:
        return self.player.name if self.player else None
