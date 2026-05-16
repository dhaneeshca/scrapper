"""
OLX used-car scraper (India) — hybrid Playwright + JSON API.

Strategy:
  1. Playwright (Stealth): load the HTML landing page once per state to establish
     session cookies and pass OLX's bot checks (page 1 is SSR, not API-driven).
  2. requests.Session with those cookies: call the internal JSON API for page=1,
     2, 3, … until data is exhausted. All structured data (variant, fuel,
     transmission, km, city) comes directly from the API response.

API:
  GET https://www.olx.in/api/relevance/v4/search
      ?category=84&location={state_id}&query={make}+{model}
      &page={n}&size=40&lang=en-IN&platform=web-desktop
      &user=anonymous&relaxedFilters=true&pttEnabled=true
      &facet_limit=1000&location_facet_limit=40&spellcheck=true
"""
import hashlib
import logging
import time
from typing import Optional
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth
from scraper.base import Scraper, RawListing

_log = logging.getLogger(__name__)

_BASE = "https://www.olx.in"
_API_URL = "https://www.olx.in/api/relevance/v4/search"
_PAGE_SIZE = 40
_API_DELAY = 1.5   # seconds between API pages
_INIT_WAIT = 5000  # ms — Akamai Bot Manager JS challenge needs ~3–5s to complete

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

_PANAMERA_CLIENT_ID = "web-desktop"
_PANAMERA_CLIENT_VERSION = "11.40.4"

# Base headers for API requests — Referer is set per-request to match the state page
_BASE_HEADERS = {
    "User-Agent": _UA,
    "Accept": "*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="147", "Not.A/Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-panamera-client-id": _PANAMERA_CLIENT_ID,
    "x-panamera-client-version": _PANAMERA_CLIENT_VERSION,
}


def _panamera_fingerprint() -> str:
    """Generate a plausible x-panamera-fingerprint header value."""
    h = hashlib.md5(_PANAMERA_CLIENT_ID.encode()).hexdigest()
    return f"{h}#{int(time.time() * 1000)}"

# state_key → (slug, location_id)
_STATES: dict[str, tuple[str, str]] = {
    "tamil-nadu":    ("tamil-nadu",    "2001173"),
    "delhi":         ("delhi",         "2001160"),
    "maharashtra":   ("maharashtra",   "2001168"),
    "karnataka":     ("karnataka",     "2001165"),
    "telangana":     ("telangana",     "2001154"),
    "kerala":        ("kerala",        "2001166"),
    "gujarat":       ("gujarat",       "2001164"),
    "west-bengal":   ("west-bengal",   "2001176"),
    "rajasthan":     ("rajasthan",     "2001171"),
    "uttar-pradesh": ("uttar-pradesh", "2001174"),
    "punjab":        ("punjab",        "2001170"),
}

# city_lower → state key
_CITY_TO_STATE: dict[str, str] = {
    # Tamil Nadu
    "chennai": "tamil-nadu", "coimbatore": "tamil-nadu",
    "madurai": "tamil-nadu", "trichy": "tamil-nadu",
    "tiruchirappalli": "tamil-nadu", "salem": "tamil-nadu",
    "tirunelveli": "tamil-nadu", "erode": "tamil-nadu",
    "vellore": "tamil-nadu", "thanjavur": "tamil-nadu",
    # Delhi / NCR
    "delhi": "delhi", "new delhi": "delhi",
    "noida": "uttar-pradesh", "ghaziabad": "uttar-pradesh",
    # Maharashtra
    "mumbai": "maharashtra", "pune": "maharashtra",
    "nagpur": "maharashtra", "thane": "maharashtra", "navi mumbai": "maharashtra",
    # Karnataka
    "bangalore": "karnataka", "bengaluru": "karnataka", "mysore": "karnataka",
    # Telangana / AP
    "hyderabad": "telangana", "secunderabad": "telangana",
    # Kerala
    "kochi": "kerala", "thiruvananthapuram": "kerala", "kozhikode": "kerala",
    # Gujarat
    "ahmedabad": "gujarat", "surat": "gujarat", "vadodara": "gujarat",
    # West Bengal
    "kolkata": "west-bengal",
    # Rajasthan
    "jaipur": "rajasthan",
    # Punjab / Chandigarh
    "chandigarh": "punjab", "ludhiana": "punjab", "amritsar": "punjab",
}


def _get_param(params: list, key: str) -> str:
    for p in params:
        if p.get("key") == key:
            return p.get("value_name", "")
    return ""


def _item_to_raw(item: dict, make: str, model: str) -> Optional[RawListing]:
    params = item.get("parameters", [])
    price = item.get("price", {}).get("value", {}).get("raw", 0)
    if not price:
        return None

    year_str = _get_param(params, "year")
    year = int(year_str) if year_str.isdigit() else 0

    km_str = _get_param(params, "mileage")
    km = int(km_str) if km_str.isdigit() else 0

    # key="petrol" but value_name is the human fuel label ("Diesel", "Petrol", ...)
    fuel = _get_param(params, "petrol")
    transmission = _get_param(params, "transmission")
    variant = _get_param(params, "variant")

    ad_id = str(item.get("id", ""))
    locs = item.get("locations_resolved", {})
    city = locs.get("ADMIN_LEVEL_3_name", "")
    state = locs.get("ADMIN_LEVEL_1_name", "")

    city_slug = city.lower().replace(" ", "-")
    make_slug = make.lower().replace(" ", "-")
    model_slug = model.lower().replace(" ", "-")
    var_slug = variant.lower().replace(" ", "-") if variant else ""
    if var_slug:
        url = f"{_BASE}/item/cars-c84-used-{make_slug}-{model_slug}-{var_slug}-in-{city_slug}-iid-{ad_id}"
    else:
        url = f"{_BASE}/item/cars-c84-used-{make_slug}-{model_slug}-in-{city_slug}-iid-{ad_id}"

    images = [img["url"] for img in item.get("images", [])[:3]]
    seller_type = "dealer" if item.get("is_business") else "individual"

    return RawListing(
        source="olx",
        source_id=ad_id,
        url=url,
        make=make,
        model=model,
        variant=variant,
        year=year,
        km_driven=km,
        fuel_type=fuel,
        transmission=transmission,
        price=price,
        location_city=city,
        location_state=state,
        seller_type=seller_type,
        images=images,
    )


class OLXScraper(Scraper):
    name = "olx"

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
        states_seen: dict[str, tuple[str, str]] = {}  # state_key → (slug, loc_id)
        for city in (regions or []):
            state_key = _CITY_TO_STATE.get(city.lower())
            if state_key and state_key not in states_seen:
                states_seen[state_key] = _STATES[state_key]

        if not states_seen:
            # Nationwide fallback — no location filter, no HTML init URL
            states_seen["nationwide"] = ("", "")

        query = f"{make} {model}"
        query_slug = f"{make}-{model}".lower().replace(" ", "-")
        results: list[RawListing] = []

        with Stealth().use_sync(sync_playwright()) as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_UA)
            pw_page = ctx.new_page()

            for state_key, (slug, loc_id) in states_seen.items():
                # Step 1: load HTML page to establish cookies / pass bot check
                if slug and loc_id:
                    html_url = f"{_BASE}/{slug}_g{loc_id}/cars_c84/q-{query_slug}?isSearchCall=true"
                else:
                    html_url = f"{_BASE}/cars_c84/q-{query_slug}?isSearchCall=true"

                _log.info("olx cookie init — %s  %s", state_key, html_url)
                try:
                    pw_page.goto(html_url, wait_until="domcontentloaded", timeout=30_000)
                    pw_page.wait_for_timeout(_INIT_WAIT)
                except PlaywrightTimeout:
                    _log.warning("olx timeout during cookie init for %s", state_key)

                # Step 2: transfer cookies to requests session
                session = requests.Session()
                session.headers.update(_BASE_HEADERS)
                session.headers["Referer"] = html_url
                session.headers["x-panamera-fingerprint"] = _panamera_fingerprint()
                for c in ctx.cookies():
                    session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

                # Step 3: paginate via JSON API
                self._scrape_all_pages(
                    session, query, loc_id or None,
                    make, model, year_min, year_max, budget_max, results,
                )

            browser.close()

        return results

    def _scrape_all_pages(
        self,
        session: requests.Session,
        query: str,
        location_id: Optional[str],
        make: str,
        model: str,
        year_min: int,
        year_max: int,
        budget_max: int,
        out: list[RawListing],
    ) -> None:
        seen: set[str] = set()
        page = 1
        loc_label = location_id or "nationwide"

        while True:
            params: dict = {
                "category": "84",
                "facet_limit": "1000",
                "lang": "en-IN",
                "location_facet_limit": "40",
                "page": str(page),
                "platform": "web-desktop",
                "pttEnabled": "true",
                "query": query,
                "relaxedFilters": "true",
                "size": str(_PAGE_SIZE),
                "spellcheck": "true",
                "user": "anonymous",
            }
            if location_id:
                params["location"] = location_id

            _log.info("olx API page %d — location=%s query=%r", page, loc_label, query)
            try:
                resp = session.get(_API_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json().get("data", [])
            except Exception as exc:
                _log.warning("olx API error page %d location=%s: %s", page, loc_label, exc)
                break

            if not data:
                break

            added = 0
            for item in data:
                raw = _item_to_raw(item, make, model)
                if not raw or raw.source_id in seen:
                    continue
                seen.add(raw.source_id)
                if year_min and raw.year and raw.year < year_min:
                    continue
                if year_max and raw.year and raw.year > year_max:
                    continue
                if budget_max and raw.price > budget_max:
                    continue
                out.append(raw)
                added += 1

            _log.info("olx page %d — %d items, %d kept (total: %d)", page, len(data), added, len(out))

            if len(data) < _PAGE_SIZE:
                break
            page += 1
            time.sleep(_API_DELAY)
