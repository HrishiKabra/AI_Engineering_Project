"""Ablation grid: vary one retrieval knob at a time and measure the effect.

The grid is defined over four axes (chunking x embedding x retrieval x top_k). The
two query-time axes (retrieval mode, top_k) re-run against the existing index and
are swept here by default — cheap, no re-ingest. The chunking and embedding axes
change the ingested vectors (re-ingest / BGE+torch) and are declared in
``FULL_GRID`` for reference but not run in the default grid; see README.

    python -m eval.ablation                      # retrieval x top_k over smoke set
    python -m eval.ablation --subset full --k-list 3,5,10
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from app.agent.context import AgentContext
from app.config import get_settings
from app.db.pool import get_conn
from app.ingestion.embed import get_embedder
from app.llm.client import OpenAIChat
from eval.run_eval import RESULTS_DIR, _load, evaluate

EVAL_DIR = Path(__file__).parent

# Query-time axes actually swept (no re-ingest needed).
RETRIEVAL_MODES = ["sparse", "dense", "hybrid"]
TOP_K = [3, 5, 10]

# Declared full design (chunking/embedding require re-ingest / BGE — see README).
FULL_GRID = {
    "chunking": ["fixed512", "structure", "parent_child"],
    "embedding": ["openai", "bge"],
    "retrieval": RETRIEVAL_MODES,
    "top_k": TOP_K,
}


def run_grid(subset: str | None, modes: list[str], ks: list[int]) -> list[dict]:
    items = _load(EVAL_DIR / "golden.jsonl")
    unans = _load(EVAL_DIR / "unanswerable.jsonl")
    if subset == "smoke":
        items = [i for i in items if i.get("smoke")]
        unans = [i for i in unans if i.get("smoke")]

    s = get_settings()
    cells: list[dict] = []
    with get_conn() as conn:
        ctx = AgentContext(
            conn=conn,
            llm=OpenAIChat(model=s.chat_model, temperature=0.0, max_tokens=s.max_tokens),
            embedder=get_embedder(s),
            settings=s,
        )
        for mode, k in itertools.product(modes, ks):
            config = {"mode": mode, "top_k": k, "candidate_k": max(20, k * 4)}
            result = evaluate(items, unans, ctx, config=config, k=k)
            agg = result["aggregate"]
            label = f"{mode}/k={k}"
            print(
                f"{label:>14}  coverage={agg['citation_coverage']}  "
                f"recall={agg['recall@k']}  ndcg={agg['ndcg@k']}  cost=${agg['avg_cost_usd']}"
            )
            cells.append({"label": label, "mode": mode, "top_k": k, **agg})
    return cells


def _svg_bar_chart(cells: list[dict], metric: str = "citation_coverage") -> str:
    """Hand-rolled SVG bar chart (no plotting deps) for embedding in the README."""
    w, h, pad, bottom = 720, 320, 40, 60
    bar_area = h - pad - bottom
    n = len(cells)
    bw = (w - 2 * pad) / max(n, 1) * 0.7
    gap = (w - 2 * pad) / max(n, 1) * 0.3
    vmax = max([c.get(metric) or 0 for c in cells] + [0.001])
    bars = []
    for i, c in enumerate(cells):
        v = c.get(metric) or 0
        x = pad + i * (bw + gap)
        bh = bar_area * (v / vmax)
        y = pad + (bar_area - bh)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="#ff2e63" rx="3"/>'
            f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" font-size="11" text-anchor="middle" fill="#333">{v:.2f}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{h - bottom + 18:.1f}" font-size="10" text-anchor="middle" '
            f'fill="#555" transform="rotate(35 {x + bw / 2:.1f} {h - bottom + 18:.1f})">{c["label"]}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="system-ui,sans-serif">'
        f'<rect width="{w}" height="{h}" fill="#fafafa"/>'
        f'<text x="{pad}" y="24" font-size="14" font-weight="600" fill="#222">'
        f'{metric.replace("_", " ")} by retrieval config</text>'
        + "".join(bars)
        + "</svg>"
    )


def _balance(c: dict) -> float:
    """Rank configs by the harmonic mean of coverage and recall, so a config can't
    win by refusing everything it can't ground (which inflates coverage)."""
    cov = c.get("citation_coverage") or 0.0
    rec = c.get("recall@k") or 0.0
    return 0.0 if (cov + rec) == 0 else 2 * cov * rec / (cov + rec)


def _summary_md(cells: list[dict]) -> str:
    best = max(cells, key=_balance)
    head = "| config | citation_coverage | recall@k | ndcg@k | citation_correctness | refusal | $/q |\n"
    head += "|---|---|---|---|---|---|---|\n"
    rows = "".join(
        f"| {c['label']} | {c['citation_coverage']} | {c['recall@k']} | {c['ndcg@k']} | "
        f"{c['citation_correctness']} | {c['refusal_correctness']} | {c['avg_cost_usd']} |\n"
        for c in cells
    )
    cov_b = best["citation_coverage"]
    notes = (
        f"\n**Best balanced config:** `{best['label']}` — citation_coverage "
        f"**{cov_b}**, recall@k **{best['recall@k']}** (harmonic-mean ranked, so a "
        f"config can't win by over-refusing).\n\n"
        "**Read coverage alongside recall.** A sparse-only retriever can post a high "
        "citation_coverage while retrieving few relevant articles (low recall): it "
        "answers only the questions it can ground and refuses the rest. Coverage is "
        "only meaningful when recall is healthy.\n\n"
        "Increasing top-k raises both recall and coverage (more chances to surface the "
        "governing article) at a modest latency/cost increase. Axes swept: retrieval "
        "mode × top-k (query-time). The chunking and embedding axes are defined in "
        "`FULL_GRID` but require re-ingestion / a local BGE model and are not part of "
        "this run.\n"
    )
    return "# Ablation results\n\n" + head + rows + notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", choices=["smoke", "full"], default="smoke")
    ap.add_argument("--modes", default=",".join(RETRIEVAL_MODES))
    ap.add_argument("--k-list", default=",".join(map(str, TOP_K)))
    args = ap.parse_args()

    modes = args.modes.split(",")
    ks = [int(x) for x in args.k_list.split(",")]
    cells = run_grid(None if args.subset == "full" else "smoke", modes, ks)

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "grid.json").write_text(json.dumps(cells, indent=2))
    (RESULTS_DIR / "ablation.svg").write_text(_svg_bar_chart(cells))
    (RESULTS_DIR / "summary.md").write_text(_summary_md(cells))
    print(f"\nwrote grid.json, ablation.svg, summary.md to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
