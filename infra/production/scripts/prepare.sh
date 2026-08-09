#!/usr/bin/env sh
set -eu
docker compose --env-file "${ENV_FILE:-.env}" -f compose.yml run --rm taxicarga_web python manage.py migrate --noinput
docker compose --env-file "${ENV_FILE:-.env}" -f compose.yml run --rm taxicarga_web python manage.py collectstatic --noinput
