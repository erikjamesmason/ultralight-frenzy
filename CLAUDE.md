# Ultralight Frenzy — Claude Context

## What this project is
FastAPI + ChromaDB RAG app for ultralight backpacking gear. Scrapers collect gear data into a
vector DB; a Claude agentic loop answers natural-language queries using semantic search tools.

## Development workflow

### Docker (primary)
```bash
docker-compose up --build     # first run, or after pyproject.toml changes
docker-compose restart gear   # after Python code changes (no rebuild needed — source is volume-mounted)
docker-compose exec gear uv run gear <command>   # run CLI commands inside container
```

### Local (no Docker)
```bash
uv sync
uv run gear <command>
```
Note: local dev on Intel Mac (x86_64) requires the ONNX embedding path — see Architecture section.

## CLI commands
```bash
uv run gear ingest --sources lighterpack --lp-ids <ID>   # scrape and store
uv run gear query 'question here'                         # single-turn agent query
uv run gear chat                                          # multi-turn interactive chat
uv run gear search 'query'                                # raw vector search, no LLM
uv run gear list                                          # list all DB items
uv run gear filter --category shelter --max-weight 1000  # filter and rank
uv run gear debug-lp <ID>                                 # inspect LighterPack page structure
```

**Shell quoting:** always use single quotes for queries containing `$` (e.g. `'lightest tent under $400'`).
Double-quoted `$400` gets shell-expanded to empty string before the CLI sees it.

## Key environment variables
| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `API_KEY` | unset (auth skipped) | X-API-Key header value for protected endpoints |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `SESSION_TTL_SECONDS` | `3600` | Chat session expiry (seconds) |
| `CHROMA_HOST` | unset | Set to use HTTP ChromaDB server instead of local file |
| `CHROMA_PORT` | `8000` | ChromaDB HTTP server port |
| `CHROMA_PERSIST_PATH` | `./data/chroma` | Local file path (when CHROMA_HOST is unset) |

## API endpoints summary
- `POST /chat` — stateless chat (client passes history each turn)
- `POST /chat/stream` — stateless streaming chat (SSE, `data: delta\n\n` + `data: [DONE]\n\n`)
- `POST /chat/sessions` — create server-managed session
- `POST /chat/sessions/{id}` — send message in session
- `POST /chat/sessions/{id}/stream` — streaming version of session chat
- `POST /ingest/scrape` — trigger scrapers (requires `X-API-Key`)
- `POST /agent/query` — single-turn agent query (requires `X-API-Key`)
- `DELETE /gear/{id}` — delete item (requires `X-API-Key`)
- `GET /health` — liveness check with item count
- Full interactive docs at `http://localhost:8000/docs`

## Architecture decisions

### Embeddings: ONNX via ChromaDB DefaultEmbeddingFunction (no torch)
`sentence-transformers>=3.0` requires `torch>=2.4`, which has no wheels for Intel Mac x86_64.
We use `chromadb`'s built-in `DefaultEmbeddingFunction` (all-MiniLM-L6-v2 via onnxruntime) which
avoids torch entirely. The stored vectors are identical — ONNX vs PyTorch produce the same floats
for the same model. If running on Apple Silicon or Linux, torch+sentence-transformers works fine.

### ChromaDB: file vs HTTP mode
`db/client.py` checks `CHROMA_HOST` env var. If set → `chromadb.HttpClient` (Docker/cloud).
If unset → `chromadb.PersistentClient` (local file). Docker Compose sets `CHROMA_HOST=chroma`.

### Auth: optional API key
`app/dependencies.py` has `verify_api_key`. If `API_KEY` env var is unset, the check is skipped
(dev mode). Set it in `.env` before any public exposure.

### Streaming: hand-rolled SSE
`agent/agent.py::stream_chat_turn` is an async generator over `client.messages.stream()`.
Tool-call turns cause a brief pause (tools execute synchronously before the next stream starts).
Full Agent SDK migration (which eliminates the pause) is a planned follow-up sprint.

## Scraper notes
- **LighterPack**: most reliable — semantic class names, weight in `input.lpMG[value]` (milligrams).
  Requires user-supplied list IDs (`--lp-ids`).
- **REI**: tries JSON-LD `<script type="application/ld+json">` first (most reliable), falls back to
  HTML selectors. REI uses React so HTML selectors go stale frequently.
- **OutdoorGearLab**: spec tables parsed via `<th>/<td>` pairing. Brand extracted from element,
  then checked against `KNOWN_MULTIWORD_BRANDS` set before falling back to first word of name.

## Git
Active development branch: `claude/plan-gear-rag-app-l2sRz`
