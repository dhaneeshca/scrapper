"""
CarTrade used-car scraper.

URL: https://www.cartrade.com/second-hand/{city_slug}/#so=-1&sc=-1&city={city_id}&car={make_id}.{root_id}
Cards: li[uniqueid] — server-rendered, available after ~5s JS hydration.
Pagination: "Next" link in .pagination area; pn= in hash does not reload data.

Make/model IDs are looked up once per process via the CarTrade REST API and cached.
"""
import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

from scraper.base import Scraper, RawListing

_log = logging.getLogger(__name__)

_BASE = "https://www.cartrade.com"
_MAKES_API = f"{_BASE}/api/v2/makes/?shouldSortByPopularity=true"
_MODELS_API = f"{_BASE}/api/v2/models/?makeId={{make_id}}"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PAGE_DELAY = 3.0
_HYDRATION_WAIT = 8.0   # seconds for JS to render cards after page load
_CARD_SEL = "li[uniqueid]"

# City name (lowercase) → (slug, city_id)
_CITY_MAP: dict[str, tuple[str, int]] = {
    "mumbai":     ("mumbai",     1),
    "delhi":      ("delhi",      10),
    "pune":       ("pune",       12),
    "bangalore":  ("bangalore",  2),
    "bengaluru":  ("bangalore",  2),
    "chennai":    ("chennai",    176),
    "hyderabad":  ("hyderabad",  105),
    "kolkata":    ("kolkata",    198),
    "ahmedabad":  ("ahmedabad",  128),
    # Tamil Nadu
    "coimbatore":      ("coimbatore",      177),
    "dindigul":        ("dindigul",        181),
    "madurai":         ("madurai",         184),
    "salem":           ("salem",           191),
    "thanjavur":       ("thanjavur",       193),
    "tiruchirappalli": ("tiruchirappalli", 194),
    "trichy":          ("tiruchirappalli", 194),
    "tirunelveli":     ("tirunelveli",     195),
    "vellore":         ("vellore",         304),
    "erode":           ("erode",           340),
    "nagercoil":       ("nagercoil",       342),
    "namakkal":        ("namakkal",        343),
    "tiruppur":        ("tiruppur",        347),
    "kanchipuram":     ("kancheepuram",    474),
    "kancheepuram":    ("kancheepuram",    474),
    "hosur":           ("hosur",           534),
    "thoothukudi":     ("thoothukudi",     1535),
}

# Process-level cache: (make_lower, model_lower) → (make_id, root_id)
_ID_CACHE: dict[tuple[str, str], Optional[tuple[int, int]]] = {}


def _api_get(url: str) -> Optional[list | dict]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _log.warning("cartrade API HTTP %s: %s", e.code, url)
    except Exception as e:
        _log.warning("cartrade API error: %s — %s", e, url)
    return None


def _lookup_ids(make: str, model: str) -> Optional[tuple[int, int]]:
    """Return (make_id, root_id) for the given make/model, or None if not found."""
    key = (make.lower(), model.lower())
    if key in _ID_CACHE:
        return _ID_CACHE[key]

    makes_data = _api_get(_MAKES_API)
    if not isinstance(makes_data, list):
        _ID_CACHE[key] = None
        return None

    make_entry = next(
        (m for m in makes_data if m.get("makeName", "").lower() == make.lower()),
        None,
    )
    if not make_entry:
        _log.warning("cartrade: make '%s' not found", make)
        _ID_CACHE[key] = None
        return None

    make_id = make_entry["makeId"]
    models_data = _api_get(_MODELS_API.format(make_id=make_id))
    model_list = (
        models_data.get("modelList") if isinstance(models_data, dict) else models_data
    ) or []

    model_entry = next(
        (m for m in model_list if m.get("name", "").lower() == model.lower()),
        None,
    )
    if not model_entry:
        _log.warning("cartrade: model '%s' not found for make '%s'", model, make)
        _ID_CACHE[key] = None
        return None

    result = (make_id, model_entry["rootId"])
    _ID_CACHE[key] = result
    _log.info("cartrade IDs: %s %s → makeId=%d rootId=%d", make, model, *result)
    return result


def _search_url(city_slug: str, city_id: int, make_id: int, root_id: int) -> str:
    return f"{_BASE}/second-hand/{city_slug}/#so=-1&sc=-1&city={city_id}&car={make_id}.{root_id}"


def _parse_card_text(text: str, make: str, model: str) -> dict:
    """
    Card text format (after stripping):
      '{year} {make} {model} {variant}
       ₹{price}[  ₹{original_price}]
       [tags like HOME TEST DRIVE, GREAT PRICE]
       {km} KMs  |  {fuel}  |  {area}, {city}'
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # Year + variant from first line: "2015 Volkswagen Vento Highline Diesel"
    year = 0
    variant = ""
    if lines:
        m = re.match(r"^(\d{4})\s+", lines[0])
        if m:
            year = int(m.group(1))
            # variant is everything after "{year} {make} {model} "
            prefix = f"{m.group(1)} {make} {model} "
            if lines[0].startswith(prefix):
                variant = lines[0][len(prefix):].strip()

    # Price: first line starting with ₹, take the first number
    price = 0
    for ln in lines[1:]:
        if ln.startswith("₹"):
            nums = re.findall(r"[\d,]+", ln)
            if nums:
                price = int(nums[0].replace(",", ""))
            break

    # KMs / fuel / location: line with "|" containing "KMs"
    km = 0
    fuel = ""
    location = ""
    for ln in lines:
        if "|" in ln and re.search(r"KM", ln, re.I):
            parts = [p.strip() for p in ln.split("|")]
            km_m = re.search(r"([\d,]+)\s*KMs?", parts[0], re.I)
            if km_m:
                km = int(km_m.group(1).replace(",", ""))
            if len(parts) > 1:
                fuel = parts[1].strip()
            if len(parts) > 2:
                loc_parts = parts[2].strip().split(",")
                location = loc_parts[-1].strip()
            break

    # Transmission from variant name
    transmission = ""
    v_lower = variant.lower()
    if "automatic" in v_lower or "at" in v_lower.split():
        transmission = "Automatic"
    elif "manual" in v_lower or "mt" in v_lower.split():
        transmission = "Manual"
    elif "amt" in v_lower:
        transmission = "AMT"

    return {
        "year": year,
        "variant": variant,
        "price": price,
        "km": km,
        "fuel": fuel.title(),
        "transmission": transmission,
        "location": location,
    }


def _extract_cards(page: Page, make: str, model: str) -> list[RawListing]:
    raw_cards = page.evaluate(
        """() => Array.from(document.querySelectorAll('li[uniqueid]')).map(card => {
            const label = card.getAttribute('data-label') || '';
            const stockMatch = label.match(/stockId=([^|]+)/);
            const stockId = stockMatch ? stockMatch[1] : '';
            const shareEl = card.querySelector('[data-share-tiny]');
            const detailUrl = shareEl ? shareEl.getAttribute('data-share-tiny') : '';
            return {
                stockId: stockId,
                detailUrl: detailUrl || '',
                text: card.innerText.trim(),
            };
        })"""
    )

    results: list[RawListing] = []
    for card in raw_cards:
        stock_id = card.get("stockId", "")
        detail_url = card.get("detailUrl", "").split("?")[0]  # strip ?dc=0
        text = card.get("text", "")
        if not stock_id or not text:
            continue

        parsed = _parse_card_text(text, make, model)
        if parsed["price"] == 0 or parsed["year"] == 0:
            continue

        results.append(
            RawListing(
                source="cartrade",
                source_id=stock_id,
                url=detail_url,
                make=make,
                model=model,
                variant=parsed["variant"],
                year=parsed["year"],
                km_driven=parsed["km"],
                fuel_type=parsed["fuel"],
                transmission=parsed["transmission"],
                price=parsed["price"],
                location_city=parsed["location"],
            )
        )
    return results


class CartradeScraper(Scraper):
    name = "cartrade"

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
        ids = _lookup_ids(make, model)
        if not ids:
            _log.warning("cartrade: skipping %s %s — IDs not found", make, model)
            return []

        make_id, root_id = ids
        cities = regions if regions else [""]
        results: list[RawListing] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_UA)
            page = ctx.new_page()
            page.set_extra_http_headers({"Accept-Language": "en-IN,en;q=0.9"})

            for city in cities:
                city_lower = city.lower().strip()
                city_info = _CITY_MAP.get(city_lower)
                if not city_info:
                    _log.warning("cartrade: unknown city '%s', skipping", city)
                    continue
                city_slug, city_id = city_info
                self._scrape_city(
                    page, city_slug, city_id, make_id, root_id,
                    make, model, year_min, year_max, budget_max, results,
                )
                time.sleep(_PAGE_DELAY)

            browser.close()

        return results

    def _scrape_city(
        self,
        page: Page,
        city_slug: str,
        city_id: int,
        make_id: int,
        root_id: int,
        make: str,
        model: str,
        year_min: int,
        year_max: int,
        budget_max: int,
        out: list[RawListing],
    ) -> None:
        seen_ids: set[str] = set()
        page_num = 1
        url = _search_url(city_slug, city_id, make_id, root_id)

        _log.info("cartrade loading city=%s: %s", city_slug, url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            page.wait_for_selector(_CARD_SEL, timeout=12_000)
        except PlaywrightTimeout:
            _log.warning("cartrade timeout loading city=%s", city_slug)
            return

        time.sleep(2)

        while True:
            cards = _extract_cards(page, make, model)
            new_ids = {c.source_id for c in cards} - seen_ids
            if not new_ids:
                break

            added = 0
            for card in cards:
                if card.source_id in seen_ids:
                    continue
                seen_ids.add(card.source_id)

                if year_min and card.year and card.year < year_min:
                    continue
                if year_max and card.year and card.year > year_max:
                    continue
                if budget_max and card.price > budget_max:
                    continue

                out.append(card)
                added += 1

            _log.info(
                "cartrade city=%s page=%d — %d cards, %d kept (total: %d)",
                city_slug, page_num, len(cards), added, len(out),
            )

            # Pagination: look for a "Next" link in the pagination block
            next_link = page.query_selector("a.next, .pagination a[rel='next'], [class*='pagination'] a:has-text('Next')")
            if not next_link:
                break

            old_first_id = cards[0].source_id if cards else ""
            try:
                next_link.click()
                page.wait_for_function(
                    f"""() => {{
                        const first = document.querySelector('{_CARD_SEL}');
                        return first && first.getAttribute('uniqueid') !== {repr(old_first_id)};
                    }}""",
                    timeout=12_000,
                )
                page_num += 1
                time.sleep(_PAGE_DELAY)
            except PlaywrightTimeout:
                _log.info("cartrade city=%s: no more pages", city_slug)
                break
