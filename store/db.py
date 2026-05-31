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
    ("owner_count",         "ALTER TABLE listings ADD COLUMN owner_count INTEGER"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing_cols = {c["name"] for c in inspector.get_columns("listings")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("listings")}
    with engine.connect() as conn:
        for col, stmt in _LISTING_MIGRATIONS:
            if col not in existing_cols:
                conn.execute(text(stmt))

        # Collapse duplicate (source, source_id) rows before creating unique index.
        # Keep the row with the latest scraped_at; repoint price_history to the survivor.
        if "uq_listing_source_id" not in existing_indexes:
            conn.execute(text("""
                UPDATE price_history ph
                SET listing_id = keeper.id
                FROM (
                    SELECT DISTINCT ON (source, source_id)
                        id,
                        source,
                        source_id
                    FROM listings
                    ORDER BY source, source_id, scraped_at DESC
                ) keeper
                JOIN listings dup ON dup.source = keeper.source
                    AND dup.source_id = keeper.source_id
                    AND dup.id != keeper.id
                WHERE ph.listing_id = dup.id
            """))
            conn.execute(text("""
                DELETE FROM listings
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                            ROW_NUMBER() OVER (
                                PARTITION BY source, source_id
                                ORDER BY scraped_at DESC
                            ) AS rn
                        FROM listings
                    ) ranked
                    WHERE rn > 1
                )
            """))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_source_id "
                "ON listings (source, source_id)"
            ))

        # Index for price_history sparkline/delta queries
        ph_indexes = {idx["name"] for idx in inspector.get_indexes("price_history")}
        if "ix_price_history_listing_observed" not in ph_indexes:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_price_history_listing_observed "
                "ON price_history (listing_id, observed_at DESC)"
            ))

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
