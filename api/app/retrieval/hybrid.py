"""Hybrid retrieval: dense (pgvector) + sparse (full-text) fused with RRF.

Dense alone misses exact rule numbers; sparse alone misses paraphrases. We fuse
the two ranked lists with Reciprocal Rank Fusion, then expand retrieved
child/field chunks to their parent article so the generator sees full
cross-referenced context.
"""

from __future__ import annotations

from psycopg import Connection


def _vec_literal(vec: list[float]) -> str:
    """pgvector text literal. Used with an explicit ``::vector`` cast because the
    distance operator gives psycopg no type context to infer the vector type."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _filter_sql(filters: dict | None) -> tuple[str, list]:
    if not filters:
        return "", []
    clauses, params = [], []
    for col in ("season", "grand_prix", "doc_type"):
        if filters.get(col) is not None:
            clauses.append(f"d.{col} = %s")
            params.append(filters[col])
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def dense_search(
    conn: Connection,
    query_vec: list[float],
    table: str,
    k: int,
    filters: dict | None = None,
) -> list[tuple[int, float]]:
    where, fparams = _filter_sql(filters)
    vec = _vec_literal(query_vec)
    sql = f"""
        SELECT e.chunk_id, 1 - (e.embedding <=> %s::vector) AS score
        FROM {table} e
        JOIN chunks c    ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        WHERE TRUE {where}
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [vec, *fparams, vec, k])
        return [(r[0], float(r[1])) for r in cur.fetchall()]


def sparse_search(
    conn: Connection,
    query_text: str,
    k: int,
    filters: dict | None = None,
) -> list[tuple[int, float]]:
    where, fparams = _filter_sql(filters)
    sql = f"""
        SELECT c.id, ts_rank(c.tsv, q) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id,
             plainto_tsquery('english', %s) q
        WHERE c.tsv @@ q {where}
        ORDER BY score DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [query_text, *fparams, k])
        return [(r[0], float(r[1])) for r in cur.fetchall()]


def rrf_fuse(rankings: list[list[tuple[int, float]]], rrf_k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion. Each ranking is an ordered [(id, score), ...]; the
    score is ignored, only rank matters. Returns fused [(id, rrf_score), ...]."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, (cid, _) in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def hybrid_retrieve(
    conn: Connection,
    query_text: str,
    query_vec: list[float] | None,
    *,
    table: str,
    k: int = 20,
    mode: str = "hybrid",
    filters: dict | None = None,
    rrf_k: int = 60,
) -> list[int]:
    """Return fused chunk ids. ``mode`` is 'dense' | 'sparse' | 'hybrid'."""
    if mode == "sparse":
        return [cid for cid, _ in sparse_search(conn, query_text, k, filters)]
    if mode == "dense":
        if query_vec is None:
            raise ValueError("dense retrieval requires a query vector")
        return [cid for cid, _ in dense_search(conn, query_vec, table, k, filters)]

    # hybrid
    rankings = [sparse_search(conn, query_text, k, filters)]
    if query_vec is not None:
        rankings.append(dense_search(conn, query_vec, table, k, filters))
    return [cid for cid, _ in rrf_fuse(rankings, rrf_k)][:k]


def expand_to_parents(conn: Connection, chunk_ids: list[int]) -> list[dict]:
    """Resolve chunk ids to retrieval docs, expanding child chunks to their parent
    article text (for cross-reference context) while keeping the child as snippet.
    Dedupes by the expanded content key; preserves input order."""
    if not chunk_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.kind, c.article_id, c.field_name, c.content,
                   c.parent_chunk_id, p.content AS parent_content, p.article_id AS parent_article,
                   d.doc_type, d.doc_subtype, d.source_file, d.grand_prix,
                   d.season, d.document_number
            FROM chunks c
            LEFT JOIN chunks p ON p.id = c.parent_chunk_id
            JOIN documents d   ON d.id = c.document_id
            WHERE c.id = ANY(%s)
            """,
            (chunk_ids,),
        )
        by_id = {r[0]: r for r in cur.fetchall()}

    docs: list[dict] = []
    seen: set[tuple] = set()
    for cid in chunk_ids:
        r = by_id.get(cid)
        if r is None:
            continue
        (
            _id, kind, article_id, field_name, content, parent_chunk_id,
            parent_content, parent_article, doc_type, doc_subtype, source_file,
            grand_prix, season, document_number,
        ) = r
        # Child regs chunks expand to the full parent article; decisions/penalty keep self.
        if kind == "child" and parent_content:
            context = parent_content
            ctx_article = parent_article or article_id
        else:
            context = content
            ctx_article = article_id

        key = (doc_type, ctx_article, source_file)
        if key in seen:
            continue
        seen.add(key)
        docs.append(
            {
                "chunk_id": cid,
                "kind": kind,
                "article_id": article_id,
                "field_name": field_name,
                "doc_type": doc_type,
                "doc_subtype": doc_subtype,
                "source_file": source_file,
                "grand_prix": grand_prix,
                "season": season,
                "document_number": document_number,
                "content": context,
                "snippet": content[:300],
            }
        )
    return docs
