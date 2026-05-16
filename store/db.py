import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from store.models import Base

load_dotenv()

engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

_LISTING_MIGRATIONS = [
    ("variant_canonical",   "ALTER TABLE listings ADD COLUMN variant_canonical TEXT"),
    ("is_manually_edited",  "ALTER TABLE listings ADD COLUMN is_manually_edited BOOLEAN NOT NULL DEFAULT FALSE"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("listings")}
    with engine.connect() as conn:
        for col, stmt in _LISTING_MIGRATIONS:
            if col not in existing:
                conn.execute(text(stmt))
        conn.commit()


def get_session() -> Session:
    """Use as a context manager: `with get_session() as s:`"""
    return SessionLocal()
