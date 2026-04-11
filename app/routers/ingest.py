"""Ingest endpoints — trigger scrape jobs."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from app.dependencies import verify_api_key
from app.schemas import AgentQueryRequest, AgentQueryResponse, IngestRequest, IngestResponse
from db import operations as db

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

# Simple in-memory status tracker
_ingest_status: dict[str, str] = {"status": "idle", "last_count": "0"}


@router.post("/ingest/scrape", response_model=IngestResponse, dependencies=[Depends(verify_api_key)])
async def trigger_scrape(req: IngestRequest, background_tasks: BackgroundTasks):
    items_upserted = 0
    errors: list[str] = []
    sources_run: list[str] = []

    for source in req.sources:
        try:
            count = await _run_scraper(source)
            items_upserted += count
            sources_run.append(source)
        except Exception as exc:
            logger.error("Scraper %s failed: %s", source, exc)
            errors.append(f"{source}: {exc}")

    return IngestResponse(
        items_upserted=items_upserted,
        sources_run=sources_run,
        errors=errors,
    )


@router.get("/ingest/status")
def ingest_status():
    return {
        "status": _ingest_status.get("status", "idle"),
        "total_items": db.item_count(),
    }


@router.post("/agent/query", response_model=AgentQueryResponse, dependencies=[Depends(verify_api_key)])
async def agent_query(req: AgentQueryRequest):
    from agent.agent import run_query
    result = await run_query(req.message)
    return AgentQueryResponse(response=result)


async def _run_scraper(source: str) -> int:
    from scrapers.lighterpack import LighterPackScraper
    from scrapers.rei import REIScraper
    from scrapers.outdoorgearlab import OutdoorGearLabScraper

    scrapers = {
        "lighterpack": LighterPackScraper,
        "rei": REIScraper,
        "outdoorgearlab": OutdoorGearLabScraper,
    }

    cls = scrapers.get(source.lower())
    if not cls:
        raise ValueError(f"Unknown scraper source: {source!r}")

    scraper = cls()
    items = await scraper.scrape()
    item_dicts = [item.to_dict() for item in items if item.weight_g > 0]
    count = db.upsert_items(item_dicts)
    return count
