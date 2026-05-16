# Used Car Scraper

A self-hosted used-car research tool for the Indian market. Scrapes listings from multiple platforms, deduplicates them, tracks prices over time, and surfaces deal scores against fair market value — all in a local web UI.

---

## Features

- **Multi-source scraping** — Cars24, CarWale, CarDekho, CarTrade, Spinny, OLX
- **Deduplication** — fuzzy cross-source matching so the same car appears once
- **Deal score** — compares each listing against the fair price band for that variant/year
- **Price history** — tracks price changes across scrape runs
- **Shortlist** — save and annotate cars you want to follow
- **Car Info** — generational feature diff across variant trims (scraped from manufacturer specs)
- **Variant normalisation** — raw scraped names are preserved; canonical names are used only for analysis

---

## Quick Start

```bash
# 1. Clone
git clone git@github.com:dhaneeshca/scrapper.git
cd scrapper

# 2. One-time setup — installs Python/Node if missing, creates DB, seeds configs
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

Change `DATABASE_URL` if your Postgres user/port differs.

---

## Make Targets

| Target | What it does |
|--------|--------------|
| `make setup` | Full first-time setup: checks tools, starts Postgres, creates DB, installs Python + Node deps, installs Playwright browser, seeds default search configs |
| `make run` | Builds frontend, starts production API server on `:8000` |
| `make dev` | Starts backend (`:8000`, hot reload) + Vite dev server (`:5173`) in parallel |
| `make build` | Builds frontend static files into `web/dist/` |
| `make seed` | Seeds default search configs if none exist |
| `make db-start` | Starts Postgres via Homebrew services if not running |

---

## Architecture

```
scrapper/
├── api/           FastAPI routes (listings, configs, scrape, stats, specs, variants)
├── scraper/       Per-source scrapers (Cars24, CarWale, OLX, …) + dedup engine
├── store/         SQLAlchemy models + DB init
├── web/           React + Vite + Tailwind frontend
├── main.py        Production entry point (uvicorn)
├── dev.py         Dev runner (backend + Vite in parallel)
└── Makefile
```

### Scrapers

| Source | Strategy |
|--------|----------|
| Cars24, CarWale, CarDekho, CarTrade, Spinny | Playwright (headless Chromium) |
| OLX | Playwright for cookie init (Akamai bot check) → internal JSON API for pagination |

### Data flow

1. UI triggers scrape for a config → `POST /api/scrape/{config_id}`
2. Scraper engine runs all enabled sources in sequence
3. Results are deduped (fuzzy match on make/model/variant/year/km) and upserted
4. Variant names are fuzzy-matched against `variant_aliases` table → `variant_canonical` filled
5. Listings UI shows raw scraped variant names; deal score and fair value use canonical

---

## Default Search Configs

`make setup` seeds two configs if the DB is empty:

| Config | Make | Model | Years | Budget |
|--------|------|-------|-------|--------|
| Skoda Rapid 2017–2022 | Skoda | Rapid | 2017–2022 | ₹9 L |
| Skoda Slavia | Skoda | Slavia | 2022+ | ₹14 L |

Add more from the **Configs** tab in the UI or via:

```bash
curl -s -X POST http://localhost:8000/api/configs/ \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Honda City 2018-2023",
    "make": "Honda", "model": "City",
    "year_min": 2018, "year_max": 2023,
    "budget_max": 1000000,
    "regions": ["Chennai", "Bangalore", "Mumbai"]
  }'
```
