import logging
import time
from datetime import datetime
from typing import Callable
import log as applog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from store.db import get_session
from store.models import Listing, PriceHistory, SearchConfig, SourceCityConfig, VariantAlias
from scraper.base import RawListing
from scraper.cardekho import CardekhoScraper
from scraper.cars24 import Cars24Scraper
from scraper.carwale import CarwaleScraper
from scraper.olx import OLXScraper
from scraper.spinny import SpinnyScraper
from scraper.cartrade import CartradeScraper

_log = logging.getLogger(__name__)

_SCRAPERS = [CardekhoScraper(), Cars24Scraper(), CarwaleScraper(), OLXScraper(), SpinnyScraper(), CartradeScraper()]

ProgressCb = Callable[[dict], None]


def _dedup_key(r: RawListing) -> str:
    km_bucket = (r.km_driven // 5000) * 5000
    city = r.location_city.lower().replace(" ", "_")
    return f"{r.make}_{r.model}_{r.year}_{km_bucket}_{city}".lower()


_RUN_DEADLINE_SECS = 1800  # 30 min hard cap per run


def run_config(config_id: str, source: str | None = None, on_progress: ProgressCb | None = None, run_id: str | None = None) -> dict:
    """Scrape all active scrapers for the given config. Returns a run summary."""
    run_id = applog.set_run_id(run_id) if run_id else applog.new_run_id()
    run_start = time.monotonic()

    with get_session() as session:
        config = session.query(SearchConfig).filter_by(id=config_id).first()
        if not config:
            _log.error("config not found: %s", config_id)
            return {"error": "config not found"}

        make = config.make
        model = config.model
        variants = config.variants or []
        regions = config.regions or []
        year_min = config.year_min or 0
        year_max = config.year_max or 9999
        budget_max = config.budget_max or 999_999_999

    state_keys = [r.lower() for r in regions]
    with get_session() as session:
        city_rows = (
            session.query(SourceCityConfig)
            .filter(SourceCityConfig.state_key.in_(state_keys))
            .all()
        )
    # city_key → source → {is_supported, source_config}
    city_configs: dict[str, dict] = {}
    for row in city_rows:
        city_configs.setdefault(row.city_key, {})[row.source] = {
            "is_supported": row.is_supported,
            "source_config": row.source_config or {},
        }

    _log.info(
        "run start — config=%s  %s %s  regions=%s  source=%s  budget_max=%s",
        config_id, make, model, regions, source or "all", budget_max,
    )

    now = datetime.utcnow()
    seen_listing_ids: set[str] = set()
    completed_sources: set[str] = set()  # sources that finished without raising
    summary = {"inserted": 0, "updated": 0, "price_changes": 0, "errors": []}

    def _emit(event: dict) -> None:
        if on_progress:
            on_progress(event)

    # First event: run_id so the frontend can cross-reference log.txt
    _emit({"type": "run_start", "run_id": run_id})

    with get_session() as session:
        alias_rows = (
            session.query(VariantAlias)
            .filter_by(make=make, model=model, confirmed=True)
            .all()
        )
    _aliases: dict[str, str] = {a.raw_variant: a.canonical_variant for a in alias_rows}
    if _aliases:
        _log.info("loaded %d confirmed variant aliases", len(_aliases))

    scrapers = [s for s in _SCRAPERS if source is None or s.name == source]
    for scraper in scrapers:
        elapsed = time.monotonic() - run_start
        if elapsed > _RUN_DEADLINE_SECS:
            _log.warning("run deadline reached after %.0fs — stopping after %d scrapers", elapsed, len(completed_sources))
            _emit({"type": "run_timeout", "elapsed_secs": int(elapsed)})
            break
        _emit({"type": "scraper_start", "source": scraper.name, "regions": regions})
        _log.info("scraper start — %s  regions=%s", scraper.name, regions)
        scraper_inserted = scraper_updated = scraper_price_changes = 0

        try:
            results = scraper.search(
                make=make,
                model=model,
                variants=variants,
                regions=regions,
                year_min=year_min,
                year_max=year_max,
                budget_max=budget_max,
                city_configs=city_configs or None,
            )
        except Exception as exc:
            msg = f"{scraper.name}: {exc}"
            _log.error("scraper error — %s", msg)
            summary["errors"].append(msg)
            _emit({"type": "scraper_error", "source": scraper.name, "message": str(exc)})
            continue

        raw_count = len(results)
        _log.info("scraper fetched %d raw results from %s", raw_count, scraper.name)
        if raw_count == 0:
            _log.warning("zero-yield — %s returned no listings (may be a layout/API change)", scraper.name)

        seen_source_ids: set[str] = set()
        skipped_dupes = 0
        with get_session() as session:
            for raw in results:
                if raw.source_id in seen_source_ids:
                    skipped_dupes += 1
                    continue
                seen_source_ids.add(raw.source_id)

                canonical = _aliases.get(raw.variant) if raw.variant else None

                # Fetch the existing row (if any) first — needed to detect new vs update
                # and to read old_price/canonical. The unique index makes this lookup fast.
                existing = (
                    session.query(Listing)
                    .filter_by(source=raw.source, source_id=raw.source_id)
                    .first()
                )

                if existing:
                    if existing.price != raw.price:
                        _log.info(
                            "price change — %s  %s  %s → %s",
                            raw.source_id, raw.variant or "?", existing.price, raw.price,
                        )
                        session.add(PriceHistory(listing_id=existing.id, price=raw.price, observed_at=now))
                        summary["price_changes"] += 1
                        scraper_price_changes += 1
                    existing.price = raw.price
                    existing.last_seen_at = now
                    existing.is_active = True
                    if canonical and not existing.is_manually_edited:
                        existing.variant_canonical = canonical
                    if raw.owner_count is not None:
                        existing.owner_count = raw.owner_count
                    seen_listing_ids.add(existing.id)
                    summary["updated"] += 1
                    scraper_updated += 1
                else:
                    # Race-safe insert: ON CONFLICT does nothing if a concurrent run
                    # inserted the same row between our SELECT and now.
                    stmt = (
                        pg_insert(Listing)
                        .values(
                            source=raw.source,
                            source_id=raw.source_id,
                            url=raw.url,
                            make=raw.make,
                            model=raw.model,
                            variant=raw.variant,
                            year=raw.year,
                            km_driven=raw.km_driven,
                            fuel_type=raw.fuel_type,
                            transmission=raw.transmission,
                            price=raw.price,
                            location_city=raw.location_city,
                            location_state=raw.location_state,
                            seller_type=raw.seller_type,
                            images=raw.images,
                            description=raw.description,
                            listed_at=raw.listed_at,
                            scraped_at=now,
                            last_seen_at=now,
                            is_active=True,
                            dedup_key=_dedup_key(raw),
                            config_id=config_id,
                            variant_canonical=canonical,
                            owner_count=raw.owner_count,
                        )
                        .on_conflict_do_update(
                            index_elements=["source", "source_id"],
                            set_={
                                "price": raw.price,
                                "last_seen_at": now,
                                "is_active": True,
                            },
                        )
                        .returning(Listing.__table__.c.id)
                    )
                    result = session.execute(stmt)
                    inserted_row = result.fetchone()
                    if not inserted_row:
                        continue
                    listing_id = inserted_row[0]
                    session.flush()
                    session.add(PriceHistory(listing_id=listing_id, price=raw.price, observed_at=now))
                    seen_listing_ids.add(listing_id)
                    _log.info(
                        "new listing — %s  %s %s %s  ₹%s  %s",
                        raw.source_id, raw.year, raw.make, raw.variant or "?",
                        raw.price, raw.location_city,
                    )
                    summary["inserted"] += 1
                    scraper_inserted += 1

            session.commit()

        if skipped_dupes:
            _log.info("%s skipped %d duplicate source_ids", scraper.name, skipped_dupes)
        _log.info(
            "scraper done — %s  inserted=%d  updated=%d  price_changes=%d",
            scraper.name, scraper_inserted, scraper_updated, scraper_price_changes,
        )
        completed_sources.add(scraper.name)
        _emit({
            "type": "scraper_done",
            "source": scraper.name,
            "inserted": scraper_inserted,
            "updated": scraper_updated,
            "price_changes": scraper_price_changes,
        })

    # Mark listings NOT seen this run as inactive, per successfully-completed source.
    # Scoping by source means: only deactivate for sources that actually ran and finished
    # without raising — so a zero-yield successful run still deactivates gone listings,
    # but a crashed/skipped source never wrongly deactivates its listings.
    if completed_sources:
        with get_session() as session:
            q = session.query(Listing).filter(
                Listing.config_id == config_id,
                Listing.id.notin_(seen_listing_ids) if seen_listing_ids else True,
                Listing.is_active.is_(True),
                Listing.source.in_(completed_sources),
            )
            deactivated = q.update({"is_active": False}, synchronize_session=False)
            session.commit()
        if deactivated:
            _log.info("deactivated %d listings no longer seen this run", deactivated)

    _log.info(
        "run done — config=%s  inserted=%d  updated=%d  price_changes=%d  errors=%d",
        config_id, summary["inserted"], summary["updated"],
        summary["price_changes"], len(summary["errors"]),
    )
    _emit({"type": "done", **summary})
    return summary
