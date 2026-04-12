"""Config-driven Shopify scraper using the public products.json API."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from scrapers.base import BaseScraper, GearItem, parse_price_usd
from scrapers.configs.sites import (
    DEFAULT_CATEGORY_MAP,
    SHOPIFY_STORES,
    ShopifyStore,
)

logger = logging.getLogger(__name__)

# Shopify returns up to 250 products per page; most small brands have < 250
_PAGE_SIZE = 250


def _weight_to_grams(weight: float, unit: str) -> float | None:
    """Convert Shopify variant weight to grams."""
    unit = (unit or "g").lower().strip()
    if unit in ("g", "gram", "grams"):
        return float(weight)
    if unit in ("oz", "ounce", "ounces"):
        return round(float(weight) * 28.3495, 1)
    if unit in ("lb", "lbs", "pound", "pounds"):
        return round(float(weight) * 453.592, 1)
    if unit in ("kg", "kilogram", "kilograms"):
        return round(float(weight) * 1000.0, 1)
    return None


def _map_category(product_type: str, category_map: dict[str, str]) -> str:
    lower = product_type.lower()
    for key, cat in category_map.items():
        if key in lower:
            return cat
    return "other"


class ShopifyScraper(BaseScraper):
    """Scrapes Shopify stores via the public /products.json API endpoint."""

    def __init__(
        self,
        stores: list[ShopifyStore] | None = None,
        rate_limit: float = 1.5,
    ) -> None:
        super().__init__(rate_limit=rate_limit)
        self.stores = stores or SHOPIFY_STORES

    async def scrape(self) -> list[GearItem]:
        items: list[GearItem] = []
        async with httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            for store in self.stores:
                try:
                    store_items = await self._scrape_store(client, store)
                    items.extend(store_items)
                    logger.info(
                        "Shopify %s: scraped %d items", store.name, len(store_items)
                    )
                except Exception as exc:
                    logger.warning("Shopify %s failed: %s", store.name, exc)
        return items

    async def _scrape_store(
        self, client: httpx.AsyncClient, store: ShopifyStore
    ) -> list[GearItem]:
        category_map = store.category_map or DEFAULT_CATEGORY_MAP
        items: list[GearItem] = []
        page = 1

        while True:
            await self._throttle()
            url = f"{store.base_url}/products.json?limit={_PAGE_SIZE}&page={page}"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Shopify %s page %d HTTP error: %s", store.name, page, exc
                )
                break

            data = resp.json()
            products = data.get("products", [])
            if not products:
                break

            for product in products:
                parsed = self._parse_product(product, store, category_map)
                items.extend(parsed)

            if len(products) < _PAGE_SIZE:
                break  # last page
            page += 1

        return items

    def _parse_product(
        self,
        product: dict[str, Any],
        store: ShopifyStore,
        category_map: dict[str, str],
    ) -> list[GearItem]:
        """Parse one Shopify product dict into zero or more GearItems.

        One product can have multiple variants (e.g. size/color options).
        We create one GearItem per unique weight variant, deduplicating by weight.
        """
        title = (product.get("title") or "").strip()
        if not title:
            return []

        brand = store.name
        product_type = (product.get("product_type") or "").strip()
        category = _map_category(product_type, category_map)

        # Build description from body_html (strip tags)
        body_html = product.get("body_html") or ""
        description = re.sub(r"<[^>]+>", " ", body_html).strip()
        description = re.sub(r"\s+", " ", description)[:500]

        handle = product.get("handle") or ""
        source_url = f"{store.base_url}/products/{handle}" if handle else store.base_url

        variants = product.get("variants") or []
        seen_weights: set[float] = set()
        items: list[GearItem] = []

        for variant in variants:
            raw_weight = variant.get("weight")
            weight_unit = variant.get("weight_unit") or "g"

            if raw_weight is None or float(raw_weight) == 0:
                continue

            weight_g = _weight_to_grams(float(raw_weight), weight_unit)
            if weight_g is None or weight_g <= 0:
                continue

            # Deduplicate variants by weight (avoid one entry per size/color)
            if weight_g in seen_weights:
                continue
            seen_weights.add(weight_g)

            price_str = variant.get("price") or ""
            price_usd = parse_price_usd(price_str) if price_str else None

            # Build a unique ID including variant title if multiple weights exist
            variant_title = (variant.get("title") or "").strip()
            if variant_title and variant_title.lower() != "default title":
                item_id = GearItem.make_id(brand, f"{title} {variant_title}")
                item_name = f"{title} — {variant_title}"
            else:
                item_id = GearItem.make_id(brand, title)
                item_name = title

            value_rating = GearItem.compute_value_rating(price_usd, weight_g)

            items.append(
                GearItem(
                    id=item_id,
                    name=item_name,
                    brand=brand,
                    category=category,
                    weight_g=weight_g,
                    price_usd=price_usd,
                    value_rating=value_rating,
                    description=description,
                    source_url=source_url,
                )
            )

        # If no variant had weight data, fall back to a single zero-weight entry
        # (caller will filter these out with weight_g > 0 check)
        return items
