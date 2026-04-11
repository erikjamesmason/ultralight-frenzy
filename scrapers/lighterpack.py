"""LighterPack scraper — parses public pack list pages."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from scrapers.base import (
    BaseScraper,
    GearItem,
    normalize_category,
    parse_weight_g,
)

logger = logging.getLogger(__name__)


class LighterPackScraper(BaseScraper):
    """
    Scrapes public LighterPack gear lists.

    Pass list IDs via the constructor or the CLI --lp-ids flag.
    Find IDs in any public LighterPack share URL:
      https://lighterpack.com/r/<ID>
    """

    def __init__(
        self,
        list_ids: list[str] | None = None,
        rate_limit: float = 1.0,
    ) -> None:
        super().__init__(rate_limit)
        self.list_ids = list_ids or []

    async def scrape(self) -> list[GearItem]:
        if not self.list_ids:
            logger.warning(
                "No LighterPack list IDs provided. "
                "Pass them with --lp-ids, e.g.: "
                "uv run gear ingest --sources lighterpack --lp-ids abc123 def456"
            )
            return []

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
        url = f"https://lighterpack.com/r/{list_id}"
        resp = await client.get(url)
        resp.raise_for_status()

        # Try to find embedded JSON in the page (LighterPack hydrates the page
        # with a JSON blob in a <script> tag)
        data = self._extract_json(resp.text)
        if data:
            return self._parse_json(data, list_id, url)

        # Fallback: parse the HTML table directly
        return self._parse_html(resp.text, list_id, url)

    # ------------------------------------------------------------------
    # JSON extraction (LighterPack embeds pack data in the page script)
    # ------------------------------------------------------------------

    def _extract_json(self, html: str) -> dict[str, Any] | None:
        """Look for the JSON pack data embedded in <script> tags."""
        # Pattern 1: window.list = {...}  or  var list = {...}
        for pattern in [
            r'window\.list\s*=\s*(\{.+?\});',
            r'var\s+list\s*=\s*(\{.+?\});',
            r'"list"\s*:\s*(\{.+?"categories".+?\])',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue

        # Pattern 2: look for any script tag that contains "categories"
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"categories"' in text:
                # Try to extract the JSON object containing categories
                m = re.search(r'(\{[^{}]*"categories"\s*:\s*\[.+?\]\s*\})', text, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(1))
                    except json.JSONDecodeError:
                        continue
        return None

    def _parse_json(
        self, data: dict[str, Any], list_id: str, source_url: str
    ) -> list[GearItem]:
        items: list[GearItem] = []
        categories = data.get("categories", [])
        for cat_data in categories:
            cat_name = cat_data.get("name", "other")
            category = normalize_category(cat_name)
            for entry in cat_data.get("items", []):
                item = self._entry_to_gear_item(entry, category, list_id, source_url)
                if item:
                    items.append(item)
        return items

    def _entry_to_gear_item(
        self,
        entry: dict[str, Any],
        category: str,
        list_id: str,
        source_url: str,
    ) -> GearItem | None:
        name = (entry.get("name") or "").strip()
        if not name:
            return None

        # Weight: LighterPack stores in grams or as a display string
        weight_g = 0.0
        raw_weight = entry.get("weight", 0)
        if isinstance(raw_weight, (int, float)):
            weight_g = float(raw_weight)
        else:
            w = parse_weight_g(str(raw_weight))
            weight_g = w or 0.0

        # LighterPack unit field: 1=oz, 2=lb, 3=g, 4=kg
        unit = entry.get("unit", 3)
        if weight_g > 0 and unit == 1:
            weight_g = round(weight_g * 28.3495, 1)
        elif weight_g > 0 and unit == 2:
            weight_g = round(weight_g * 453.592, 1)
        elif weight_g > 0 and unit == 4:
            weight_g = round(weight_g * 1000, 1)

        brand = (entry.get("brand") or "Unknown").strip()
        description = (entry.get("description") or "").strip()
        link = (entry.get("url") or "").strip()

        return GearItem(
            id=GearItem.make_id(brand, name),
            name=name,
            brand=brand,
            category=category,
            weight_g=weight_g,
            description=description,
            source_url=link or source_url,
        )

    # ------------------------------------------------------------------
    # HTML table fallback
    # ------------------------------------------------------------------

    def _parse_html(
        self, html: str, list_id: str, source_url: str
    ) -> list[GearItem]:
        """
        Fallback: parse the rendered HTML gear table.
        LighterPack renders rows like:
          <tr class="item-row"> ... <td class="item-name">...</td> ...
        """
        soup = BeautifulSoup(html, "html.parser")
        items: list[GearItem] = []
        current_category = "other"

        for row in soup.select("tr"):
            # Category header rows
            cat_cell = row.select_one(".category-name, [class*='categoryName']")
            if cat_cell:
                current_category = normalize_category(cat_cell.get_text(strip=True))
                continue

            # Item rows
            name_cell = row.select_one(
                ".item-name, [class*='itemName'], [class*='item-name']"
            )
            if not name_cell:
                continue
            name = name_cell.get_text(strip=True)
            if not name:
                continue

            weight_cell = row.select_one(
                ".item-weight, [class*='itemWeight'], [class*='item-weight']"
            )
            weight_g = 0.0
            if weight_cell:
                w = parse_weight_g(weight_cell.get_text(strip=True))
                weight_g = w or 0.0

            items.append(
                GearItem(
                    id=GearItem.make_id("unknown", name),
                    name=name,
                    brand="Unknown",
                    category=current_category,
                    weight_g=weight_g,
                    source_url=source_url,
                )
            )
        return items
