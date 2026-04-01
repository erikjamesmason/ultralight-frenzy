"""Singleton ChromaDB client and collection setup."""

from __future__ import annotations

import chromadb
from chromadb import Collection

from db.embeddings import LocalEmbeddingFunction

_client: chromadb.ClientAPI | None = None
_collection: Collection | None = None


def get_client(persist_path: str = "./data/chroma") -> chromadb.ClientAPI:
    global _client
    if _client is None:
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
