from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from store.db import get_session
from store.models import Shortlist, Listing

router = APIRouter()


class ShortlistEntry(BaseModel):
    listing_id: str
    notes: str
    added_at: datetime

    model_config = {"from_attributes": True}


class NotesIn(BaseModel):
    notes: str = ""


@router.get("/", response_model=list[ShortlistEntry])
def get_shortlist():
    with get_session() as session:
        rows = session.query(Shortlist).order_by(Shortlist.added_at.desc()).all()
        return [ShortlistEntry.model_validate(r) for r in rows]


@router.post("/{listing_id}", response_model=ShortlistEntry, status_code=201)
def add_to_shortlist(listing_id: str, body: NotesIn = NotesIn()):
    with get_session() as session:
        if not session.query(Listing).filter_by(id=listing_id).first():
            raise HTTPException(404, "listing not found")
        existing = session.query(Shortlist).filter_by(listing_id=listing_id).first()
        if existing:
            return ShortlistEntry.model_validate(existing)
        entry = Shortlist(listing_id=listing_id, notes=body.notes, added_at=datetime.utcnow())
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return ShortlistEntry.model_validate(entry)


@router.patch("/{listing_id}", response_model=ShortlistEntry)
def update_notes(listing_id: str, body: NotesIn):
    with get_session() as session:
        entry = session.query(Shortlist).filter_by(listing_id=listing_id).first()
        if not entry:
            raise HTTPException(404, "not shortlisted")
        entry.notes = body.notes
        session.commit()
        session.refresh(entry)
        return ShortlistEntry.model_validate(entry)


@router.delete("/{listing_id}", status_code=204)
def remove_from_shortlist(listing_id: str):
    with get_session() as session:
        entry = session.query(Shortlist).filter_by(listing_id=listing_id).first()
        if not entry:
            raise HTTPException(404, "not shortlisted")
        session.delete(entry)
        session.commit()
