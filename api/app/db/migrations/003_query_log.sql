-- Per-request observability log powering /metrics and /dashboard.

CREATE TABLE IF NOT EXISTS query_log (
    id                BIGSERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
    question          TEXT,
    route             TEXT,
    retrieved_ids     BIGINT[],
    grade             REAL,
    attempts          INT,
    verified          BOOLEAN,
    refused           BOOLEAN,
    answer            TEXT,
    citations         JSONB,
    latency_ms        INT,
    ttft_ms           INT,
    prompt_tokens     INT,
    completion_tokens INT,
    embed_tokens      INT,
    cost_usd          NUMERIC(10, 6),
    config            JSONB
);

CREATE INDEX IF NOT EXISTS query_log_ts_idx ON query_log (ts DESC);
