import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB

from store.db import get_session
from store.models import SearchConfig, ScrapeRun
from scraper.engine import run_config
import log as applog

_log = logging.getLogger(__name__)

_VALID_SOURCES = {"cardekho", "cars24", "carwale", "olx", "spinny", "cartrade"}
_executor = ThreadPoolExecutor(max_workers=4)

# In-flight lock: config_id → threading.Event (set when the run finishes)
# Prevents duplicate concurrent runs for the same config.
_in_flight: dict[str, threading.Event] = {}
_in_flight_lock = threading.Lock()

router = APIRouter()


def _run_key(config_id: str, source: Optional[str]) -> str:
    return f"{config_id}:{source or '*'}"


def _start_run(config_id: str, source: Optional[str] = None) -> str:
    """Dispatch run_config in the background; return run_id immediately.

    Raises HTTPException 409 if a run for this config+source is already in flight.
    """
    key = _run_key(config_id, source)
    with _in_flight_lock:
        if key in _in_flight and not _in_flight[key].is_set():
            raise HTTPException(409, f"A scrape run for this config/source is already in progress")
        done_event = threading.Event()
        _in_flight[key] = done_event

    run_id = applog.new_run_id()

    # Persist initial ScrapeRun row
    with get_session() as session:
        session.add(ScrapeRun(
            run_id=run_id,
            config_id=config_id,
            source=source,
            status="running",
            started_at=datetime.utcnow(),
        ))
        session.commit()

    def _task():
        try:
            def _on_progress(event: dict) -> None:
                if event.get("type") == "done":
                    with get_session() as s:
                        run = s.query(ScrapeRun).filter_by(run_id=run_id).first()
                        if run:
                            run.status = "done"
                            run.inserted = event.get("inserted", 0)
                            run.updated = event.get("updated", 0)
                            run.price_changes = event.get("price_changes", 0)
                            run.errors = event.get("errors", [])
                            run.finished_at = datetime.utcnow()
                            s.commit()

            run_config(config_id, source=source, on_progress=_on_progress, run_id=run_id)
        except Exception as exc:
            _log.error("scrape task error — run_id=%s: %s", run_id, exc)
            with get_session() as s:
                run = s.query(ScrapeRun).filter_by(run_id=run_id).first()
                if run:
                    run.status = "error"
                    run.errors = [str(exc)]
                    run.finished_at = datetime.utcnow()
                    s.commit()
        finally:
            with _in_flight_lock:
                ev = _in_flight.pop(key, None)
            if ev:
                ev.set()

    _executor.submit(_task)
    return run_id


@router.post("/")
def scrape_all():
    """Trigger background scrapes for all active configs. Returns list of job IDs."""
    with get_session() as session:
        configs = session.query(SearchConfig).filter_by(is_active=True).all()
        config_ids = [c.id for c in configs]
    run_ids = []
    for cid in config_ids:
        try:
            run_ids.append(_start_run(cid))
        except HTTPException:
            _log.info("scrape all — skipping %s (already in flight)", cid)
    return {"ok": True, "run_ids": run_ids}


@router.post("/{config_id}")
def scrape_one(config_id: str):
    """Start a background scrape for a config. Returns job_id immediately (202)."""
    with get_session() as session:
        if not session.query(SearchConfig).filter_by(id=config_id).first():
            raise HTTPException(404, "config not found")
    run_id = _start_run(config_id)
    _log.info("scrape one — config=%s run_id=%s", config_id, run_id)
    return {"ok": True, "run_id": run_id, "status": "running"}


@router.post("/{config_id}/{source}")
def scrape_source(config_id: str, source: str):
    """Start a background single-source scrape. Returns job_id immediately (202)."""
    if source not in _VALID_SOURCES:
        raise HTTPException(400, f"unknown source '{source}', valid: {sorted(_VALID_SOURCES)}")
    with get_session() as session:
        if not session.query(SearchConfig).filter_by(id=config_id).first():
            raise HTTPException(404, "config not found")
    run_id = _start_run(config_id, source=source)
    _log.info("scrape source — config=%s source=%s run_id=%s", config_id, source, run_id)
    return {"ok": True, "run_id": run_id, "status": "running"}


@router.post("/state/{state_key}")
def scrape_by_state(state_key: str):
    """Start background scrapes for all active configs referencing the given state."""
    with get_session() as session:
        configs = session.query(SearchConfig).filter(
            SearchConfig.is_active.is_(True),
            SearchConfig.regions.contains(cast([state_key], JSONB)),
        ).all()
        config_ids = [c.id for c in configs]
    if not config_ids:
        raise HTTPException(404, f"no active configs reference state '{state_key}'")
    run_ids = []
    for cid in config_ids:
        try:
            run_ids.append(_start_run(cid))
        except HTTPException:
            _log.info("scrape by state — skipping %s (already in flight)", cid)
    _log.info("scrape by state — state=%s triggered=%d", state_key, len(run_ids))
    return {"ok": True, "triggered": len(run_ids), "run_ids": run_ids}


@router.get("/runs")
def list_runs(config_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    """List recent scrape runs."""
    with get_session() as session:
        q = session.query(ScrapeRun).order_by(ScrapeRun.started_at.desc())
        if config_id:
            q = q.filter(ScrapeRun.config_id == config_id)
        if status:
            q = q.filter(ScrapeRun.status == status)
        runs = q.limit(limit).all()
        return [
            {
                "run_id": r.run_id,
                "config_id": r.config_id,
                "source": r.source,
                "status": r.status,
                "inserted": r.inserted,
                "updated": r.updated,
                "price_changes": r.price_changes,
                "errors": r.errors,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in runs
        ]


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    """Get status of a specific scrape run."""
    with get_session() as session:
        run = session.query(ScrapeRun).filter_by(run_id=run_id).first()
        if not run:
            raise HTTPException(404, "run not found")
        return {
            "run_id": run.run_id,
            "config_id": run.config_id,
            "source": run.source,
            "status": run.status,
            "inserted": run.inserted,
            "updated": run.updated,
            "price_changes": run.price_changes,
            "errors": run.errors,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }


@router.get("/{config_id}/stream")
async def scrape_stream(config_id: str, source: Optional[str] = None):
    """
    SSE endpoint — streams scraping progress as newline-delimited JSON events.
    Starts a new scrape run and streams its events. If a run is already in flight
    for this config, returns 409 immediately.

    Event shapes:
      {"type": "run_start",    "run_id": "...", }
      {"type": "scraper_start","source": "cardekho", "regions": [...]}
      {"type": "scraper_done", "source": "cardekho", "inserted": N, "updated": N, "price_changes": N}
      {"type": "scraper_error","source": "cardekho", "message": "..."}
      {"type": "done",         "inserted": N, "updated": N, "price_changes": N, "errors": [...]}
    """
    if source and source not in _VALID_SOURCES:
        raise HTTPException(400, f"unknown source '{source}'")
    with get_session() as session:
        if not session.query(SearchConfig).filter_by(id=config_id).first():
            raise HTTPException(404, "config not found")

    key = _run_key(config_id, source)
    with _in_flight_lock:
        if key in _in_flight and not _in_flight[key].is_set():
            raise HTTPException(409, "A scrape run for this config/source is already in progress")
        done_event = threading.Event()
        _in_flight[key] = done_event

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    run_id = applog.new_run_id()

    # Persist initial ScrapeRun row
    with get_session() as session:
        session.add(ScrapeRun(
            run_id=run_id,
            config_id=config_id,
            source=source,
            status="running",
            started_at=datetime.utcnow(),
        ))
        session.commit()

    def on_progress(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    def run_in_thread() -> None:
        try:
            run_config(config_id, source=source, on_progress=on_progress, run_id=run_id)
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "done", "inserted": 0, "updated": 0,
                           "price_changes": 0, "errors": [str(exc)]}),
                loop,
            )
        finally:
            with _in_flight_lock:
                ev = _in_flight.pop(key, None)
            if ev:
                ev.set()

    loop.run_in_executor(_executor, run_in_thread)

    async def generate():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                # No event for 30s (a slow source is normal) — keep the connection
                # alive and keep listening. The engine's run deadline guarantees a
                # terminal 'done' event so this loop can't run forever.
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "done":
                with get_session() as s:
                    run = s.query(ScrapeRun).filter_by(run_id=run_id).first()
                    if run:
                        run.status = "done"
                        run.inserted = event.get("inserted", 0)
                        run.updated = event.get("updated", 0)
                        run.price_changes = event.get("price_changes", 0)
                        run.errors = event.get("errors", [])
                        run.finished_at = datetime.utcnow()
                        s.commit()
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
