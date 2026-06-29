-- Core schema: pgvector extension, documents, chunks.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id              BIGSERIAL PRIMARY KEY,
    doc_type        TEXT NOT NULL,            -- 'sporting_regulation' | 'penalty_points' | 'steward_decision'
    doc_subtype     TEXT,                     -- 'infringement' | 'decision' | 'summons' | 'classification' | ...
    source_file     TEXT NOT NULL,
    content_hash    TEXT NOT NULL,            -- stable hash of file text, for re-ingest skip / dedupe
    season          INT,
    grand_prix      TEXT,
    document_number TEXT,
    is_table_only   BOOLEAN NOT NULL DEFAULT FALSE,  -- classification / championship-points docs
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_file)
);

CREATE TABLE IF NOT EXISTS chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    article_id      TEXT,                     -- 'B1.4.2' | '33.3' | '30.3(e)' | NULL
    parent_chunk_id BIGINT REFERENCES chunks(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,            -- 'parent' | 'child' | 'row' | 'field'
    field_name      TEXT,                     -- decisions: 'Fact' | 'Infringement' | 'Decision' | 'Reason'
    content         TEXT NOT NULL,
    token_count     INT,
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_tsv_idx        ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_article_id_idx ON chunks (article_id);
CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id);
CREATE INDEX IF NOT EXISTS chunks_kind_idx       ON chunks (kind);
