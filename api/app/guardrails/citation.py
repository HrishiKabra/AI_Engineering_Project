"""Citation extraction, normalization, and verification.

Handles the 2025-decisions-vs-2026-regs numbering mismatch: the 2026 Sporting
Regulations number articles with a section-letter prefix (``B1.4.2``) while 2025
steward decisions cite the prior plain numbering (``33.3``, ``55.15``,
``30.3(e)``). :func:`normalize_article` collapses both forms so they compare
equal, and :func:`verify_citations` accepts a citation that matches *either* a
retrieved regulation chunk *or* a retrieved steward decision (a decision is
ground truth for the article it itself cites).
"""

from __future__ import annotations

import re

# "Article 33.3", "Article B1.4.2", "Article 30.3(e)", "[Article 55.15]".
# Requires a dotted number (so plain ISC refs like "Article 15" / "Article 2 d)"
# are skipped in favour of the sporting-regulation article) plus an optional
# parenthetical sub-item; the dot requirement also prevents grabbing the next word.
_ARTICLE_RE = re.compile(
    r"\bArticle\s+(B?\d{1,3}(?:\.\d+)+(?:\([a-z0-9]{1,3}\))?)",
    re.IGNORECASE,
)
# Bare section ids used in the penalty-points table cells, e.g. "30.3(e)", "23.6".
_BARE_RE = re.compile(r"\b(B?\d{1,3}(?:\.\d+)+(?:\([a-z]\))?)")


def normalize_article(article: str) -> str:
    """Canonical form for cross-scheme matching: drop the section-letter prefix,
    strip spaces, lowercase. ``B33.3`` and ``33.3`` -> ``33.3``; ``30.3(e)`` kept."""
    a = article.strip().lower().replace(" ", "")
    a = re.sub(r"^b(?=\d)", "", a)  # drop a leading section letter immediately before a digit
    a = a.rstrip(".,;")
    return a


def extract_citations(text: str) -> list[str]:
    """Pull article references that follow the word 'Article'. Returns raw tokens
    (de-duplicated, order preserved)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _ARTICLE_RE.finditer(text or ""):
        tok = m.group(1).strip().rstrip(".,;")
        key = normalize_article(tok)
        if key and key not in seen:
            seen.add(key)
            out.append(tok)
    return out


def first_article(text: str) -> str | None:
    """First article id cited in a span (used to tag decision/penalty chunks)."""
    cites = extract_citations(text)
    if cites:
        return cites[0]
    m = _BARE_RE.search(text or "")
    return m.group(1) if m else None


def verify_citations(
    answer: str, retrieved_article_ids: list[str | None]
) -> tuple[list[str], list[str]]:
    """Split an answer's cited articles into (verified, unverified) against the
    normalized article ids of the retrieved documents."""
    available = {normalize_article(a) for a in retrieved_article_ids if a}
    verified: list[str] = []
    unverified: list[str] = []
    for cite in extract_citations(answer):
        if normalize_article(cite) in available:
            verified.append(cite)
        else:
            unverified.append(cite)
    return verified, unverified
