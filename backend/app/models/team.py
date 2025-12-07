from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Team(Base):
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    level = Column(String, nullable=True)
    season_label = Column(String, nullable=True)
    created_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, default=func.now())

    players = relationship("Player", back_populates="team")
    games_home = relationship("Game", back_populates="home_team", foreign_keys="Game.home_team_id")
    games_away = relationship("Game", back_populates="away_team", foreign_keys="Game.away_team_id")
    memberships = relationship("TeamMembership", back_populates="team", cascade="all, delete-orphan")
    invites = relationship("TeamInvite", back_populates="team", cascade="all, delete-orphan")
    creator = relationship("User", back_populates="teams_created", foreign_keys=[created_by_id])
    clips = relationship("Clip", back_populates="team", cascade="all, delete-orphan")
    game_uploads = relationship("GameUpload", back_populates="team", cascade="all, delete-orphan")
