"""Typer CLI for ultralight-frenzy."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(
    name="gear",
    help="Ultralight Frenzy — agentic gear database CLI",
    no_args_is_help=True,
)
console = Console()


@app.command()
def debug_lp(
    list_id: str = typer.Argument(..., help="LighterPack list ID to inspect."),
):
    """Fetch a LighterPack page and print what the scraper sees — for debugging."""
    import asyncio
    import httpx
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; UltralightFrenzy/1.0)"
        )
    }

    async def fetch():
        async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
            url = f"https://lighterpack.com/r/{list_id}"
            console.print(f"Fetching [bold]{url}[/bold]…")
            resp = await client.get(url)
            console.print(f"Status: {resp.status_code}")
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            console.print(f"\n[bold]<script> tags found:[/bold] {len(soup.find_all('script'))}")
            for i, script in enumerate(soup.find_all("script")):
                text = (script.string or "")
                src = script.get("src", "")
                console.print(f"  [{i}] src={src!r} len={len(text)} "
                              f"has_categories={'categories' in text} "
                              f"has_items={'\"items\"' in text} "
                              f"preview={text[:120]!r}")

            console.print(f"\n[bold]Rows with 'item' in class:[/bold]")
            for row in soup.find_all(class_=lambda c: c and "item" in c.lower())[:5]:
                console.print(f"  {row.name} class={row.get('class')} text={row.get_text(strip=True)[:80]!r}")

            console.print(f"\n[bold]First 2000 chars of raw HTML:[/bold]")
            console.print(html[:2000])

    asyncio.run(fetch())


def _init_db():
    from db.client import get_collection
    return get_collection(
        persist_path=os.environ.get("CHROMA_PERSIST_PATH", "./data/chroma"),
        collection_name=os.environ.get("CHROMA_COLLECTION", "gear"),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
    )


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@app.command()
def ingest(
    sources: list[str] = typer.Option(
        ["lighterpack", "rei", "outdoorgearlab"],
        "--sources",
        "-s",
        help="Scraper sources to run (lighterpack, rei, outdoorgearlab).",
    ),
    lp_ids: Optional[list[str]] = typer.Option(
        None,
        "--lp-ids",
        help=(
            "LighterPack list IDs to scrape. Find the ID in any public share URL: "
            "https://lighterpack.com/r/<ID>. "
            "Example: --lp-ids abc123 --lp-ids def456"
        ),
    ),
):
    """Scrape gear data and upsert into the vector database."""
    from scrapers.lighterpack import LighterPackScraper
    from scrapers.rei import REIScraper
    from scrapers.outdoorgearlab import OutdoorGearLabScraper
    from db import operations as db

    _init_db()

    total = 0
    for source in sources:
        source = source.lower()
        with console.status(f"Scraping [bold]{source}[/bold]…"):
            if source == "lighterpack":
                if not lp_ids:
                    console.print(
                        "[yellow]lighterpack:[/yellow] no list IDs provided — "
                        "pass them with [bold]--lp-ids <ID>[/bold]\n"
                        "  Find the ID in a share URL: lighterpack.com/r/[bold]<ID>[/bold]"
                    )
                    continue
                items = asyncio.run(LighterPackScraper(list_ids=lp_ids).scrape())
            elif source == "rei":
                items = asyncio.run(REIScraper().scrape())
            elif source == "outdoorgearlab":
                items = asyncio.run(OutdoorGearLabScraper().scrape())
            else:
                console.print(f"[red]Unknown source:[/red] {source}")
                continue

        valid = [i.to_dict() for i in items if i.weight_g > 0]
        count = db.upsert_items(valid)
        total += count
        console.print(f"[green]✓[/green] {source}: {count} items upserted")

    console.print(f"\n[bold]Total:[/bold] {total} items in database")


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

@app.command()
def query(
    message: str = typer.Argument(..., help="Natural language gear query."),
):
    """Ask the AI agent a free-form gear question."""
    from agent.agent import run_query_sync

    _init_db()
    with console.status("Thinking…"):
        result = run_query_sync(message)
    console.print(result)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@app.command()
def search(
    q: str = typer.Argument(..., help="Search query."),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results."),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
):
    """Semantic similarity search (no LLM, raw vector results)."""
    from db import operations as db

    _init_db()
    results = db.query_similar(q, top_k=top_k, category=category)
    _print_gear_table(results)


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

@app.command()
def compare(
    item_ids: list[str] = typer.Argument(..., help="Two or more item IDs to compare."),
):
    """Compare gear items side by side."""
    from db import operations as db

    _init_db()
    items = db.get_by_ids(item_ids)
    if not items:
        console.print("[red]No items found.[/red]")
        raise typer.Exit(1)
    _print_gear_table(items, show_reviews=True)


# ---------------------------------------------------------------------------
# kit
# ---------------------------------------------------------------------------

@app.command()
def kit(
    base_weight: Optional[float] = typer.Option(
        None, "--base-weight", "-w", help="Target base weight in grams."
    ),
    budget: Optional[float] = typer.Option(
        None, "--budget", "-b", help="Max budget in USD."
    ),
    style: Optional[str] = typer.Option(
        None, "--style", help="Kit style: ultralight, budget, comfort."
    ),
):
    """Build a complete ultralight kit within weight/budget constraints."""
    from agent.tools import run_build_kit

    _init_db()
    with console.status("Building kit…"):
        raw = run_build_kit(
            target_base_weight_g=base_weight,
            budget_usd=budget,
            style=style,
        )
    data = json.loads(raw)

    table = Table(title="Ultralight Kit", show_lines=True)
    table.add_column("Category", style="bold cyan")
    table.add_column("Item")
    table.add_column("Brand")
    table.add_column("Weight (g)", justify="right")
    table.add_column("Price ($)", justify="right")

    for cat, item in data.get("kit", {}).items():
        table.add_row(
            cat,
            item.get("name", "-"),
            item.get("brand", "-"),
            str(item.get("weight_g", "-")),
            str(item.get("price_usd", "-")),
        )

    console.print(table)
    console.print(
        f"\n[bold]Total weight:[/bold] {data['total_weight_g']}g "
        f"({data['total_weight_lbs']} lbs)"
    )
    console.print(f"[bold]Total cost:[/bold] ${data['total_cost_usd']}")
    missing = data.get("categories_missing", [])
    if missing:
        console.print(f"[yellow]No items found for:[/yellow] {', '.join(missing)}")


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------

@app.command(name="filter")
def filter_gear(
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    max_weight: Optional[float] = typer.Option(
        None, "--max-weight", "-w", help="Max weight in grams."
    ),
    max_price: Optional[float] = typer.Option(
        None, "--max-price", "-p", help="Max price in USD."
    ),
    rank_by: str = typer.Option(
        "weight_g", "--rank-by", help="Sort by: weight_g, price_usd, value_rating."
    ),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """Filter and rank gear by category, weight, or price."""
    from db import operations as db

    _init_db()
    results = db.filter_and_rank(
        category=category,
        max_weight_g=max_weight,
        max_price_usd=max_price,
        rank_by=rank_by,
        limit=limit,
    )
    _print_gear_table(results)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_gear(
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List all gear items in the database."""
    from db import operations as db

    _init_db()
    items = db.list_items(category=category, limit=limit)
    console.print(f"[bold]{db.item_count()}[/bold] total items in DB")
    _print_gear_table(items)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start the FastAPI development server."""
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_gear_table(
    items: list[dict], show_reviews: bool = False
) -> None:
    if not items:
        console.print("[yellow]No items found.[/yellow]")
        return

    table = Table(show_lines=False, highlight=True)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name")
    table.add_column("Brand")
    table.add_column("Category")
    table.add_column("Weight (g)", justify="right")
    table.add_column("Price ($)", justify="right")
    table.add_column("Val ($/g)", justify="right")
    if show_reviews:
        table.add_column("Notes")

    for item in items:
        row = [
            item.get("id", "-"),
            item.get("name", "-"),
            item.get("brand", "-"),
            item.get("category", "-"),
            str(item.get("weight_g") or "-"),
            str(item.get("price_usd") or "-"),
            str(round(item["value_rating"], 3)) if item.get("value_rating") else "-",
        ]
        if show_reviews:
            row.append((item.get("reviews") or "")[:60])
        table.add_row(*row)

    console.print(table)


if __name__ == "__main__":
    app()
