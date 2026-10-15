#!/bin/sh
# Usage: deploy/restore-db.sh <v2-dump.sql> <v1-dump.sql>
# Loads dumps into freshly started (empty) databases. Run BEFORE starting the apps.
set -e
cd "$(dirname "$0")/.."
[ $# -eq 2 ] || { echo "usage: $0 academic_reading_eng.sql academic_reading_v1.sql" >&2; exit 1; }
docker compose up -d --wait mariadb_academic_reading mariadb_academic_reading_v1
docker compose exec -T mariadb_academic_reading sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" academic_reading_eng' < "$1"
docker compose exec -T mariadb_academic_reading_v1 sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" academic_reading_v1' < "$2"
echo "restored. now: docker compose up -d --build"
