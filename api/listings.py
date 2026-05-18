from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_

from store.db import get_session
from store.models import Listing, Shortlist, NotInterested

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

        return {
            "variants": distinct(Listing.variant_canonical),
            "cities": distinct(Listing.location_city),
            "fuel_types": distinct(Listing.fuel_type),
            "transmissions": distinct(Listing.transmission),
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
    sort_by: str = Query("scraped_at", pattern="^(price|km_driven|year|scraped_at|last_seen_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    with get_session() as session:
        sq = session.query(Listing)

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
        if q:
            sq = _apply_q(q, sq)

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

        out = []
        for r in rows:
            d = ListingOut.model_validate(r)
            d.shortlisted = r.id in shortlisted_ids
            d.not_interested = r.id in not_interested_ids
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
    limit: int = Query(200, le=500),
):
    with get_session() as session:
        sq = session.query(Listing).filter(
            Listing.is_active.is_(True),
            Listing.dedup_key.isnot(None),
        )
        if config_id:
            sq = sq.filter(Listing.config_id == config_id)
        if make:
            sq = sq.filter(func.lower(Listing.make) == make.lower())
        if model:
            sq = sq.filter(func.lower(Listing.model) == model.lower())
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
        if q:
            sq = _apply_q(q, sq)

        rows = sq.order_by(Listing.price.asc()).limit(limit).all()

        ids = [r.id for r in rows]
        shortlisted_ids = {
            r.listing_id
            for r in session.query(Shortlist.listing_id).filter(Shortlist.listing_id.in_(ids))
        }
        not_interested_ids = {
            r.listing_id
            for r in session.query(NotInterested.listing_id).filter(NotInterested.listing_id.in_(ids))
        }

        groups: dict[str, list[Listing]] = {}
        no_dedup: list[Listing] = []
        for r in rows:
            if r.dedup_key:
                groups.setdefault(r.dedup_key, []).append(r)
            else:
                no_dedup.append(r)

        result = []
        for key, members in groups.items():
            rep = members[0]
            d = ListingOut.model_validate(rep)
            d.shortlisted = rep.id in shortlisted_ids
            d.not_interested = rep.id in not_interested_ids
            result.append(DedupGroup(
                dedup_key=key,
                best_price=rep.price or 0,
                sources=list({m.source for m in members}),
                listing_ids=[m.id for m in members],
                representative=d,
            ))

        for r in no_dedup:
            d = ListingOut.model_validate(r)
            d.shortlisted = r.id in shortlisted_ids
            d.not_interested = r.id in not_interested_ids
            result.append(DedupGroup(
                dedup_key=r.id,
                best_price=r.price or 0,
                sources=[r.source],
                listing_ids=[r.id],
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
