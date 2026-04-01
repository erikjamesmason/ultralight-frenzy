"""REI product page scraper."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from scrapers.base import (
    BaseScraper,
    GearItem,
    normalize_category,
    parse_price_usd,
    parse_weight_g,
)

logger = logging.getLogger(__name__)

# REI category search pages to crawl
SEED_CATEGORIES = [
    ("https://www.rei.com/c/backpacking-tents", "shelter"),
    ("https://www.rei.com/c/sleeping-bags", "sleep"),
    ("https://www.rei.com/c/sleeping-pads", "sleep"),
    ("https://www.rei.com/c/backpacks", "pack"),
    ("https://www.rei.com/c/trail-running-shoes", "footwear"),
    ("https://www.rei.com/c/hiking-boots", "footwear"),
    ("https://www.rei.com/c/rain-jackets", "clothing"),
    ("https://www.rei.com/c/camp-stoves", "cooking"),
]


class REIScraper(BaseScraper):
    """Scrapes REI product listing pages for gear specs and prices."""

    def __init__(
        self,
        category_urls: list[tuple[str, str]] | None = None,
        max_pages: int = 2,
        rate_limit: float = 1.5,
    ) -> None:
        super().__init__(rate_limit)
        self.category_urls = category_urls or SEED_CATEGORIES
        self.max_pages = max_pages

    async def scrape(self) -> list[GearItem]:
        items: list[GearItem] = []
        async with httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            for url, category in self.category_urls:
                try:
                    fetched = await self._scrape_category(client, url, category)
                    items.extend(fetched)
                    logger.info("REI %s: scraped %d items", category, len(fetched))
                except Exception as exc:
                    logger.warning("REI category %s failed: %s", url, exc)
        return items

    async def _scrape_category(
        self, client: httpx.AsyncClient, base_url: str, category: str
    ) -> list[GearItem]:
        items: list[GearItem] = []
        for page in range(1, self.max_pages + 1):
            await self._throttle()
            url = f"{base_url}?page={page}" if page > 1 else base_url
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                page_items = self._parse_listing(resp.text, category, base_url)
                if not page_items:
                    break
                items.extend(page_items)
            except httpx.HTTPStatusError as exc:
                logger.warning("REI page %s failed: %s", url, exc)
                break
        return items

    def _parse_listing(
        self, html: str, category: str, source_url: str
    ) -> list[GearItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[GearItem] = []

        # REI uses a React-hydrated store — try JSON-LD and fallback to meta tags
        product_cards = soup.select("[data-ui='product-card']") or soup.select(
            ".product-card"
        )
        if not product_cards:
            # Attempt to find any product-like article elements
            product_cards = soup.find_all("article")

        for card in product_cards:
            item = self._parse_card(card, category, source_url)
            if item:
                items.append(item)

        return items

    def _parse_card(
        self, card: Any, category: str, source_url: str
    ) -> GearItem | None:
        try:
            name_el = card.select_one(
                "[data-ui='product-title'], .product-title, h2, h3"
            )
            if not name_el:
                return None
            name = name_el.get_text(strip=True)
            if not name:
                return None

            brand_el = card.select_one(
                "[data-ui='product-brand'], .product-brand, [class*='brand']"
            )
            brand = brand_el.get_text(strip=True) if brand_el else "Unknown"

            price_el = card.select_one(
                "[data-ui='price'], .price, [class*='price']"
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_usd = parse_price_usd(price_text)

            # Weight is in the specs table or subtitle
            weight_el = card.select_one("[data-ui='weight'], [class*='weight']")
            weight_g = None
            if weight_el:
                weight_g = parse_weight_g(weight_el.get_text())

            link_el = card.select_one("a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else f"https://www.rei.com{href}"

            item_id = GearItem.make_id(brand, name)
            value_rating = GearItem.compute_value_rating(price_usd, weight_g or 1.0)

            return GearItem(
                id=item_id,
                name=name,
                brand=brand,
                category=category,
                weight_g=weight_g or 0.0,
                price_usd=price_usd,
                value_rating=value_rating,
                source_url=link or source_url,
            )
        except Exception as exc:
            logger.debug("Failed to parse REI card: %s", exc)
            return None
