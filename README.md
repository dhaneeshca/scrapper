# Used Car Scraper

A self-hosted used-car research tool for the Indian market. Scrapes listings from six platforms, deduplicates them, tracks prices over time, and surfaces deal scores against fair market value — all in a local web UI.

---

## Features

- **Multi-source scraping** — Cars24, CarWale, CarDekho, CarTrade, Spinny, OLX
- **Deduplication** — fuzzy cross-source matching so the same car appears once in "Unique cars" view
- **Deal score** — compares each listing against the fair price band for that variant/year
- **Price history** — tracks price changes across scrape runs
- **Live scrape progress** — SSE stream shows per-source results in real time
- **State-based city config** — States tab lets you manage which cities and sources are active; configs reference states, engine expands to all cities automatically
- **Shortlist** — save and compare up to 4 cars side by side
- **Variant normalisation** — raw scraped names preserved; canonical names used for deal score and stats
- **Not interested** — dismiss listings you don't want to see again
- **Stats** — variant × year price range heatmap to understand fair value

---

## Quick Start

```bash
# 1. Clone
git clone git@github.com:dhaneeshca/scrapper.git
cd scrapper

# 2. One-time setup — installs Python/Node deps, creates DB, seeds configs
make setup

# 3. Run (builds frontend, starts API server)
make run
# → http://localhost:8000
```

For development with hot reload on both frontend and backend:

```bash
make dev
# backend  → http://localhost:8000  (uvicorn --reload)
# frontend → http://localhost:5173  (Vite dev server)
```

---

## Prerequisites

`make setup` will install missing tools automatically **if [Homebrew](https://brew.sh) is available**. Otherwise install manually:

| Tool | Min version | Install |
|------|-------------|---------|
| Python | 3.11+ | `brew install python` |
| Node.js | 18+ | `brew install node` |
| PostgreSQL | 14+ | `brew install postgresql@16` |

---

## Configuration

Copy `.env.example` to `.env` (done automatically by `make setup`):

```env
DATABASE_URL=postgresql://localhost:5432/scrapper
SCRAPE_INTERVAL_HOURS=6
```

---

## Make Targets

| Target | What it does |
|--------|--------------|
| `make setup` | Full first-time setup: checks tools, starts Postgres, creates DB, installs deps, installs Playwright browser, seeds default configs |
| `make run` | Builds frontend, starts production API server on `:8000` |
| `make dev` | Starts backend (`:8000`, hot reload) + Vite dev server (`:5173`) in parallel |
| `make build` | Builds frontend static files into `web/dist/` |
| `make seed` | Seeds default search configs and city source configs |
| `make db-start` | Starts Postgres via Homebrew services if not running |

---

## Architecture

```
scrapper/
├── api/
│   ├── main.py          FastAPI app, CORS, router mount
│   ├── listings.py      GET /listings, /listings/deduped, /listings/:id, PATCH
│   ├── configs.py       CRUD /configs
│   ├── scrape.py        POST /scrape/:id, /scrape/state/:state_key (SSE stream)
│   ├── source_cities.py GET/PUT/POST/DELETE /source-cities (city-source config)
│   ├── shortlist.py     POST/DELETE /shortlist
│   ├── stats.py         GET /stats/price-range, /stats/config/:id/sources
│   ├── specs.py         Car spec scraping
│   └── variants.py      Variant alias management
├── scraper/
│   ├── base.py          Abstract Scraper interface
│   ├── engine.py        Runs scrapers, upserts listings, price history, dedup
│   ├── cardekho.py      Playwright — JS-rendered cards
│   ├── cars24.py        Playwright — React hydration
│   ├── carwale.py       Playwright — paginated anchor links
│   ├── cartrade.py      Playwright — hash URL with makeId.rootId
│   ├── spinny.py        Pure JSON API (no browser)
│   └── olx.py           Playwright cookie init → internal JSON API pagination
├── store/
│   ├── db.py            SQLAlchemy engine, init_db (migrations), session
│   └── models.py        ORM models
├── web/src/
│   ├── App.tsx          Tab routing
│   ├── lib/constants.ts Shared source colours, source list
│   └── pages/
│       ├── Listings.tsx       All listings + Unique cars (deduped) with filters
│       ├── SearchConfigs.tsx  Manage search configs, trigger scrapes, SSE progress
│       ├── SourceCities.tsx   States tab — city-source config, per-state run
│       ├── Shortlist.tsx      Saved cars + side-by-side comparison
│       └── Stats.tsx          Variant × year price heatmap
├── seed.py              Seeds search configs + city-source config (idempotent)
├── main.py              Production entry point (uvicorn)
├── dev.py               Dev runner (backend + Vite in parallel)
└── Makefile
```

### Scrapers

| Source | Strategy |
|--------|----------|
| CarDekho | Playwright (headless Chromium) |
| Cars24 | Playwright — React hydration wait |
| CarWale | Playwright — paginated anchor scrape |
| CarTrade | Playwright — hash URL with `makeId.rootId`, city IDs from DB |
| Spinny | Pure JSON API — no browser needed |
| OLX | Playwright for cookie/bot-check init, then internal JSON API for pagination |

### Data flow

1. User triggers scrape for a config → `POST /api/scrape/{config_id}` (or SSE stream variant)
2. Engine expands config's state keys (e.g. `["tamil-nadu"]`) into all active cities from `source_city_configs`
3. Each scraper receives `city_configs` dict and uses per-source flags (`is_supported`, `source_config`) to decide which cities to scrape and what IDs/slugs to use
4. Results are deduplicated (fuzzy key: `make_model_year_km-bucket_city`) and upserted
5. Variant names are matched against confirmed `variant_aliases` → `variant_canonical` filled for deal scoring
6. Listings not seen this run are marked `is_active = false`

### State-based city config

Cities and their per-source metadata live in `source_city_configs`. Manage them from the **States** tab:

- Toggle each source on/off per city
- Edit `source_config` JSON inline (e.g. OLX location IDs, CarTrade city IDs)
- Add cities or whole new states
- ▶ Run button per state triggers all active search configs linked to that state

Search configs reference states (`regions: ["tamil-nadu"]`), not individual cities. Adding a city to a state in the States tab automatically includes it in all configs that reference that state.

---

## Default Search Configs

`make setup` seeds two configs:

| Config | Make | Model | Years | Budget |
|--------|------|-------|-------|--------|
| Skoda Rapid 2017–2022 | Skoda | Rapid | 2017–2022 | ₹9 L |
| Skoda Slavia | Skoda | Slavia | 2022+ | ₹14 L |

Add more from the **Searches** tab in the UI or via:

```bash
curl -s -X POST http://localhost:8000/api/configs/ \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Honda City 2018-2023",
    "make": "Honda", "model": "City",
    "year_min": 2018, "year_max": 2023,
    "budget_max": 1000000,
    "regions": ["tamil-nadu"]
  }'
```

`regions` takes state keys (e.g. `"tamil-nadu"`, `"karnataka"`). The engine resolves these to cities using the States tab config.
