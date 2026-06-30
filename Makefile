.PHONY: up down build migrate ingest ingest-sample scraper-image scrape update watch eval eval-smoke \
	test fmt lint logs psql prod-up prod-down prod-migrate prod-ingest prod-logs prod-update prod-watch

PROD := docker compose -f docker-compose.prod.yml

# Season + GP for scrape/update/watch, e.g. `make update GP=qatar`.
SEASON ?= 2025
GP ?=
INTERVAL ?= 120
SCRAPER_IMAGE ?= f1-scraper

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

# Prebuilt scraper image (Playwright + browsers), so scrape/watch don't reinstall each run.
scraper-image:
	docker build -q -t $(SCRAPER_IMAGE) -f scripts/Dockerfile.scraper scripts >/dev/null

# Scrape one Grand Prix's decision documents into data/decision_docs/<season>_<gp>.
#   make scrape GP=qatar          (SEASON defaults to 2025)
scrape: scraper-image
	@test -n "$(GP)" || (echo "set GP=<slug>, e.g. make scrape GP=qatar"; exit 1)
	docker run --rm -v "$(PWD)/data:/data" -v "$(PWD)/scripts:/scripts:ro" \
		$(SCRAPER_IMAGE) \
		python /scripts/get_decision_docs.py --season $(SEASON) --gp '$(GP)' --out /data/decision_docs

# Auto-update: scrape one GP, then ingest just that race folder (incremental).
#   make update GP=qatar
update: scrape
	docker compose run --rm api python -m app.ingestion.run_ingest \
		--data /srv/data/decision_docs/$(SEASON)_$(GP)

# Live race-weekend watcher: poll one GP for new docs + ingest them as they appear.
#   make watch GP=monaco [SEASON=2026] [INTERVAL=120]
watch: scraper-image
	@test -n "$(GP)" || (echo "set GP=<slug>, e.g. make watch GP=monaco"; exit 1)
	GP="$(GP)" SEASON="$(SEASON)" INTERVAL="$(INTERVAL)" bash scripts/watch.sh

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

# --- production (single host / droplet); see docs/DEPLOY.md ---
prod-up:
	$(PROD) up -d --build
prod-down:
	$(PROD) down
prod-migrate:
	$(PROD) run --rm api python -m app.db.migrate
prod-ingest:
	$(PROD) run --rm api python -m app.ingestion.run_ingest --data /srv/data $(ARGS)
prod-logs:
	$(PROD) logs -f
# Scrape one GP + ingest into the production stack (for the live watcher on the droplet).
prod-update: scrape
	$(PROD) run --rm api python -m app.ingestion.run_ingest \
		--data /srv/data/decision_docs/$(SEASON)_$(GP)
# Live race-weekend watcher against production: `make prod-watch GP=monaco SEASON=2026`.
prod-watch: scraper-image
	@test -n "$(GP)" || (echo "set GP=<slug>, e.g. make prod-watch GP=monaco"; exit 1)
	GP="$(GP)" SEASON="$(SEASON)" INTERVAL="$(INTERVAL)" UPDATE_TARGET=prod-update bash scripts/watch.sh
