"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    stream: bool = True
    config: dict | None = None  # per-request overrides: mode, top_k, table, filters


class Citation(BaseModel):
    article_id: str
    doc: str = ""
    doc_subtype: str | None = None
    snippet: str = ""
    verified: bool = True


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    route: str = ""
    grade: float = 0.0
    attempts: int = 0
    verified: bool = False
    refused: bool = False
    latency_ms: int = 0
    ttft_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embed_tokens: int = 0
    cost_usd: float = 0.0
