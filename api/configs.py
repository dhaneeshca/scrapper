import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from store.db import get_session
from store.models import SearchConfig

router = APIRouter()


class ConfigIn(BaseModel):
    name: str
    make: str
    model: str
    variants: list[str] = []
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    fuel_types: list[str] = []
    transmissions: list[str] = []
    budget_max: Optional[int] = None
    regions: list[str] = []


class ConfigOut(ConfigIn):
    id: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[ConfigOut])
def list_configs():
    with get_session() as session:
        rows = session.query(SearchConfig).order_by(SearchConfig.created_at.desc()).all()
        return [ConfigOut.model_validate(r) for r in rows]


@router.post("/", response_model=ConfigOut, status_code=201)
def create_config(body: ConfigIn):
    with get_session() as session:
        config = SearchConfig(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            **body.model_dump(),
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return ConfigOut.model_validate(config)


@router.put("/{config_id}", response_model=ConfigOut)
def update_config(config_id: str, body: ConfigIn):
    with get_session() as session:
        config = session.query(SearchConfig).filter_by(id=config_id).first()
        if not config:
            raise HTTPException(404, "not found")
        for k, v in body.model_dump().items():
            setattr(config, k, v)
        session.commit()
        session.refresh(config)
        return ConfigOut.model_validate(config)


@router.delete("/{config_id}", status_code=204)
def delete_config(config_id: str):
    with get_session() as session:
        config = session.query(SearchConfig).filter_by(id=config_id).first()
        if not config:
            raise HTTPException(404, "not found")
        session.delete(config)
        session.commit()


@router.post("/{config_id}/toggle", response_model=ConfigOut)
def toggle_config(config_id: str):
    with get_session() as session:
        config = session.query(SearchConfig).filter_by(id=config_id).first()
        if not config:
            raise HTTPException(404, "not found")
        config.is_active = not config.is_active
        session.commit()
        session.refresh(config)
        return ConfigOut.model_validate(config)
