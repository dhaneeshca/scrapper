from datetime import datetime

from fastapi import APIRouter, HTTPException

from store.db import get_session
from store.models import NotInterested, Listing

router = APIRouter()


@router.post("/{listing_id}", status_code=201)
def mark_not_interested(listing_id: str):
    with get_session() as session:
        if not session.query(Listing).filter_by(id=listing_id).first():
            raise HTTPException(404, "listing not found")
        existing = session.query(NotInterested).filter_by(listing_id=listing_id).first()
        if existing:
            return {}
        session.add(NotInterested(listing_id=listing_id, added_at=datetime.utcnow()))
        session.commit()
        return {}


@router.delete("/{listing_id}", status_code=204)
def unmark_not_interested(listing_id: str):
    with get_session() as session:
        entry = session.query(NotInterested).filter_by(listing_id=listing_id).first()
        if not entry:
            raise HTTPException(404, "not marked")
        session.delete(entry)
        session.commit()
