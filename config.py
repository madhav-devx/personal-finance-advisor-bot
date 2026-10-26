"""Application configuration. Sensitive values come from environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
load_dotenv(BASE_DIR / ".env")


def _flag(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or None  # create_app() generates a local one if missing
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + (INSTANCE_DIR / "finance.db").as_posix()
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = _flag("FLASK_DEBUG", False)
    PORT = int(os.environ.get("PORT", "5001"))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", False)  # set true behind HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = 3600 * 8
    MAX_CONTENT_LENGTH = 1024 * 1024

    # Optional external AI. Nothing is sent unless a key is set AND the user opts in on their profile.
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic").strip().lower()
    AI_API_KEY = os.environ.get("AI_API_KEY") or None
    AI_MODEL = os.environ.get("AI_MODEL") or None
    AI_BASE_URL = os.environ.get("AI_BASE_URL") or None


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"  # overridden per-test in conftest
    AI_API_KEY = None
