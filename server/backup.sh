#!/bin/sh
# Daily backup of the SSAS database to a folder (e.g. a USB disk mounted at /mnt/backup).
# Usage: ./backup.sh /mnt/backup        (keeps the last 30 backups)
set -eu
DEST="${1:-/mnt/backup}/ssas"
mkdir -p "$DEST"
cd "$(dirname "$0")"
STAMP=$(date +%Y-%m-%d_%H%M)
docker compose exec -T ssas python -c "import sqlite3; s=sqlite3.connect('/data/ssas.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close()"
cp data/backup.sqlite3 "$DEST/ssas-$STAMP.sqlite3"
rm -f data/backup.sqlite3
cp -r data/certs "$DEST/" 2>/dev/null || true
ls -1t "$DEST"/ssas-*.sqlite3 | tail -n +31 | xargs -r rm -f
echo "Backup written to $DEST/ssas-$STAMP.sqlite3"
