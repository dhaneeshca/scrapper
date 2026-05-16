import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from store.db import get_session
from store.models import SearchConfig
from scraper.engine import run_config

_log = logging.getLogger(__name__)

_VALID_SOURCES = {"cardekho", "cars24", "carwale", "olx", "spinny", "cartrade"}
_executor = ThreadPoolExecutor(max_workers=4)

router = APIRouter()


def _run_all_active():
    with get_session() as session:
        configs = session.query(SearchConfig).filter_by(is_active=True).all()
        config_ids = [c.id for c in configs]
    for cid in config_ids:
        run_config(cid)


@router.post("/")
def scrape_all(background_tasks: BackgroundTasks):
    """Trigger a scrape run for all active configs."""
    _log.info("scrape all active configs triggered")
    background_tasks.add_task(_run_all_active)
    return {"ok": True, "message": "scrape started in background"}


@router.post("/{config_id}")
def scrape_one(config_id: str):
    """Run all scrapers for a single config synchronously and return the summary."""
    with get_session() as session:
        if not session.query(SearchConfig).filter_by(id=config_id).first():
            raise HTTPException(404, "config not found")
    _log.info("scrape one — config=%s", config_id)
    result = run_config(config_id)
    _log.info("scrape one done — config=%s  %s", config_id, result)
    return {"ok": True, **result}


@router.post("/{config_id}/{source}")
def scrape_source(config_id: str, source: str):
    """Run a single scraper for a config synchronously and return the summary."""
    if source not in _VALID_SOURCES:
        raise HTTPException(400, f"unknown source '{source}', valid: {sorted(_VALID_SOURCES)}")
    with get_session() as session:
        if not session.query(SearchConfig).filter_by(id=config_id).first():
            raise HTTPException(404, "config not found")
    _log.info("scrape source — config=%s  source=%s", config_id, source)
    result = run_config(config_id, source=source)
    _log.info("scrape source done — config=%s  source=%s  %s", config_id, source, result)
    return {"ok": True, **result}


@router.get("/{config_id}/stream")
async def scrape_stream(config_id: str, source: Optional[str] = None):
    """
    SSE endpoint — streams scraping progress as newline-delimited JSON events.

    Event shapes:
      {"type": "scraper_start", "source": "cardekho", "regions": [...]}
      {"type": "scraper_done",  "source": "cardekho", "inserted": N, "updated": N, "price_changes": N}
      {"type": "scraper_error", "source": "cardekho", "message": "..."}
      {"type": "done",          "inserted": N, "updated": N, "price_changes": N, "errors": [...]}
    """
    if source and source not in _VALID_SOURCES:
        raise HTTPException(400, f"unknown source '{source}'")
    with get_session() as session:
        if not session.query(SearchConfig).filter_by(id=config_id).first():
            raise HTTPException(404, "config not found")

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_progress(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    def run_in_thread() -> None:
        try:
            run_config(config_id, source=source, on_progress=on_progress)
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "done", "inserted": 0, "updated": 0,
                           "price_changes": 0, "errors": [str(exc)]}),
                loop,
            )

    loop.run_in_executor(_executor, run_in_thread)

    async def generate():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "done":
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
