
from sqlalchemy.orm import Session

from database.models import Audio, Reel, ScanHistory


def get_audio_by_audio_id(db: Session, audio_id: str):
    return db.query(Audio).filter(Audio.audio_id == audio_id).first()


def create_audio(db: Session, audio_data: dict):
    audio = Audio(**audio_data)
    db.add(audio)
    db.commit()
    db.refresh(audio)
    return audio


def get_reel_by_url(db: Session, reel_url: str):
    return db.query(Reel).filter(Reel.reel_url == reel_url).first()


def create_reel(db: Session, reel_data: dict):
    reel = Reel(**reel_data)
    db.add(reel)
    db.commit()
    db.refresh(reel)
    return reel


def create_scan_history(db: Session, scan_data: dict):
    scan = ScanHistory(**scan_data)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan
