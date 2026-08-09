#!/usr/bin/env sh
set -eu

: "${BACKUP_DEST:?BACKUP_DEST is required}"
: "${COMPOSE_FILE:=../compose.yml}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DEST}/${stamp}"
mkdir -p "$target"

docker compose -f "$COMPOSE_FILE" exec -T taxicarga_db pg_dump -U taxicarga_app -d taxicarga_prod -Fc > "$target/taxicarga.dump"
docker compose -f "$COMPOSE_FILE" exec -T chatwoot_db pg_dump -U chatwoot_app -d chatwoot_prod -Fc > "$target/chatwoot.dump"
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -v "$target:/backup" taxicarga_web sh -c 'tar -C /app/datos_privados/media -czf /backup/django-media.tar.gz .'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -v "$target:/backup" chatwoot_rails sh -c 'tar -C /app/storage -czf /backup/chatwoot-storage.tar.gz .'
(cd "$target" && sha256sum *.dump *.tar.gz > SHA256SUMS)
printf 'backup=%s status=ok\n' "$target"
