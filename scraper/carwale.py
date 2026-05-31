"""
CarWale used-car scraper.

URL: https://www.carwale.com/used/{city}/volkswagen-vento/
     https://www.carwale.com/used/volkswagen-vento/  (all cities fallback)

Cards: anchor tags  a[href*="/used/"][href*="{model-slug}"]
       whose text contains Rs. or ₹

Text format per card:
  "2021 Volkswagen Vento Highline Plus 1.0L TSI Automatic
   77,342 km  |  Petrol  |  Vadapalani, Chennai
   Rs. 7.54 Lakh
   EMI at  Rs.13,570
   Make Offer  Great Price"
"""
import logging
import re
import time
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from scraper.base import Scraper, RawListing, _parse_owner_count

_log = logging.getLogger(__name__)

_BASE = "https://www.carwale.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PAGE_DELAY = 2.5


def _slug(s: str) -> str:
    return s.lower().replace(" ", "-")


def _parse_price(text: str) -> int:
    """
    'Rs. 7.54 Lakh' or 'Rs. 7.54 Lakh  Rs. 7.69 Lakh' → take first (listed price).
    """
    m = re.search(r"Rs\.\s*([\d.,]+)\s*Lakh", text, re.IGNORECASE)
    if not m:
        return 0
    return int(float(m.group(1).replace(",", "")) * 100_000)


def _parse_km(text: str) -> int:
    m = re.search(r"([\d,]+)\s*km", text, re.IGNORECASE)
    return int(m.group(1).replace(",", "")) if m else 0


def _parse_year(text: str) -> int:
    m = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    return int(m.group()) if m else 0


def _source_id_from_url(url: str) -> str:
    """Extract the alphanumeric slug: /used/chennai/volkswagen-vento/8s6aa5gk/ → 8s6aa5gk"""
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else url


def _card_text_to_raw(href: str, text: str, make: str, model: str) -> Optional[RawListing]:
    if not href or not text:
        return None
    price = _parse_price(text)
    if price == 0:
        return None

    year = _parse_year(text)
    km = _parse_km(text)

    # Variant: first line minus year + make + model
    first_line = text.splitlines()[0].strip()
    variant = re.sub(rf"(?i)\b{re.escape(make)}\b", "", first_line)
    variant = re.sub(rf"(?i)\b{re.escape(model)}\b", "", variant)
    variant = re.sub(r"\b(20\d{2}|19\d{2})\b", "", variant)
    variant = " ".join(variant.split())

    # Fuel and location from the "km | Fuel | Area, City" line
    pipe_line = re.search(r"[\d,]+\s*km\s*\|(.+)", text)
    fuel = ""
    transmission = ""
    city = ""
    if pipe_line:
        parts = [p.strip() for p in pipe_line.group(1).split("|")]
        if parts:
            fuel_raw = parts[0].strip()
            if fuel_raw.lower() in ("petrol", "diesel", "cng", "electric", "lpg"):
                fuel = fuel_raw.title()
        if len(parts) >= 2:
            loc = parts[1].strip()
            loc_parts = [p.strip() for p in loc.split(",")]
            city = loc_parts[-1] if loc_parts else loc

    # Transmission from variant text
    for t in ("Automatic", "Manual", "AMT", "CVT"):
        if t.lower() in variant.lower():
            transmission = t
            break

    return RawListing(
        source="carwale",
        source_id=_source_id_from_url(href),
        url=href,
        make=make,
        model=model,
        variant=variant,
        year=year,
        km_driven=km,
        fuel_type=fuel,
        transmission=transmission,
        price=price,
        location_city=city,
        owner_count=_parse_owner_count(text),
    )


def _extract_cards(page: Page, model: str) -> list[dict]:
    model_slug = _slug(model)
    return page.evaluate(
        """(modelSlug) => {
            const links = Array.from(document.querySelectorAll('a[href*="/used/"]')).filter(a =>
                a.href.includes(modelSlug) &&
                (a.innerText.includes('Rs.') || a.innerText.includes('₹')) &&
                a.innerText.length > 40
            );
            return links.map(a => ({href: a.href, text: a.innerText.trim()}));
        }""",
        model_slug,
    )


class CarwaleScraper(Scraper):
    name = "carwale"

    def search(
        self,
        make: str,
        model: str,
        variants: list[str],
        regions: list[str],
        year_min: int,
        year_max: int,
        budget_max: int,
        city_configs: dict[str, dict] | None = None,
    ) -> list[RawListing]:
        cities = list(city_configs.keys()) if city_configs else (regions if regions else [""])
        results: list[RawListing] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_UA)
            page = ctx.new_page()

            for city in cities:
                url = self._search_url(make, model, city)
                _log.info("scraping %s", url)
                self._scrape_paginated(page, url, make, model, year_min, year_max, budget_max, results)
                time.sleep(_PAGE_DELAY)

            browser.close()

        return results

    def _search_url(self, make: str, model: str, city: str) -> str:
        make_model = f"{_slug(make)}-{_slug(model)}"
        if city:
            return f"{_BASE}/used/{_slug(city)}/{make_model}/"
        return f"{_BASE}/used/{make_model}/"

    def _scrape_paginated(
        self,
        page: Page,
        start_url: str,
        make: str,
        model: str,
        year_min: int,
        year_max: int,
        budget_max: int,
        out: list[RawListing],
    ) -> None:
        seen: set[str] = set()
        page_num = 1

        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeout:
            _log.warning("timeout loading %s", start_url)
            return

        if "not found" in page.title().lower() or "page not found" in page.title().lower():
            _log.warning("404 for %s", start_url)
            return

        while True:
            cards = _extract_cards(page, model)
            added = 0
            for card in cards:
                raw = _card_text_to_raw(card["href"], card["text"], make, model)
                if not raw or raw.url in seen:
                    continue
                seen.add(raw.url)
                if year_min and raw.year and raw.year < year_min:
                    continue
                if year_max and raw.year and raw.year > year_max:
                    continue
                if budget_max and raw.price > budget_max:
                    continue
                out.append(raw)
                added += 1

            _log.info("carwale page %d — %d cards, %d kept (total: %d)", page_num, len(cards), added, len(out))

            # Pagination: try next page URL
            next_url = page.evaluate("""() => {
                const a = document.querySelector('a[rel="next"]');
                return a ? a.href : null;
            }""")
            if not next_url:
                break
            try:
                page.goto(next_url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2500)
                page_num += 1
            except PlaywrightTimeout:
                break

            time.sleep(_PAGE_DELAY)
