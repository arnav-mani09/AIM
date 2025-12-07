from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class TeamMembership(Base):
    __tablename__ = "team_membership"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    role = Column(String, nullable=False, default="member")
    joined_at = Column(DateTime, nullable=False, server_default=func.now(), default=func.now())

    team = relationship("Team", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_membership_team_user"),)
