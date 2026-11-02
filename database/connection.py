
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")


# Database configuration
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# Validate configuration
required_values = {
    "DB_HOST": DB_HOST,
    "DB_PORT": DB_PORT,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
}

missing_values = [
    key for key, value in required_values.items()
    if not value
]

if missing_values:
    raise ValueError(
        f"Missing database configuration: {missing_values}"
    )


# PostgreSQL connection URL
DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


# Database session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# Base class for ORM models
Base = declarative_base()


def get_db():
    """Provide and close a database session."""

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
