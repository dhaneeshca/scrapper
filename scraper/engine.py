import logging
from datetime import datetime
from typing import Callable
import log as applog
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


def run_config(config_id: str, source: str | None = None, on_progress: ProgressCb | None = None) -> dict:
    """Scrape all active scrapers for the given config. Returns a run summary."""
    run_id = applog.new_run_id()

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

        _log.info("scraper fetched %d raw results from %s", len(results), scraper.name)

        seen_source_ids: set[str] = set()
        skipped_dupes = 0
        with get_session() as session:
            for raw in results:
                if raw.source_id in seen_source_ids:
                    skipped_dupes += 1
                    continue
                seen_source_ids.add(raw.source_id)

                existing = (
                    session.query(Listing)
                    .filter_by(source=raw.source, source_id=raw.source_id)
                    .first()
                )

                canonical = _aliases.get(raw.variant) if raw.variant else None

                if existing:
                    if existing.price != raw.price:
                        _log.info(
                            "price change — %s  %s  %s → %s",
                            raw.source_id, raw.variant or "?", existing.price, raw.price,
                        )
                        session.add(
                            PriceHistory(
                                listing_id=existing.id,
                                price=raw.price,
                                observed_at=now,
                            )
                        )
                        summary["price_changes"] += 1
                        scraper_price_changes += 1
                    existing.price = raw.price
                    existing.last_seen_at = now
                    existing.is_active = True
                    if canonical and not existing.is_manually_edited:
                        existing.variant_canonical = canonical
                    seen_listing_ids.add(existing.id)
                    summary["updated"] += 1
                    scraper_updated += 1
                else:
                    listing = Listing(
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
                    )
                    session.add(listing)
                    session.flush()
                    session.add(
                        PriceHistory(
                            listing_id=listing.id,
                            price=raw.price,
                            observed_at=now,
                        )
                    )
                    seen_listing_ids.add(listing.id)
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
        _emit({
            "type": "scraper_done",
            "source": scraper.name,
            "inserted": scraper_inserted,
            "updated": scraper_updated,
            "price_changes": scraper_price_changes,
        })

    # Mark listings NOT seen this run as inactive.
    # Scope to the specific source if one was requested — otherwise we'd incorrectly
    # deactivate listings from sources that weren't scraped this run.
    if seen_listing_ids:
        with get_session() as session:
            q = session.query(Listing).filter(
                Listing.config_id == config_id,
                Listing.id.notin_(seen_listing_ids),
                Listing.is_active.is_(True),
            )
            if source:
                q = q.filter(Listing.source == source)
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
