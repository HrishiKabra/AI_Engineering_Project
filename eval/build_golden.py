"""Semi-automatic golden-set seeding.

Pulls real steward decisions that (a) describe an incident in their Fact field and
(b) cite a dotted sporting-regulation article, and turns each into a labeled eval
item whose ``relevant_articles`` are the articles the decision itself cites. The
result is hand-checkable and grounded in the actual corpus. Curated regulation /
penalty questions and a stable smoke subset are appended.

    python -m eval.build_golden            # writes eval/golden.jsonl
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.db.pool import get_conn

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"

_DOTTED = re.compile(r"^B?\d{1,3}\.\d")


def _fetch_decision_items(conn, limit: int = 45) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.id, d.grand_prix, d.season, d.doc_subtype,
                   max(CASE WHEN c.field_name = 'Fact' THEN c.content END) AS fact,
                   array_remove(array_agg(DISTINCT c.article_id), NULL)     AS articles
            FROM documents d
            JOIN chunks c ON c.document_id = d.id
            WHERE d.doc_type = 'steward_decision'
              AND d.doc_subtype IN ('infringement', 'decision')
            GROUP BY d.id, d.grand_prix, d.season, d.doc_subtype
            HAVING max(CASE WHEN c.field_name = 'Fact' THEN c.content END) IS NOT NULL
            ORDER BY d.id
            """
        )
        rows = cur.fetchall()

    items: list[dict] = []
    seen_articles: set[str] = set()
    for doc_id, gp, season, _subtype, fact, articles in rows:
        dotted = [a for a in articles if _DOTTED.match(a or "")]
        if not dotted:
            continue
        # Encourage article variety across the set.
        key = dotted[0]
        if key in seen_articles and len([i for i in items]) > 15:
            continue
        seen_articles.add(key)

        fact_text = fact.replace("Fact:", "").strip()
        if len(fact_text) < 12:
            continue
        items.append(
            {
                "id": f"{season}_{gp}_doc{doc_id}",
                "question": f"Why was a penalty given for this incident: {fact_text}",
                "relevant_articles": dotted,
                "category": "single_rule",
                "season": season,
                "grand_prix": gp,
                "expect_refusal": False,
            }
        )
        if len(items) >= limit:
            break
    return items


# Curated questions over the regulations + penalty-points table (stable smoke set).
_CURATED = [
    {
        "id": "curated_unsafe_release",
        "question": "What is the penalty for an unsafe release in the pit lane?",
        "relevant_articles": ["34.14(a)", "34.14(c)"],
        "category": "single_rule",
        "expect_refusal": False,
        "smoke": True,
    },
    {
        "id": "curated_track_limits",
        "question": "Why are a driver's lap times deleted for leaving the track and gaining an advantage?",
        "relevant_articles": ["33.3", "12.4.1"],
        "category": "single_rule",
        "expect_refusal": False,
        "smoke": True,
    },
    {
        "id": "curated_tyre_identification",
        "question": "What is the sanction for using tyres without appropriate identification?",
        "relevant_articles": ["30.3(e)"],
        "category": "single_rule",
        "expect_refusal": False,
        "smoke": True,
    },
    {
        "id": "curated_five_reprimands",
        "question": "What happens if a driver receives five reprimands in a season?",
        "relevant_articles": ["18.2"],
        "category": "single_rule",
        "expect_refusal": False,
        "smoke": True,
    },
]


def main() -> None:
    with get_conn() as conn:
        items = _fetch_decision_items(conn)
    # Mark the first few decision items as smoke too, for a richer stable subset.
    for it in items[:4]:
        it["smoke"] = True
    all_items = _CURATED + items

    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        for it in all_items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"wrote {len(all_items)} golden items ({sum(1 for i in all_items if i.get('smoke'))} smoke) -> {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
