# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The **F1 Rule & Penalty Interpreter** — an agentic RAG system that explains FIA Formula 1 penalties
and regulations to fans, grounded in the FIA Sporting Regulations + ~1,360 steward decision PDFs.

There are two generations in this repo:
- **v2 (primary, active):** a deployed FastAPI + LangGraph + Postgres/pgvector system under `api/`,
  `eval/`, `web/`, orchestrated by `docker-compose.yml`. This is what you should work on. Spec:
  `docs/V2_BUILD_SPEC.md`. User-facing docs: `README.md`.
- **v1 (legacy):** `legacy/AI_Engineering_Project.ipynb` — the original Colab/Gradio notebook
  (keyword RAG, no vector DB). Kept for reference; do not extend it. `legacy/milestones.ipynb` is the
  generic course scaffold. `docs/PROPOSAL.md` / `docs/PROJECT_REQUIREMENTS.md` are the course docs.

**Layout:** `data/` is the FIA PDF corpus (`data/regulations/`, `data/decision_docs/<season>_<gp>/`)
— it is tracked in git, NOT gitignored. `docs/` holds project documentation. This file (`CLAUDE.md`)
stays at the repo root so Claude Code auto-loads it.

## Working on v2 — commands

Everything runs through Docker (no host Postgres/Python deps needed). The `api/app`, `tests`, and
`eval` dirs are bind-mounted into the `api` container, so Python changes need **no rebuild**; restart
the server (`docker compose restart api`) to pick up changes in the long-running uvicorn process.
Changes to `web/static` or `requirements.txt` **do** need a rebuild (`docker compose up -d --build`).

- `make up` / `make down` — full stack (db + api + web)
- `make migrate` — apply `api/app/db/migrations/*.sql` (idempotent, tracked in `schema_version`)
- `make ingest` (or `ingest-sample` for `--limit 20`) — parse + embed corpus into pgvector
- `make update GP=qatar [SEASON=2025]` — incremental auto-update: scrape one GP's decision docs
  (via the Playwright image) into `data/decision_docs/<season>_<gp>`, then ingest just that folder.
  `make scrape GP=...` does only the download. Ingest is idempotent (skips unchanged by content hash;
  decisions are keyed on `(season, grand_prix, document_number)` so re-issued docs update in place).
- `make test` — pytest (offline: LLM + DB mocked). Single test:
  `docker compose run --rm api pytest tests/test_parsers.py::test_regs_parent_child_skips_toc`
- `make lint` / `make eval` / `make eval-smoke` / `make psql`
- Ablation: `docker compose run --rm api python -m eval.ablation --subset smoke`
- Regenerate golden set from the DB: `docker compose run --rm api python -m eval.build_golden`

## v2 architecture (the big picture)

Request flow is a **LangGraph corrective-RAG state machine** compiled once and run per request with a
runtime context (`AgentContext`: db conn, llm, embedder) passed via `config.configurable.ctx` — the
graph itself is stateless. Nodes (`api/app/agent/nodes.py`, wired in `graph.py`):

`router → retrieve → grader → (rewrite → retrieve)* → generate → verify`

- **router** classifies scope (out_of_scope → refuse) after input hygiene/injection stripping.
- **retrieve** = `retrieval/hybrid.py`: dense (pgvector `<=>`) + sparse (`tsvector`) fused with RRF,
  then `expand_to_parents` swaps retrieved regs *child* chunks for their full *parent* article.
- **grader** is LLM-as-judge; the grade drives `guardrails/coverage.py::coverage_decision`
  (generate / rewrite / refuse). Node is named `grader` (not `grade`) because LangGraph forbids a
  node name colliding with a state key.
- **verify** = `guardrails/citation.py`: extracts cited articles, verifies each against retrieved
  article ids, allows one regeneration, then drops/flags unverified citations.

**Data model** (migrations `001–003`): `documents` → `chunks` (kind ∈ parent/child/row/field,
`article_id`, `parent_chunk_id`, generated `tsv`) → **one embedding table per model**
(`emb_openai_1536`, `emb_bge_768`) so the 1536-dim default and 768-dim BGE ablation coexist without a
migration. `query_log` powers `/metrics` + `/dashboard`.

**Ingestion** (`api/app/ingestion/`): `pdf.py` (PyMuPDF + `clean_text`) → `classify_doc.py` → one of
three parsers (`regs_parser` parent/child, `penalty_parser` table rows, `decisions_parser` labeled
fields) → `embed.py` (OpenAI default, BGE lazy) → `upsert.py`. Table-only docs (classification,
championship points) are stored but **not embedded**.

## Critical gotchas (learned while building)

- **`OPENAI_KEY` vs `OPENAI_API_KEY`:** `.env` defines `OPENAI_KEY`; the OpenAI SDK wants
  `OPENAI_API_KEY`. `config.py::export_openai_env` bridges this and **overwrites an empty**
  `OPENAI_API_KEY` (compose used to inject `""`, which shadowed the real key). compose passes only
  `OPENAI_KEY` through.
- **Migrations use a plain connection, not the pool.** `db/pool.py` registers the pgvector type on
  every connection, but that type doesn't exist until migration 001 runs — chicken-and-egg. So
  `db/migrate.py` uses a direct `psycopg.connect`, and `_configure` swallows registration errors.
- **Query vectors need an explicit cast.** Passing a Python list to the `<=>` operator adapts as
  `float8[]`. `retrieval/hybrid.py` formats a vector literal and casts `%s::vector` (inserts work
  without this because the column type provides context).
- **Article-number mismatch:** 2025 decisions cite plain numbers (`33.3`); the 2026 regs use
  `B…` prefixes. `citation.normalize_article` strips the prefix so they match; the verifier also
  accepts an article cited by a retrieved decision itself. See README "Known limitations".
- **SSE is pseudo-streamed:** the graph runs to completion (so the citation guardrail sees the whole
  answer) and `routes/ask.py` then streams the answer as `token`/`citation`/`done` events.

## Conventions

- Settings are a single pydantic `Settings` (`config.py`); prefer adding a field there over
  hardcoding — the eval ablation flips behavior purely through per-request `config` overrides
  (`mode`, `top_k`, `table`, `filters`).
- Tests are offline by design (mock LLM + DB via `dependency_overrides` / monkeypatch) so CI needs no
  API key. The eval gate is the only thing that needs a live key, and it's secret-gated in CI.
- Lint config: `api/pyproject.toml` for `api/`, root `ruff.toml` for `eval/` + `tests/`.
