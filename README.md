# Ultralight Frenzy

Agentic RAG app for ultralight backpacking gear. Scrapers collect gear data from
specialty brands and community lists into a ChromaDB vector database. A Claude-powered
agent answers natural-language queries using semantic search tools.

```
gear query 'lightest sub-1kg shelter under $400'
```
```
The Durston X-Mid Pro 2 weighs 454g (1 lb 0 oz) and retails for $375. It uses DCF
(Dyneema Composite Fabric) and pitches with trekking poles — no tent poles needed.
Closest alternative is the Zpacks Duplex at 368g but $649...
```

---

## How It Works

### RAG Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  INGESTION (offline)                                        │
│                                                             │
│  Scrapers  ──►  GearItem  ──►  ChromaDB                     │
│  (LighterPack,     │          ┌──────────────┐              │
│   Shopify,         │          │ embed text   │              │
│   OGL)             │          │ store metadata│              │
│                    │          │ cosine index  │              │
│                    └─────────►└──────────────┘              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  QUERY (online)                                             │
│                                                             │
│  User question                                              │
│       │                                                     │
│       ▼                                                     │
│  Claude agent ──► tool_use: semantic_search("...")          │
│       │                │                                    │
│       │                ▼                                    │
│       │         ChromaDB: embed query                       │
│       │         cosine similarity search                    │
│       │         return top-k items + scores                 │
│       │                │                                    │
│       ◄────────────────┘                                    │
│       │                                                     │
│  Claude reasons over results, may call more tools           │
│  (compare_items, filter_and_rank, build_kit)                │
│       │                                                     │
│       ▼                                                     │
│  Natural language answer with specific weights / prices     │
└─────────────────────────────────────────────────────────────┘
```

### The Agent Loop

The agent (`agent/agent.py`) runs a tool-call loop with up to 10 iterations per turn:

1. Claude receives the user message and a system prompt establishing its role
2. Claude calls one or more tools (`tool_use` stop reason)
3. Tools execute against ChromaDB and return JSON results
4. Results are fed back as `tool_result` messages
5. Claude calls more tools or produces a final text answer (`end_turn`)

Streaming is supported: `stream_chat_turn` yields text deltas via
`client.messages.stream()`. Tool-call iterations cause a brief pause between streamed
segments while tools execute.

**Available tools:**

| Tool | What it does |
|---|---|
| `semantic_search` | Embed query → cosine similarity search, optional category filter |
| `filter_and_rank` | Metadata filter by weight/price/category, sort by any scalar field |
| `compare_items` | Side-by-side comparison with weight/price delta computation |
| `build_kit` | Allocate weight/budget across 7 categories, pick best item per category |

### The Vector Database

ChromaDB stores each gear item as:

- **Document** (embedded): concatenated text of name + brand + category + description +
  reviews + material + specs JSON. This is what semantic search runs against.
- **Metadata** (filterable): scalar fields — weight_g, price_usd, category, brand, etc.
  Used for `WHERE` clauses in `filter_and_rank`.

Embeddings use `all-MiniLM-L6-v2` via ONNX (no PyTorch required). The index metric is
cosine similarity. ChromaDB runs either as a local persistent file (dev) or as an HTTP
server sidecar (Docker/production), controlled by `CHROMA_HOST` env var.

---

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY
docker compose up --build     # first run — builds image, downloads Chromium + ONNX model
```

Then in a second terminal:

```bash
# Ingest gear data
docker compose exec api gear discover --ingest        # find + ingest LighterPack lists from Reddit
docker compose exec api gear ingest --sources shopify # scrape Zpacks, Katabatic, Durston, etc.

# Query
docker compose exec api gear query 'lightest 3-season tent'
docker compose exec api gear chat                     # interactive multi-turn

# Browse
docker compose exec api gear list
docker compose exec api gear filter --category shelter --max-weight 800
```

API docs: http://localhost:8000/docs

### Local (no Docker)

```bash
uv sync
uv run gear ingest --sources lighterpack --lp-ids <ID>
uv run gear query 'lightest tent under 500g'
```

Requires Python 3.11–3.12. On Intel Mac: installs ONNX Runtime instead of PyTorch
(no wheels exist for torch>=2.4 on x86_64 Mac).

---

## Data Sources

| Source | Method | Notes |
|---|---|---|
| **LighterPack** | HTTP + BeautifulSoup | Most reliable. Parses weight from `input.lpMG[value]` (milligrams). Requires list IDs. |
| **Shopify brands** | `/products.json` API | Zpacks, Katabatic, Gossamer Gear, Six Moon Designs, Durston, Hyperlite. Falls back to parsing weight from product description if variant weight fields are empty. |
| **OutdoorGearLab** | HTTP + BeautifulSoup | Spec table parsing via `<th>/<td>` pairs. |
| **LighterPack discovery** | Reddit JSON API | `gear discover` searches r/ultralight for shared list URLs. |

REI is available (`--sources rei`) but blocked by Akamai bot detection on datacenter IPs.

### Finding LighterPack list IDs

```bash
# Discover IDs from Reddit and print them
gear discover

# Discover and ingest in one step
gear discover --ingest

# Search further back in time
gear discover --time all
```

IDs are the short code in any public share URL: `lighterpack.com/r/<ID>`

---

## CLI Reference

```bash
gear ingest [--sources SOURCE...] [--lp-ids ID...]   # scrape and store
gear query 'question'                                 # single-turn agent query
gear chat                                             # interactive multi-turn chat
gear discover [--time FILTER] [--ingest]              # find LighterPack list IDs
gear search 'query' [--top-k N] [--category CAT]      # raw vector search, no LLM
gear filter [--category CAT] [--max-weight G] [--max-price USD] [--rank-by FIELD]
gear list [--category CAT] [--limit N]
gear compare ITEM_ID ITEM_ID [...]
gear kit [--base-weight G] [--budget USD] [--style ultralight|budget|comfort]
gear serve [--host HOST] [--port PORT]
```

**Shell quoting:** use single quotes for queries containing `$`:
```bash
gear query 'lightest tent under $400'   # correct — $400 is not expanded
gear query "lightest tent under $400"   # wrong — shell eats $400
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness check, returns item count |
| `POST` | `/chat` | Stateless chat (client passes history each turn) |
| `POST` | `/chat/stream` | Stateless streaming chat (SSE) |
| `POST` | `/chat/sessions` | Create server-managed session |
| `POST` | `/chat/sessions/{id}` | Send message in session |
| `POST` | `/chat/sessions/{id}/stream` | Streaming session chat (SSE) |
| `POST` | `/ingest/scrape` | Trigger scrapers (requires `X-API-Key`) |
| `POST` | `/agent/query` | Single-turn query (requires `X-API-Key`) |
| `DELETE` | `/gear/{id}` | Delete item (requires `X-API-Key`) |

SSE streaming format: `data: <delta>\n\n` … `data: [DONE]\n\n`

Full interactive docs at `http://localhost:8000/docs`.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `CHROMA_HOST` | unset | Set to use HTTP ChromaDB (Docker sets this to `chroma`) |
| `CHROMA_PORT` | `8000` | ChromaDB HTTP port |
| `CHROMA_PERSIST_PATH` | `./data/chroma` | Local file path when `CHROMA_HOST` is unset |
| `API_KEY` | unset | `X-API-Key` value for protected endpoints; skipped if unset |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `SESSION_TTL_SECONDS` | `3600` | Server-side chat session expiry |

---

## Development

```bash
# Run tests
uv run --extra dev pytest tests/ -v

# Code changes — no rebuild needed (source is volume-mounted)
docker compose restart api

# Rebuild only after pyproject.toml or Dockerfile changes
docker compose up --build

# Inspect a LighterPack page structure
gear debug-lp <LIST_ID>
```

### Project Layout

```
agent/          Claude agentic loop + tool definitions
app/            FastAPI application (routers, schemas, dependencies)
cli/            Typer CLI entry point
db/             ChromaDB client, embedding function, operations
scrapers/       Scraper implementations + GearItem dataclass
  configs/      Shopify store configurations
tests/          Pytest unit tests
```

---

## Architecture Notes

**Embeddings without PyTorch.** `sentence-transformers>=3.0` requires `torch>=2.4`,
which has no wheels for Intel Mac x86_64. ChromaDB's built-in `DefaultEmbeddingFunction`
runs the same `all-MiniLM-L6-v2` model via ONNX Runtime — identical vectors, no torch.

**ChromaDB dual mode.** `db/client.py` checks `CHROMA_HOST`. If set, connects via
`HttpClient` to a remote/sidecar instance. If unset, uses `PersistentClient` (local
file). Docker Compose sets `CHROMA_HOST=chroma`.

**Streaming and tool calls.** The streaming path (`stream_chat_turn`) yields text deltas
immediately but must pause when Claude calls a tool: tools execute synchronously, then a
new stream starts for the next iteration. This produces a brief stutter at tool-call
boundaries. A full Agent SDK migration (which interleaves tool execution with streaming)
is a planned improvement.

**Shopify weight fallback.** Most ultralight Shopify stores don't populate the variant
weight field. `ShopifyScraper` falls back to `parse_weight_g()` on the product
description HTML, which catches weight specs published as free text (e.g. "Weight: 454g").
