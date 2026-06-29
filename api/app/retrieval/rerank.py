"""Optional cross-encoder reranker (ablation-only).

Disabled by default. When ``RERANK_ENABLED`` is set, lazily loads
``bge-reranker-base`` (pulls torch) and re-scores the fused candidates. Kept out
of the default API image / CI; intended for local ablation runs only.
"""

from __future__ import annotations

from app.config import Settings


class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, docs: list[dict], top_n: int) -> list[dict]:
        if not docs:
            return docs
        pairs = [(query, d["content"]) for d in docs]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(docs, scores, strict=True), key=lambda ds: ds[1], reverse=True)
        return [d for d, _ in ranked[:top_n]]


def get_reranker(settings: Settings) -> CrossEncoderReranker | None:
    if not settings.rerank_enabled:
        return None
    return CrossEncoderReranker()
