"""REI product page scraper — uses Playwright to bypass Akamai bot detection."""

from __future__ import annotations

import json
import logging
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext

from scrapers.base import (
    GearItem,
    normalize_category,
    parse_price_usd,
    parse_weight_g,
)
from scrapers.playwright_base import PlaywrightScraper

logger = logging.getLogger(__name__)

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

# Selectors to try when waiting for the product grid to render
_PRODUCT_SELECTORS = [
    "[data-ui='product-card']",
    ".VFTitledCard",
    "[class*='product-card']",
    "article",
]


class REIScraper(PlaywrightScraper):
    """Scrapes REI category pages using headless Chromium."""

    def __init__(
        self,
        category_urls: list[tuple[str, str]] | None = None,
        max_pages: int = 2,
        rate_limit: float = 2.5,
    ) -> None:
        super().__init__(rate_limit=rate_limit)
        self.category_urls = category_urls or SEED_CATEGORIES
        self.max_pages = max_pages

    async def _scrape_with_context(self, context: BrowserContext) -> list[GearItem]:
        items: list[GearItem] = []
        for url, category in self.category_urls:
            try:
                fetched = await self._scrape_category(context, url, category)
                items.extend(fetched)
                logger.info("REI %s: scraped %d items", category, len(fetched))
            except Exception as exc:
                logger.warning("REI category %s failed: %s", url, exc)
        return items

    async def _scrape_category(
        self, context: BrowserContext, base_url: str, category: str
    ) -> list[GearItem]:
        items: list[GearItem] = []
        for page_num in range(1, self.max_pages + 1):
            url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
            try:
                # Try each wait selector in order; first match wins
                wait_sel = _PRODUCT_SELECTORS[0]
                page = await self._fetch_page(context, url, wait_selector=wait_sel, timeout=20000)
                html = await page.content()
                await page.close()

                page_items = self._parse_listing(html, category, url)
                if not page_items:
                    break
                items.extend(page_items)
            except Exception as exc:
                logger.warning("REI page %s failed: %s", url, exc)
                break
        return items

    def _extract_from_json_ld(
        self, soup: BeautifulSoup, category: str, source_url: str
    ) -> list[GearItem]:
        items: list[GearItem] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except Exception:
                continue

            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("@type") != "Product":
                    continue

                name = entry.get("name", "").strip()
                if not name:
                    continue

                brand_raw = entry.get("brand", {})
                brand = (brand_raw.get("name", "Unknown") if isinstance(brand_raw, dict) else str(brand_raw or "Unknown")).strip() or "Unknown"

                price_usd: float | None = None
                offers = entry.get("offers")
                if isinstance(offers, dict):
                    try:
                        price_usd = float(offers["price"])
                    except (KeyError, TypeError, ValueError):
                        pass
                elif isinstance(offers, list) and offers:
                    try:
                        price_usd = float(offers[0]["price"])
                    except (KeyError, TypeError, ValueError):
                        pass

                weight_g: float | None = None
                for prop in entry.get("additionalProperty", []):
                    if not isinstance(prop, dict):
                        continue
                    if "weight" in prop.get("name", "").lower():
                        weight_g = parse_weight_g(str(prop.get("value", "")))
                        if weight_g is not None:
                            break

                item_url = entry.get("url") or source_url
                item_id = GearItem.make_id(brand, name)
                value_rating = GearItem.compute_value_rating(price_usd, weight_g or 1.0)

                items.append(GearItem(
                    id=item_id,
                    name=name,
                    brand=brand,
                    category=category,
                    weight_g=weight_g or 0.0,
                    price_usd=price_usd,
                    value_rating=value_rating,
                    description=entry.get("description", ""),
                    source_url=item_url,
                ))
        return items

    def _parse_listing(self, html: str, category: str, source_url: str) -> list[GearItem]:
        soup = BeautifulSoup(html, "html.parser")

        items = self._extract_from_json_ld(soup, category, source_url)
        if items:
            zero_weight = sum(1 for i in items if i.weight_g == 0)
            if zero_weight:
                logger.info("REI %s: %d/%d items have zero weight", source_url, zero_weight, len(items))
            return items

        # Fallback: card scraping
        product_cards = (
            soup.select("[data-ui='product-card']")
            or soup.select(".VFTitledCard")
            or soup.select("[class*='product-card']")
            or soup.find_all("article")
        )
        for card in product_cards:
            item = self._parse_card(card, category, source_url)
            if item:
                items.append(item)

        zero_weight = sum(1 for i in items if i.weight_g == 0)
        if zero_weight:
            logger.info("REI %s: %d/%d items have zero weight", source_url, zero_weight, len(items))
        return items

    def _parse_card(self, card: Any, category: str, source_url: str) -> GearItem | None:
        try:
            name_el = card.select_one("[data-ui='product-title'], .product-title, h2, h3")
            if not name_el:
                return None
            name = name_el.get_text(strip=True)
            if not name:
                return None

            brand_el = card.select_one("[data-ui='product-brand'], .product-brand, [class*='brand']")
            brand = brand_el.get_text(strip=True) if brand_el else "Unknown"

            price_el = card.select_one("[data-ui='price'], .price, [class*='price']")
            price_usd = parse_price_usd(price_el.get_text(strip=True)) if price_el else None

            weight_el = card.select_one("[data-ui='weight'], [class*='weight']")
            weight_g = parse_weight_g(weight_el.get_text()) if weight_el else None

            link_el = card.select_one("a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else f"https://www.rei.com{href}"

            item_id = GearItem.make_id(brand, name)
            value_rating = GearItem.compute_value_rating(price_usd, weight_g or 1.0)

            return GearItem(
                id=item_id, name=name, brand=brand, category=category,
                weight_g=weight_g or 0.0, price_usd=price_usd,
                value_rating=value_rating, source_url=link or source_url,
            )
        except Exception as exc:
            logger.debug("Failed to parse REI card: %s", exc)
            return None
