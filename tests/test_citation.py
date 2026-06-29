"""Tests for citation extraction / normalization / verification."""

from app.guardrails.citation import (
    extract_citations,
    normalize_article,
    verify_citations,
)


def test_extract_both_numbering_forms():
    text = "This breaches Article 33.3 and Article B1.4.2, see also Article 30.3(e)."
    cites = extract_citations(text)
    assert "33.3" in cites
    assert "B1.4.2" in cites
    assert any("30.3" in c for c in cites)


def test_normalize_strips_section_prefix():
    assert normalize_article("B33.3") == "33.3"
    assert normalize_article("33.3") == "33.3"
    assert normalize_article("B1.4.2") == "1.4.2"
    assert normalize_article(" 30.3(e) ") == "30.3(e)"


def test_verify_matches_across_schemes():
    # Answer cites plain 33.3; retrieved docs only have the B-prefixed form.
    answer = "The penalty follows from Article 33.3."
    verified, unverified = verify_citations(answer, retrieved_article_ids=["B33.3", "55.15"])
    assert verified == ["33.3"]
    assert unverified == []


def test_verify_flags_hallucinated_citation():
    answer = "See Article 99.9 which does not exist in context."
    verified, unverified = verify_citations(answer, retrieved_article_ids=["33.3", "55.15"])
    assert verified == []
    assert unverified == ["99.9"]
