"""Shared ingestion data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocMeta:
    doc_type: str                      # 'sporting_regulation' | 'penalty_points' | 'steward_decision'
    source_file: str
    content_hash: str
    doc_subtype: str | None = None
    season: int | None = None
    grand_prix: str | None = None
    document_number: str | None = None
    is_table_only: bool = False


@dataclass
class ChunkRow:
    kind: str                          # 'parent' | 'child' | 'row' | 'field'
    content: str
    article_id: str | None = None
    field_name: str | None = None
    # Index into the same document's chunk list identifying this row's parent,
    # resolved to a DB id at upsert time. None for top-level rows.
    parent_index: int | None = None
    token_count: int | None = None
    # Children that should NOT be embedded (e.g. parent article aggregates) set this.
    embed: bool = True
    metadata: dict = field(default_factory=dict)
