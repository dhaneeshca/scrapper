import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from store.db import get_session
from store.models import SourceCityConfig

router = APIRouter()

ALL_SOURCES = ["olx", "cartrade", "cars24", "spinny", "carwale", "cardekho"]


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SourceEntryOut(BaseModel):
    is_supported: bool
    source_config: dict


class CityOut(BaseModel):
    city_name: str
    city_key: str
    sources: dict[str, SourceEntryOut]


class StateGroupOut(BaseModel):
    state_name: str
    state_key: str
    cities: list[CityOut]


class SourceCityUpsert(BaseModel):
    is_supported: bool
    source_config: dict = {}


class NewCityIn(BaseModel):
    state_name: str
    state_key: str
    city_name: str
    city_key: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_rows(rows: list[SourceCityConfig]) -> list[StateGroupOut]:
    states: dict[str, dict] = {}
    state_meta: dict[str, tuple[str, str]] = {}
    city_meta: dict[str, tuple[str, str]] = {}

    for row in rows:
        if row.state_key not in states:
            states[row.state_key] = {}
            state_meta[row.state_key] = (row.state_name, row.state_key)
        if row.city_key not in states[row.state_key]:
            states[row.state_key][row.city_key] = {}
            city_meta[row.city_key] = (row.city_name, row.state_key)
        states[row.state_key][row.city_key][row.source] = row

    result = []
    for state_key in sorted(state_meta):
        state_name, _ = state_meta[state_key]
        cities = []
        for city_key in sorted(states[state_key]):
            city_name, _ = city_meta[city_key]
            source_map = states[state_key][city_key]
            sources = {}
            for src in ALL_SOURCES:
                if src in source_map:
                    r = source_map[src]
                    sources[src] = SourceEntryOut(
                        is_supported=r.is_supported,
                        source_config=r.source_config or {},
                    )
                else:
                    sources[src] = SourceEntryOut(is_supported=False, source_config={})
            cities.append(CityOut(city_name=city_name, city_key=city_key, sources=sources))
        result.append(StateGroupOut(state_name=state_name, state_key=state_key, cities=cities))
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

class StateOut(BaseModel):
    state_name: str
    state_key: str
    city_count: int


@router.get("/states", response_model=list[StateOut])
def list_states():
    with get_session() as session:
        rows = (
            session.query(
                SourceCityConfig.state_name,
                SourceCityConfig.state_key,
                func.count(func.distinct(SourceCityConfig.city_key)).label("city_count"),
            )
            .group_by(SourceCityConfig.state_name, SourceCityConfig.state_key)
            .order_by(SourceCityConfig.state_name)
            .all()
        )
    return [StateOut(state_name=r.state_name, state_key=r.state_key, city_count=r.city_count) for r in rows]


@router.get("/", response_model=list[StateGroupOut])
def list_city_configs():
    with get_session() as session:
        rows = session.query(SourceCityConfig).order_by(
            SourceCityConfig.state_key, SourceCityConfig.city_key, SourceCityConfig.source
        ).all()
        return _group_rows(rows)


@router.put("/{city_key}/{source}", response_model=SourceEntryOut)
def upsert_city_source(city_key: str, source: str, body: SourceCityUpsert):
    if source not in ALL_SOURCES:
        raise HTTPException(400, f"unknown source '{source}'")
    with get_session() as session:
        row = session.query(SourceCityConfig).filter_by(city_key=city_key, source=source).first()
        if not row:
            raise HTTPException(404, f"city '{city_key}' not found — add it first via POST /cities")
        row.is_supported = body.is_supported
        row.source_config = body.source_config
        session.commit()
        return SourceEntryOut(is_supported=row.is_supported, source_config=row.source_config)


@router.post("/cities", response_model=CityOut, status_code=201)
def add_city(body: NewCityIn):
    with get_session() as session:
        existing = session.query(SourceCityConfig).filter_by(city_key=body.city_key).first()
        if existing:
            raise HTTPException(409, f"city '{body.city_key}' already exists")
        for source in ALL_SOURCES:
            session.add(SourceCityConfig(
                id=str(uuid.uuid4()),
                state_name=body.state_name,
                state_key=body.state_key,
                city_name=body.city_name,
                city_key=body.city_key,
                source=source,
                is_supported=False,
                source_config={},
            ))
        session.commit()
    sources = {src: SourceEntryOut(is_supported=False, source_config={}) for src in ALL_SOURCES}
    return CityOut(city_name=body.city_name, city_key=body.city_key, sources=sources)


@router.delete("/cities/{city_key}", status_code=204)
def delete_city(city_key: str):
    with get_session() as session:
        deleted = session.query(SourceCityConfig).filter_by(city_key=city_key).delete()
        if not deleted:
            raise HTTPException(404, f"city '{city_key}' not found")
        session.commit()
