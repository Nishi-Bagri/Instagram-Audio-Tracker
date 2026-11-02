
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.connection import Base


class Audio(Base):
    __tablename__ = "audios"

    id = Column(Integer, primary_key=True, index=True)
    audio_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=True)
    artist = Column(String(255), nullable=True)
    audio_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reels = relationship("Reel", back_populates="audio")
    scans = relationship("ScanHistory", back_populates="audio")


class Reel(Base):
    __tablename__ = "reels"

    id = Column(Integer, primary_key=True, index=True)
    reel_url = Column(Text, unique=True, nullable=False)
    audio_id = Column(Integer, ForeignKey("audios.id"), nullable=False)
    creator_username = Column(String(255), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(Text, nullable=True)
    first_discovered_at = Column(DateTime(timezone=True), server_default=func.now())

    audio = relationship("Audio", back_populates="reels")


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id = Column(Integer, primary_key=True, index=True)
    audio_id = Column(Integer, ForeignKey("audios.id"), nullable=False)
    scanned_at = Column(DateTime(timezone=True), server_default=func.now())
    new_reels_found = Column(Integer, default=0)
    total_reels_found = Column(Integer, default=0)
    status = Column(String(50), default="success")

    audio = relationship("Audio", back_populates="scans")
