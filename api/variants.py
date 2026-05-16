"""
Variant normalization API.

Fuzzy clustering uses rapidfuzz.token_sort_ratio which handles:
  - Different ordering: "1.0 TSI Highline" vs "HIGHLINE 1.0L TSI"
  - Case differences: "Highline" vs "HIGHLINE"
  - Minor spelling: "1.0L TSI" vs "1.0 TSI"
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy import func

from store.db import get_session
from store.models import Listing, VariantAlias

router = APIRouter()

_DEFAULT_THRESHOLD = 70


def _cluster_variants(raw_counts: dict[str, int], threshold: int) -> list[dict]:
    """
    Groups variant strings by token_sort_ratio similarity using complete linkage:
    a variant joins a cluster only if it scores >= threshold against ALL existing
    members. This prevents snowballing where distantly related variants chain into
    the same group through intermediate matches.
    """
    variants = list(raw_counts.keys())
    clusters: list[list[str]] = []

    for v in variants:
        best_cluster = None
        best_min_score = threshold - 1
        for ci, cluster in enumerate(clusters):
            # Complete linkage: must meet threshold against every existing member
            min_score = min(fuzz.token_sort_ratio(v, m) for m in cluster)
            if min_score >= threshold and min_score > best_min_score:
                best_min_score = min_score
                best_cluster = ci
        if best_cluster is not None:
            clusters[best_cluster].append(v)
        else:
            clusters.append([v])

    result = []
    for cluster in clusters:
        # Pick the most common member as the canonical suggestion
        by_count = sorted(cluster, key=lambda x: raw_counts.get(x, 0), reverse=True)
        canonical = by_count[0]
        members = []
        for m in cluster:
            score = fuzz.token_sort_ratio(m, canonical) if m != canonical else 100.0
            members.append({
                "raw": m,
                "count": raw_counts.get(m, 0),
                "score": round(score, 1),
            })
        members.sort(key=lambda x: x["count"], reverse=True)
        total = sum(raw_counts.get(m, 0) for m in cluster)
        min_score = min(x["score"] for x in members)
        result.append({
            "canonical_suggestion": canonical,
            "members": members,
            "total_count": total,
            "confidence": round(min_score, 1),
            "is_singleton": len(cluster) == 1,
        })

    result.sort(key=lambda x: (-x["total_count"], x["canonical_suggestion"]))
    return result


@router.get("/")
def list_variants(make: str = Query(...), model: str = Query(...)):
    """All unique raw variants for a make+model with counts and any existing canonical."""
    with get_session() as session:
        rows = (
            session.query(Listing.variant, Listing.variant_canonical, func.count().label("count"))
            .filter(
                func.lower(Listing.make) == make.lower(),
                func.lower(Listing.model) == model.lower(),
                Listing.is_active.is_(True),
                Listing.variant.isnot(None),
            )
            .group_by(Listing.variant, Listing.variant_canonical)
            .order_by(func.count().desc())
            .all()
        )
    return [
        {"raw": r.variant, "canonical": r.variant_canonical, "count": r.count}
        for r in rows
    ]


@router.get("/suggest")
def suggest_normalization(
    make: str = Query(...),
    model: str = Query(...),
    threshold: int = Query(_DEFAULT_THRESHOLD, ge=50, le=99),
):
    """Run fuzzy clustering on all unique raw variants and return proposed groups.

    Raw variants that already have a confirmed VariantAlias are excluded — they
    have already been normalised and will no longer appear after apply.
    """
    with get_session() as session:
        rows = (
            session.query(Listing.variant, func.count().label("count"))
            .filter(
                func.lower(Listing.make) == make.lower(),
                func.lower(Listing.model) == model.lower(),
                Listing.is_active.is_(True),
                Listing.variant.isnot(None),
                Listing.variant != "",
            )
            .group_by(Listing.variant)
            .all()
        )

        confirmed = {
            a.raw_variant
            for a in session.query(VariantAlias.raw_variant).filter_by(
                make=make, model=model, confirmed=True
            )
        }

    if not rows:
        return []

    raw_counts = {r.variant: r.count for r in rows if r.variant not in confirmed}
    if not raw_counts:
        return []

    return _cluster_variants(raw_counts, threshold)


class ApplyMapping(BaseModel):
    raw: str
    canonical: str


class ApplyRequest(BaseModel):
    make: str
    model: str
    mappings: list[ApplyMapping]


@router.post("/apply")
def apply_normalization(body: ApplyRequest):
    """
    Bulk-set variant_canonical on listings and upsert into variant_aliases.
    Only processes mappings where canonical is non-empty.
    """
    mappings = [m for m in body.mappings if m.canonical.strip()]
    if not mappings:
        return {"updated": 0}

    updated = 0
    with get_session() as session:
        for m in mappings:
            # Bulk update listings
            n = (
                session.query(Listing)
                .filter(
                    func.lower(Listing.make) == body.make.lower(),
                    func.lower(Listing.model) == body.model.lower(),
                    Listing.variant == m.raw,
                )
                .update({"variant_canonical": m.canonical.strip()}, synchronize_session=False)
            )
            updated += n

            # Upsert alias
            existing = (
                session.query(VariantAlias)
                .filter_by(
                    make=body.make,
                    model=body.model,
                    raw_variant=m.raw,
                )
                .first()
            )
            if existing:
                existing.canonical_variant = m.canonical.strip()
                existing.confirmed = True
            else:
                session.add(
                    VariantAlias(
                        id=str(uuid.uuid4()),
                        make=body.make,
                        model=body.model,
                        raw_variant=m.raw,
                        canonical_variant=m.canonical.strip(),
                        confirmed=True,
                    )
                )
        session.commit()

    return {"updated": updated, "mappings_applied": len(mappings)}
