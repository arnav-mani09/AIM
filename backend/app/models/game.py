from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Game(Base):
    id = Column(Integer, primary_key=True, index=True)
    matchup = Column(String, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    location = Column(String, nullable=True)
    home_team_id = Column(Integer, ForeignKey("team.id"), nullable=True)
    away_team_id = Column(Integer, ForeignKey("team.id"), nullable=True)

    possessions = relationship("Possession", back_populates="game", cascade="all, delete-orphan")
    clips = relationship("Clip", back_populates="game", cascade="all, delete-orphan")
    uploads = relationship("GameUpload", back_populates="game")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="games_home")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="games_away")
