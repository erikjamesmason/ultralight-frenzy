"""ChromaDB upsert, query, and retrieval operations."""

from __future__ import annotations

import json
from typing import Any

from db.client import get_collection


def _build_document(item: dict[str, Any]) -> str:
    """Create a rich text representation for embedding."""
    parts = [
        item.get("name", ""),
        item.get("brand", ""),
        item.get("category", ""),
        item.get("description", ""),
        item.get("reviews", ""),
        item.get("material", ""),
    ]
    specs = item.get("specs", {})
    if specs:
        parts.append(json.dumps(specs))
    return " ".join(p for p in parts if p)


def _build_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Extract scalar fields as ChromaDB metadata (no nested dicts/None)."""
    meta: dict[str, Any] = {}
    scalar_fields = [
        "name", "brand", "category", "weight_g", "packed_weight_g",
        "price_usd", "value_rating", "material", "source_url", "scraped_at",
    ]
    for field in scalar_fields:
        val = item.get(field)
        if val is not None:
            meta[field] = val
    # Flatten dimensions to strings
    dims = item.get("dimensions_cm")
    if dims:
        meta["dimensions_cm"] = json.dumps(dims)
    # Flatten specs
    specs = item.get("specs")
    if specs:
        meta["specs"] = json.dumps(specs)
    return meta


def upsert_item(item: dict[str, Any]) -> None:
    """Insert or update a gear item in ChromaDB."""
    collection = get_collection()
    doc = _build_document(item)
    meta = _build_metadata(item)
    collection.upsert(
        ids=[item["id"]],
        documents=[doc],
        metadatas=[meta],
    )


def upsert_items(items: list[dict[str, Any]]) -> int:
    """Batch upsert. Returns number of items upserted."""
    if not items:
        return 0
    collection = get_collection()
    ids = [item["id"] for item in items]
    documents = [_build_document(item) for item in items]
    metadatas = [_build_metadata(item) for item in items]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(items)


def query_similar(
    query_text: str,
    top_k: int = 5,
    category: str | None = None,
    max_weight_g: float | None = None,
    max_price_usd: float | None = None,
) -> list[dict[str, Any]]:
    """Semantic similarity search with optional metadata filters."""
    collection = get_collection()

    where: dict[str, Any] | None = None
    filters = []
    if category:
        filters.append({"category": {"$eq": category}})
    if max_weight_g is not None:
        filters.append({"weight_g": {"$lte": max_weight_g}})
    if max_price_usd is not None:
        filters.append({"price_usd": {"$lte": max_price_usd}})

    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    kwargs: dict[str, Any] = {
        "query_texts": [query_text],
        "n_results": min(top_k, max(1, collection.count())),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)
    return _format_results(results)


def get_by_id(item_id: str) -> dict[str, Any] | None:
    """Fetch a single item by ID."""
    collection = get_collection()
    result = collection.get(
        ids=[item_id],
        include=["documents", "metadatas"],
    )
    if not result["ids"] or not result["ids"][0]:
        return None
    meta = result["metadatas"][0] if result["metadatas"] else {}
    return {"id": item_id, **_decode_metadata(meta)}


def get_by_ids(item_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch multiple items by ID."""
    collection = get_collection()
    result = collection.get(
        ids=item_ids,
        include=["documents", "metadatas"],
    )
    items = []
    for i, item_id in enumerate(result["ids"]):
        meta = result["metadatas"][i] if result["metadatas"] else {}
        items.append({"id": item_id, **_decode_metadata(meta)})
    return items


def list_items(
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all gear items, optionally filtered by category."""
    collection = get_collection()
    where = {"category": {"$eq": category}} if category else None
    kwargs: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "include": ["metadatas"],
    }
    if where:
        kwargs["where"] = where
    result = collection.get(**kwargs)
    items = []
    for i, item_id in enumerate(result["ids"]):
        meta = result["metadatas"][i] if result["metadatas"] else {}
        items.append({"id": item_id, **_decode_metadata(meta)})
    return items


def delete_item(item_id: str) -> None:
    collection = get_collection()
    collection.delete(ids=[item_id])


def item_count() -> int:
    return get_collection().count()


def filter_and_rank(
    category: str | None = None,
    max_weight_g: float | None = None,
    max_price_usd: float | None = None,
    rank_by: str = "weight_g",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Filter by metadata fields and rank by a scalar attribute."""
    filters = []
    if category:
        filters.append({"category": {"$eq": category}})
    if max_weight_g is not None:
        filters.append({"weight_g": {"$lte": max_weight_g}})
    if max_price_usd is not None:
        filters.append({"price_usd": {"$lte": max_price_usd}})

    collection = get_collection()
    where: dict[str, Any] | None = None
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    kwargs: dict[str, Any] = {
        "limit": max(limit * 3, 30),  # over-fetch for sorting
        "include": ["metadatas"],
    }
    if where:
        kwargs["where"] = where

    result = collection.get(**kwargs)
    items = []
    for i, item_id in enumerate(result["ids"]):
        meta = result["metadatas"][i] if result["metadatas"] else {}
        items.append({"id": item_id, **_decode_metadata(meta)})

    # Sort by rank_by field (ascending — lower weight/price/value is better)
    items.sort(key=lambda x: x.get(rank_by) or float("inf"))
    return items[:limit]


def _format_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert raw ChromaDB query results to a list of dicts."""
    items = []
    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i, item_id in enumerate(ids):
        meta = metadatas[i] if metadatas else {}
        distance = distances[i] if distances else None
        similarity = round(1 - distance, 4) if distance is not None else None
        item = {"id": item_id, "similarity": similarity, **_decode_metadata(meta)}
        items.append(item)
    return items


def _decode_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Expand JSON-serialized fields back to dicts."""
    decoded = dict(meta)
    for field in ("dimensions_cm", "specs"):
        if field in decoded and isinstance(decoded[field], str):
            try:
                decoded[field] = json.loads(decoded[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return decoded
