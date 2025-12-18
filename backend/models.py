#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Database models (SQLAlchemy ORM)
#===============================================================

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Text, Boolean, DateTime, Enum, ForeignKey, Float, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


# Enums
class MediaType(PyEnum):
    """Type of media content."""
    MOVIE = "movie"
    TV = "tv"


class TranscodeStatus(PyEnum):
    """Status of a transcoding job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


# Media Model
class Media(Base):
    """Represents a movie or TV show in the library."""
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False)
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    backdrop_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    folder_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # For movies
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Seconds
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    episodes: Mapped[List["Episode"]] = relationship("Episode", back_populates="media", cascade="all, delete-orphan")
    transcode_jobs: Mapped[List["TranscodeJob"]] = relationship("TranscodeJob", back_populates="media", cascade="all, delete-orphan")
    watch_progress: Mapped[List["WatchProgress"]] = relationship("WatchProgress", back_populates="media", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Media(id={self.id}, title='{self.title}', type={self.media_type.value})>"


# Episode Model (for TV Shows)
class Episode(Base):
    """Represents a single episode of a TV show."""
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id"), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    episode: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Seconds
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    media: Mapped["Media"] = relationship("Media", back_populates="episodes")
    transcode_jobs: Mapped[List["TranscodeJob"]] = relationship("TranscodeJob", back_populates="episode", cascade="all, delete-orphan")
    watch_progress: Mapped[List["WatchProgress"]] = relationship("WatchProgress", back_populates="episode", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Episode(id={self.id}, S{self.season:02d}E{self.episode:02d})>"


# TranscodeJob Model
class TranscodeJob(Base):
    """Represents a video transcoding job in the queue."""
    __tablename__ = "transcode_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("media.id"), nullable=True)
    episode_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("episodes.id"), nullable=True)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    output_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[TranscodeStatus] = mapped_column(Enum(TranscodeStatus), default=TranscodeStatus.PENDING)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    media: Mapped[Optional["Media"]] = relationship("Media", back_populates="transcode_jobs")
    episode: Mapped[Optional["Episode"]] = relationship("Episode", back_populates="transcode_jobs")

    def __repr__(self):
        return f"<TranscodeJob(id={self.id}, status={self.status.value}, progress={self.progress}%)>"


# WatchProgress Model
class WatchProgress(Base):
    """Tracks user's watch progress for resume functionality."""
    __tablename__ = "watch_progress"
    __table_args__ = (UniqueConstraint('media_id', 'episode_id', name='uq_watch_progress_media_episode'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id"), nullable=False)
    episode_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("episodes.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)  # Seconds
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Total duration
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    media: Mapped["Media"] = relationship("Media", back_populates="watch_progress")
    episode: Mapped[Optional["Episode"]] = relationship("Episode", back_populates="watch_progress")

    @property
    def progress_percent(self) -> float:
        """Calculate watch progress as percentage."""
        if self.duration and self.duration > 0:
            return (self.position / self.duration) * 100
        return 0.0

    def __repr__(self):
        return f"<WatchProgress(media_id={self.media_id}, position={self.position}s, completed={self.completed})>"


# Settings Model
class Settings(Base):
    """Key-value store for application settings."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Settings(key='{self.key}')>"
