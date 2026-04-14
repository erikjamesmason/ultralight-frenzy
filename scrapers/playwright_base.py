"""Base class for Playwright-backed scrapers."""

from __future__ import annotations

import asyncio
import time
from abc import abstractmethod
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from scrapers.base import BaseScraper, GearItem


class PlaywrightScraper(BaseScraper):
    """Scraper base class that uses a shared headless Chromium browser."""

    BROWSER_ARGS = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]

    def __init__(self, rate_limit: float = 2.0) -> None:
        super().__init__(rate_limit=rate_limit)

    async def scrape(self) -> list[GearItem]:
        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(
                headless=True,
                args=self.BROWSER_ARGS,
            )
            context: BrowserContext = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            try:
                return await self._scrape_with_context(context)
            finally:
                await browser.close()

    @abstractmethod
    async def _scrape_with_context(self, context: BrowserContext) -> list[GearItem]:
        """Subclasses implement scraping logic using the provided browser context."""
        ...

    async def _fetch_page(self, context: BrowserContext, url: str, wait_selector: str | None = None, timeout: int = 30000) -> Page:
        """Navigate to url, optionally wait for a CSS selector, return the Page."""
        await self._throttle()
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=timeout)
            except Exception:
                pass  # proceed even if selector never appears; page may still have JSON-LD
        return page
