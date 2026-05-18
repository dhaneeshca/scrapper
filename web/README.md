# Frontend

React + TypeScript + Vite + Tailwind. Dark-theme UI for the used-car scraper.

See the [root README](../README.md) for setup and run instructions.

## Dev

```bash
npm install
npm run dev   # → http://localhost:5173 (proxies /api to :8000)
```

## Build

```bash
npm run build   # outputs to dist/ — served by the FastAPI app in production
```

## Pages

| Page | Route | Description |
|------|-------|-------------|
| Listings | default | All listings + Unique cars (deduped) with filters, deal score, shortlist |
| Searches | Searches tab | Search config CRUD, scrape trigger with live SSE progress |
| States | States tab | City-source config — toggle sources per city, edit JSON config, run per state |
| Shortlist | Shortlist tab | Saved cars + side-by-side comparison |
| Stats | Stats tab | Variant × year price heatmap |
