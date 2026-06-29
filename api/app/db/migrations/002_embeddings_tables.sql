-- One embedding table per model: a pgvector column is fixed-dimension, so we keep
-- the 1536-dim OpenAI vectors and the 768-dim BGE vectors in separate tables.
-- Retrieval selects the table by the active EMBED_MODEL config. This lets both
-- coexist for the ablation grid without a migration between runs.

CREATE TABLE IF NOT EXISTS emb_openai_1536 (
    chunk_id  BIGINT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL
);
CREATE INDEX IF NOT EXISTS emb_openai_1536_hnsw
    ON emb_openai_1536 USING hnsw (embedding vector_cosine_ops);

-- Ablation backend; only populated when EMBED_MODEL=bge.
CREATE TABLE IF NOT EXISTS emb_bge_768 (
    chunk_id  BIGINT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    embedding vector(768) NOT NULL
);
CREATE INDEX IF NOT EXISTS emb_bge_768_hnsw
    ON emb_bge_768 USING hnsw (embedding vector_cosine_ops);
