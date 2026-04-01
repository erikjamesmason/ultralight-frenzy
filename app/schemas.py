"""Pydantic request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Gear item
# ---------------------------------------------------------------------------

class GearItemOut(BaseModel):
    id: str
    name: str
    brand: str
    category: str
    weight_g: float
    packed_weight_g: float | None = None
    dimensions_cm: dict[str, float] | None = None
    price_usd: float | None = None
    value_rating: float | None = None
    material: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    reviews: str = ""
    source_url: str = ""
    scraped_at: str = ""
    similarity: float | None = None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    category: str | None = None
    max_weight_g: float | None = None
    max_price_usd: float | None = None


class SearchResponse(BaseModel):
    results: list[GearItemOut]
    total: int


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    item_ids: list[str] = Field(min_length=2, max_length=5)


class CompareResponse(BaseModel):
    items: list[GearItemOut]
    weight_diff_g: float | None = None
    price_diff_usd: float | None = None


# ---------------------------------------------------------------------------
# Kit builder
# ---------------------------------------------------------------------------

class KitRequest(BaseModel):
    target_base_weight_g: float | None = None
    budget_usd: float | None = None
    style: str | None = None


class KitResponse(BaseModel):
    kit: dict[str, GearItemOut]
    total_weight_g: float
    total_weight_lbs: float
    total_cost_usd: float
    categories_missing: list[str]


# ---------------------------------------------------------------------------
# Filter + rank
# ---------------------------------------------------------------------------

class FilterRequest(BaseModel):
    category: str | None = None
    max_weight_g: float | None = None
    max_price_usd: float | None = None
    rank_by: str = "weight_g"
    limit: int = Field(default=10, ge=1, le=50)


class FilterResponse(BaseModel):
    results: list[GearItemOut]
    total: int


# ---------------------------------------------------------------------------
# Agentic query
# ---------------------------------------------------------------------------

class AgentQueryRequest(BaseModel):
    message: str


class AgentQueryResponse(BaseModel):
    response: str


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    sources: list[str] = Field(
        default=["lighterpack", "rei", "outdoorgearlab"],
        description="Scraper sources to run.",
    )


class IngestResponse(BaseModel):
    items_upserted: int
    sources_run: list[str]
    errors: list[str]
