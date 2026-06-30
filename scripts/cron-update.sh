#!/usr/bin/env bash
# Scheduled auto-update: scrape the current season's newly published FIA documents
# and ingest them into the running production stack. Idempotent — already-downloaded
# files and already-ingested docs are skipped, so it is safe to run on a schedule.
#
# Install (on the droplet) as a weekly cron, e.g.:
#   0 6 * * 1  /root/f1/scripts/cron-update.sh >> /var/log/f1-autoupdate.log 2>&1
#
# SEASON defaults to the current calendar year; override with: SEASON=2026 ./cron-update.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
SEASON="${SEASON:-$(date +%Y)}"

# Prevent overlapping runs.
exec 9>"/tmp/f1-autoupdate.lock"
if ! flock -n 9; then
  echo "$(date -u +%FT%TZ) another auto-update is already running; exiting."
  exit 0
fi

echo "=== $(date -u +%FT%TZ) auto-update: season ${SEASON} ==="
make scrape GP=all SEASON="${SEASON}"   # download any new races/documents
make prod-ingest                        # ingest the new docs (deduped, incremental)
echo "=== $(date -u +%FT%TZ) auto-update complete ==="
