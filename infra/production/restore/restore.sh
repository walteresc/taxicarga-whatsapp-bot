#!/usr/bin/env sh
set -eu

: "${RESTORE_SOURCE:?RESTORE_SOURCE is required}"
: "${RESTORE_TARGET:?RESTORE_TARGET must name an explicit non-production target}"
: "${ALLOW_RESTORE:?Set ALLOW_RESTORE=YES after verifying the target}"
[ "$ALLOW_RESTORE" = "YES" ] || { echo "ALLOW_RESTORE must equal YES" >&2; exit 2; }
case "$RESTORE_TARGET" in *prod*|production) echo "Production restore blocked by this helper" >&2; exit 2;; esac
(cd "$RESTORE_SOURCE" && sha256sum -c SHA256SUMS)
: "${PGHOST:?PGHOST is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"
pg_restore --exit-on-error --clean --if-exists --no-owner --dbname="$PGDATABASE" "$RESTORE_SOURCE/$RESTORE_TARGET.dump"
printf 'restore_target=%s database=%s status=ok\n' "$RESTORE_TARGET" "$PGDATABASE"
