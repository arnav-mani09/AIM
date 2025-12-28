from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Possession(Base):
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("game.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("player.id"), nullable=True)
    label = Column(String, nullable=False)
    outcome = Column(String, nullable=True)
    video_start_second = Column(Integer, nullable=True)
    video_end_second = Column(Integer, nullable=True)

    game = relationship("Game", back_populates="possessions")
    player = relationship("Player", back_populates="possessions")
