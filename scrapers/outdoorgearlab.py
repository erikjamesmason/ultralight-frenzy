"""OutdoorGearLab review scraper."""

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

KNOWN_MULTIWORD_BRANDS = {
    "big agnes", "sea to summit", "six moon", "zpacks", "enlightened equipment",
    "outdoor research", "mountain hardwear", "black diamond", "gregory mountain",
    "osprey packs", "therm a", "western mountaineering",
}

SEED_REVIEW_URLS = [
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-backpacking-tent", "shelter"),
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-backpacking-sleeping-bag", "sleep"),
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-backpacking-sleeping-pad", "sleep"),
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-backpacking-backpack", "pack"),
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-trail-running-shoes", "footwear"),
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-hardshell-jackets", "clothing"),
    ("https://www.outdoorgearlab.com/topics/camping-and-hiking/best-backpacking-stove", "cooking"),
]


class OutdoorGearLabScraper(BaseScraper):
    """Scrapes OutdoorGearLab best-of pages for gear reviews and scores."""

    def __init__(
        self,
        review_urls: list[tuple[str, str]] | None = None,
        rate_limit: float = 1.5,
    ) -> None:
        super().__init__(rate_limit)
        self.review_urls = review_urls or SEED_REVIEW_URLS

    async def scrape(self) -> list[GearItem]:
        items: list[GearItem] = []
        async with httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            for url, category in self.review_urls:
                try:
                    await self._throttle()
                    fetched = await self._scrape_page(client, url, category)
                    items.extend(fetched)
                    logger.info(
                        "OGL %s: scraped %d items", category, len(fetched)
                    )
                except Exception as exc:
                    logger.warning("OGL %s failed: %s", url, exc)
        return items

    async def _scrape_page(
        self, client: httpx.AsyncClient, url: str, category: str
    ) -> list[GearItem]:
        resp = await client.get(url)
        resp.raise_for_status()
        return self._parse(resp.text, category, url)

    def _parse(self, html: str, category: str, source_url: str) -> list[GearItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[GearItem] = []

        # OGL product entries are in award/ranked sections
        product_sections = soup.select(
            ".award-card, .product-card, [class*='ProductCard'], [class*='award']"
        ) or soup.select("article")

        for section in product_sections:
            item = self._parse_section(section, category, source_url)
            if item:
                items.append(item)

        return items

    def _parse_section(
        self, section: Any, category: str, source_url: str
    ) -> GearItem | None:
        try:
            # Product name
            name_el = section.select_one(
                "h2, h3, h4, [class*='product-name'], [class*='productName']"
            )
            if not name_el:
                return None
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                return None

            # Brand — explicit brand element, multi-word known brands, or first word
            brand_el = section.select_one("[class*='brand']")
            if brand_el:
                brand = brand_el.get_text(strip=True)
            else:
                words = name.split()
                two_word_prefix = " ".join(words[:2]).lower() if len(words) >= 2 else ""
                if two_word_prefix and two_word_prefix in KNOWN_MULTIWORD_BRANDS:
                    brand = " ".join(words[:2])
                else:
                    brand = words[0] if words else "Unknown"

            # Price
            price_el = section.select_one("[class*='price'], [data-price]")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_usd = parse_price_usd(price_text)

            # Weight — look in spec tables or text
            weight_g = self._extract_weight(section)

            # Score / review text
            score_el = section.select_one(
                "[class*='score'], [class*='rating'], [class*='award-name']"
            )
            review_text = score_el.get_text(strip=True) if score_el else ""

            # Longer prose
            body_el = section.select_one("p, [class*='description'], [class*='summary']")
            if body_el:
                review_text = f"{review_text} {body_el.get_text(strip=True)}".strip()

            link_el = section.select_one("a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = (
                    href
                    if href.startswith("http")
                    else f"https://www.outdoorgearlab.com{href}"
                )

            item_id = GearItem.make_id(brand, name)
            value_rating = GearItem.compute_value_rating(price_usd, weight_g or 1.0)

            # Collect any visible specs using th/td pairing
            specs: dict[str, str] = {}
            for table in section.select("table"):
                for row in table.select("tr"):
                    th = row.select_one("th")
                    td = row.select_one("td")
                    if th and td:
                        key = th.get_text(strip=True)
                        val = td.get_text(strip=True)
                        if key:
                            specs[key] = val

            return GearItem(
                id=item_id,
                name=name,
                brand=brand,
                category=category,
                weight_g=weight_g or 0.0,
                price_usd=price_usd,
                value_rating=value_rating,
                specs=specs,
                reviews=review_text,
                source_url=link or source_url,
            )
        except Exception as exc:
            logger.debug("Failed to parse OGL section: %s", exc)
            return None

    def _extract_weight(self, section: Any) -> float | None:
        # Check explicit weight elements
        for selector in ["[class*='weight']", "td", "li", "span"]:
            for el in section.select(selector):
                text = el.get_text()
                if re.search(r"\d+\s*(g|oz|lb)", text, re.I):
                    w = parse_weight_g(text)
                    if w:
                        return w
        return None
