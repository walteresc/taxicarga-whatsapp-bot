#!/bin/bash
set -e

echo "[entrypoint] Waiting for PostgreSQL..."
while ! pg_isready -h $DB_HOST -U $DB_USER -d $DB_NAME -t 1; do
    sleep 1
done
echo "[entrypoint] PostgreSQL ready"

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput

echo "[entrypoint] Starting application..."
exec "$@"
