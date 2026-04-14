"""Singleton ChromaDB client and collection setup.

Client mode is controlled by environment variables:
  CHROMA_HOST  — if set, connects via HTTP to a ChromaDB server (Docker / cloud)
  CHROMA_PORT  — port for the HTTP server (default: 8000)
  CHROMA_PERSIST_PATH — local file path when NOT using HTTP mode (default: ./data/chroma)
"""

from __future__ import annotations

import os

import chromadb
from chromadb import Collection

from db.embeddings import LocalEmbeddingFunction

_client: chromadb.ClientAPI | None = None
_collection: Collection | None = None


def get_client(persist_path: str = "./data/chroma") -> chromadb.ClientAPI:
    global _client
    if _client is None:
        host = os.environ.get("CHROMA_HOST")
        if host:
            port = int(os.environ.get("CHROMA_PORT", "8000"))
            _client = chromadb.HttpClient(host=host, port=port)
        else:
            _client = chromadb.PersistentClient(path=persist_path)
    return _client


def get_collection(
    persist_path: str = "./data/chroma",
    collection_name: str = "gear",
    embedding_model: str = "all-MiniLM-L6-v2",
) -> Collection:
    global _collection
    if _collection is None:
        client = get_client(persist_path)
        ef = LocalEmbeddingFunction(model_name=embedding_model)
        _collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def reset_singletons() -> None:
    """Reset singletons — used in tests."""
    global _client, _collection
    _client = None
    _collection = None
