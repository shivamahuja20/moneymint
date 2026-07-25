#!/bin/bash
# Monthly holdings ETL: parses AMFI/AMC portfolio disclosures into holdings +
# sector_allocation. Run after the SEBI disclosure deadline (10th of each month).
# Resilient: one AMC's bad file is logged and skipped, others still load.
cd "$(dirname "$0")"
LOG_FILE="holdings_update.log"
echo "===== $(date) =====" >> "$LOG_FILE"
./venv/bin/python -m app.ingestion.holdings.runner >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"
