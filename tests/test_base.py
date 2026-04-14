"""Unit tests for scrapers/base.py pure functions."""

import pytest
from scrapers.base import GearItem, parse_price_usd, parse_weight_g


class TestParseWeightG:
    def test_grams(self):
        assert parse_weight_g("540g") == 540.0

    def test_grams_with_space(self):
        assert parse_weight_g("540 g") == 540.0

    def test_ounces(self):
        assert parse_weight_g("19.0 oz") == pytest.approx(538.6, abs=0.1)

    def test_pounds_only(self):
        assert parse_weight_g("2 lb") == pytest.approx(907.2, abs=0.1)

    def test_pounds_and_ounces(self):
        assert parse_weight_g("1 lb 3 oz") == pytest.approx(538.0, abs=1.0)

    def test_no_weight(self):
        assert parse_weight_g("no weight here") is None

    def test_empty_string(self):
        assert parse_weight_g("") is None


class TestParsePriceUsd:
    def test_with_dollar_sign(self):
        assert parse_price_usd("$249.99") == 249.99

    def test_without_dollar_sign(self):
        assert parse_price_usd("149.00") == 149.0

    def test_with_commas(self):
        assert parse_price_usd("1,299.00") == 1299.0

    def test_empty_string(self):
        assert parse_price_usd("") is None

    def test_no_price(self):
        assert parse_price_usd("free") is None


class TestMakeId:
    def test_normal(self):
        assert GearItem.make_id("Zpacks", "Arc Blast 55L") == "zpacks-arc-blast-55l"

    def test_special_characters_collapsed(self):
        assert GearItem.make_id("Big Agnes", "Fly Creek HV UL2") == "big-agnes-fly-creek-hv-ul2"

    def test_empty_brand(self):
        result = GearItem.make_id("", "Tent Peg")
        assert result == "tent-peg"

    def test_empty_name(self):
        result = GearItem.make_id("Zpacks", "")
        assert result == "zpacks"

    def test_both_empty_returns_unknown(self):
        # Critical: empty ID causes ChromaDB InvalidArgumentError
        result = GearItem.make_id("", "")
        assert result == "unknown"
        assert len(result) > 0

    def test_only_special_chars_returns_unknown(self):
        result = GearItem.make_id("---", "!!!   ???")
        assert result == "unknown"
        assert len(result) > 0

    def test_unicode_stripped(self):
        result = GearItem.make_id("Kühl", "Shirt")
        assert len(result) > 0  # should not be empty even with non-ascii
