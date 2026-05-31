from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_

from store.db import get_session
from store.models import Listing, PriceHistory, Shortlist, NotInterested

router = APIRouter()


class ListingOut(BaseModel):
    id: str
    source: str
    url: str
    make: Optional[str]
    model: Optional[str]
    variant: Optional[str]
    variant_canonical: Optional[str]
    year: Optional[int]
    km_driven: Optional[int]
    fuel_type: Optional[str]
    transmission: Optional[str]
    price: Optional[int]
    location_city: Optional[str]
    location_state: Optional[str]
    seller_type: Optional[str]
    images: Optional[list]
    description: Optional[str]
    scraped_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    is_active: bool
    is_manually_edited: bool = False
    dedup_key: Optional[str]
    config_id: Optional[str]
    shortlisted: bool = False
    not_interested: bool = False
    price_change_delta: Optional[int] = None  # last-step delta (back-compat)
    owner_count: Optional[int] = None
    # Price-movement summary (total since first listed)
    price_first: Optional[int] = None
    price_total_delta: Optional[int] = None
    price_total_pct: Optional[float] = None
    first_seen_at: Optional[datetime] = None
    last_change_at: Optional[datetime] = None
    days_on_market: Optional[int] = None
    num_price_points: Optional[int] = None
    price_points: Optional[list] = None  # [{price, observed_at}] for the loaded set

    model_config = {"from_attributes": True}


class ListingPatch(BaseModel):
    variant: Optional[str] = None
    year: Optional[int] = None
    km_driven: Optional[int] = None
    price: Optional[int] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    location_city: Optional[str] = None
    description: Optional[str] = None


def _batch_price_deltas(session, ids: list[str]) -> dict[str, int]:
    """Return {listing_id: delta} where delta = latest_price - second_latest_price."""
    if not ids:
        return {}
    subq = (
        session.query(
            PriceHistory.listing_id,
            PriceHistory.price,
            func.row_number().over(
                partition_by=PriceHistory.listing_id,
                order_by=PriceHistory.observed_at.desc(),
            ).label("rn"),
        )
        .filter(PriceHistory.listing_id.in_(ids))
        .subquery()
    )
    rows = session.query(subq).filter(subq.c.rn <= 2).all()
    by_id: dict[str, list[int]] = {}
    for row in rows:
        by_id.setdefault(row.listing_id, []).append(row.price)
    return {lid: prices[0] - prices[1] for lid, prices in by_id.items() if len(prices) == 2}


def _summarize_points(pts: list, now: datetime) -> dict:
    """Pure price-movement summary for one listing's ordered (price, observed_at) points.

    `pts` must be sorted ascending by observed_at. Pure (no DB) so it is unit-testable.
    """
    first_price, first_at = pts[0]
    current_price, _ = pts[-1]
    total_delta = current_price - first_price
    total_pct = round(100 * total_delta / first_price, 1) if first_price else None
    # last_change_at = observed_at of the most recent point whose price differs from the prior one
    last_change_at = first_at
    for i in range(1, len(pts)):
        if pts[i][0] != pts[i - 1][0]:
            last_change_at = pts[i][1]
    first_aware = first_at if first_at.tzinfo else first_at.replace(tzinfo=timezone.utc)
    return {
        "price_first": first_price,
        "price_total_delta": total_delta,
        "price_total_pct": total_pct,
        "first_seen_at": first_at,
        "last_change_at": last_change_at,
        "days_on_market": (now - first_aware).days,
        "num_price_points": len(pts),
        "price_points": [{"price": p, "observed_at": o.isoformat()} for p, o in pts],
    }


def _batch_price_summary(session, ids: list[str]) -> dict[str, dict]:
    """Per-listing price-movement summary based on the FULL history (not just last step).

    Returns {listing_id: {price_first, price_total_delta, price_total_pct, first_seen_at,
    last_change_at, days_on_market, num_price_points, price_points}}.
    """
    if not ids:
        return {}
    rows = (
        session.query(PriceHistory.listing_id, PriceHistory.price, PriceHistory.observed_at)
        .filter(PriceHistory.listing_id.in_(ids))
        .order_by(PriceHistory.listing_id, PriceHistory.observed_at.asc())
        .all()
    )
    by_id: dict[str, list] = {}
    for r in rows:
        by_id.setdefault(r.listing_id, []).append((r.price, r.observed_at))

    now = datetime.now(timezone.utc)
    return {lid: _summarize_points(pts, now) for lid, pts in by_id.items()}


def _apply_price_summary(d: "ListingOut", summary: dict | None) -> None:
    """Attach price-movement fields from _batch_price_summary onto a ListingOut."""
    if not summary:
        return
    d.price_first = summary["price_first"]
    d.price_total_delta = summary["price_total_delta"]
    d.price_total_pct = summary["price_total_pct"]
    d.first_seen_at = summary["first_seen_at"]
    d.last_change_at = summary["last_change_at"]
    d.days_on_market = summary["days_on_market"]
    d.num_price_points = summary["num_price_points"]
    d.price_points = summary["price_points"]


def _apply_q(q: str, query):
    term = f"%{q}%"
    return query.filter(
        or_(
            Listing.make.ilike(term),
            Listing.model.ilike(term),
            Listing.variant.ilike(term),
            Listing.variant_canonical.ilike(term),
            Listing.location_city.ilike(term),
            Listing.description.ilike(term),
        )
    )


@router.get("/options")
def listing_options(
    make: Optional[str] = None,
    model: Optional[str] = None,
):
    """Distinct values for autocomplete dropdowns, scoped to active listings."""
    with get_session() as session:
        q = session.query(Listing).filter(Listing.is_active.is_(True))
        if make:
            q = q.filter(func.lower(Listing.make) == make.lower())
        if model:
            q = q.filter(func.lower(Listing.model) == model.lower())

        def distinct(col):
            return [
                r[0] for r in
                q.with_entities(col).filter(col.isnot(None)).distinct().order_by(col).all()
                if r[0]
            ]

        owner_counts = sorted([
            r[0] for r in
            q.with_entities(Listing.owner_count).filter(Listing.owner_count.isnot(None)).distinct().all()
        ])
        return {
            "variants": distinct(Listing.variant_canonical),
            "cities": distinct(Listing.location_city),
            "fuel_types": distinct(Listing.fuel_type),
            "transmissions": distinct(Listing.transmission),
            "owner_counts": owner_counts,
        }


@router.get("/", response_model=list[ListingOut])
def list_listings(
    config_id: Optional[str] = None,
    source: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    variant: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    km_max: Optional[int] = None,
    fuel_type: Optional[str] = None,
    transmission: Optional[str] = None,
    city: Optional[str] = None,
    q: Optional[str] = None,
    active_only: bool = True,
    owner_max: Optional[int] = None,
    price_change: Optional[str] = Query(None, pattern="^(drop|rise)$"),
    sort_by: str = Query("scraped_at", pattern="^(price|km_driven|year|scraped_at|last_seen_at|price_drop)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    with get_session() as session:
        sq = session.query(Listing)

        # Price-movement filter/sort: join a per-listing (first_price, current_price)
        # subquery so total_delta = current_price - first_price (move since first listed)
        # can drive a WHERE (drop/rise) and an ORDER BY (biggest drop first) over the
        # whole dataset — not just the page the client already loaded.
        needs_movement = price_change is not None or sort_by == "price_drop"
        move_sq = None
        if needs_movement:
            move_sq = (
                session.query(
                    PriceHistory.listing_id.label("lid"),
                    func.first_value(PriceHistory.price).over(
                        partition_by=PriceHistory.listing_id,
                        order_by=PriceHistory.observed_at.asc(),
                    ).label("first_price"),
                    func.first_value(PriceHistory.price).over(
                        partition_by=PriceHistory.listing_id,
                        order_by=PriceHistory.observed_at.desc(),
                    ).label("current_price"),
                )
                .distinct()
                .subquery()
            )
            sq = sq.join(move_sq, move_sq.c.lid == Listing.id)
            # Plausibility guard: a real used-car move rarely exceeds 2x/half; bigger
            # swings are almost always a misparse in one observation, so exclude them
            # from the drop/rise feature (the listing's true history still shows in detail).
            if price_change == "drop":
                sq = sq.filter(
                    move_sq.c.current_price < move_sq.c.first_price,
                    move_sq.c.current_price >= move_sq.c.first_price * 0.5,
                )
            elif price_change == "rise":
                sq = sq.filter(
                    move_sq.c.current_price > move_sq.c.first_price,
                    move_sq.c.current_price <= move_sq.c.first_price * 2.0,
                )

        if active_only:
            sq = sq.filter(Listing.is_active.is_(True))
        if config_id:
            sq = sq.filter(Listing.config_id == config_id)
        if source:
            sq = sq.filter(Listing.source == source)
        if make:
            sq = sq.filter(func.lower(Listing.make) == make.lower())
        if model:
            sq = sq.filter(func.lower(Listing.model) == model.lower())
        if variant:
            sq = sq.filter(
                or_(
                    func.lower(Listing.variant).contains(variant.lower()),
                    func.lower(Listing.variant_canonical).contains(variant.lower()),
                )
            )
        if year_min:
            sq = sq.filter(Listing.year >= year_min)
        if year_max:
            sq = sq.filter(Listing.year <= year_max)
        if price_min:
            sq = sq.filter(Listing.price >= price_min)
        if price_max:
            sq = sq.filter(Listing.price <= price_max)
        if km_max:
            sq = sq.filter(Listing.km_driven <= km_max)
        if fuel_type:
            sq = sq.filter(func.lower(Listing.fuel_type) == fuel_type.lower())
        if transmission:
            sq = sq.filter(func.lower(Listing.transmission) == transmission.lower())
        if city:
            sq = sq.filter(func.lower(Listing.location_city).contains(city.lower()))
        if owner_max:
            sq = sq.filter(Listing.owner_count.isnot(None), Listing.owner_count <= owner_max)
        if q:
            sq = _apply_q(q, sq)

        if sort_by == "price_drop":
            # most-negative total_delta first (biggest drop)
            total_delta = move_sq.c.current_price - move_sq.c.first_price
            sq = sq.order_by(total_delta.asc())
        else:
            col = getattr(Listing, sort_by)
            sq = sq.order_by(col.desc() if sort_dir == "desc" else col.asc())
        rows = sq.offset(offset).limit(limit).all()

        ids = [r.id for r in rows]
        shortlisted_ids = {
            r.listing_id
            for r in session.query(Shortlist.listing_id).filter(Shortlist.listing_id.in_(ids))
        }
        not_interested_ids = {
            r.listing_id
            for r in session.query(NotInterested.listing_id).filter(NotInterested.listing_id.in_(ids))
        }
        deltas = _batch_price_deltas(session, ids)
        summaries = _batch_price_summary(session, ids)

        out = []
        for r in rows:
            d = ListingOut.model_validate(r)
            d.shortlisted = r.id in shortlisted_ids
            d.not_interested = r.id in not_interested_ids
            d.price_change_delta = deltas.get(r.id)
            _apply_price_summary(d, summaries.get(r.id))
            out.append(d)
        return out


class DedupGroup(BaseModel):
    dedup_key: str
    best_price: int
    sources: list[str]
    listing_ids: list[str]
    representative: ListingOut


@router.get("/deduped", response_model=list[DedupGroup])
def deduped_listings(
    config_id: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    km_max: Optional[int] = None,
    fuel_type: Optional[str] = None,
    transmission: Optional[str] = None,
    city: Optional[str] = None,
    q: Optional[str] = None,
    owner_max: Optional[int] = None,
    limit: int = Query(200, le=500),
):
    with get_session() as session:
        # Step 1: build the filtered base query
        base = session.query(Listing).filter(
            Listing.is_active.is_(True),
            Listing.dedup_key.isnot(None),
        )
        if config_id:
            base = base.filter(Listing.config_id == config_id)
        if make:
            base = base.filter(func.lower(Listing.make) == make.lower())
        if model:
            base = base.filter(func.lower(Listing.model) == model.lower())
        if year_min:
            base = base.filter(Listing.year >= year_min)
        if year_max:
            base = base.filter(Listing.year <= year_max)
        if price_min:
            base = base.filter(Listing.price >= price_min)
        if price_max:
            base = base.filter(Listing.price <= price_max)
        if km_max:
            base = base.filter(Listing.km_driven <= km_max)
        if fuel_type:
            base = base.filter(func.lower(Listing.fuel_type) == fuel_type.lower())
        if transmission:
            base = base.filter(func.lower(Listing.transmission) == transmission.lower())
        if city:
            base = base.filter(func.lower(Listing.location_city).contains(city.lower()))
        if owner_max:
            base = base.filter(Listing.owner_count.isnot(None), Listing.owner_count <= owner_max)
        if q:
            base = _apply_q(q, base)

        # Step 2: group by dedup_key in SQL to find the cheapest GROUPS.
        # Limit applies to the number of GROUPS, not raw rows — so no members get
        # silently dropped (the bug was capping rows then grouping in Python).
        group_rows = (
            base.with_entities(
                Listing.dedup_key,
                func.min(Listing.price).label("best_price"),
            )
            .group_by(Listing.dedup_key)
            .order_by(func.min(Listing.price).asc())
            .limit(limit)
            .all()
        )
        keys = [r.dedup_key for r in group_rows]

        # Step 3: fetch ALL members of those groups, preserving the SAME filters
        # (config_id, price, year, fuel, etc.) by querying from `base`.
        members_rows = (
            base.filter(Listing.dedup_key.in_(keys)).order_by(Listing.price.asc()).all()
            if keys else []
        )

        ids = [r.id for r in members_rows]
        shortlisted_ids = {
            r.listing_id
            for r in session.query(Shortlist.listing_id).filter(Shortlist.listing_id.in_(ids))
        }
        not_interested_ids = {
            r.listing_id
            for r in session.query(NotInterested.listing_id).filter(NotInterested.listing_id.in_(ids))
        }
        deltas = _batch_price_deltas(session, ids)
        summaries = _batch_price_summary(session, ids)

        groups: dict[str, list[Listing]] = {}
        for r in members_rows:
            groups.setdefault(r.dedup_key, []).append(r)

        result = []
        for key, members in groups.items():
            rep = members[0]  # cheapest first due to ORDER BY price ASC
            d = ListingOut.model_validate(rep)
            d.shortlisted = rep.id in shortlisted_ids
            d.not_interested = rep.id in not_interested_ids
            d.price_change_delta = deltas.get(rep.id)
            _apply_price_summary(d, summaries.get(rep.id))
            result.append(DedupGroup(
                dedup_key=key,
                best_price=rep.price or 0,
                sources=list({m.source for m in members}),
                listing_ids=[m.id for m in members],
                representative=d,
            ))

        result.sort(key=lambda g: g.best_price)
        return result


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: str):
    with get_session() as session:
        row = session.query(Listing).filter_by(id=listing_id).first()
        if not row:
            raise HTTPException(404, "not found")
        sl = session.query(Shortlist).filter_by(listing_id=listing_id).first()
        ni = session.query(NotInterested).filter_by(listing_id=listing_id).first()
        d = ListingOut.model_validate(row)
        d.shortlisted = sl is not None
        d.not_interested = ni is not None
        _apply_price_summary(d, _batch_price_summary(session, [listing_id]).get(listing_id))
        return d


@router.patch("/{listing_id}", response_model=ListingOut)
def patch_listing(listing_id: str, body: ListingPatch):
    with get_session() as session:
        row = session.query(Listing).filter_by(id=listing_id).first()
        if not row:
            raise HTTPException(404, "not found")
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.is_manually_edited = True
        session.commit()
        session.refresh(row)
        sl = session.query(Shortlist).filter_by(listing_id=listing_id).first()
        ni = session.query(NotInterested).filter_by(listing_id=listing_id).first()
        d = ListingOut.model_validate(row)
        d.shortlisted = sl is not None
        d.not_interested = ni is not None
        return d


@router.get("/{listing_id}/price-history")
def listing_price_history(listing_id: str):
    with get_session() as session:
        if not session.query(Listing).filter_by(id=listing_id).first():
            raise HTTPException(404, "not found")
        rows = (
            session.query(PriceHistory)
            .filter_by(listing_id=listing_id)
            .order_by(PriceHistory.observed_at.asc())
            .all()
        )
        return [{"price": r.price, "observed_at": r.observed_at.isoformat()} for r in rows]
