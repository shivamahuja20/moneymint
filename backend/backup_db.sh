#!/bin/bash
# Weekly PostgreSQL backup.
#
# The whole database rebuilds from public sources (AMFI + MFAPI), but that costs
# ~40 min of throttled API calls, so a dump is worth keeping. Compressed it is
# ~110 MB versus 2.2 GB live, and disk here is limited (~13 GB free), so we keep
# only the last KEEP dumps.
#
# Backups live OUTSIDE the project: the project sits under ~/Desktop, which macOS
# protects (TCC), and keeping 100 MB blobs out of a git repo is right anyway.
set -u
PGBIN="/opt/homebrew/opt/postgresql@17/bin"
DEST="$HOME/Library/Application Support/MoneyMint/backups"
LOG_FILE="$HOME/Library/Logs/moneymint/backup_db.log"
KEEP=4

mkdir -p "$DEST" "$(dirname "$LOG_FILE")"
STAMP=$(date +%Y%m%d)
OUT="$DEST/moneymint_$STAMP.pgc"

echo "===== $(date) =====" >> "$LOG_FILE"
if "$PGBIN/pg_dump" -d moneymint -Fc -Z6 -f "$OUT" 2>>"$LOG_FILE"; then
    # a dump that can't be read back is not a backup — verify before trusting it
    if "$PGBIN/pg_restore" -l "$OUT" > /dev/null 2>>"$LOG_FILE"; then
        echo "OK  $(du -h "$OUT" | cut -f1)  $OUT" >> "$LOG_FILE"
    else
        echo "FAILED verification, removing $OUT" >> "$LOG_FILE"
        rm -f "$OUT"
        exit 1
    fi
else
    echo "FAILED pg_dump" >> "$LOG_FILE"
    rm -f "$OUT"
    exit 1
fi

# prune oldest, keep the newest $KEEP
ls -1t "$DEST"/moneymint_*.pgc 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    echo "pruned $old" >> "$LOG_FILE"
    rm -f "$old"
done
echo "" >> "$LOG_FILE"
