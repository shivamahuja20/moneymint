#!/bin/bash
# Nightly ingestion: syncs scheme_master + all-schemes NAVs from AMFI, refreshes
# the legacy 10-fund tables the frontend uses. Logs to daily_update.log.

cd "$(dirname "$0")"
LOG_FILE="daily_update.log"

echo "===== $(date) =====" >> "$LOG_FILE"
./venv/bin/python -m app.ingestion.daily_sync >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"
