"""Tests for price-movement summary + server-side drop filter/sort.

The _summarize_points tests are pure (no DB). The query tests run against the
configured Postgres DB and skip automatically if it is unreachable.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.listings import _summarize_points


# ── Pure unit tests: price summary math ─────────────────────────────────────────

NOW = datetime(2026, 5, 31, tzinfo=timezone.utc)


def _pt(price, days_ago):
    return (price, NOW - timedelta(days=days_ago))


class TestSummarizePoints:
    def test_drop(self):
        s = _summarize_points([_pt(900_000, 20), _pt(800_000, 2)], NOW)
        assert s["price_first"] == 900_000
        assert s["price_total_delta"] == -100_000
        assert s["price_total_pct"] == pytest.approx(-11.1, abs=0.1)
        assert s["num_price_points"] == 2
        assert s["days_on_market"] == 20

    def test_rise(self):
        s = _summarize_points([_pt(700_000, 15), _pt(760_000, 1)], NOW)
        assert s["price_total_delta"] == 60_000
        assert s["price_total_pct"] == pytest.approx(8.6, abs=0.1)

    def test_single_point_no_change(self):
        s = _summarize_points([_pt(500_000, 5)], NOW)
        assert s["price_total_delta"] == 0
        assert s["num_price_points"] == 1
        assert s["days_on_market"] == 5

    def test_last_change_at_tracks_real_change_not_repeat(self):
        # price stays flat after the drop — last_change_at is the drop, not the latest repeat
        pts = [_pt(900_000, 30), _pt(800_000, 20), _pt(800_000, 5)]
        s = _summarize_points(pts, NOW)
        assert s["last_change_at"] == pts[1][1]

    def test_points_serialized(self):
        s = _summarize_points([_pt(900_000, 20), _pt(800_000, 2)], NOW)
        assert len(s["price_points"]) == 2
        assert s["price_points"][0]["price"] == 900_000
        assert isinstance(s["price_points"][0]["observed_at"], str)


# ── Integration tests: server-side drop filter/sort + deduped scoping ────────────

def _db_available() -> bool:
    try:
        from store.db import engine
        with engine.connect():
            return True
    except Exception:
        return False


pytestmark_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@pytestmark_db
class TestDropQueries:
    CFG = "test-pricedrop-cfg"
    IDS = ["t-drop", "t-rise", "t-flat"]

    @pytest.fixture(autouse=True)
    def seed(self):
        from store.db import init_db, get_session
        from store.models import SearchConfig, Listing, PriceHistory

        def cleanup():
            with get_session() as s:
                s.query(PriceHistory).filter(PriceHistory.listing_id.in_(self.IDS)).delete(synchronize_session=False)
                s.query(Listing).filter(Listing.id.in_(self.IDS)).delete(synchronize_session=False)
                s.query(SearchConfig).filter_by(id=self.CFG).delete(synchronize_session=False)
                s.commit()

        init_db()
        cleanup()
        now = datetime.utcnow()
        with get_session() as s:
            s.add(SearchConfig(id=self.CFG, name="t", make="Skoda", model="Slavia", regions=[]))
            s.commit()
        with get_session() as s:
            specs = [
                ("t-drop", 800_000, [(900_000, now - timedelta(days=20)), (800_000, now - timedelta(days=2))]),
                ("t-rise", 760_000, [(700_000, now - timedelta(days=15)), (760_000, now - timedelta(days=1))]),
                ("t-flat", 500_000, [(500_000, now - timedelta(days=5))]),
            ]
            for lid, price, hist in specs:
                s.add(Listing(id=lid, source="test", source_id=lid, url=f"http://x/{lid}",
                              make="Skoda", model="Slavia", year=2023, km_driven=20000, price=price,
                              location_city="Chennai", is_active=True,
                              dedup_key=f"sk_sl_2023_20000_chennai_{lid}", config_id=self.CFG))
                for p, o in hist:
                    s.add(PriceHistory(listing_id=lid, price=p, observed_at=o))
            s.commit()
        yield
        cleanup()

    def _LL(self, **kw):
        from api.listings import list_listings
        base = dict(price_change=None, sort_by="scraped_at", sort_dir="desc",
                    active_only=True, limit=100, offset=0)
        base.update(kw)
        return list_listings(config_id=self.CFG, **base)

    def test_drop_filter(self):
        rows = self._LL(price_change="drop")
        assert [r.id for r in rows] == ["t-drop"]
        assert rows[0].price_total_delta == -100_000

    def test_rise_filter(self):
        rows = self._LL(price_change="rise")
        assert [r.id for r in rows] == ["t-rise"]

    def test_biggest_drop_sort(self):
        rows = self._LL(sort_by="price_drop", sort_dir="asc")
        assert rows[0].id == "t-drop"      # most negative first
        assert rows[-1].id == "t-rise"     # most positive last

    def test_deduped_respects_config(self):
        from api.listings import deduped_listings
        groups = deduped_listings(config_id=self.CFG, limit=100)
        member_ids = {mid for g in groups for mid in g.listing_ids}
        assert member_ids == set(self.IDS)
