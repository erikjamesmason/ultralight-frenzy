"""Unit tests for db/operations.py preprocessing logic."""

from unittest.mock import MagicMock, patch
import pytest
from db.operations import upsert_items


def _make_item(item_id: str, name: str = "Test Item") -> dict:
    return {
        "id": item_id,
        "name": name,
        "brand": "TestBrand",
        "category": "shelter",
        "weight_g": 500.0,
        "price_usd": 200.0,
        "value_rating": 0.4,
        "description": "",
        "reviews": "",
        "material": None,
        "source_url": "",
        "scraped_at": "2024-01-01T00:00:00+00:00",
        "packed_weight_g": None,
        "dimensions_cm": None,
        "specs": {},
    }


@patch("db.operations.get_collection")
class TestUpsertItems:
    def test_empty_list_returns_zero(self, mock_get_collection):
        assert upsert_items([]) == 0
        mock_get_collection.assert_not_called()

    def test_filters_empty_id(self, mock_get_collection):
        mock_col = MagicMock()
        mock_get_collection.return_value = mock_col

        items = [_make_item(""), _make_item("valid-id")]
        count = upsert_items(items)

        assert count == 1
        call_ids = mock_col.upsert.call_args.kwargs["ids"]
        assert "" not in call_ids
        assert "valid-id" in call_ids

    def test_filters_none_id(self, mock_get_collection):
        mock_col = MagicMock()
        mock_get_collection.return_value = mock_col

        item = _make_item("good-id")
        bad_item = dict(item, id=None)
        count = upsert_items([bad_item, item])

        assert count == 1
        call_ids = mock_col.upsert.call_args.kwargs["ids"]
        assert None not in call_ids

    def test_deduplicates_by_id(self, mock_get_collection):
        mock_col = MagicMock()
        mock_get_collection.return_value = mock_col

        # Same ID appearing three times (e.g. from multiple LighterPack lists)
        items = [_make_item("shared-tent")] * 3
        count = upsert_items(items)

        assert count == 1
        call_ids = mock_col.upsert.call_args.kwargs["ids"]
        assert call_ids == ["shared-tent"]

    def test_all_empty_ids_returns_zero(self, mock_get_collection):
        mock_col = MagicMock()
        mock_get_collection.return_value = mock_col

        items = [_make_item(""), _make_item("")]
        count = upsert_items(items)

        assert count == 0
        mock_col.upsert.assert_not_called()

    def test_normal_batch_upserted(self, mock_get_collection):
        mock_col = MagicMock()
        mock_get_collection.return_value = mock_col

        items = [_make_item("item-a"), _make_item("item-b"), _make_item("item-c")]
        count = upsert_items(items)

        assert count == 3
        mock_col.upsert.assert_called_once()
        call_ids = mock_col.upsert.call_args.kwargs["ids"]
        assert set(call_ids) == {"item-a", "item-b", "item-c"}
