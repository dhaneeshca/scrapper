"""
CarDekho used-car scraper.

URL pattern:
  with city : https://www.cardekho.com/used-{make}-{model}+cars+in+{city}
  without   : https://www.cardekho.com/used-{make}-{model}+cars

Pagination: JS-driven Next button (no href) — click + wait for card refresh.
"""
import logging
import re
import time
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from scraper.base import Scraper, RawListing

_log = logging.getLogger(__name__)

_BASE = "https://www.cardekho.com"
_CARD_SEL = ".NewUcExCard"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PAGE_DELAY = 3.0


def _slug(s: str) -> str:
    return s.lower().replace(" ", "-")


def _parse_price_lakh(raw: str) -> int:
    """
    CarDekho prices come in two forms:
      simple  : '₹4.40L'
      discount: '₹5.09 L  ₹4.49L  (Save ₹60K)'  ← take the second (discounted) amount
    Returns INR integer.
    """
    amounts = re.findall(r"₹\s*([\d.,]+)\s*(?:L|Lakh|CR|Cr)?", raw, re.IGNORECASE)
    if not amounts:
        return 0
    # Take the last amount (discounted price when there are two)
    val = float(amounts[-1].replace(",", ""))
    unit = raw.upper()
    if "CR" in unit:
        return int(val * 10_000_000)
    return int(val * 100_000)


def _parse_km(raw: str) -> int:
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else 0


def _parse_year(raw: str) -> int:
    m = re.search(r"\b(19|20)\d{2}\b", raw)
    return int(m.group()) if m else 0


def _variant_from_url(url: str, model: str) -> str:
    """
    Extract variant from the URL slug.
    e.g. 'used-Volkswagen-vento-16-highline-plus-cars-Chennai_UUID.htm'
         → '1.6 Highline Plus'
    """
    m = re.search(
        rf"used-[^/]*?-{re.escape(model.lower())}-(.+?)-cars-",
        url,
        re.IGNORECASE,
    )
    if not m:
        return ""
    parts = m.group(1).split("-")
    out = []
    for p in parts:
        if re.fullmatch(r"\d{2}", p):       # '16' → '1.6'
            out.append(f"{p[0]}.{p[1]}")
        elif p.upper() in ("TDI", "TSI", "MPI", "AT", "MT", "CVT", "AMT"):
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def _source_id_from_url(url: str) -> str:
    """Pull the UUID out of the CarDekho detail URL."""
    m = re.search(r"_([0-9a-f\-]{36})\.htm", url)
    if m:
        return m.group(1)
    return url.rstrip("/").split("/")[-1]


def _extract_cards(page: Page) -> list[dict]:
    return page.evaluate(
        """(sel) => Array.from(document.querySelectorAll(sel)).map(card => {
            const link     = card.querySelector('a[href*="used-car-details"], a[href*="buy-used-car-details"]');
            const titleEl  = card.querySelector('.titlebox');
            const priceEl  = card.querySelector('.Price');
            const distEl   = card.querySelector('.distanceText');
            const imgEl    = card.querySelector('img');
            return {
                url:      link    ? link.href              : '',
                fullText: titleEl ? titleEl.innerText      : '',
                priceRaw: priceEl ? priceEl.innerText      : '',
                location: distEl  ? distEl.innerText.trim(): '',
                img:      imgEl   ? (imgEl.src || imgEl.dataset.src || '') : '',
            };
        })""",
        _CARD_SEL,
    )


def _parse_full_text(text: str) -> dict:
    """
    Parse the mixed title+specs string from .titlebox.

    Format (simple):
        'Volkswagen Vento 2016\n\n₹4.40L\n\n1,38,210 kms\n•\nManual\n•\nPetrol'
    Format (with discount):
        'Volkswagen Vento 2016\n₹5.09 L\n\n₹4.49L\n\n(Save ₹60K)\n60,180 kms\n•\nManual\n•\nDiesel'
    """
    year = _parse_year(text)

    km_match = re.search(r"([\d,]+)\s*kms?", text, re.IGNORECASE)
    km = _parse_km(km_match.group(1)) if km_match else 0

    fuel = ""
    trans = ""
    for token in re.split(r"[\n•]+", text):
        t = token.strip().lower()
        if t in ("petrol", "diesel", "cng", "electric", "lpg"):
            fuel = t.title()
        elif t in ("manual", "automatic", "amt", "cvt"):
            trans = t.title() if t != "amt" else "AMT"

    return {"year": year, "km": km, "fuel": fuel, "transmission": trans}


def _card_to_raw(card: dict, make: str, model: str) -> Optional[RawListing]:
    url = card.get("url", "")
    if not url:
        return None

    price = _parse_price_lakh(card.get("priceRaw", "") or card.get("fullText", ""))
    if price == 0:
        return None

    parsed = _parse_full_text(card.get("fullText", ""))
    variant = _variant_from_url(url, model)

    location = card.get("location", "")
    parts = [p.strip() for p in location.split(",")]
    city = parts[-1] if parts else ""   # last part is the city name

    return RawListing(
        source="cardekho",
        source_id=_source_id_from_url(url),
        url=url,
        make=make,
        model=model,
        variant=variant,
        year=parsed["year"],
        km_driven=parsed["km"],
        fuel_type=parsed["fuel"],
        transmission=parsed["transmission"],
        price=price,
        location_city=city,
        images=[card["img"]] if card.get("img") else [],
    )


class CardekhoScraper(Scraper):
    name = "cardekho"

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
            page.set_extra_http_headers({"Accept-Language": "en-IN,en;q=0.9"})

            for city in cities:
                url = self._search_url(make, model, city)
                _log.info("scraping %s", url)
                self._scrape_paginated(page, url, make, model, city, year_min, year_max, budget_max, results)
                time.sleep(_PAGE_DELAY)

            browser.close()

        return results

    def _search_url(self, make: str, model: str, city: str) -> str:
        slug = f"used-{_slug(make)}-{_slug(model)}+cars"
        if city:
            slug += f"+in+{_slug(city)}"
        return f"{_BASE}/{slug}"

    def _scrape_paginated(
        self,
        page: Page,
        start_url: str,
        make: str,
        model: str,
        city: str,
        year_min: int,
        year_max: int,
        budget_max: int,
        out: list[RawListing],
    ) -> None:
        seen_urls: set[str] = set()
        page_num = 1
        city_lower = city.lower() if city else ""

        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_selector(_CARD_SEL, timeout=15_000)
        except PlaywrightTimeout:
            _log.warning("timeout loading %s", start_url)
            return

        while True:
            cards = _extract_cards(page)
            if not cards:
                break

            added = 0
            for card in cards:
                raw = _card_to_raw(card, make, model)
                if raw is None or raw.url in seen_urls:
                    continue
                seen_urls.add(raw.url)

                if city_lower and raw.location_city.lower() != city_lower:
                    _log.debug("skip out-of-region listing: %s (expected %s)", raw.location_city, city)
                    continue
                if year_min and raw.year and raw.year < year_min:
                    continue
                if year_max and raw.year and raw.year > year_max:
                    continue
                if budget_max and raw.price > budget_max:
                    continue

                out.append(raw)
                added += 1

            _log.info("page %d — %d cards, %d kept (total so far: %d)", page_num, len(cards), added, len(out))

            # Click Next — CarDekho's Next button has no href, it's JS-driven
            next_btn = page.query_selector("a.next")
            if not next_btn:
                break
            try:
                old_first_url = cards[0].get("url", "")
                next_btn.click()
                # Wait until card content changes (new page loaded)
                page.wait_for_function(
                    f"""() => {{
                        const link = document.querySelector('{_CARD_SEL} a[href*="used-car-details"], {_CARD_SEL} a[href*="buy-used-car-details"]');
                        return link && link.href !== {repr(old_first_url)};
                    }}""",
                    timeout=15_000,
                )
                page_num += 1
                time.sleep(_PAGE_DELAY)
            except PlaywrightTimeout:
                _log.info("no more pages (next click timed out)")
                break
