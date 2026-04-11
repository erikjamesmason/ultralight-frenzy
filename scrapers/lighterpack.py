"""LighterPack scraper — parses public pack list pages."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup, Tag

from scrapers.base import (
    BaseScraper,
    GearItem,
    normalize_category,
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
                "uv run gear ingest --sources lighterpack --lp-ids abc123"
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
        return self._parse_html(resp.text, list_id, url)

    def _parse_html(self, html: str, list_id: str, source_url: str) -> list[GearItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[GearItem] = []

        # Each category is a <div> or <ul> with class lpCategory, containing:
        #   - a category name header
        #   - <li class="lpItem"> rows
        # Walk all lpItem elements and track the nearest preceding category header.

        current_category = "other"

        # Collect all category headers and item rows in document order
        for el in soup.find_all(True):
            if not isinstance(el, Tag):
                continue

            classes = el.get("class") or []

            # Category header — lpCategory or lpCategoryName
            if "lpCategory" in classes or "lpCategoryName" in classes:
                text = el.get_text(strip=True)
                if text:
                    current_category = normalize_category(text)
                continue

            # Also catch <li class="lpRow"> that has a category name cell
            if "lpRow" in classes and "lpHeader" not in classes and "lpItem" not in classes:
                name_cell = el.select_one(".lpCell:not(.lpNumber):not(.lpLegendCell)")
                if name_cell:
                    text = name_cell.get_text(strip=True)
                    if text and text not in ("Category", "Price", "Weight", "Qty", ""):
                        current_category = normalize_category(text)
                continue

            # Item rows
            if "lpItem" in classes:
                item = self._parse_item(el, current_category, source_url)
                if item:
                    items.append(item)

        return items

    def _parse_item(self, el: Tag, category: str, source_url: str) -> GearItem | None:
        try:
            # --- Weight (most reliable: mg attribute) ---
            weight_g = 0.0
            weight_el = el.select_one("[mg]")
            if weight_el:
                mg = weight_el.get("mg")
                if mg:
                    weight_g = round(int(mg) / 1000, 1)

            # --- Name ---
            name = ""
            for selector in [".lpName", ".lpItemName", "[class*='lpName']"]:
                name_el = el.select_one(selector)
                if name_el:
                    name = name_el.get_text(strip=True)
                    break

            # Fallback: first text-heavy cell that isn't price/weight
            if not name:
                for cell in el.select(".lpCell"):
                    text = cell.get_text(strip=True)
                    # Skip cells that look like price/weight/qty
                    if text and not re.match(r'^[\$\d\.,\s]+$', text) and len(text) > 2:
                        name = text
                        break

            # Last resort: strip price/weight noise from full element text
            if not name:
                full = el.get_text(separator=" ", strip=True)
                # Remove dollar amounts and unit selectors
                full = re.sub(r'\$[\d\.]+', '', full)
                full = re.sub(r'\b\d+\s*(oz|lb|g|kg)\b', '', full, flags=re.I)
                full = re.sub(r'\b(oz|lb|g|kg)\b', '', full, flags=re.I)
                full = re.sub(r'\s+', ' ', full).strip()
                name = full[:80] if full else ""

            if not name:
                return None

            # --- Brand: first word(s) of the name heuristic ---
            brand = "Unknown"
            parts = name.split()
            if len(parts) >= 2:
                brand = " ".join(parts[:2]).title()

            # --- Price ---
            price_usd = None
            price_el = el.select_one(".lpPrice, [class*='lpPrice']")
            if price_el:
                price_text = price_el.get_text(strip=True)
                m = re.search(r'[\d\.]+', price_text.replace(",", ""))
                if m:
                    val = float(m.group())
                    if val > 0:
                        price_usd = val

            # --- Description ---
            desc = ""
            desc_el = el.select_one(".lpDescription, [class*='lpDescription']")
            if desc_el:
                desc = desc_el.get_text(strip=True)

            return GearItem(
                id=GearItem.make_id(brand, name),
                name=name,
                brand=brand,
                category=category,
                weight_g=weight_g,
                price_usd=price_usd,
                value_rating=GearItem.compute_value_rating(price_usd, weight_g or 1.0),
                description=desc,
                source_url=source_url,
            )
        except Exception as exc:
            logger.debug("Failed to parse lpItem: %s", exc)
            return None
