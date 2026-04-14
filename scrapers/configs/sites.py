"""Config-driven Shopify store definitions for ultralight gear brands."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShopifyStore:
    name: str          # human-readable brand name
    base_url: str      # store root, no trailing slash
    # Maps Shopify product_type values to our canonical categories.
    # Keys are lowercase substrings; first match wins.
    category_map: dict[str, str] = field(default_factory=dict)


# Default category map used when a store doesn't supply one
DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "tent": "shelter",
    "tarp": "shelter",
    "bivy": "shelter",
    "shelter": "shelter",
    "sleeping bag": "sleep",
    "quilt": "sleep",
    "underquilt": "sleep",
    "pad": "sleep",
    "hammock": "sleep",
    "backpack": "pack",
    "pack": "pack",
    "stuff sack": "pack",
    "bag": "pack",
    "shoe": "footwear",
    "boot": "footwear",
    "jacket": "clothing",
    "rain": "clothing",
    "insulation": "clothing",
    "stove": "cooking",
    "pot": "cooking",
    "cookware": "cooking",
    "titanium": "cooking",
    "poncho": "clothing",
    "shirt": "clothing",
    "pants": "clothing",
    "shorts": "clothing",
    "wind": "clothing",
}


SHOPIFY_STORES: list[ShopifyStore] = [
    ShopifyStore(
        name="Zpacks",
        base_url="https://zpacks.com",
    ),
    ShopifyStore(
        name="Katabatic Gear",
        base_url="https://katabaticgear.com",
    ),
    ShopifyStore(
        name="Gossamer Gear",
        base_url="https://gossamergear.com",
    ),
    ShopifyStore(
        name="Six Moon Designs",
        base_url="https://sixmoondesigns.com",
    ),
    ShopifyStore(
        name="Durston Gear",
        base_url="https://durstongear.com",
    ),
    ShopifyStore(
        name="Hyperlite Mountain Gear",
        base_url="https://www.hyperlitemountaingear.com",
    ),
    # Confirmed NOT Shopify (404 or non-JSON on /products.json) — removed:
    # Hammock Gear (WooCommerce), Tarptent, Mountain Laurel Designs, ULA Equipment
]
