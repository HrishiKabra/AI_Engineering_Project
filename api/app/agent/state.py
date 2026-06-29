"""Agent graph state."""

from __future__ import annotations

from typing import Literal, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    config: dict                 # per-request overrides: embed table, mode, top_k, candidate_k
    route: Literal["single_rule", "precedent", "out_of_scope"]
    query_text: str              # current (possibly rewritten) retrieval query
    docs: list[dict]             # expanded parent docs
    grade: float
    grade_missing: str
    attempts: int                # retrieval attempts (rewrite count)
    regens: int                  # generation regeneration count (citation loop)
    answer: str
    citations: list[dict]        # [{article_id, doc, snippet, verified}]
    verified: bool
    refused: bool
    usage: dict                  # accumulated tokens / model names
