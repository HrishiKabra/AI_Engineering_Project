"""Hand-written evaluation metrics.

Retrieval metrics compare retrieved article ids against a golden set's
``relevant_articles``. The headline metric, citation coverage, and citation
correctness are implemented here (not imported) because they are the core claim
the eval makes. All article comparisons go through ``normalize_article`` so the
2025/2026 numbering schemes match.
"""

from __future__ import annotations

import math
import re

from app.guardrails.citation import extract_citations, normalize_article

# A sentence makes a rule/penalty *claim* if it asserts a sanction or that a rule
# was breached. Kept to penalty/breach conclusions (not generic "must/shall/rule"
# prose) so coverage measures whether the answer grounds its rulings in a citation.
_CLAIM_RE = re.compile(
    r"\b(penalty|penalised|penalized|breach|infring|deleted|disqualif|reprimand|"
    r"drive[- ]?through|stop[- ]?and[- ]?go|grid (?:place|position) penalty|"
    r"time penalty|fine|sanction|prohibited)\b",
    re.IGNORECASE,
)
_CITE_IN_SENTENCE = re.compile(r"\bArticle\s+B?\d{1,3}(?:\.\d+)+", re.IGNORECASE)


def _norm_set(articles) -> set[str]:
    return {normalize_article(a) for a in articles if a}


def recall_at_k(retrieved_articles: list[str], relevant: list[str], k: int) -> float:
    rel = _norm_set(relevant)
    if not rel:
        return 0.0
    got = _norm_set(retrieved_articles[:k])
    return len(got & rel) / len(rel)


def precision_at_k(retrieved_articles: list[str], relevant: list[str], k: int) -> float:
    rel = _norm_set(relevant)
    topk = [normalize_article(a) for a in retrieved_articles[:k] if a]
    if not topk:
        return 0.0
    hits = sum(1 for a in topk if a in rel)
    return hits / len(topk)


def ndcg_at_k(retrieved_articles: list[str], relevant: list[str], k: int) -> float:
    rel = _norm_set(relevant)
    if not rel:
        return 0.0
    dcg = 0.0
    for i, a in enumerate([normalize_article(x) for x in retrieved_articles[:k]]):
        if a in rel:
            dcg += 1.0 / math.log2(i + 2)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), k)))
    return dcg / ideal if ideal else 0.0


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def citation_coverage(answer: str, citations: list[dict] | None = None) -> float | None:
    """Fraction of rule/penalty claim-sentences that carry a verifiable citation.

    Returns None when the answer makes no rule/penalty claims (e.g. a refusal),
    so such items can be excluded from the average rather than scored 0 or 1.
    """
    verified = {normalize_article(c["article_id"]) for c in (citations or []) if c.get("verified")}
    claims = [s for s in _sentences(answer) if _CLAIM_RE.search(s)]
    if not claims:
        return None
    supported = 0
    for s in claims:
        cited = {normalize_article(a) for a in extract_citations(s)}
        if cited & verified:
            supported += 1
    return supported / len(claims)


def citation_correctness(citations: list[dict], relevant: list[str]) -> float | None:
    """Of the articles the answer cites, the fraction that are in the golden set."""
    cited = _norm_set(c["article_id"] for c in (citations or []))
    if not cited:
        return None
    rel = _norm_set(relevant)
    return len(cited & rel) / len(cited)


def refusal_correctness(records: list[dict]) -> float:
    """Accuracy of the refuse/answer decision over a labeled set.

    Each record: {"expect_refusal": bool, "refused": bool}.
    """
    if not records:
        return 0.0
    correct = sum(1 for r in records if bool(r["expect_refusal"]) == bool(r["refused"]))
    return correct / len(records)
