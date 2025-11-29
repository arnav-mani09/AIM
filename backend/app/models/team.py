from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Team(Base):
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    level = Column(String, nullable=True)

    players = relationship("Player", back_populates="team")
    games_home = relationship("Game", back_populates="home_team", foreign_keys="Game.home_team_id")
    games_away = relationship("Game", back_populates="away_team", foreign_keys="Game.away_team_id")
