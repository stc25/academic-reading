#!/bin/sh
set -e

# Apply Django migrations. Safe to run on every start — migrate is idempotent.
if [ -n "${DATABASE_URL:-}" ]; then
  max_attempts="${DB_READY_MAX_ATTEMPTS:-60}"
  sleep_seconds="${DB_READY_SLEEP_SECONDS:-2}"
  for attempt in $(seq 1 "$max_attempts"); do
    if python /app/manage.py migrate --noinput; then
      break
    fi
    if [ "$attempt" -eq "$max_attempts" ]; then
      exit 1
    fi
    echo "Database not ready yet (attempt $attempt/$max_attempts); retrying in ${sleep_seconds}s..." >&2
    sleep "$sleep_seconds"
  done
else
  python /app/manage.py migrate --noinput
fi

# Collect static files so whitenoise can serve them with DEBUG=false.
python /app/manage.py collectstatic --noinput

exec gunicorn \
  --bind 0.0.0.0:8000 \
  --workers "${APP_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-180}" \
  --access-logfile - \
  academic_reading_django.wsgi:application
