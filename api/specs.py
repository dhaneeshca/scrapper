"""
/api/specs — Car spec storage and retrieval.

GET  /?make=&model=   — return stored specs ordered by variant
POST /fetch           — scrape CarDekho and upsert into car_specs table
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert

from store.db import get_session
from store.models import CarSpec
from scraper.specs import scrape_specs

_log = logging.getLogger(__name__)

router = APIRouter()


class FetchRequest(BaseModel):
    make: str
    model: str


class SpecOut(BaseModel):
    id: str
    make: str
    model: str
    variant: str
    year_from: int | None
    year_to: int | None
    features: dict
    source_url: str
    scraped_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[SpecOut])
def get_specs(
    make: str = Query(...),
    model: str = Query(...),
):
    with get_session() as session:
        rows = (
            session.query(CarSpec)
            .filter(CarSpec.make.ilike(make), CarSpec.model.ilike(model))
            .order_by(CarSpec.variant)
            .all()
        )
        return [SpecOut.model_validate(r) for r in rows]


@router.post("/fetch")
def fetch_specs(body: FetchRequest):
    make = body.make.strip()
    model = body.model.strip()
    if not make or not model:
        raise HTTPException(400, "make and model are required")

    _log.info("spec fetch — %s %s", make, model)
    variants = scrape_specs(make, model)

    if not variants:
        _log.warning("spec fetch returned 0 variants — %s %s", make, model)
        return {"scraped": 0}

    now = datetime.utcnow()
    with get_session() as session:
        for v in variants:
            stmt = (
                pg_insert(CarSpec)
                .values(
                    make=make,
                    model=model,
                    variant=v["variant"],
                    year_from=v["year_from"],
                    year_to=v["year_to"],
                    features=v["features"],
                    source_url=v["source_url"],
                    scraped_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_car_specs_make_model_variant",
                    set_={
                        "year_from":  v["year_from"],
                        "year_to":    v["year_to"],
                        "features":   v["features"],
                        "source_url": v["source_url"],
                        "scraped_at": now,
                    },
                )
            )
            session.execute(stmt)
        session.commit()

    _log.info("spec fetch done — %s %s — %d variants upserted", make, model, len(variants))
    return {"scraped": len(variants)}
