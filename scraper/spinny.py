"""
Spinny used-car scraper — pure JSON API, no browser required.

API: https://api.spinny.com/v3/api/listing/v6/
     ?city={city_slug}&product_type=cars&model={model_slug}&category=used
     &availability=available,booked&page={n}&is_new_price=true
Pagination: response["next"] is None on last page.
"""
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional

from scraper.base import Scraper, RawListing

_log = logging.getLogger(__name__)

_BASE = "https://api.spinny.com/v3/api/listing/v6/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PAGE_DELAY = 1.5

# Cities Spinny operates in (from sitemap verification)
_SUPPORTED_CITIES: set[str] = {
    "chennai", "coimbatore", "tiruchirappalli", "trichy",
    "salem", "vellore", "erode", "tiruppur", "hosur",
}


def _get_json(url: str) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _log.warning("spinny HTTP %s: %s", e.code, url)
    except Exception as e:
        _log.warning("spinny fetch error: %s — %s", e, url)
    return None


class SpinnyScraper(Scraper):
    name = "spinny"

    def search(
        self,
        make: str,
        model: str,
        variants: list[str],
        regions: list[str],
        year_min: int,
        year_max: int,
        budget_max: int,
    ) -> list[RawListing]:
        cities = regions if regions else [""]
        model_slug = model.lower().replace(" ", "-")
        results: list[RawListing] = []

        for city in cities:
            city_slug = city.lower().replace(" ", "-")
            if city and city_slug not in _SUPPORTED_CITIES:
                _log.debug("spinny skipping unsupported city: %s", city)
                continue
            self._fetch_city(make, model_slug, city_slug, year_min, year_max, budget_max, results)

        return results

    def _fetch_city(
        self,
        make: str,
        model_slug: str,
        city_slug: str,
        year_min: int,
        year_max: int,
        budget_max: int,
        out: list[RawListing],
    ) -> None:
        page = 1
        while True:
            url = (
                f"{_BASE}?city={city_slug}&product_type=cars&model={model_slug}"
                f"&category=used&availability=available,booked&page={page}&is_new_price=true"
            )
            _log.info("spinny city=%s model=%s page=%d", city_slug, model_slug, page)
            data = _get_json(url)
            if not data:
                break

            items = data.get("results") or []
            if not items:
                _log.info("spinny city=%s — no results (count=%s)", city_slug, data.get("count"))
                break

            added = 0
            for item in items:
                raw = _to_raw(item, make, year_min, year_max, budget_max)
                if raw:
                    out.append(raw)
                    added += 1

            _log.info(
                "spinny city=%s page=%d — %d items, %d kept (total so far: %d)",
                city_slug, page, len(items), added, len(out),
            )

            if not data.get("next"):
                break

            page += 1
            time.sleep(_PAGE_DELAY)


def _to_raw(
    item: dict, make: str, year_min: int, year_max: int, budget_max: int
) -> Optional[RawListing]:
    year = int(item.get("make_year") or 0)
    price = int(item.get("price") or 0)

    if year_min and year and year < year_min:
        return None
    if year_max and year and year > year_max:
        return None
    if budget_max and price and price > budget_max:
        return None

    permanent_url = item.get("permanent_url") or ""
    detail_url = f"https://www.spinny.com{permanent_url}" if permanent_url else ""

    images = [
        "https:" + img["file"]["absurl"]
        for img in (item.get("images") or [])
        if img.get("file", {}).get("absurl")
    ]

    return RawListing(
        source="spinny",
        source_id=str(item["id"]),
        url=detail_url,
        make=item.get("make") or make,
        model=item.get("model") or "",
        variant=item.get("variant") or "",
        year=year,
        km_driven=int(item.get("mileage") or 0),
        fuel_type=(item.get("fuel_type") or "").title(),
        transmission=(item.get("transmission") or "").title(),
        price=price,
        location_city=(item.get("city") or "").strip(),
        seller_type=item.get("seller_type") or "",
        images=images,
    )
