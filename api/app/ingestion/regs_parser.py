"""Structure-aware parent-child parser for the FIA Sporting Regulations.

Layout (post-cleanup): a table of contents lists every ``ARTICLE Bn`` header once,
then the body repeats them with content. In the body a sub-article number sits on
its own line (``B1.1.1``) followed by its text until the next number/header.

We emit one ``parent`` chunk per Article (the full article text, NOT embedded —
fetched at generation time for cross-reference context) and one ``child`` chunk
per sub-article (embedded individually, tagged with its ``article_id``).
"""

from __future__ import annotations

import re

from app.ingestion.models import ChunkRow

ARTICLE_RE = re.compile(r"^ARTICLE\s+([A-Z]\d+)\s*:?\s*(.*)$")
SUBART_RE = re.compile(r"^([A-Z]\d+(?:\.\d+){1,3})\s*$")


def _find_body_start(lines: list[str]) -> int:
    """Skip the table of contents: the body begins at the *second* occurrence of
    the first article header (the first occurrence is the TOC entry)."""
    first_header_id: str | None = None
    seen_first = False
    for i, ln in enumerate(lines):
        m = ARTICLE_RE.match(ln)
        if not m:
            continue
        if first_header_id is None:
            first_header_id = m.group(1)
            seen_first = True
            continue
        if seen_first and m.group(1) == first_header_id:
            return i
    return 0


def parse_regs(text: str) -> list[ChunkRow]:
    lines = text.split("\n")
    body_start = _find_body_start(lines)
    rows: list[ChunkRow] = []

    parent_index: int | None = None
    parent_buf: list[str] = []
    child_index: int | None = None
    child_buf: list[str] = []

    def flush_child() -> None:
        nonlocal child_index, child_buf
        if child_index is not None:
            content = "\n".join(child_buf).strip()
            rows[child_index].content = content
            if not content:
                rows[child_index].embed = False  # bare/empty sub-article: keep structure, skip embed
        child_index = None
        child_buf = []

    def flush_parent() -> None:
        nonlocal parent_index, parent_buf
        if parent_index is not None:
            rows[parent_index].content = "\n".join(parent_buf).strip()
        parent_index = None
        parent_buf = []

    for ln in lines[body_start:]:
        art = ARTICLE_RE.match(ln)
        sub = SUBART_RE.match(ln)

        if art:
            flush_child()
            flush_parent()
            title = art.group(2).strip()
            parent_index = len(rows)
            rows.append(
                ChunkRow(
                    kind="parent",
                    content="",
                    article_id=art.group(1),
                    field_name=title or None,
                    embed=False,
                )
            )
            parent_buf = [ln.strip()]
        elif sub:
            flush_child()
            child_index = len(rows)
            rows.append(
                ChunkRow(
                    kind="child",
                    content="",
                    article_id=sub.group(1),
                    parent_index=parent_index,
                )
            )
            child_buf = []
            parent_buf.append(ln.strip())
        else:
            if child_index is not None:
                child_buf.append(ln)
            if parent_index is not None:
                parent_buf.append(ln)

    flush_child()
    flush_parent()

    # Prefix each child's content with its article id so the embedded text is
    # self-describing (helps both dense + sparse retrieval on "Article B1.1.1").
    for r in rows:
        if r.kind == "child" and r.content and r.article_id:
            r.content = f"Article {r.article_id}: {r.content}"
    return rows
