from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class ClipPossessionLink(Base):
    __tablename__ = "clip_possession_link"

    clip_id = Column(Integer, ForeignKey("clip.id", ondelete="CASCADE"), primary_key=True)
    possession_id = Column(Integer, ForeignKey("possession.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    possession = relationship("Possession")
