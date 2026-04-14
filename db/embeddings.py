"""ChromaDB embedding function — uses the built-in ONNX default (no torch required)."""

from __future__ import annotations

from chromadb import EmbeddingFunction, Documents, Embeddings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as _DefaultEF


class LocalEmbeddingFunction(EmbeddingFunction):
    """
    Wraps chromadb's built-in DefaultEmbeddingFunction (all-MiniLM-L6-v2 via onnxruntime).

    No torch or sentence-transformers required — onnxruntime handles inference.
    The model_name parameter is accepted for API compatibility but the bundled
    ONNX model is always all-MiniLM-L6-v2.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._ef = _DefaultEF()

    def __call__(self, input: Documents) -> Embeddings:
        return self._ef(input)
