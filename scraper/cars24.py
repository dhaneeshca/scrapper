"""
Cars24 used-car scraper.

URL: https://www.cars24.com/buy-used-{make}-{model}-cars-{city}/
Cards: .styles_contentWrap__9oSrl  (React, rendered after hydration)

Text format per card:
  "Cars24 Owned Stock\n
   2016 Volkswagen Vento HIGHLINE 1.6 MPI\n
   72,889 km\n  Petrol\n  Manual\n  TN-19\n
   EMI ₹11,167/m*\n  ₹5.22L\n  ₹5.02 lakh\n
   Vadapalani"
"""
import logging
import re
import time
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from scraper.base import Scraper, RawListing, _parse_owner_count

_log = logging.getLogger(__name__)

_BASE = "https://www.cars24.com"
_CARD_SEL = ".styles_contentWrap__9oSrl"

# Cars24 uses full city names in URL slugs; map common short forms
_CITY_SLUGS: dict[str, str] = {
    "trichy": "tiruchirappalli",
    "tiruchirappalli": "tiruchirappalli",
}

# Cities where Cars24 has physical hubs — others timeout with no cards
_SUPPORTED_CITIES: set[str] = {
    "chennai", "coimbatore", "tiruchirappalli", "trichy",
    "madurai", "salem", "erode", "hosur", "tirunelveli",
    "vellore", "tiruppur", "dindigul", "namakkal",
}
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PAGE_DELAY = 3.0
_HYDRATION_WAIT = 5000   # ms — max wait for cards before concluding "no inventory"


def _slug(s: str) -> str:
    return s.lower().replace(" ", "-")


def _parse_price(text: str) -> int:
    """Take the second ₹ amount (discounted) if present, else first."""
    amounts = re.findall(r"₹\s*([\d.,]+)\s*(?:L|lakh)?", text, re.IGNORECASE)
    # skip EMI amounts (preceded by "EMI")
    non_emi = [
        a for a in re.finditer(r"₹\s*([\d.,]+)\s*(?:L|lakh)?", text, re.IGNORECASE)
        if not re.search(r"EMI", text[max(0, a.start()-10):a.start()], re.IGNORECASE)
    ]
    if not non_emi:
        return 0
    # prefer last non-EMI price (discounted)
    raw = non_emi[-1].group(1).replace(",", "")
    return round(float(raw) * 100_000)


def _parse_km(text: str) -> int:
    m = re.search(r"([\d,]+)\s*km", text, re.IGNORECASE)
    return int(m.group(1).replace(",", "")) if m else 0


def _parse_year(text: str) -> int:
    m = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    return int(m.group()) if m else 0


def _variant_from_name(full_name: str, make: str, model: str) -> str:
    """'2016 Volkswagen Vento HIGHLINE 1.6 MPI' → 'HIGHLINE 1.6 MPI'"""
    v = re.sub(rf"(?i)\b{re.escape(make)}\b", "", full_name)
    v = re.sub(rf"(?i)\b{re.escape(model)}\b", "", v)
    v = re.sub(r"\b(20\d{2}|19\d{2})\b", "", v)
    return " ".join(v.split())


def _source_id_from_url(url: str) -> str:
    m = re.search(r"-(\d{10,})/?$", url)
    return m.group(1) if m else url.split("/")[-2]


def _extract_cards(page: Page) -> list[dict]:
    return page.evaluate(
        """(sel) => Array.from(document.querySelectorAll(sel)).map(card => {
            const link = card.closest('a') || card.parentElement?.closest('a');
            const img  = card.closest('[class*="card"],[class*="wrap"]')?.querySelector('img');
            return {
                url:  link ? link.href  : '',
                text: card.innerText.trim(),
                img:  img  ? (img.src || img.dataset.src || '') : '',
            };
        })""",
        _CARD_SEL,
    )


def _card_to_raw(card: dict, make: str, model: str, city: str = "") -> Optional[RawListing]:
    url = card.get("url", "")
    text = card.get("text", "")
    if not url or not text:
        return None

    # Cars24 appends a "similar cars" section with other models — filter by URL
    make_slug = make.lower().replace(" ", "-")
    model_slug = model.lower().replace(" ", "-")
    if f"buy-used-{make_slug}-{model_slug}" not in url:
        return None

    price = _parse_price(text)
    if price == 0:
        return None

    year = _parse_year(text)
    km = _parse_km(text)

    # Car name is the line starting with the year
    name_match = re.search(rf"\b{year}\b.*", text) if year else None
    full_name = name_match.group().split("\n")[0].strip() if name_match else ""
    variant = _variant_from_name(full_name, make, model)

    fuel = ""
    transmission = ""
    for token in re.split(r"[\n|•]+", text):
        t = token.strip().lower()
        if t in ("petrol", "diesel", "cng", "electric", "lpg"):
            fuel = t.title()
        elif t in ("manual", "auto", "automatic", "amt", "cvt"):
            transmission = "Automatic" if t in ("auto", "automatic") else t.upper() if t == "amt" else t.title()

    # Location: last meaningful line — Cars24-owned cards have a short area name,
    # "Verified Direct Seller" cards have a full street address.
    # Fall back to the search city when the last line is a long street address.
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    location = lines[-1] if lines else ""
    if re.fullmatch(r"[A-Za-z]{3}\s+\d{1,2}", location):
        location = lines[-2] if len(lines) >= 2 else ""
    if len(location) > 40:
        location = city.title() if city else location

    return RawListing(
        source="cars24",
        source_id=_source_id_from_url(url),
        url=url,
        make=make,
        model=model,
        variant=variant,
        year=year,
        km_driven=km,
        fuel_type=fuel,
        transmission=transmission,
        price=price,
        location_city=location,
        seller_type="dealer",
        images=[card["img"]] if card.get("img") else [],
        owner_count=_parse_owner_count(text),
    )


class Cars24Scraper(Scraper):
    name = "cars24"

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
                if city_configs:
                    c24 = city_configs.get(city.lower(), {}).get("cars24", {})
                    if city and not c24.get("is_supported"):
                        _log.debug("cars24 skipping unsupported city: %s", city)
                        continue
                    slug = c24.get("source_config", {}).get("slug") or city.lower().replace(" ", "-")
                else:
                    slug = _CITY_SLUGS.get(city.lower(), city.lower().replace(" ", "-"))
                    if city and slug not in _SUPPORTED_CITIES:
                        _log.debug("cars24 skipping unsupported city: %s", city)
                        continue
                url = self._search_url(make, model, city, slug)
                _log.info("scraping %s", url)
                self._scrape_page(page, url, make, model, city, year_min, year_max, budget_max, results)
                time.sleep(_PAGE_DELAY)

            browser.close()

        return results

    def _search_url(self, make: str, model: str, city: str, city_slug: str = "") -> str:
        parts = [_slug(make), _slug(model)]
        base = f"{_BASE}/buy-used-{'-'.join(parts)}-cars"
        if city:
            slug = city_slug or _CITY_SLUGS.get(city.lower(), _slug(city))
            return f"{base}-{slug}/"
        return f"{base}/"

    def _scrape_page(
        self,
        page: Page,
        url: str,
        make: str,
        model: str,
        city: str,
        year_min: int,
        year_max: int,
        budget_max: int,
        out: list[RawListing],
    ) -> None:
        # Real load failure (network/DNS/timeout) → warn. A loaded page with no cards
        # is a separate, expected case (no inventory for this make/model in this city).
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeout:
            _log.warning("cars24 page load failed (timeout) at %s", url)
            return

        try:
            page.wait_for_selector(_CARD_SEL, timeout=_HYDRATION_WAIT)
        except PlaywrightTimeout:
            # Page loaded fine but no cards rendered → no inventory, not a failure.
            _log.info("cars24 %s: no inventory for this make/model", url.split("/")[-2])
            return

        seen: set[str] = set()
        cards = _extract_cards(page)
        added = 0
        parsed = 0

        for card in cards:
            raw = _card_to_raw(card, make, model, city)
            if not raw:
                continue
            parsed += 1
            if raw.url in seen:
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

        _log.info("cars24 %s — %d cards, %d kept", url.split("/")[-2], len(cards), added)
        # Alarm only on genuine parse failure (cards present, none match the model URL /
        # parse), not on year/budget filtering.
        if cards and parsed == 0:
            _log.warning("cars24 %s: %d cards rendered but 0 parseable — selector likely stale", url.split("/")[-2], len(cards))
