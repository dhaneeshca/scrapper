"""
CarDekho spec-page scraper — response-interception approach.

The /api/v3/model/pwamodelspecs endpoint requires a server-generated sessionid
from the page JS, so we cannot call it directly.  Instead we:
  1. Load the spec page once via Playwright.
  2. For each variant, click it via the typeahead and intercept the JSON
     response that CarDekho fires automatically.
  3. Parse the intercepted JSON for boolean feature categories.

Response structure:
  data["data"]["specs"] → dict with keys "specification", "featured", "keySpecs"
  data["data"]["specs"]["specification"] → list of
    {id, heading/title, items: [{text, value, ...}]}
  item["value"]: "Yes" | "Not Available" | etc.

URL pattern: https://www.cardekho.com/{make}/{model}/specs  (lowercase)
"""
import logging
import re
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

_log = logging.getLogger(__name__)

_BASE = "https://www.cardekho.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SKIP_CATEGORIES = {
    "engine & transmission",
    "fuel & performance",
    "suspension, steering & brakes",
    "dimensions & capacity",
    "fuel economy",
    "mileage",
    "performance",
    "engine",
    "dimensions",
}
_VARIANT_INPUT = "#techSpecsAllVariantId"
_DROPDOWN_ITEM = ".gs_ta_results li, .typeHeadContainer li"
_SPEC_SECTION  = ".specsRight"
_API_PATH      = "pwamodelspecs"

_stealth = Stealth()

_YES_VALUES = {"yes", "available", "standard", "1", "true"}
_NO_VALUES  = {"no", "not available", "0", "false", "-", "na", "n/a", "–", "—"}


def _spec_url(make: str, model: str) -> str:
    m  = make.strip().lower().replace(" ", "-")
    mo = model.strip().lower().replace(" ", "-")
    return f"{_BASE}/{m}/{mo}/specs"


def _clean_variant_name(raw: str, make: str, model: str) -> str:
    """Strip 'Make Model ' prefix and ' (Fuel) NN Lakh*' suffix."""
    name = raw.strip()
    prefix = f"{make.strip().title()} {model.strip().title()} "
    if name.startswith(prefix):
        name = name[len(prefix):]
    name = re.sub(r"\s*\([^)]+\)\s*[\d.,]+\s*Lakh\*?.*$", "", name, flags=re.IGNORECASE)
    return name.strip()


def _find_list(d: dict, *keys) -> list:
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
    return []


def _find_str(d: dict, *keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _bool_value(item: dict) -> Optional[bool]:
    """Return True/False from item dict, or None if value is non-boolean (e.g. "5 seater")."""
    for key in ("value", "status", "val"):
        raw = item.get(key)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int) and raw in (0, 1):
            return bool(raw)
        if isinstance(raw, str):
            norm = raw.strip().lower()
            if norm in _YES_VALUES:
                return True
            if norm in _NO_VALUES:
                return False
    return None


def _parse_features(data: dict) -> dict[str, dict[str, bool]]:
    """
    Convert CarDekho API response into {category: {feature: bool}}.
    Skips engine/dimension categories and non-boolean value rows.
    """
    features: dict[str, dict[str, bool]] = {}
    inner = data.get("data") or {}

    specs_obj = inner.get("specs")
    if not specs_obj:
        _log.debug("no 'specs' key in data['data']; keys: %s", list(inner.keys())[:10])
        return features

    if isinstance(specs_obj, list):
        specs_list = specs_obj
    elif isinstance(specs_obj, dict):
        # "featured" has the boolean feature sections (Safety, Comfort, etc.)
        # "specification" has engine/dimension data — skip it
        specs_list = (
            specs_obj.get("featured") or
            specs_obj.get("specification") or
            []
        )
    else:
        return features

    for section in specs_list:
        if not isinstance(section, dict):
            continue
        cat = _find_str(section, "heading", "title", "category", "id", "name")
        if not cat or cat.lower() in _SKIP_CATEGORIES:
            continue

        items = _find_list(section, "items", "features", "specs", "list")
        cat_feats: dict[str, bool] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _find_str(item, "text", "name", "title", "featureName", "label")
            if not name:
                continue
            val = _bool_value(item)
            if val is not None:
                cat_feats[name] = val

        if cat_feats:
            features[cat] = cat_feats

    return features


def _open_dropdown(page) -> bool:
    """
    Clear the typeahead input and reopen the dropdown.
    Must blur first — clicking an already-focused input does not re-trigger onFocus.
    Returns True if dropdown items are visible after the attempt.
    """
    try:
        page.evaluate("document.querySelector('#techSpecsAllVariantId')?.blur()")
        page.wait_for_timeout(200)
        page.fill(_VARIANT_INPUT, "")
        page.wait_for_timeout(300)
        page.click(_VARIANT_INPUT, timeout=4_000)
        page.wait_for_selector(_DROPDOWN_ITEM, state="visible", timeout=8_000)
        return True
    except PlaywrightTimeout:
        return False


def scrape_specs(make: str, model: str) -> list[dict]:
    """
    Scrape all variant specs for make+model from CarDekho.

    Returns a list of dicts:
      {variant, year_from, year_to, features, source_url}
    year_from/year_to are None (not available on the spec page).
    """
    url = _spec_url(make, model)
    results: list[dict] = []
    _log.info("spec scrape start — %s %s — %s", make, model, url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=_UA)
        page = ctx.new_page()
        _stealth.apply_stealth_sync(page)
        page.set_extra_http_headers({"Accept-Language": "en-IN,en;q=0.9"})

        # ── Load spec page ─────────────────────────────────────────────────
        try:
            page.goto(url, wait_until="networkidle", timeout=40_000)
            page.wait_for_selector(_SPEC_SECTION, timeout=15_000)
        except PlaywrightTimeout:
            _log.warning("spec page timeout or not found: %s", url)
            browser.close()
            return []

        page.wait_for_timeout(2000)

        # ── Collect all variant option texts ───────────────────────────────
        try:
            page.focus(_VARIANT_INPUT)
            page.wait_for_timeout(500)
            page.click(_VARIANT_INPUT, timeout=5_000)
            page.wait_for_selector(_DROPDOWN_ITEM, timeout=8_000)
            option_texts: list[str] = page.evaluate("""
                () => [...document.querySelectorAll('.gs_ta_results li, .typeHeadContainer li')]
                      .map(li => li.innerText.trim())
                      .filter(Boolean)
            """)
        except PlaywrightTimeout:
            raw = page.input_value(_VARIANT_INPUT) or f"{make} {model}"
            _log.warning("dropdown did not open — single-variant fallback: %s", raw[:60])
            option_texts = [raw]

        _log.info("found %d variant options — %s %s", len(option_texts), make, model)

        # ── Iterate variants: click → intercept JSON response ──────────────
        seen: set[str] = set()

        for i, opt in enumerate(option_texts):
            variant_name = _clean_variant_name(opt, make, model)
            if not variant_name or variant_name in seen:
                continue
            seen.add(variant_name)

            try:
                if not _open_dropdown(page):
                    _log.warning("dropdown did not reopen for variant: %s", variant_name)
                    continue

                # Verify the target option is visible before setting up response listener
                all_opts = page.evaluate("""
                    () => [...document.querySelectorAll('.gs_ta_results li, .typeHeadContainer li')]
                          .map(li => li.innerText.trim())
                """)
                if opt not in all_opts:
                    _log.warning("option '%s' not in current dropdown list", variant_name)
                    continue

                with page.expect_response(
                    lambda r: _API_PATH in r.url and r.status == 200,
                    timeout=15_000,
                ) as resp_info:
                    clicked = page.evaluate("""
                        (targetText) => {
                            const items = document.querySelectorAll(
                                '.gs_ta_results li, .typeHeadContainer li');
                            for (const li of items) {
                                if (li.innerText.trim() === targetText) {
                                    li.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """, opt)

                if not clicked:
                    _log.warning("option not clicked: %s", variant_name)
                    continue

            except PlaywrightTimeout:
                _log.warning("no API response for variant: %s", variant_name)
                continue
            except Exception as exc:
                _log.warning("variant '%s' failed: %s", variant_name, exc)
                continue

            try:
                api_data = resp_info.value.json()
            except Exception as exc:
                _log.warning("JSON parse failed for variant %s: %s", variant_name, exc)
                continue

            features = _parse_features(api_data)
            if not features:
                _log.warning("no boolean features for variant: %s", variant_name)
                continue

            results.append({
                "variant": variant_name,
                "year_from": None,
                "year_to": None,
                "features": features,
                "source_url": url,
            })
            _log.info(
                "variant %d/%d: %s — %d categories",
                i + 1, len(option_texts), variant_name, len(features),
            )

        browser.close()

    _log.info("spec scrape done — %s %s — %d variants", make, model, len(results))
    return results
