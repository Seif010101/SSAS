#!/bin/sh
# Back up the SSAS database and the server's certificate to a folder; keeps the last 30 backups.
# Run it in the folder of the docker-compose.yml you use:
#     sh backup.sh /mnt/backup                   local server (in server/)
#     sh ../../backup.sh /root/ssas-backups      VPS (in server/deploy/vps/)
# Every night at 23:00 with cron (crontab -e), for a VPS:
#     0 23 * * * cd /root/ssas/server/deploy/vps && sh ../../backup.sh /root/ssas-backups
set -eu
DEST="${1:-/mnt/backup}/ssas"
mkdir -p "$DEST"
[ -f docker-compose.yml ] || cd "$(dirname "$0")"
STAMP=$(date +%Y-%m-%d_%H%M)
docker compose exec -T ssas python -c "import sqlite3; s = sqlite3.connect('/data/ssas.sqlite3'); d = sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close()"
docker compose cp ssas:/data/backup.sqlite3 "$DEST/ssas-$STAMP.sqlite3"
docker compose exec -T ssas rm -f /data/backup.sqlite3
docker compose cp ssas:/data/certs "$DEST/" 2>/dev/null || true
ls -1t "$DEST"/ssas-*.sqlite3 | tail -n +31 | xargs -r rm -f
echo "Backup written to $DEST/ssas-$STAMP.sqlite3"
