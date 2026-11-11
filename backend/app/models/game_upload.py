from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class GameUpload(Base):
    __tablename__ = "game_upload"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    uploaded_by_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    game_id = Column(Integer, ForeignKey("game.id"), nullable=True)
    title = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    # Expected size and the R2 multipart upload id, set while status == "uploading".
    size_bytes = Column(BigInteger, nullable=True)
    storage_upload_id = Column(String, nullable=True)
    # 720p playback copy and thumbnail made by the Modal worker, plus its job.
    proxy_url = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    processing_job_id = Column(String, nullable=True)
    processing_error = Column(Text, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    # Player detection on the Modal GPU, started after the proxy is ready.
    # detection_status: None (not started), "running", "done", "error".
    detection_status = Column(String, nullable=True)
    detection_job_id = Column(String, nullable=True)
    detection_error = Column(Text, nullable=True)
    detection_started_at = Column(DateTime, nullable=True)
    detection_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    detection_model = Column(String, nullable=True)
    tracks_url = Column(String, nullable=True)
    # Drafted shot events, made from the tracks after detection (film_worker.make_events).
    # events_status: None (not started), "running", "done", "error".
    events_status = Column(String, nullable=True)
    events_job_id = Column(String, nullable=True)
    events_error = Column(Text, nullable=True)
    events_started_at = Column(DateTime, nullable=True)
    events_url = Column(String, nullable=True)
    # Game window, halftime, basket vote and whether the team colors were guessed.
    events_info = Column(JSON, nullable=True)
    # Jersey colors ("white", "light blue", ...) so the model knows which team is Valley.
    # Optional: without them the teams are a guess the coach can flip in one click.
    valley_jersey = Column(String, nullable=True)
    opponent_jersey = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now(), default=func.now())

    team = relationship("Team", back_populates="game_uploads")
    uploaded_by = relationship("User")
    game = relationship("Game", back_populates="uploads")
    segments = relationship("FilmSegment", back_populates="upload", cascade="all, delete-orphan")
    shot_events = relationship("ShotEvent", back_populates="upload", cascade="all, delete-orphan")

    @property
    def has_proxy(self) -> bool:
        return self.proxy_url is not None

    @property
    def game_matchup(self) -> str | None:
        return self.game.matchup if self.game else None

    @property
    def game_scheduled_at(self):
        return self.game.scheduled_at if self.game else None
