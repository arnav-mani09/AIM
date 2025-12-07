from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class TeamInvite(Base):
    __tablename__ = "team_invite"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    code = Column(String, nullable=False, unique=True, index=True)
    role = Column(String, nullable=False, default="member")
    expires_at = Column(DateTime, nullable=True)
    max_uses = Column(Integer, nullable=True)
    uses = Column(Integer, nullable=False, default=0)
    created_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), default=func.now())
    is_active = Column(Boolean, nullable=False, server_default=func.true(), default=True)

    team = relationship("Team", back_populates="invites")
    created_by = relationship("User", foreign_keys=[created_by_id])
