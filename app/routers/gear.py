"""CRUD endpoints for individual gear items."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import GearItemOut
from db import operations as db

router = APIRouter(prefix="/gear", tags=["gear"])


@router.get("", response_model=list[GearItemOut])
def list_gear(
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items = db.list_items(category=category, limit=limit, offset=offset)
    return [GearItemOut(**item) for item in items]


@router.get("/count")
def count_gear():
    return {"count": db.item_count()}


@router.get("/{item_id}", response_model=GearItemOut)
def get_gear(item_id: str):
    item = db.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return GearItemOut(**item)


@router.delete("/{item_id}", status_code=204)
def delete_gear(item_id: str):
    item = db.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    db.delete_item(item_id)
