"""LighterPack scraper — fetches public pack list JSON exports."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from scrapers.base import (
    BaseScraper,
    GearItem,
    normalize_category,
    parse_weight_g,
)

logger = logging.getLogger(__name__)

# Curated list of public LighterPack list IDs to seed the database.
# Each entry is a (list_id, description) tuple.
SEED_LIST_IDS = [
    ("rg6tge", "UL thru-hiker base kit"),
    ("fBpvs2", "3-season ultralight setup"),
    ("8fJ3k1", "SUL summer kit"),
]

LIGHTERPACK_JSON_URL = "https://lighterpack.com/r/{list_id}"


class LighterPackScraper(BaseScraper):
    """Scrapes public LighterPack gear lists via their JSON export endpoint."""

    def __init__(
        self,
        list_ids: list[str] | None = None,
        rate_limit: float = 1.0,
    ) -> None:
        super().__init__(rate_limit)
        self.list_ids = list_ids or [lid for lid, _ in SEED_LIST_IDS]

    async def scrape(self) -> list[GearItem]:
        items: list[GearItem] = []
        async with httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            for list_id in self.list_ids:
                try:
                    await self._throttle()
                    fetched = await self._fetch_list(client, list_id)
                    items.extend(fetched)
                    logger.info(
                        "LighterPack %s: scraped %d items", list_id, len(fetched)
                    )
                except Exception as exc:
                    logger.warning("LighterPack %s failed: %s", list_id, exc)
        return items

    async def _fetch_list(
        self, client: httpx.AsyncClient, list_id: str
    ) -> list[GearItem]:
        url = f"https://lighterpack.com/api/shared/{list_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return self._parse(data, list_id)

    def _parse(self, data: dict[str, Any], list_id: str) -> list[GearItem]:
        items: list[GearItem] = []
        categories = data.get("categories", [])
        for cat_data in categories:
            cat_name = cat_data.get("name", "other")
            category = normalize_category(cat_name)
            for entry in cat_data.get("items", []):
                name = entry.get("name", "").strip()
                if not name:
                    continue
                # LighterPack stores weight in grams
                weight_g = float(entry.get("weight", 0) or 0)
                if weight_g <= 0:
                    # fallback: try parsing the display string
                    wt = parse_weight_g(str(entry.get("weight", "")))
                    weight_g = wt or 0.0

                brand = entry.get("brand", "").strip() or "Unknown"
                description = entry.get("description", "") or ""
                link = entry.get("url", "") or ""
                item_id = GearItem.make_id(brand, name)

                items.append(
                    GearItem(
                        id=item_id,
                        name=name,
                        brand=brand,
                        category=category,
                        weight_g=weight_g,
                        description=description,
                        source_url=link or f"https://lighterpack.com/r/{list_id}",
                    )
                )
        return items
