"""Runtime context passed to agent nodes (not part of serializable state)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings


@dataclass
class AgentContext:
    conn: Any                 # live psycopg connection (borrowed from the pool)
    llm: Any                  # ChatLLM
    embedder: Any             # Embedder
    settings: Settings
    reranker: Any = None


def ctx_from_config(config: dict) -> AgentContext:
    return config["configurable"]["ctx"]
