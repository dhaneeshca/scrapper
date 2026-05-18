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

        # Migrate SearchConfig.regions from city key lists → state key lists.
        # Only runs if source_city_configs is populated AND any config still has city keys.
        city_count = conn.execute(text("SELECT COUNT(*) FROM source_city_configs")).scalar()
        if city_count:
            conn.execute(text("""
                UPDATE search_configs
                SET regions = (
                    SELECT coalesce(jsonb_agg(DISTINCT scc.state_key), '[]'::jsonb)
                    FROM source_city_configs scc
                    WHERE scc.city_key = ANY(
                        SELECT lower(v)
                        FROM jsonb_array_elements_text(search_configs.regions) AS v
                    )
                )
                WHERE EXISTS (
                    SELECT 1 FROM source_city_configs scc
                    WHERE scc.city_key = ANY(
                        SELECT lower(v)
                        FROM jsonb_array_elements_text(regions) AS v
                    )
                )
            """))

        conn.commit()


def get_session() -> Session:
    """Use as a context manager: `with get_session() as s:`"""
    return SessionLocal()
