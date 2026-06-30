"""Deterministic tests for Reciprocal Rank Fusion + Grand Prix detection."""

from app.retrieval.hybrid import detect_grand_prix, rrf_fuse


def test_detect_grand_prix():
    assert detect_grand_prix("Who won the 2025 Abu Dhabi Grand Prix?") == "abudhabi"
    assert detect_grand_prix("what happened in Austrian GP qualifying?") == "austrian"
    assert detect_grand_prix("who took pole at Silverstone?") == "british"
    assert detect_grand_prix("podium at Las Vegas?") == "lasvegas"
    # No GP named -> None (so global rule questions aren't filtered to a race).
    assert detect_grand_prix("What is the penalty for an unsafe pit release?") is None


def test_rrf_rewards_agreement():
    # id 1 ranks top in both lists -> should win the fusion.
    dense = [(1, 0.9), (2, 0.8), (3, 0.7)]
    sparse = [(1, 5.0), (3, 4.0), (2, 3.0)]
    fused = rrf_fuse([dense, sparse])
    assert fused[0][0] == 1


def test_rrf_uses_rank_not_score():
    # Sparse has a huge raw score for id 2, but dense ranks id 1 first in both
    # senses; RRF ignores magnitude, so consistent high rank wins.
    a = [(1, 0.01), (2, 0.001)]
    b = [(1, 0.02), (2, 1000.0)]
    fused = dict(rrf_fuse([a, b]))
    assert fused[1] > fused[2]


def test_rrf_unions_ids():
    a = [(1, 1.0), (2, 1.0)]
    b = [(3, 1.0)]
    ids = {cid for cid, _ in rrf_fuse([a, b])}
    assert ids == {1, 2, 3}


def test_rrf_k_dampens_rank_gap():
    a = [(i, 0.0) for i in range(100)]
    # With a large rrf_k, rank differences matter less (scores compress).
    small = dict(rrf_fuse([a], rrf_k=1))
    large = dict(rrf_fuse([a], rrf_k=1000))
    assert (small[0] - small[50]) > (large[0] - large[50])
