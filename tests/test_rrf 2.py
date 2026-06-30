"""Deterministic tests for Reciprocal Rank Fusion."""

from app.retrieval.hybrid import rrf_fuse


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
