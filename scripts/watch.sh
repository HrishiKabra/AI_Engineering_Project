#!/usr/bin/env bash
# Live race-weekend watcher. Polls the FIA documents page for one Grand Prix and
# ingests new documents as they are published, so an incident becomes answerable a
# minute or two after the stewards post a decision. Run it during a session; Ctrl-C
# to stop. Idempotent — already-seen documents are skipped.
#
#   make watch GP=monaco                  # SEASON = current year, INTERVAL = 120s
#   GP=qatar SEASON=2026 INTERVAL=90 ./scripts/watch.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
: "${GP:?set GP=<slug>, e.g. GP=monaco}"
SEASON="${SEASON:-$(date +%Y)}"
INTERVAL="${INTERVAL:-120}"

# UPDATE_TARGET=update (dev stack) or prod-update (production stack on the droplet).
TARGET="${UPDATE_TARGET:-update}"

echo "Live-watching ${SEASON} ${GP} via '${TARGET}': polling every ${INTERVAL}s. Press Ctrl-C to stop."
trap 'echo; echo "stopped."; exit 0' INT
while true; do
  echo "--- $(date -u +%FT%TZ) checking for new ${GP} documents ---"
  make "${TARGET}" GP="${GP}" SEASON="${SEASON}" || echo "poll failed; retrying next interval"
  sleep "${INTERVAL}"
done
