"""Unit tests for scraper parser functions.

These lock the regex/parsing logic so layout drift or refactors
cause an immediate test failure rather than a silent 0-yield run.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scraper.base import _parse_owner_count, RawListing
from scraper.engine import _dedup_key
from scraper.cardekho import _parse_price_lakh, _parse_km, _parse_year, _variant_from_url
from scraper.cars24 import _parse_price as cars24_parse_price, _parse_km as cars24_parse_km, _parse_year as cars24_parse_year
from scraper.carwale import _parse_price as carwale_parse_price
from scraper.spinny import _to_raw


# ── cardekho ──────────────────────────────────────────────────────────────────

class TestCardekhoParsePrice:
    def test_simple_lakh(self):
        assert _parse_price_lakh("₹4.40L") == 440_000

    def test_discount_takes_last(self):
        # "₹5.09 L  ₹4.49L  (Save ₹60K)" → discounted price
        assert _parse_price_lakh("₹5.09 L  ₹4.49L  (Save ₹60K)") == 449_000

    def test_crore(self):
        assert _parse_price_lakh("₹1.25CR") == 12_500_000

    def test_empty(self):
        assert _parse_price_lakh("") == 0

    def test_no_unit_defaults_lakh(self):
        # price with no unit label should default to lakh
        assert _parse_price_lakh("₹8.50") == 850_000

    def test_mixed_lakh_and_crore_takes_last_with_correct_unit(self):
        # Should NOT apply CR to the lakh amount
        result = _parse_price_lakh("₹15.00L  ₹1.20CR")
        assert result == 12_000_000  # last match is CR


class TestCardekhoParseKm:
    def test_with_commas(self):
        assert _parse_km("1,38,210") == 138_210

    def test_plain(self):
        assert _parse_km("72000") == 72_000

    def test_empty(self):
        assert _parse_km("") == 0


class TestCardekhoParseYear:
    def test_year(self):
        assert _parse_year("Volkswagen Vento 2016") == 2016

    def test_no_year(self):
        assert _parse_year("no year here") == 0


class TestCardekhoVariantFromUrl:
    def test_extracts_variant(self):
        url = "https://www.cardekho.com/used-car-details/used-Volkswagen-vento-16-highline-plus-cars-Chennai_abc123.htm"
        assert _variant_from_url(url, "vento") == "1.6 Highline Plus"

    def test_no_match(self):
        assert _variant_from_url("https://example.com/no-variant", "vento") == ""


# ── cars24 ────────────────────────────────────────────────────────────────────

class TestCars24ParsePrice:
    def test_lakh_price(self):
        text = "2016 Volkswagen Vento HIGHLINE 1.6 MPI\n72,889 km\nPetrol\nManual\nEMI ₹11,167/m*\n₹5.22L\n₹5.02 lakh\nVadapalani"
        price = cars24_parse_price(text)
        # float precision: 5.02 * 100_000 = 501999.99...; accept ±1
        assert abs(price - 502_000) <= 1

    def test_skips_emi(self):
        text = "EMI ₹11,167/m*\n₹5.22L"
        price = cars24_parse_price(text)
        assert price == 522_000  # EMI skipped, takes the ₹5.22L

    def test_no_price(self):
        assert cars24_parse_price("no price here") == 0


class TestCars24ParseKm:
    def test_with_comma(self):
        assert cars24_parse_km("72,889 km") == 72_889


class TestCars24ParseYear:
    def test_year(self):
        assert cars24_parse_year("2021 Hyundai Verna") == 2021


# ── carwale ───────────────────────────────────────────────────────────────────

class TestCarwaleParsePrice:
    def test_lakh(self):
        assert carwale_parse_price("Rs. 7.54 Lakh") == 754_000

    def test_no_price(self):
        assert carwale_parse_price("no price") == 0


# ── owner count ───────────────────────────────────────────────────────────────

class TestParseOwnerCount:
    def test_ordinal(self):
        assert _parse_owner_count("1st Owner") == 1
        assert _parse_owner_count("2nd Owner") == 2
        assert _parse_owner_count("3rd Owner") == 3

    def test_word(self):
        assert _parse_owner_count("First Owner") == 1
        assert _parse_owner_count("second owner") == 2

    def test_numeric(self):
        assert _parse_owner_count("2 owner") == 2

    def test_no_match(self):
        assert _parse_owner_count("no info") is None


# ── dedup key ─────────────────────────────────────────────────────────────────

def _raw(**kwargs):
    defaults = dict(
        source="test", source_id="x", url="", make="Skoda", model="Rapid",
        variant="", year=2020, km_driven=50_000, fuel_type="Petrol",
        transmission="Manual", price=500_000, location_city="Chennai",
    )
    return RawListing(**{**defaults, **kwargs})


class TestDedupKey:
    def test_basic(self):
        assert _dedup_key(_raw()) == "skoda_rapid_2020_50000_chennai"

    def test_km_bucket(self):
        assert _dedup_key(_raw(km_driven=9999)) == "skoda_rapid_2020_5000_chennai"
        assert _dedup_key(_raw(km_driven=10001)) == "skoda_rapid_2020_10000_chennai"

    def test_km_bucket_boundary_creates_different_keys(self):
        # Known limitation: 9999 and 10001 produce different keys
        k1 = _dedup_key(_raw(km_driven=9999))
        k2 = _dedup_key(_raw(km_driven=10001))
        assert k1 != k2

    def test_city_normalised(self):
        assert _dedup_key(_raw(location_city="New Delhi")) == "skoda_rapid_2020_50000_new_delhi"

    def test_case_insensitive(self):
        k1 = _dedup_key(_raw(make="SKODA", model="RAPID"))
        k2 = _dedup_key(_raw(make="skoda", model="rapid"))
        assert k1 == k2


# ── spinny model fallback ─────────────────────────────────────────────────────

class TestSpinnyModelFallback:
    def _item(self, model_val):
        return {
            "id": "123",
            "make_year": 2020,
            "price": 500000,
            "make": "Skoda",
            "model": model_val,
            "variant": "Style",
            "mileage": 50000,
            "fuel_type": "Petrol",
            "transmission": "Manual",
            "city": "Chennai",
            "permanent_url": "/cars/skoda/rapid/123",
        }

    def test_model_present(self):
        raw = _to_raw(self._item("Rapid"), "Skoda", "Rapid", 0, 9999, 9_999_999)
        assert raw.model == "Rapid"

    def test_model_empty_falls_back_to_config(self):
        raw = _to_raw(self._item(""), "Skoda", "Rapid", 0, 9999, 9_999_999)
        assert raw.model == "Rapid"

    def test_model_none_falls_back_to_config(self):
        item = self._item(None)
        raw = _to_raw(item, "Skoda", "Rapid", 0, 9999, 9_999_999)
        assert raw.model == "Rapid"
