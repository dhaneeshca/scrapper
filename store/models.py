import uuid
from datetime import datetime
from sqlalchemy import Column, Index, String, Integer, Boolean, Date, Text, ForeignKey, DateTime, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    variants = Column(JSONB, default=list)
    year_min = Column(Integer)
    year_max = Column(Integer)
    fuel_types = Column(JSONB, default=list)
    transmissions = Column(JSONB, default=list)
    budget_max = Column(Integer)
    regions = Column(JSONB, default=list)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Listing(Base):
    __tablename__ = "listings"

    id = Column(String, primary_key=True, default=_uuid)
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_listing_source_id"),
    )
    url = Column(Text)
    make = Column(String)
    model = Column(String)
    variant = Column(String)
    year = Column(Integer)
    km_driven = Column(Integer)
    fuel_type = Column(String)
    transmission = Column(String)
    price = Column(Integer)
    location_city = Column(String)
    location_state = Column(String)
    seller_type = Column(String)
    images = Column(JSONB, default=list)
    description = Column(Text)
    listed_at = Column(Date)
    scraped_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    dedup_key = Column(String, index=True)
    config_id = Column(String, ForeignKey("search_configs.id"))
    variant_canonical = Column(String)
    is_manually_edited = Column(Boolean, default=False, nullable=False, server_default="false")
    owner_count = Column(Integer, nullable=True)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(String, primary_key=True, default=_uuid)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    price = Column(Integer, nullable=False)
    observed_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Shortlist(Base):
    __tablename__ = "shortlist"

    listing_id = Column(String, ForeignKey("listings.id"), primary_key=True)
    notes = Column(Text, default="")
    added_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class NotInterested(Base):
    __tablename__ = "not_interested"

    listing_id = Column(String, ForeignKey("listings.id"), primary_key=True)
    added_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class VariantAlias(Base):
    __tablename__ = "variant_aliases"

    id = Column(String, primary_key=True, default=_uuid)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    raw_variant = Column(String, nullable=False)
    canonical_variant = Column(String, nullable=False)
    similarity_score = Column(Float)
    confirmed = Column(Boolean, default=False, nullable=False)


class CarSpec(Base):
    __tablename__ = "car_specs"

    id         = Column(String, primary_key=True, default=_uuid)
    make       = Column(String, nullable=False)
    model      = Column(String, nullable=False)
    variant    = Column(String, nullable=False)
    year_from  = Column(Integer, nullable=True)
    year_to    = Column(Integer, nullable=True)
    features   = Column(JSONB, nullable=False, default=dict)
    source_url = Column(Text, nullable=False)
    scraped_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("make", "model", "variant", name="uq_car_specs_make_model_variant"),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    run_id     = Column(String, primary_key=True)
    config_id  = Column(String, ForeignKey("search_configs.id"), nullable=False)
    source     = Column(String, nullable=True)   # NULL = all sources
    status     = Column(String, nullable=False, default="running")  # running | done | error
    inserted   = Column(Integer, nullable=False, default=0)
    updated    = Column(Integer, nullable=False, default=0)
    price_changes = Column(Integer, nullable=False, default=0)
    raw_fetched = Column(Integer, nullable=False, default=0)
    errors     = Column(JSONB, nullable=False, default=list)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class SourceCityConfig(Base):
    __tablename__ = "source_city_configs"

    id           = Column(String, primary_key=True, default=_uuid)
    state_name   = Column(String, nullable=False)   # "Tamil Nadu"
    state_key    = Column(String, nullable=False)   # "tamil-nadu"
    city_name    = Column(String, nullable=False)   # "Chennai"
    city_key     = Column(String, nullable=False)   # "chennai"
    source       = Column(String, nullable=False)   # "olx" | "cartrade" | "cars24" | "spinny" | "carwale" | "cardekho"
    is_supported = Column(Boolean, nullable=False, default=False)
    source_config = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("city_key", "source", name="uq_source_city_config"),
    )
