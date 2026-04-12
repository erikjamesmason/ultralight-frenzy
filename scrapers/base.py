"""Base scraper and GearItem dataclass."""

from __future__ import annotations

import asyncio
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class GearItem:
    id: str                                  # slug: brand-name-variant
    name: str
    brand: str
    category: str                            # shelter|sleep|pack|footwear|clothing|cooking|nav|other
    weight_g: float
    packed_weight_g: float | None = None
    dimensions_cm: dict[str, float] | None = None
    price_usd: float | None = None
    value_rating: float | None = None        # price_usd / weight_g
    material: str | None = None
    specs: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    reviews: str = ""
    source_url: str = ""
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "weight_g": self.weight_g,
            "packed_weight_g": self.packed_weight_g,
            "dimensions_cm": self.dimensions_cm,
            "price_usd": self.price_usd,
            "value_rating": self.value_rating,
            "material": self.material,
            "specs": self.specs,
            "description": self.description,
            "reviews": self.reviews,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at,
        }

    @staticmethod
    def make_id(brand: str, name: str) -> str:
        raw = f"{brand}-{name}".lower()
        return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")

    @staticmethod
    def compute_value_rating(price_usd: float | None, weight_g: float) -> float | None:
        if price_usd is not None and weight_g > 0:
            return round(price_usd / weight_g, 4)
        return None


CATEGORY_MAP = {
    "tent": "shelter",
    "tarp": "shelter",
    "bivy": "shelter",
    "shelter": "shelter",
    "sleeping bag": "sleep",
    "quilt": "sleep",
    "sleeping pad": "sleep",
    "pad": "sleep",
    "backpack": "pack",
    "pack": "pack",
    "stuff sack": "pack",
    "shoe": "footwear",
    "boot": "footwear",
    "footwear": "footwear",
    "jacket": "clothing",
    "rain": "clothing",
    "insulation": "clothing",
    "clothing": "clothing",
    "stove": "cooking",
    "pot": "cooking",
    "cookware": "cooking",
    "cooking": "cooking",
    "navigation": "nav",
    "compass": "nav",
    "gps": "nav",
}


def normalize_category(raw: str) -> str:
    lower = raw.lower()
    for key, cat in CATEGORY_MAP.items():
        if key in lower:
            return cat
    return "other"


def parse_weight_g(text: str) -> float | None:
    """Parse weight strings like '1 lb 3 oz', '540g', '19.0 oz' → grams."""
    text = text.strip().lower()
    # Already in grams
    m = re.search(r"([\d.]+)\s*g\b", text)
    if m:
        return float(m.group(1))
    # Ounces
    m = re.search(r"([\d.]+)\s*oz", text)
    if m:
        return round(float(m.group(1)) * 28.3495, 1)
    # Pounds + oz
    lb = re.search(r"([\d.]+)\s*lb", text)
    oz = re.search(r"([\d.]+)\s*oz", text)
    if lb:
        grams = float(lb.group(1)) * 453.592
        if oz:
            grams += float(oz.group(1)) * 28.3495
        return round(grams, 1)
    return None


def parse_price_usd(text: str) -> float | None:
    text = text.strip()
    m = re.search(r"\$?([\d,]+\.?\d*)", text.replace(",", ""))
    if m:
        return float(m.group(1))
    return None


class BaseScraper(ABC):
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, rate_limit: float = 1.0) -> None:
        self._rate_limit = rate_limit
        self._last_request: float = 0.0

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self._rate_limit - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    @abstractmethod
    async def scrape(self) -> list[GearItem]:
        """Scrape source and return list of GearItem."""
        ...
