"""FastAPI dependencies. ``get_ctx`` is overridden in tests via dependency_overrides."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from app.agent.context import AgentContext
from app.config import get_settings
from app.db.pool import get_conn
from app.ingestion.embed import Embedder, get_embedder
from app.llm.client import OpenAIChat


@lru_cache
def _llm() -> OpenAIChat:
    s = get_settings()
    return OpenAIChat(model=s.chat_model, temperature=s.temperature, max_tokens=s.max_tokens)


@lru_cache
def _embedder() -> Embedder:
    return get_embedder(get_settings())


@lru_cache
def _reranker():
    from app.retrieval.rerank import get_reranker

    return get_reranker(get_settings())


def get_ctx() -> Iterator[AgentContext]:
    """Yield a per-request agent context with a pooled DB connection."""
    settings = get_settings()
    with get_conn() as conn:
        yield AgentContext(
            conn=conn,
            llm=_llm(),
            embedder=_embedder(),
            settings=settings,
            reranker=_reranker(),
        )
