"""Application configuration loaded from local environment variables."""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL


load_dotenv(override=True)


def build_database_uri() -> str:
    """Build a safely escaped MySQL connection URI for SQLAlchemy."""
    # An explicit URL supports isolated test/CI databases without changing MySQL defaults.
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("DB_USER", "friendly_user"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "friendly_db"),
        query={"charset": "utf8mb4"},
    )
    return database_url.render_as_string(hide_password=False)


class Config:
    """Configuration shared by all application environments."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    PROFILE_UPLOAD_FOLDER = Path(__file__).resolve().parent / "instance" / "uploads" / "profile_photos"
    # Development uses local storage; production can select a future backend here.
    PROFILE_PHOTO_STORAGE_BACKEND = os.getenv("PROFILE_PHOTO_STORAGE_BACKEND", "local")
    MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024
    # Allow multipart overhead while enforcing the exact file limit separately.
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024


class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True
