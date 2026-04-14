"""Discover public LighterPack list IDs from Reddit posts and comments."""

from __future__ import annotations

import logging
import re
from typing import Iterator

import httpx

logger = logging.getLogger(__name__)

# Pattern matches lighterpack.com/r/<ID> in any text
_LP_PATTERN = re.compile(r"lighterpack\.com/r/([A-Za-z0-9]+)")

_REDDIT_HEADERS = {
    "User-Agent": "UltralightFrenzy/1.0 gear-rag-scraper (opensource)",
    "Accept": "application/json",
}

# Subreddits to search + their relevant search queries
_SEARCH_TARGETS: list[tuple[str, str]] = [
    ("ultralight", "lighterpack"),
    ("ultralight", "gear list"),
    ("Ultralight", "lighterpack"),
    ("CampingandHiking", "lighterpack"),
    ("backpacking", "lighterpack ultralight"),
]

# Also scrape the top posts of these subreddits directly (no search query)
_HOT_SUBREDDITS = ["ultralight", "Ultralight"]

_TIME_FILTERS = ["year", "all"]


def _extract_ids_from_text(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(_LP_PATTERN.findall(text))


def _extract_ids_from_post(post_data: dict) -> set[str]:
    """Pull LighterPack IDs from a Reddit post object (title, selftext, url)."""
    ids: set[str] = set()
    ids |= _extract_ids_from_text(post_data.get("title"))
    ids |= _extract_ids_from_text(post_data.get("selftext"))
    ids |= _extract_ids_from_text(post_data.get("url"))
    return ids


async def discover_ids(
    *,
    include_comments: bool = False,
    limit_per_request: int = 100,
    time_filter: str = "year",
) -> list[str]:
    """
    Search Reddit for LighterPack list IDs.

    Returns a sorted, deduplicated list of LighterPack list IDs found across
    r/ultralight and related subreddits.

    Args:
        include_comments: if True, also fetch the top-level comments of each
            found post (slower but finds more IDs shared in comment threads).
        limit_per_request: how many posts to fetch per API call (max 100).
        time_filter: Reddit time filter — "hour", "day", "week", "month",
            "year", or "all".
    """
    found: set[str] = set()

    async with httpx.AsyncClient(
        headers=_REDDIT_HEADERS,
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        # 1. Search queries
        for subreddit, query in _SEARCH_TARGETS:
            try:
                url = (
                    f"https://www.reddit.com/r/{subreddit}/search.json"
                    f"?q={httpx.QueryParams({'q': query})}"
                    f"&restrict_sr=1&sort=top&t={time_filter}"
                    f"&limit={limit_per_request}"
                )
                # Build properly encoded URL
                params = {
                    "q": query,
                    "restrict_sr": "1",
                    "sort": "top",
                    "t": time_filter,
                    "limit": str(limit_per_request),
                }
                resp = await client.get(
                    f"https://www.reddit.com/r/{subreddit}/search.json",
                    params=params,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Reddit search r/%s %r → HTTP %d", subreddit, query, resp.status_code
                    )
                    continue
                data = resp.json()
                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    found |= _extract_ids_from_post(post.get("data", {}))
                logger.debug(
                    "Reddit search r/%s %r: %d posts, %d IDs so far",
                    subreddit, query, len(posts), len(found),
                )
            except Exception as exc:
                logger.warning("Reddit search r/%s %r failed: %s", subreddit, query, exc)

        # 2. Hot / top posts of key subreddits
        for subreddit in _HOT_SUBREDDITS:
            for sort in ("hot", "top"):
                try:
                    params = {"limit": str(limit_per_request), "t": time_filter}
                    resp = await client.get(
                        f"https://www.reddit.com/r/{subreddit}/{sort}.json",
                        params=params,
                    )
                    if resp.status_code != 200:
                        logger.warning(
                            "Reddit r/%s/%s → HTTP %d", subreddit, sort, resp.status_code
                        )
                        continue
                    data = resp.json()
                    posts = data.get("data", {}).get("children", [])
                    for post in posts:
                        found |= _extract_ids_from_post(post.get("data", {}))
                except Exception as exc:
                    logger.warning("Reddit r/%s/%s failed: %s", subreddit, sort, exc)

    return sorted(found)


def discover_ids_sync(
    *,
    time_filter: str = "year",
) -> list[str]:
    """Synchronous wrapper around discover_ids for CLI use."""
    import asyncio
    return asyncio.run(discover_ids(time_filter=time_filter))
