#!/usr/bin/env bash
# Fully-automatic, always-on F1 document watcher.
#
# Adaptive polling with no manual intervention and no calendar: it scrapes the
# current season's FIA documents and ingests new ones, polling FAST while documents
# are actively being published (i.e. a session is live) and backing off to idle
# checks when nothing is happening. Ingests only the active race folder, so each
# cycle is cheap. Intended to run unattended as a systemd service (see docs/DEPLOY.md).
#
# Env (all optional): SEASON (default: current year), MIN_INTERVAL=120, MAX_INTERVAL=1800,
#   INGEST_CMD (compose project; default production).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

SEASON="${SEASON:-$(date +%Y)}"
MIN_INTERVAL="${MIN_INTERVAL:-120}"
MAX_INTERVAL="${MAX_INTERVAL:-1800}"
INGEST="${INGEST_CMD:-docker compose -f docker-compose.prod.yml}"
interval="$MIN_INTERVAL"

log() { echo "$(date -u +%FT%TZ) [autowatch] $*"; }
trap 'log "stopped"; exit 0' INT TERM
log "started: season ${SEASON}, adaptive ${MIN_INTERVAL}-${MAX_INTERVAL}s"

while true; do
  # 1) Download any newly published documents across the season (skips existing).
  make scrape GP=all SEASON="${SEASON}" >/dev/null 2>&1 || log "scrape error (continuing)"

  # 2) Ingest the most-recently-updated race folder — the active one during a weekend.
  ingested=0
  latest="$(ls -dt data/decision_docs/${SEASON}_*/ 2>/dev/null | head -1 | sed 's#/$##; s#.*/##')"
  if [ -n "${latest:-}" ]; then
    out="$($INGEST run --rm api python -m app.ingestion.run_ingest \
            --data "/srv/data/decision_docs/${latest}" 2>&1 || true)"
    ingested="$(printf '%s' "$out" | sed -n 's/.*ingested: \([0-9][0-9]*\).*/\1/p' | head -1)"
    ingested="${ingested:-0}"
  fi

  # 3) Adapt: poll fast right after activity, otherwise back off (capped).
  if [ "${ingested}" -gt 0 ]; then
    log "ingested ${ingested} new doc(s) from ${latest}; polling fast (${MIN_INTERVAL}s)"
    interval="$MIN_INTERVAL"
  else
    interval=$(( interval * 2 ))
    [ "$interval" -gt "$MAX_INTERVAL" ] && interval="$MAX_INTERVAL"
    log "no new docs; next check in ${interval}s"
  fi
  sleep "$interval"
done
