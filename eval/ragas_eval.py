"""Optional Ragas metrics (faithfulness / answer relevancy / context precision).

Ragas + its datasets/langchain deps are heavy and call OpenAI, so this is imported
lazily and only when ``--ragas`` is requested. Each eval run record must carry
``question``, ``answer``, ``contexts`` (list of retrieved snippets), and optionally
``reference``.
"""

from __future__ import annotations


def run_ragas(records: list[dict]) -> dict:
    """Return mean Ragas scores over the records. Returns {} on any import/runtime
    failure so the harness degrades gracefully."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, faithfulness
    except Exception as e:  # noqa: BLE001
        return {"error": f"ragas unavailable: {type(e).__name__}: {e}"}

    rows = [r for r in records if r.get("answer") and r.get("contexts")]
    if not rows:
        return {}

    ds = Dataset.from_list(
        [
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
                "reference": r.get("reference", r["answer"]),
            }
            for r in rows
        ]
    )
    metrics = [faithfulness, answer_relevancy, context_precision]
    try:
        result = evaluate(ds, metrics=metrics)
        return {k: round(float(v), 4) for k, v in result.items() if isinstance(v, int | float)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"ragas evaluate failed: {type(e).__name__}: {e}"}
