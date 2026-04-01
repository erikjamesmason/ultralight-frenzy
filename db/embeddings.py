"""Local sentence-transformers embedding function for ChromaDB."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chromadb import EmbeddingFunction, Documents, Embeddings

if TYPE_CHECKING:
    pass

_model = None


def _get_model(model_name: str):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
    return _model


class LocalEmbeddingFunction(EmbeddingFunction):
    """Wraps sentence-transformers for use as a ChromaDB embedding function."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        model = _get_model(self.model_name)
        embeddings = model.encode(list(input), show_progress_bar=False)
        return embeddings.tolist()
