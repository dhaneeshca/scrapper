# Progress

## Phase 1 — Foundation + CarDekho Scraper

- [x] Postgres schema + SQLAlchemy models (`store/db.py`, `store/models.py`)
- [x] Base scraper abstraction (`scraper/base.py`)
- [x] Playwright setup + Chromium installed
- [x] CarDekho scraper (`scraper/cardekho.py`)
- [x] Scraper engine — upsert + price history (`scraper/engine.py`)
- [x] FastAPI app skeleton (`api/main.py`)
- [x] Search configs CRUD (`api/configs.py`)
- [x] Listings list endpoint with filters (`api/listings.py`)
- [x] Manual scrape trigger (`api/scrape.py`)
- [x] React app shell + routing (`web/src/App.tsx`)
- [x] SearchConfigs page — create/edit/delete configs
- [x] Listings table — filters, sort, source badge, shortlist toggle

## Phase 2 — All Sources

- [x] Cars24 scraper (`scraper/cars24.py`)
- [x] CarWale scraper (`scraper/carwale.py`)
- [x] OLX scraper (`scraper/olx.py`) — Playwright stealth for cookie init, internal JSON API for pagination
- [x] CarTrade scraper (`scraper/cartrade.py`) — Playwright, hash URL with makeId.rootId, city IDs
- [x] Spinny scraper (`scraper/spinny.py`) — pure JSON API, no browser
- [x] All 6 scrapers wired into engine

## Phase 3 — Deduplication

- [x] Dedup key on ingest (`scraper/engine.py` → `_dedup_key`)
- [x] `GET /listings/deduped` grouped endpoint (`api/listings.py`)
- [x] UI toggle: All listings / Unique cars (`web/src/pages/Listings.tsx`)
- [x] "N sources" badge + best price display in deduped view
- [x] Fuel type + transmission filters available in both all and unique cars views

## Phase 4 — Variant Price Intelligence

- [x] `GET /stats/price-range` endpoint (`api/stats.py`)
- [x] Stats page — variant × year price range table (`web/src/pages/Stats.tsx`)
- [x] Listing count per cell + color scale
- [x] Quick pick from existing search configs
- [x] Deal score on listing rows (compares price against fair value band for variant/year)

## Phase 5 — Shortlist + Comparison

- [x] Shortlist toggle on listing row (all and deduped modes)
- [x] `POST/DELETE /shortlist`, `GET /shortlist` endpoints (`api/shortlist.py`)
- [x] Not interested toggle — hides listings from default view
- [x] Shortlist page — card grid with notes editing (`web/src/pages/Shortlist.tsx`)
- [x] Side-by-side comparison table for up to 4 selected cars
- [x] Best price highlighted in green in compare view

## Phase 6 — Variant Normalisation + SSE Scraping

- [x] `variant_aliases` table — maps raw scraped variant names to canonical names
- [x] Variants page — review unconfirmed aliases, confirm/reject/edit
- [x] `variant_canonical` on listings — used for deal score and stats, raw name preserved for display
- [x] SSE stream endpoint `GET /api/scrape/:id/stream` — real-time per-source progress
- [x] SearchConfigs page wired to SSE — live inserted/updated counts per source

## Phase 7 — State-Based City Config

- [x] `source_city_configs` table — per-city per-source flags and config (`store/models.py`)
- [x] `api/source_cities.py` — CRUD endpoints (list by state, upsert source config, add/delete city)
- [x] States tab (`web/src/pages/SourceCities.tsx`) — manage cities, toggle sources, edit JSON config inline
- [x] Engine expanded to load city configs from DB and pass to scrapers (`scraper/engine.py`)
- [x] All 6 scrapers updated to use `city_configs` when provided, fall back to hardcoded maps otherwise
- [x] `SearchConfig.regions` migrated from city lists to state keys (idempotent migration in `init_db`)
- [x] `StateMultiSelect` in SearchConfigs form — dropdown populated from DB states
- [x] `POST /api/scrape/state/:state_key` — trigger all active configs for a state in background
- [x] ▶ Run button per state in the States tab
- [x] Seed covers Tamil Nadu (16 cities) + 9 other states across all 6 sources

## Phase 8 — Auto Refresh + Alerts

- [ ] APScheduler wired into `main.py`
- [ ] Configurable scrape interval per config (or global)
- [ ] "New since last run" tracking
- [ ] macOS desktop notification via osascript
