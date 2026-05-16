from typing import Optional
from fastapi import APIRouter, Query
from sqlalchemy import func, case
from store.db import get_session
from store.models import Listing

router = APIRouter()


@router.get("/config/{config_id}/sources")
def config_source_stats(config_id: str):
    """Active listing counts per source for a given config."""
    with get_session() as session:
        rows = (
            session.query(Listing.source, func.count().label("count"))
            .filter(Listing.config_id == config_id, Listing.is_active.is_(True))
            .group_by(Listing.source)
            .all()
        )
    return {r.source: r.count for r in rows}


@router.get("/price-range")
def price_range(
    make: str = Query(...),
    model: str = Query(...),
):
    """
    Returns variant × year price breakdown for the given make+model.
    Shape: { "SX(O)": { "2021": { "min": 750000, "max": 950000, "avg": 850000, "count": 12 } } }
    """
    effective_variant = case(
        (Listing.variant_canonical.isnot(None), Listing.variant_canonical),
        else_=Listing.variant,
    )

    with get_session() as session:
        rows = (
            session.query(
                effective_variant.label("variant"),
                Listing.year,
                func.min(Listing.price).label("min"),
                func.max(Listing.price).label("max"),
                func.avg(Listing.price).label("avg"),
                func.count().label("count"),
            )
            .filter(
                func.lower(Listing.make) == make.lower(),
                func.lower(Listing.model) == model.lower(),
                Listing.is_active.is_(True),
                Listing.price.isnot(None),
                Listing.variant.isnot(None),
                Listing.year.isnot(None),
            )
            .group_by(effective_variant, Listing.year)
            .all()
        )

    result: dict = {}
    for r in rows:
        variant = r.variant or "Unknown"
        year = str(r.year)
        result.setdefault(variant, {})[year] = {
            "min": r.min,
            "max": r.max,
            "avg": round(r.avg),
            "count": r.count,
        }
    return result


@router.get("/fair-value")
def fair_value(
    make: str = Query(...),
    model: str = Query(...),
    variant: str = Query(...),
    year: int = Query(...),
):
    """
    Returns market median price for a specific variant+year using all listings
    (active + inactive). Inactive listings are a proxy for sold cars.
    """
    effective_variant = case(
        (Listing.variant_canonical.isnot(None), Listing.variant_canonical),
        else_=Listing.variant,
    )

    with get_session() as session:
        rows = (
            session.query(Listing.price, Listing.is_active)
            .filter(
                func.lower(Listing.make) == make.lower(),
                func.lower(Listing.model) == model.lower(),
                func.lower(effective_variant) == variant.lower(),
                Listing.year == year,
                Listing.price.isnot(None),
            )
            .all()
        )

    prices = sorted(r.price for r in rows if r.price)
    n = len(prices)
    if n == 0:
        return {
            "fair_value": None, "p25": None, "p75": None,
            "sample_size": 0, "active_count": 0, "inactive_count": 0,
        }

    active_count = sum(1 for r in rows if r.is_active)

    def _pct(data: list, p: float) -> int:
        idx = (len(data) - 1) * p
        lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
        return round(data[lo] + (data[hi] - data[lo]) * (idx - lo))

    return {
        "fair_value": _pct(prices, 0.5),
        "p25": _pct(prices, 0.25),
        "p75": _pct(prices, 0.75),
        "sample_size": n,
        "active_count": active_count,
        "inactive_count": n - active_count,
    }
