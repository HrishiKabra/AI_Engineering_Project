"""Persist documents, chunks, and embeddings into Postgres/pgvector."""

from __future__ import annotations

from functools import lru_cache

from psycopg import Connection

from app.ingestion.embed import Embedder
from app.ingestion.models import ChunkRow, DocMeta


@lru_cache
def _encoder():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def upsert_document(conn: Connection, meta: DocMeta, force: bool = False) -> tuple[int, bool]:
    """Insert/update a document. Returns (document_id, changed).

    ``force`` re-processes even when the content hash is unchanged (used to re-chunk
    the whole corpus after a parser change, without dropping the database).

    ``changed`` is False when the document is already present with an identical
    content_hash (re-ingest skip). When the hash differs the old chunks are
    dropped (ON DELETE CASCADE) so the document can be re-chunked cleanly.

    Steward decisions are matched on ``(season, grand_prix, document_number)`` so a
    re-issued/corrected document (the FIA's "V2" revisions, which may arrive under a
    new filename) updates the existing entry in place rather than duplicating it.
    The last processed file for a given document number wins. Other doc types are
    matched on ``source_file``.
    """
    decision_key = (
        meta.doc_type == "steward_decision"
        and meta.document_number is not None
        and meta.season is not None
        and meta.grand_prix is not None
    )
    with conn.cursor() as cur:
        if decision_key:
            cur.execute(
                """SELECT id, content_hash FROM documents
                   WHERE doc_type = 'steward_decision'
                     AND season = %s AND grand_prix = %s AND document_number = %s""",
                (meta.season, meta.grand_prix, meta.document_number),
            )
        else:
            cur.execute(
                "SELECT id, content_hash FROM documents WHERE source_file = %s",
                (meta.source_file,),
            )
        existing = cur.fetchone()

        if existing:
            doc_id, old_hash = existing
            if old_hash == meta.content_hash and not force:
                return doc_id, False
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
            cur.execute(
                """UPDATE documents SET doc_type=%s, doc_subtype=%s, source_file=%s,
                       content_hash=%s, season=%s, grand_prix=%s, document_number=%s,
                       is_table_only=%s
                   WHERE id=%s""",
                (
                    meta.doc_type,
                    meta.doc_subtype,
                    meta.source_file,
                    meta.content_hash,
                    meta.season,
                    meta.grand_prix,
                    meta.document_number,
                    meta.is_table_only,
                    doc_id,
                ),
            )
            return doc_id, True

        cur.execute(
            """INSERT INTO documents
                   (doc_type, doc_subtype, source_file, content_hash,
                    season, grand_prix, document_number, is_table_only)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                meta.doc_type,
                meta.doc_subtype,
                meta.source_file,
                meta.content_hash,
                meta.season,
                meta.grand_prix,
                meta.document_number,
                meta.is_table_only,
            ),
        )
        return cur.fetchone()[0], True


def upsert_chunks(conn: Connection, document_id: int, chunks: list[ChunkRow]) -> list[int]:
    """Insert chunks in order, resolving each row's parent_index to a DB id.

    Parents must precede their children in ``chunks`` (the regs parser guarantees
    this). Returns the DB ids aligned with the input list.
    """
    ids: list[int] = []
    with conn.cursor() as cur:
        for row in chunks:
            parent_id = ids[row.parent_index] if row.parent_index is not None else None
            content = row.content or ""
            token_count = count_tokens(content) if content else 0
            cur.execute(
                """INSERT INTO chunks
                       (document_id, article_id, parent_chunk_id, kind, field_name,
                        content, token_count)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    document_id,
                    row.article_id,
                    parent_id,
                    row.kind,
                    row.field_name,
                    content,
                    token_count,
                ),
            )
            ids.append(cur.fetchone()[0])
    return ids


def upsert_embeddings(
    conn: Connection,
    embedder: Embedder,
    chunk_ids: list[int],
    contents: list[str],
) -> None:
    """Embed ``contents`` and write vectors into the embedder's table."""
    if not chunk_ids:
        return
    vectors = embedder.embed(contents)
    with conn.cursor() as cur:
        for cid, vec in zip(chunk_ids, vectors, strict=True):
            cur.execute(
                f"""INSERT INTO {embedder.table} (chunk_id, embedding)
                    VALUES (%s, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding""",
                (cid, vec),
            )
