"""Evaluation harness entrypoint.

Runs the golden set (and the unanswerable set for refusal) through the live agent,
computes retrieval + citation + refusal metrics, optionally Ragas, and can gate a
build on a metric threshold.

    python -m eval.run_eval                                  # full eval
    python -m eval.run_eval --subset smoke --no-ragas        # fast, deterministic-ish
    python -m eval.run_eval --gate citation_coverage:0.80    # exit 1 if below
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

from app.agent.context import AgentContext
from app.agent.graph import run_agent
from app.config import get_settings
from app.db.pool import get_conn
from app.ingestion.embed import get_embedder
from app.llm.client import OpenAIChat
from app.llm.cost import total_cost
from eval import metrics as M

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _filter_subset(items: list[dict], subset: str | None) -> list[dict]:
    if subset == "smoke":
        return [i for i in items if i.get("smoke")]
    return items


def evaluate(
    items: list[dict],
    unanswerable: list[dict],
    ctx: AgentContext,
    config: dict | None = None,
    k: int = 5,
    collect_ragas: bool = False,
) -> dict:
    per_item: list[dict] = []
    ragas_records: list[dict] = []
    refusal_records: list[dict] = []
    total_cost_usd = 0.0

    for it in items + unanswerable:
        state = run_agent(ctx, it["question"], config)
        answer = state.get("answer", "")
        citations = state.get("citations", [])
        docs = state.get("docs", [])
        retrieved_articles = [d.get("article_id") for d in docs if d.get("article_id")]
        total_cost_usd += total_cost(state.get("usage", {}))

        refusal_records.append(
            {"expect_refusal": it.get("expect_refusal", False), "refused": bool(state.get("refused"))}
        )

        rec: dict = {"id": it["id"], "refused": bool(state.get("refused"))}
        if not it.get("expect_refusal"):
            relevant = it.get("relevant_articles", [])
            if relevant:
                rec["recall@k"] = M.recall_at_k(retrieved_articles, relevant, k)
                rec["precision@k"] = M.precision_at_k(retrieved_articles, relevant, k)
                rec["ndcg@k"] = M.ndcg_at_k(retrieved_articles, relevant, k)
                rec["citation_correctness"] = M.citation_correctness(citations, relevant)
            rec["citation_coverage"] = M.citation_coverage(answer, citations)
            if collect_ragas:
                ragas_records.append(
                    {
                        "question": it["question"],
                        "answer": answer,
                        "contexts": [d.get("snippet", "") for d in docs] or ["(none)"],
                        "reference": it.get("reference", answer),
                    }
                )
        per_item.append(rec)

    def _avg(key: str) -> float | None:
        vals = [r[key] for r in per_item if r.get(key) is not None]
        return round(mean(vals), 4) if vals else None

    agg = {
        "n_answerable": len(items),
        "n_unanswerable": len(unanswerable),
        "recall@k": _avg("recall@k"),
        "precision@k": _avg("precision@k"),
        "ndcg@k": _avg("ndcg@k"),
        "citation_coverage": _avg("citation_coverage"),
        "citation_correctness": _avg("citation_correctness"),
        "refusal_correctness": round(M.refusal_correctness(refusal_records), 4),
        "avg_cost_usd": round(total_cost_usd / max(len(per_item), 1), 6),
        "k": k,
        "config": config or {},
    }
    return {"aggregate": agg, "per_item": per_item, "_ragas_records": ragas_records}


def _build_ctx(conn) -> AgentContext:
    s = get_settings()
    return AgentContext(
        conn=conn,
        llm=OpenAIChat(model=s.chat_model, temperature=0.0, max_tokens=s.max_tokens),
        embedder=get_embedder(s),
        settings=s,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", choices=["smoke"], default=None)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--gate", default=None, help="metric:threshold, e.g. citation_coverage:0.80")
    ap.add_argument("--ragas", action="store_true")
    ap.add_argument("--no-ragas", dest="ragas", action="store_false")
    ap.add_argument("--out", default=None)
    ap.set_defaults(ragas=False)
    args = ap.parse_args()

    items = _filter_subset(_load(EVAL_DIR / "golden.jsonl"), args.subset)
    unans = _filter_subset(_load(EVAL_DIR / "unanswerable.jsonl"), args.subset)

    with get_conn() as conn:
        ctx = _build_ctx(conn)
        result = evaluate(items, unans, ctx, k=args.k, collect_ragas=args.ragas)

    agg = result["aggregate"]
    if args.ragas:
        from eval.ragas_eval import run_ragas

        agg["ragas"] = run_ragas(result["_ragas_records"])

    print(json.dumps(agg, indent=2))

    RESULTS_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else RESULTS_DIR / f"eval{'_smoke' if args.subset else ''}.json"
    out.write_text(json.dumps({"aggregate": agg, "per_item": result["per_item"]}, indent=2))
    print(f"\nwrote {out}")

    if args.gate:
        metric, thr = args.gate.split(":")
        value = agg.get(metric)
        thr = float(thr)
        if value is None:
            print(f"GATE FAIL: metric '{metric}' is None")
            sys.exit(1)
        if value < thr:
            print(f"GATE FAIL: {metric}={value} < {thr}")
            sys.exit(1)
        print(f"GATE PASS: {metric}={value} >= {thr}")


if __name__ == "__main__":
    main()
