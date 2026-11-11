from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class ShotEvent(Base):
    """One drafted shot from the model, and the coach's fixes to it.

    `original` keeps the model's call exactly as drafted (with its confidence parts), so every
    coach fix can become training data later. A shot the coach adds by hand has no original.
    """

    __tablename__ = "shot_event"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("game_upload.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False, default="shot", server_default="shot")
    t = Column(Float, nullable=False)  # seconds into the film
    team = Column(String, nullable=False)  # "valley" or "opponent"
    shot_type = Column(String, nullable=False)  # "fg2", "fg3" or "ft"
    made = Column(Boolean, nullable=False)
    confidence = Column(Float, nullable=False)  # 0 to 1
    player_number = Column(Integer, nullable=True)
    # "draft" (model's call, not reviewed), "confirmed", "fixed" or "deleted"
    status = Column(String, nullable=False, default="draft", server_default="draft")
    original = Column(JSON, nullable=True)
    rim = Column(JSON, nullable=True)  # rim box [x0, y0, x1, y1] in the tracks frame
    updated_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    upload = relationship("GameUpload", back_populates="shot_events")
    updated_by = relationship("User")
