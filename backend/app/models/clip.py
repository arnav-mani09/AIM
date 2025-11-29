from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Clip(Base):
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("game.id"), nullable=False)
    title = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    shared_with = Column(String, nullable=True)

    game = relationship("Game", back_populates="clips")
