# Plan

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Best scraping ecosystem |
| Scraping | Playwright (headless Chromium) | JS-rendered pages on CarDekho, Cars24 |
| Storage | PostgreSQL (local) via SQLAlchemy | Already running locally, JSONB for arrays, easy to query |
| Backend API | FastAPI | Async, auto-docs, minimal boilerplate |
| Frontend | React + Tailwind | Clean, fast to build |

---

## Data Model

### `search_configs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | TEXT | "My Verna Hunt" |
| make | TEXT | "Hyundai" |
| model | TEXT | "Verna" |
| variants | JSONB | `["S", "SX", "SX(O)"]` |
| year_min | INTEGER | |
| year_max | INTEGER | |
| fuel_types | JSONB | `["Petrol"]` |
| transmissions | JSONB | `["Manual", "Automatic"]` |
| budget_max | INTEGER | in INR |
| regions | JSONB | `["Bangalore", "Chennai"]` |
| is_active | BOOLEAN | pause without deleting |
| created_at | TIMESTAMPTZ | |

### `listings`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| source | TEXT | cardekho / carwale / cars24 / olx |
| source_id | TEXT | original ID on the source site |
| url | TEXT | |
| make | TEXT | |
| model | TEXT | |
| variant | TEXT | normalized |
| year | INTEGER | |
| km_driven | INTEGER | |
| fuel_type | TEXT | |
| transmission | TEXT | |
| price | INTEGER | INR |
| location_city | TEXT | |
| location_state | TEXT | |
| seller_type | TEXT | dealer / individual |
| images | JSONB | array of image URLs |
| description | TEXT | |
| listed_at | DATE | date shown on site |
| scraped_at | TIMESTAMPTZ | |
| last_seen_at | TIMESTAMPTZ | |
| is_active | BOOLEAN | false when listing disappears |
| dedup_key | TEXT | for cross-site grouping |
| config_id | UUID FK | → search_configs |

### `price_history`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| listing_id | UUID FK | → listings |
| price | INTEGER | |
| observed_at | TIMESTAMPTZ | |

### `shortlist`

| Column | Type | Notes |
|---|---|---|
| listing_id | UUID PK FK | → listings |
| notes | TEXT | |
| added_at | TIMESTAMPTZ | |

---

## Deduplication

Dedup key = `{make}_{model}_{year}_{km_bucket}_{city}` where km_bucket rounds km_driven to the nearest 5,000.

Listings that share a dedup_key are the same physical car on multiple platforms. The UI merges them into one row with a "N sources" badge, showing the lowest price.

---

## Directory Structure

```
scrapper/
├── scraper/
│   ├── base.py        # Abstract Scraper: search(config) → List[RawListing]
│   ├── engine.py      # Runs all scrapers, handles DB upsert + price history
│   ├── cardekho.py
│   ├── carwale.py
│   ├── cars24.py
│   └── olx.py
├── store/
│   ├── db.py          # SQLAlchemy engine + session
│   └── models.py      # ORM models
├── api/
│   ├── main.py        # FastAPI app, CORS, router mount
│   ├── listings.py    # GET /listings, GET /listings/deduped, GET /listings/:id
│   ├── configs.py     # CRUD /configs
│   ├── shortlist.py   # POST/DELETE /shortlist, GET /shortlist
│   ├── stats.py       # GET /stats/price-range
│   └── scrape.py      # POST /scrape (manual trigger)
├── web/
│   └── src/
│       ├── App.tsx
│       └── pages/
│           ├── Listings.tsx       # Main table + filters
│           ├── SearchConfigs.tsx  # Manage search configs
│           ├── Shortlist.tsx      # Saved + comparison view
│           └── Stats.tsx          # Variant × year price heatmap
├── data/              # gitignored (seed JSONs)
├── problem.md
├── plan.md
├── progress.md
├── requirements.txt
├── .env.example
├── .gitignore
└── main.py            # Entry point: uvicorn + APScheduler
```

---

## Scraper Flow

1. For each active `search_config`:
   - Run each enabled scraper (CarDekho, Cars24, CarWale, OLX) sequentially
   - 2–3 second delay between page fetches (rate limiting)
2. Each scraper returns `List[RawListing]` (common schema)
3. Engine upserts into `listings`:
   - New listing → INSERT, log initial price in `price_history`
   - Existing (matched by `source` + `source_id`) → UPDATE `price`, `last_seen_at`; if price changed → INSERT into `price_history`
4. After each run, mark listings not seen as `is_active = false`

---

## Anti-Bot Notes

| Site | Risk | Mitigation |
|---|---|---|
| CarDekho | Medium — JS rendered | Playwright, realistic UA |
| Cars24 | Medium — JS rendered | Playwright, realistic UA |
| CarWale | Low — mostly static | requests + BeautifulSoup fallback |
| OLX | High — headless detection | playwright-stealth |
| Spinny | Low — public JSON API | urllib, no browser |
| CarTrade | Medium — JS hydration | Playwright, hash URL with makeId.rootId |

If a site blocks: cache last result, flag in UI as "stale (last refreshed: X hours ago)".

---

## Phases

### Phase 1 — Foundation + CarDekho
- Postgres schema + SQLAlchemy models
- Base scraper + Playwright setup
- CarDekho scraper
- FastAPI: configs CRUD + listings list
- React UI: SearchConfig form, listings table
- Manual scrape via POST /scrape

### Phase 2 — All Sources
- Cars24, CarWale, OLX scrapers
- Source badge per listing row

### Phase 3 — Deduplication
- Dedup key on ingest
- GET /listings/deduped grouped view
- UI toggle: All listings vs Unique cars

### Phase 4 — Variant Price Intelligence
- GET /stats/price-range → variant × year breakdown
- Stats page: price range table + listing counts

### Phase 5 — Shortlist + Comparison
- Shortlist toggle
- Side-by-side comparison (up to 4 cars)
- Notes per car

### Phase 6 — Additional Sources
- Spinny scraper: pure JSON API (`api.spinny.com/v3/api/listing/v6/`), no browser
- CarTrade scraper: Playwright, hash URL `#city={cityId}&car={makeId}.{rootId}`, city IDs from radio buttons
