"""
SQLAlchemy engine/session setup. Uses SQLite by default for POC simplicity;
swap DATABASE_URL (in app/config/settings.py) to a Postgres URL for a more
production-like setup without changing any model or API code.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config.settings import DATABASE_URL

# Render (and several other providers) hand out Postgres URLs starting with
# "postgres://", a legacy scheme SQLAlchemy 2.0 no longer accepts — it
# requires "postgresql://". Normalize it here so DATABASE_URL can be pasted
# directly from the provider dashboard with no manual editing.
_normalized_url = DATABASE_URL
if _normalized_url.startswith("postgres://"):
    _normalized_url = _normalized_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if _normalized_url.startswith("sqlite") else {}

engine = create_engine(_normalized_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and ensures it's closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called on app startup for POC simplicity
    (no migration tool needed at this stage)."""
    from app.models import db_models  # noqa: F401 (ensures models are registered)
    Base.metadata.create_all(bind=engine)
