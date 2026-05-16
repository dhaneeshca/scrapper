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
- [x] Entry point wiring (`main.py`)

## Phase 2 — All Sources

- [x] Cars24 scraper (`scraper/cars24.py`)
- [x] CarWale scraper (`scraper/carwale.py`)
- [x] OLX scraper (`scraper/olx.py`) — requires playwright-stealth
- [x] All scrapers wired into engine (`scraper/engine.py`)

## Phase 3 — Deduplication

- [x] Dedup key computation on ingest (`scraper/engine.py` → `_dedup_key`)
- [x] `GET /listings/deduped` grouped endpoint (`api/listings.py`)
- [x] UI toggle: All listings / Unique cars (`web/src/pages/Listings.tsx`)
- [x] "N sources" badge + best price display in deduped view

## Phase 4 — Variant Price Intelligence

- [x] `GET /stats/price-range` endpoint (`api/stats.py`)
- [x] Stats page — variant × year price range table (`web/src/pages/Stats.tsx`)
- [x] Listing count per cell + color scale (low → high)
- [x] Quick pick from existing search configs

## Phase 5 — Shortlist + Comparison

- [x] Shortlist toggle on listing row (both all and deduped modes)
- [x] `POST/DELETE /shortlist`, `GET /shortlist` endpoints (`api/shortlist.py`)
- [x] Shortlist page — card grid with notes editing (`web/src/pages/Shortlist.tsx`)
- [x] Side-by-side comparison table for up to 4 selected cars
- [x] Best price highlighted in green in compare view

## Phase 6 — Auto Refresh + Alerts

- [ ] APScheduler wired into main.py
- [ ] Configurable interval per config (or global)
- [ ] "New since last run" tracking
- [ ] macOS desktop notification via osascript
