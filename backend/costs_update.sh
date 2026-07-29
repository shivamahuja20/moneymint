#!/bin/bash
# Monthly refresh of real fund costs & size from AMFI's public JSON APIs:
#   - TER (expense ratios)  — published monthly, effective-dated
#   - AAUM (average AUM)    — published quarterly
# Both are idempotent (upsert the latest available month/quarter), so running
# monthly is safe; the quarterly AAUM simply re-lands the same numbers until a new
# quarter is published. Logs to costs_update.log.
cd "$(dirname "$0")"
LOG_FILE="costs_update.log"

echo "===== $(date) =====" >> "$LOG_FILE"
./venv/bin/python -m app.ingestion.ter_sync >> "$LOG_FILE" 2>&1
./venv/bin/python -m app.ingestion.aum_sync >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"
