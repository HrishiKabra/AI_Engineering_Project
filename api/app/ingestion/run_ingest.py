"""Corpus ingestion CLI.

Walks the docs tree, dispatches each PDF to the right parser, embeds the
embeddable chunks, and upserts everything into Postgres/pgvector.

Examples:
    python -m app.ingestion.run_ingest --data /srv/data
    python -m app.ingestion.run_ingest --data /srv/data --only regs
    python -m app.ingestion.run_ingest --data /srv/data/decision_docs/2025_qatar  # one race
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.config import get_settings
from app.db.pool import get_conn
from app.ingestion.classify_doc import classify
from app.ingestion.decisions_parser import parse_decision
from app.ingestion.embed import get_embedder
from app.ingestion.models import ChunkRow
from app.ingestion.pdf import load_pdf
from app.ingestion.penalty_parser import parse_penalty_points
from app.ingestion.regs_parser import parse_regs
from app.ingestion.results_parser import (
    CHAMPIONSHIP_SUBTYPE,
    RESULT_SUBTYPES,
    parse_championship,
    parse_results,
)
from app.ingestion.upsert import upsert_chunks, upsert_document, upsert_embeddings
from app.util import text_hash

_PUB_DATE = re.compile(r"published on (\d{2})\.(\d{2})\.(\d{2})", re.IGNORECASE)
_SEASON_DIR = re.compile(r"(\d{4})_")


def _latest_championship(pdfs: list[Path]) -> set[Path]:
    """The most recent Championship Points doc per season (by published date). Only
    that one is embedded, so 'who's leading the championship' returns current
    standings rather than a mid-season snapshot."""
    best: dict[int | None, tuple[tuple[int, int, int], Path]] = {}
    for p in pdfs:
        if "championship points" not in p.name.lower():
            continue
        season = next((int(m.group(1)) for part in p.parts if (m := _SEASON_DIR.match(part))), None)
        d = _PUB_DATE.search(p.name)
        date = (2000 + int(d.group(3)), int(d.group(2)), int(d.group(1))) if d else (0, 0, 0)
        if season not in best or date > best[season][0]:
            best[season] = (date, p)
    return {p for _, p in best.values()}


def _parse_document(meta, text: str, pdf_path) -> list[ChunkRow]:
    if meta.doc_type == "sporting_regulation":
        return parse_regs(text)
    if meta.doc_type == "penalty_points":
        return parse_penalty_points(text)
    if meta.doc_subtype == CHAMPIONSHIP_SUBTYPE:
        return parse_championship(pdf_path, meta.season, meta.grand_prix)
    if meta.doc_subtype in RESULT_SUBTYPES:
        # Timing sheets are parsed from the PDF directly (needs word coordinates).
        return parse_results(pdf_path, meta.season, meta.grand_prix)
    # steward_decision narrative
    _, rows = parse_decision(text)
    return rows


def _matches_filter(doc_type: str, only: str | None) -> bool:
    if only is None:
        return True
    return {
        "regs": "sporting_regulation",
        "penalty": "penalty_points",
        "decisions": "steward_decision",
    }.get(only) == doc_type


def ingest(
    data_root: Path, only: str | None = None, limit: int | None = None, force: bool = False
) -> dict:
    settings = get_settings()
    embedder = get_embedder(settings)

    pdfs = sorted(data_root.rglob("*.pdf"))
    latest_champ = _latest_championship(pdfs)
    stats = {"seen": 0, "ingested": 0, "skipped": 0, "chunks": 0, "embedded": 0}

    with get_conn() as conn:
        for pdf in pdfs:
            if limit is not None and stats["ingested"] >= limit:
                break
            text = load_pdf(pdf)
            content_hash = text_hash(text)
            meta = classify(str(pdf), text, content_hash)

            if not _matches_filter(meta.doc_type, only):
                continue
            stats["seen"] += 1

            doc_id, changed = upsert_document(conn, meta, force=force)

            # A superseded championship snapshot (a newer one exists this season):
            # drop any standings chunks it left behind so only the latest remains.
            if meta.doc_subtype == CHAMPIONSHIP_SUBTYPE and pdf not in latest_champ:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
                conn.commit()
                stats["skipped"] += 1
                continue

            if not changed:
                stats["skipped"] += 1
                continue

            rows = [] if meta.is_table_only else _parse_document(meta, text, pdf)
            chunk_ids = upsert_chunks(conn, doc_id, rows)
            stats["chunks"] += len(rows)

            # Embed only the chunks flagged embeddable with non-empty content.
            to_embed = [
                (cid, r.content)
                for cid, r in zip(chunk_ids, rows, strict=True)
                if r.embed and r.content.strip()
            ]
            if to_embed:
                ids = [c for c, _ in to_embed]
                contents = [c for _, c in to_embed]
                upsert_embeddings(conn, embedder, ids, contents)
                stats["embedded"] += len(ids)

            conn.commit()
            stats["ingested"] += 1
            print(
                f"[{stats['ingested']}] {meta.doc_type}/{meta.doc_subtype or '-'} "
                f"{pdf.name[:55]} -> {len(rows)} chunks, {len(to_embed)} embedded"
            )

    stats["embed_tokens"] = getattr(embedder, "embed_tokens", 0)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path, help="corpus root, or a single race folder")
    ap.add_argument("--only", choices=["regs", "penalty", "decisions"], default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="re-process even if unchanged")
    args = ap.parse_args()

    stats = ingest(args.data, only=args.only, limit=args.limit, force=args.force)
    print("\n=== ingestion summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
