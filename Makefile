.PHONY: up down build migrate ingest ingest-sample scrape update eval eval-smoke test fmt lint logs psql

# Season + GP for scrape/update, e.g. `make update GP=qatar`. SEASON defaults to 2025.
SEASON ?= 2025
GP ?=
PLAYWRIGHT_VERSION ?= 1.49.0
PLAYWRIGHT_IMAGE ?= mcr.microsoft.com/playwright/python:v$(PLAYWRIGHT_VERSION)-jammy

# Bring up the full stack (db + api + web).
up:
	docker compose up -d --build

down:
	docker compose down

# Build images without starting.
build:
	docker compose build

# Start only the database (fast inner loop for migrations/ingestion).
db:
	docker compose up -d db

# Apply DB migrations (idempotent) inside the api container.
migrate:
	docker compose run --rm api python -m app.db.migrate

# Full corpus ingestion. Override with ARGS, e.g. `make ingest ARGS="--only regs"`.
ingest:
	docker compose run --rm api python -m app.ingestion.run_ingest --data /srv/data $(ARGS)

# Cheap validation run over a handful of docs.
ingest-sample:
	docker compose run --rm api python -m app.ingestion.run_ingest --data /srv/data --limit 20

# Scrape one Grand Prix's decision documents into data/decision_docs/<season>_<gp>.
# Uses the official Playwright image (browsers preinstalled) so no host deps.
#   make scrape GP=qatar          (SEASON defaults to 2025)
scrape:
	@test -n "$(GP)" || (echo "set GP=<slug>, e.g. make scrape GP=qatar"; exit 1)
	docker run --rm -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
		-v "$(PWD)/data:/data" -v "$(PWD)/scripts:/scripts:ro" \
		$(PLAYWRIGHT_IMAGE) \
		sh -c "pip install -q playwright==$(PLAYWRIGHT_VERSION) && \
			python /scripts/get_decision_docs.py --season $(SEASON) --gp '$(GP)' --out /data/decision_docs"

# Auto-update: scrape one GP, then ingest just that race folder (incremental).
#   make update GP=qatar
update: scrape
	docker compose run --rm api python -m app.ingestion.run_ingest \
		--data /srv/data/decision_docs/$(SEASON)_$(GP)

# Full evaluation over the golden set.
eval:
	docker compose run --rm api python -m eval.run_eval $(ARGS)

# Deterministic smoke eval (CI gate shape).
eval-smoke:
	docker compose run --rm api python -m eval.run_eval --subset smoke --no-ragas

test:
	docker compose run --rm api pytest

fmt:
	cd api && ruff format . && ruff check --fix .

lint:
	cd api && ruff check .

logs:
	docker compose logs -f api

# Open a psql shell against the running db container.
psql:
	docker compose exec db psql -U postgres -d f1rag
