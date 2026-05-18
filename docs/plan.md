# Architecture & Design

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Best scraping ecosystem |
| Scraping | Playwright (headless Chromium) | JS-rendered pages on CarDekho, Cars24, CarTrade |
| Storage | PostgreSQL (local) via SQLAlchemy | JSONB for arrays, easy ad-hoc queries |
| Backend API | FastAPI | Async, auto-docs, minimal boilerplate |
| Frontend | React + Vite + Tailwind | Fast to build, dark-theme UI |

---

## Data Model

### `search_configs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | TEXT | "Skoda Slavia Hunt" |
| make | TEXT | "Skoda" |
| model | TEXT | "Slavia" |
| variants | JSONB | `["Style", "Ambition"]` — optional filter |
| year_min | INTEGER | |
| year_max | INTEGER | |
| budget_max | INTEGER | INR |
| regions | JSONB | `["tamil-nadu", "karnataka"]` — state keys |
| is_active | BOOLEAN | pause without deleting |
| created_at | TIMESTAMPTZ | |

### `source_city_configs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| state_name | TEXT | "Tamil Nadu" |
| state_key | TEXT | "tamil-nadu" |
| city_name | TEXT | "Chennai" |
| city_key | TEXT | "chennai" |
| source | TEXT | olx / cartrade / cars24 / spinny / carwale / cardekho |
| is_supported | BOOLEAN | whether this source scrapes this city |
| source_config | JSONB | source-specific metadata (OLX location IDs, CarTrade city IDs, etc.) |

One row per `(city_key, source)` pair. Engine loads all rows for requested states and passes them to scrapers.

### `listings`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| source | TEXT | cardekho / carwale / cars24 / olx / spinny / cartrade |
| source_id | TEXT | original ID on the source site |
| url | TEXT | |
| make, model, variant | TEXT | raw scraped values |
| variant_canonical | TEXT | normalised name from variant_aliases |
| year | INTEGER | |
| km_driven | INTEGER | |
| fuel_type | TEXT | |
| transmission | TEXT | |
| price | INTEGER | INR |
| location_city, location_state | TEXT | |
| seller_type | TEXT | dealer / individual |
| images | JSONB | array of image URLs |
| scraped_at, last_seen_at | TIMESTAMPTZ | |
| is_active | BOOLEAN | false when listing disappears |
| is_manually_edited | BOOLEAN | prevents canonical override after manual edit |
| dedup_key | TEXT | `make_model_year_kmbucket_city` |
| config_id | UUID FK | → search_configs |

### `price_history`

| Column | Type | Notes |
|---|---|---|
| listing_id | UUID FK | → listings |
| price | INTEGER | |
| observed_at | TIMESTAMPTZ | |

### `shortlist` / `not_interested`

| Column | Type |
|---|---|
| listing_id | UUID PK FK |
| notes | TEXT |
| added_at | TIMESTAMPTZ |

### `variant_aliases`

| Column | Type | Notes |
|---|---|---|
| make, model | TEXT | scopes alias to a model |
| raw_variant | TEXT | scraped string |
| canonical_variant | TEXT | normalised string |
| confirmed | BOOLEAN | only confirmed aliases are applied |

---

## Deduplication

`dedup_key = {make}_{model}_{year}_{km_bucket}_{city}` where `km_bucket` rounds `km_driven` to nearest 5,000.

Listings sharing a dedup_key are the same physical car on multiple platforms. The "Unique cars" view merges them into one row showing the lowest price and all source badges.

---

## Scraper City Config

The engine resolves `search_config.regions` (state keys) → cities via `source_city_configs`:

```
state_keys = config.regions              # e.g. ["tamil-nadu"]
city_rows  = query(state_key.in_(...))   # all cities for those states
city_configs = {city_key: {source: {is_supported, source_config}}}
```

Each scraper receives `city_configs` and uses it to decide:
- **OLX**: deduplicate to unique states, use `location_id` from config
- **CarTrade**: use `city_id` + `slug` from config
- **Cars24 / Spinny**: check `is_supported` flag, use `slug` override if set
- **CarWale / CardEkho**: build URL from city key, filter results to that city

Fallback: if `city_configs` is `None` (DB not seeded), scrapers use hardcoded maps.

---

## Anti-Bot Notes

| Site | Risk | Mitigation |
|---|---|---|
| CarDekho | Medium | Playwright, realistic UA, location filter |
| Cars24 | Medium | Playwright, React hydration wait |
| CarWale | Low | Playwright, anchor link scrape |
| CarTrade | Medium | Playwright, hash URL trick |
| Spinny | Low | Pure JSON API, urllib |
| OLX | High | playwright-stealth for cookie init, then requests session |

---

## Directory Structure

```
scrapper/
├── api/
│   ├── main.py          FastAPI app, CORS, static file serving
│   ├── listings.py      Listings CRUD + deduped view
│   ├── configs.py       Search config CRUD
│   ├── scrape.py        Scrape triggers + SSE stream
│   ├── source_cities.py City-source config management
│   ├── shortlist.py     Shortlist + not-interested
│   ├── stats.py         Price range stats
│   ├── specs.py         Car spec scraping
│   └── variants.py      Variant alias management
├── scraper/
│   ├── base.py          Abstract Scraper
│   ├── engine.py        Orchestration, upsert, dedup, price history
│   ├── cardekho.py
│   ├── cars24.py
│   ├── carwale.py
│   ├── cartrade.py
│   ├── spinny.py
│   └── olx.py
├── store/
│   ├── db.py            Engine, session, init_db (schema + migrations)
│   └── models.py        ORM models
├── web/
│   └── src/
│       ├── App.tsx
│       ├── lib/
│       │   └── constants.ts   Source colours, source list
│       └── pages/
│           ├── Listings.tsx
│           ├── SearchConfigs.tsx
│           ├── SourceCities.tsx
│           ├── Shortlist.tsx
│           └── Stats.tsx
├── docs/
├── seed.py
├── main.py
├── dev.py
└── Makefile
```
