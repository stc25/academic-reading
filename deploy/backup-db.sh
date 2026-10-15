#!/bin/sh
# Dump both databases to ./backups/ (run from /var/www/academic-reading).
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
ts=$(date +%Y%m%d-%H%M%S)
for pair in "mariadb_academic_reading academic_reading_eng" "mariadb_academic_reading_v1 academic_reading_v1"; do
  set -- $pair
  docker compose exec -T "$1" sh -c "mariadb-dump -uroot -p\"\$MARIADB_ROOT_PASSWORD\" --single-transaction --default-character-set=utf8mb4 $2" > "backups/$2-$ts.sql"
  echo "wrote backups/$2-$ts.sql"
done
