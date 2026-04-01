"""Search, compare, kit, and filter endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.schemas import (
    CompareRequest,
    CompareResponse,
    FilterRequest,
    FilterResponse,
    GearItemOut,
    KitRequest,
    KitResponse,
    SearchRequest,
    SearchResponse,
)
from db import operations as db

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    results = db.query_similar(
        req.query,
        top_k=req.top_k,
        category=req.category,
        max_weight_g=req.max_weight_g,
        max_price_usd=req.max_price_usd,
    )
    return SearchResponse(
        results=[GearItemOut(**r) for r in results],
        total=len(results),
    )


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest):
    items = db.get_by_ids(req.item_ids)
    if not items:
        raise HTTPException(status_code=404, detail="No items found for the provided IDs")

    weight_diff = None
    price_diff = None
    if len(items) == 2:
        w0 = items[0].get("weight_g") or 0
        w1 = items[1].get("weight_g") or 0
        weight_diff = round(abs(w0 - w1), 1)
        p0 = items[0].get("price_usd")
        p1 = items[1].get("price_usd")
        if p0 is not None and p1 is not None:
            price_diff = round(abs(p0 - p1), 2)

    return CompareResponse(
        items=[GearItemOut(**i) for i in items],
        weight_diff_g=weight_diff,
        price_diff_usd=price_diff,
    )


@router.post("/kit", response_model=KitResponse)
def build_kit(req: KitRequest):
    from agent.tools import run_build_kit
    raw = run_build_kit(
        target_base_weight_g=req.target_base_weight_g,
        budget_usd=req.budget_usd,
        style=req.style,
    )
    data = json.loads(raw)
    kit_items = {
        cat: GearItemOut(**item) for cat, item in data.get("kit", {}).items()
    }
    return KitResponse(
        kit=kit_items,
        total_weight_g=data.get("total_weight_g", 0),
        total_weight_lbs=data.get("total_weight_lbs", 0),
        total_cost_usd=data.get("total_cost_usd", 0),
        categories_missing=data.get("categories_missing", []),
    )


@router.post("/filter", response_model=FilterResponse)
def filter_gear(req: FilterRequest):
    results = db.filter_and_rank(
        category=req.category,
        max_weight_g=req.max_weight_g,
        max_price_usd=req.max_price_usd,
        rank_by=req.rank_by,
        limit=req.limit,
    )
    return FilterResponse(
        results=[GearItemOut(**r) for r in results],
        total=len(results),
    )
