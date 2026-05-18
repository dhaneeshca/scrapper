import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from store.db import init_db
from api import configs, listings, shortlist, not_interested, stats, scrape, variants, specs, source_cities

app = FastAPI(title="scrapper", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(configs.router, prefix="/api/configs", tags=["configs"])
app.include_router(listings.router, prefix="/api/listings", tags=["listings"])
app.include_router(shortlist.router, prefix="/api/shortlist", tags=["shortlist"])
app.include_router(not_interested.router, prefix="/api/not-interested", tags=["not_interested"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(scrape.router, prefix="/api/scrape", tags=["scrape"])
app.include_router(variants.router, prefix="/api/variants", tags=["variants"])
app.include_router(specs.router, prefix="/api/specs", tags=["specs"])
app.include_router(source_cities.router, prefix="/api/source-cities", tags=["source_cities"])

# Serve the built React app when web/dist exists (production / `make run`)
_DIST = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        return FileResponse(os.path.join(_DIST, "index.html"))
