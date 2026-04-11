"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import chat, gear, ingest, search

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up ChromaDB + embedding model on startup
    from db.client import get_collection
    get_collection(
        persist_path=os.environ.get("CHROMA_PERSIST_PATH", "./data/chroma"),
        collection_name=os.environ.get("CHROMA_COLLECTION", "gear"),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
    )
    yield


app = FastAPI(
    title="Ultralight Frenzy",
    description="Agentic RAG for ultralight backpacking gear",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat.router)
app.include_router(gear.router)
app.include_router(search.router)
app.include_router(ingest.router)


@app.get("/health")
def health():
    from db import operations as db
    return {"status": "ok", "items_in_db": db.item_count()}
