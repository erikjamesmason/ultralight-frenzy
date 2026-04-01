"""Claude tool definitions and implementations for the gear agent."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from db import operations as db

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic SDK format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "semantic_search",
        "description": (
            "Search the gear database by natural language description. "
            "Returns the most semantically similar items. Use this to answer "
            "questions like 'lightest 3-season shelter' or 'waterproof jacket under 300g'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query describing the gear you want.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 20).",
                    "default": 5,
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional: filter to one category. "
                        "One of: shelter, sleep, pack, footwear, clothing, cooking, nav, other."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "compare_items",
        "description": (
            "Compare two or more gear items side-by-side on weight, price, value rating, "
            "and specs. Provide item IDs returned from semantic_search or filter_and_rank."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2–5 gear item IDs to compare.",
                    "minItems": 2,
                    "maxItems": 5,
                },
            },
            "required": ["item_ids"],
        },
    },
    {
        "name": "build_kit",
        "description": (
            "Build a complete ultralight kit optimised for a target base weight or budget. "
            "Selects the best item per category (shelter, sleep, pack, footwear, clothing, "
            "cooking, nav) within the given constraints."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_base_weight_g": {
                    "type": "number",
                    "description": "Target total base weight in grams (e.g. 4500 for 10 lbs).",
                },
                "budget_usd": {
                    "type": "number",
                    "description": "Maximum total budget in USD.",
                },
                "style": {
                    "type": "string",
                    "description": (
                        "Optional style hint: 'ultralight', 'budget', 'comfort', 'bikepacking'."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "filter_and_rank",
        "description": (
            "Filter gear items by category, weight, and/or price, then rank by a chosen metric. "
            "Good for browsing the database or narrowing down options before comparing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter to one category (shelter, sleep, pack, etc.).",
                },
                "max_weight_g": {
                    "type": "number",
                    "description": "Maximum weight in grams.",
                },
                "max_price_usd": {
                    "type": "number",
                    "description": "Maximum price in USD.",
                },
                "rank_by": {
                    "type": "string",
                    "enum": ["weight_g", "price_usd", "value_rating"],
                    "description": "Attribute to sort by (ascending). Default: weight_g.",
                    "default": "weight_g",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results to return (default 10).",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

CATEGORIES = ["shelter", "sleep", "pack", "footwear", "clothing", "cooking", "nav", "other"]


def _summarise_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return a concise summary dict for LLM consumption."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "brand": item.get("brand"),
        "category": item.get("category"),
        "weight_g": item.get("weight_g"),
        "price_usd": item.get("price_usd"),
        "value_rating": item.get("value_rating"),
        "similarity": item.get("similarity"),
        "material": item.get("material"),
        "source_url": item.get("source_url"),
    }


def run_semantic_search(
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> str:
    top_k = min(max(1, top_k), 20)
    results = db.query_similar(query, top_k=top_k, category=category or None)
    if not results:
        return json.dumps({"results": [], "message": "No matching items found."})
    return json.dumps({"results": [_summarise_item(r) for r in results]})


def run_compare_items(item_ids: list[str]) -> str:
    items = db.get_by_ids(item_ids)
    if not items:
        return json.dumps({"error": "No items found for the provided IDs."})

    rows = []
    for item in items:
        rows.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "brand": item.get("brand"),
            "category": item.get("category"),
            "weight_g": item.get("weight_g"),
            "packed_weight_g": item.get("packed_weight_g"),
            "price_usd": item.get("price_usd"),
            "value_rating": item.get("value_rating"),
            "material": item.get("material"),
            "specs": item.get("specs"),
            "reviews": (item.get("reviews") or "")[:300],
            "source_url": item.get("source_url"),
        })

    # Compute weight diff if 2 items
    comparison: dict[str, Any] = {"items": rows}
    if len(rows) == 2:
        w0 = rows[0].get("weight_g") or 0
        w1 = rows[1].get("weight_g") or 0
        comparison["weight_diff_g"] = round(abs(w0 - w1), 1)
        p0 = rows[0].get("price_usd")
        p1 = rows[1].get("price_usd")
        if p0 is not None and p1 is not None:
            comparison["price_diff_usd"] = round(abs(p0 - p1), 2)

    return json.dumps(comparison)


def run_build_kit(
    target_base_weight_g: float | None = None,
    budget_usd: float | None = None,
    style: str | None = None,
) -> str:
    kit: dict[str, Any] = {}
    total_weight = 0.0
    total_cost = 0.0

    # Per-category weight budget allocation (rough percentages)
    weight_alloc = {
        "shelter": 0.28,
        "sleep": 0.22,
        "pack": 0.18,
        "footwear": 0.12,
        "clothing": 0.10,
        "cooking": 0.06,
        "nav": 0.04,
    }

    for category in ["shelter", "sleep", "pack", "footwear", "clothing", "cooking", "nav"]:
        max_w: float | None = None
        if target_base_weight_g:
            max_w = target_base_weight_g * weight_alloc.get(category, 0.1)

        max_p: float | None = None
        if budget_usd:
            # rough budget allocation similar to weight
            max_p = budget_usd * weight_alloc.get(category, 0.1)

        candidates = db.filter_and_rank(
            category=category,
            max_weight_g=max_w,
            max_price_usd=max_p,
            rank_by="value_rating" if style == "budget" else "weight_g",
            limit=1,
        )
        if candidates:
            item = candidates[0]
            kit[category] = _summarise_item(item)
            total_weight += item.get("weight_g") or 0
            total_cost += item.get("price_usd") or 0

    return json.dumps({
        "kit": kit,
        "total_weight_g": round(total_weight, 1),
        "total_weight_lbs": round(total_weight / 453.592, 2),
        "total_cost_usd": round(total_cost, 2),
        "categories_missing": [c for c in weight_alloc if c not in kit],
    })


def run_filter_and_rank(
    category: str | None = None,
    max_weight_g: float | None = None,
    max_price_usd: float | None = None,
    rank_by: str = "weight_g",
    limit: int = 10,
) -> str:
    limit = min(max(1, limit), 50)
    results = db.filter_and_rank(
        category=category or None,
        max_weight_g=max_weight_g,
        max_price_usd=max_price_usd,
        rank_by=rank_by,
        limit=limit,
    )
    if not results:
        return json.dumps({"results": [], "message": "No items match the filters."})
    return json.dumps({"results": [_summarise_item(r) for r in results]})


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Route a Claude tool_use call to the correct implementation."""
    if name == "semantic_search":
        return run_semantic_search(
            query=tool_input["query"],
            top_k=tool_input.get("top_k", 5),
            category=tool_input.get("category"),
        )
    elif name == "compare_items":
        return run_compare_items(item_ids=tool_input["item_ids"])
    elif name == "build_kit":
        return run_build_kit(
            target_base_weight_g=tool_input.get("target_base_weight_g"),
            budget_usd=tool_input.get("budget_usd"),
            style=tool_input.get("style"),
        )
    elif name == "filter_and_rank":
        return run_filter_and_rank(
            category=tool_input.get("category"),
            max_weight_g=tool_input.get("max_weight_g"),
            max_price_usd=tool_input.get("max_price_usd"),
            rank_by=tool_input.get("rank_by", "weight_g"),
            limit=tool_input.get("limit", 10),
        )
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})
