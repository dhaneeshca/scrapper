"""Engine insert/upsert path test — exercises run_config end-to-end with a stub
scraper so the ON CONFLICT insert path is actually covered (the bug where the
upsert referenced a non-existent constraint would have been caught here).

Runs against Postgres; skips if unreachable.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scraper.base import Scraper, RawListing


def _db_available() -> bool:
    try:
        from store.db import engine
        with engine.connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


class StubScraper(Scraper):
    name = "spinny"  # a real source name so deactivation scoping behaves normally

    def __init__(self, listings):
        self._listings = listings

    def search(self, **kwargs):
        return self._listings


def _raw(price):
    return RawListing(
        source="spinny", source_id="engine-test-1", url="http://x/engine-test-1",
        make="Skoda", model="Slavia", variant="Style", year=2023, km_driven=15000,
        fuel_type="Petrol", transmission="Manual", price=price, location_city="Chennai",
    )


class TestRunConfigUpsert:
    CFG = "engine-upsert-cfg"

    @pytest.fixture(autouse=True)
    def setup(self):
        import scraper.engine as engine
        from store.db import init_db, get_session
        from store.models import SearchConfig, Listing, PriceHistory

        def cleanup():
            with get_session() as s:
                lids = [r.id for r in s.query(Listing).filter_by(source="spinny", source_id="engine-test-1")]
                if lids:
                    s.query(PriceHistory).filter(PriceHistory.listing_id.in_(lids)).delete(synchronize_session=False)
                s.query(Listing).filter_by(source="spinny", source_id="engine-test-1").delete(synchronize_session=False)
                s.query(SearchConfig).filter_by(id=self.CFG).delete(synchronize_session=False)
                s.commit()

        init_db()
        cleanup()
        with get_session() as s:
            s.add(SearchConfig(id=self.CFG, name="eng", make="Skoda", model="Slavia", regions=[]))
            s.commit()

        self._orig_scrapers = engine._SCRAPERS
        yield engine
        engine._SCRAPERS = self._orig_scrapers
        cleanup()

    def test_insert_then_update(self, setup):
        engine = setup
        from store.db import get_session
        from store.models import Listing, PriceHistory

        # First run: INSERT (this is the ON CONFLICT path that previously crashed)
        engine._SCRAPERS = [StubScraper([_raw(1_000_000)])]
        summary = engine.run_config(self.CFG, source="spinny")
        assert summary["inserted"] == 1, summary
        assert not summary["errors"], summary["errors"]

        with get_session() as s:
            row = s.query(Listing).filter_by(source="spinny", source_id="engine-test-1").one()
            assert row.price == 1_000_000
            assert s.query(PriceHistory).filter_by(listing_id=row.id).count() == 1

        # Second run: price drop → UPDATE + price_history row + price_change
        engine._SCRAPERS = [StubScraper([_raw(900_000)])]
        summary2 = engine.run_config(self.CFG, source="spinny")
        assert summary2["updated"] == 1, summary2
        assert summary2["price_changes"] == 1, summary2
        assert not summary2["errors"], summary2["errors"]

        with get_session() as s:
            row = s.query(Listing).filter_by(source="spinny", source_id="engine-test-1").one()
            assert row.price == 900_000
            assert s.query(PriceHistory).filter_by(listing_id=row.id).count() == 2
