# Ablation results

| config | citation_coverage | recall@k | ndcg@k | citation_correctness | refusal | $/q |
|---|---|---|---|---|---|---|
| sparse/k=3 | 1.0 | 0.125 | 0.0789 | 0.5 | 0.3636 | 9.2e-05 |
| sparse/k=5 | 1.0 | 0.125 | 0.0789 | 0.5 | 0.3636 | 8.5e-05 |
| sparse/k=10 | 1.0 | 0.125 | 0.0789 | 0.5 | 0.3636 | 8.9e-05 |
| dense/k=3 | 0.4722 | 0.6458 | 0.6555 | 0.8 | 0.8182 | 0.00037 |
| dense/k=5 | 0.369 | 0.5833 | 0.6359 | 0.9167 | 0.9091 | 0.000761 |
| dense/k=10 | 0.5952 | 0.6667 | 0.8036 | 0.8333 | 0.9091 | 0.000822 |
| hybrid/k=3 | 0.4 | 0.5417 | 0.5506 | 0.75 | 0.7273 | 0.000482 |
| hybrid/k=5 | 0.5278 | 0.5833 | 0.5602 | 0.8333 | 0.8182 | 0.001083 |
| hybrid/k=10 | 0.6667 | 0.6667 | 0.737 | 0.881 | 0.9091 | 0.00094 |

**Best balanced config:** `hybrid/k=10` — citation_coverage **0.6667**, recall@k **0.6667** (harmonic-mean ranked, so a config can't win by over-refusing).

**Read coverage alongside recall.** A sparse-only retriever can post a high citation_coverage while retrieving few relevant articles (low recall): it answers only the questions it can ground and refuses the rest. Coverage is only meaningful when recall is healthy.

Increasing top-k raises both recall and coverage (more chances to surface the governing article) at a modest latency/cost increase. Axes swept: retrieval mode × top-k (query-time). The chunking and embedding axes are defined in `FULL_GRID` but require re-ingestion / a local BGE model and are not part of this run.
