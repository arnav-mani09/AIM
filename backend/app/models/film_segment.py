from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class FilmSegment(Base):
    __tablename__ = "film_segment"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("game_upload.id"), nullable=False)
    start_second = Column(Integer, nullable=False)
    end_second = Column(Integer, nullable=False)
    label = Column(String, nullable=True)
    confidence = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)

    upload = relationship("GameUpload", back_populates="segments")
    created_by = relationship("User")
