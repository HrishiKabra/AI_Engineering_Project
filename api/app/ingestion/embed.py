"""Embedding backends behind a common interface.

OpenAI ``text-embedding-3-small`` (1536-dim) is the default. BGE
(``BAAI/bge-base-en-v1.5``, 768-dim) is a lazy, ablation-only backend so the
default API image stays slim (no torch). Each backend names its own DB table so
the two dimensionalities coexist for the ablation grid.
"""

from __future__ import annotations

from typing import Protocol

from openai import OpenAI

from app.config import Settings


class Embedder(Protocol):
    name: str
    dim: int
    table: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    name = "openai"
    dim = 1536
    table = "emb_openai_1536"
    model = "text-embedding-3-small"

    def __init__(self) -> None:
        self._client = OpenAI()
        self.embed_tokens = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        # The API accepts up to 2048 inputs per request; batch conservatively.
        for i in range(0, len(texts), 256):
            batch = texts[i : i + 256]
            resp = self._client.embeddings.create(model=self.model, input=batch)
            out.extend(d.embedding for d in resp.data)
            self.embed_tokens += resp.usage.total_tokens
        return out


class BGEEmbedder:
    name = "bge"
    dim = 768
    table = "emb_bge_768"

    def __init__(self) -> None:
        # Lazy import: sentence-transformers + torch are heavy and ablation-only.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer("BAAI/bge-base-en-v1.5")
        self.embed_tokens = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vecs]


def get_embedder(settings: Settings) -> Embedder:
    if settings.embed_model == "bge":
        return BGEEmbedder()
    return OpenAIEmbedder()
