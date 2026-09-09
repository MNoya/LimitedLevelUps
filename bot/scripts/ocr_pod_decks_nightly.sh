#!/usr/bin/env bash
# On-demand / nightly runner for the pod deck-screenshot OCR pass. Reads prod through .env.supabase
# (SUPABASE_DB_URL) and .env (DISCORD_BOT_TOKEN), corrects any not-yet-marked seats, and appends to a log.
#   ./bot/scripts/ocr_pod_decks_nightly.sh            # sweep all tracked pods
#   ./bot/scripts/ocr_pod_decks_nightly.sh <event_id> # one event
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"

set -a
# shellcheck disable=SC1091
source .env.supabase
# shellcheck disable=SC1091
source .env
set +a
export DATABASE_URL="$SUPABASE_DB_URL"

mkdir -p logs
{
  echo "=== $(date --iso-8601=seconds) : ocr_pod_decks --commit $* ==="
  .venv/bin/python -u -m bot.scripts.ocr_pod_decks --commit "$@"
} 2>&1 | tee -a logs/ocr_pod_decks.log
