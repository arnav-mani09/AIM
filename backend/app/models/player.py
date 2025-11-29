from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Player(Base):
    id = Column(Integer, primary_key=True, index=True)
    jersey_number = Column(String, nullable=False)
    name = Column(String, nullable=False)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=True)

    team = relationship("Team", back_populates="players")
    possessions = relationship("Possession", back_populates="player")
