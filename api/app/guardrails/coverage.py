"""Refuse-on-low-coverage decision logic for the grade node.

Centralizes the grade-conditional edge so the graph and tests share one rule:

- grade >= pass_threshold           -> generate
- attempts exhausted:
      grade >= refuse_threshold     -> generate (best effort)
      else                          -> refuse
- otherwise                         -> rewrite (try again)
"""

from __future__ import annotations

from typing import Literal

from app.config import Settings

Decision = Literal["generate", "rewrite", "refuse"]

REFUSAL_MESSAGE = (
    "I couldn't find a governing FIA regulation or steward decision that clearly "
    "covers this, so I won't guess. Try naming the specific incident, car number, "
    "or rule area (e.g. unsafe release, track limits, causing a collision)."
)


def coverage_decision(grade: float, attempts: int, settings: Settings) -> Decision:
    if grade >= settings.grade_pass_threshold:
        return "generate"
    if attempts >= settings.max_retrieval_attempts:
        return "generate" if grade >= settings.grade_refuse_threshold else "refuse"
    return "rewrite"
