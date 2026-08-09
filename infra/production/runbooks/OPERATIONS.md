# Operación etapa 10B

## Puesta en marcha

Copiar `env.example` a `.env`, crear archivos bajo `secrets/`, validar con `docker compose --env-file .env -f compose.yml config`, ejecutar `scripts/prepare.sh` y luego `docker compose up -d`. Ningún flag de canal se activa automáticamente.

## Estado y recuperación

- `python manage.py integration_status`
- `python manage.py list_integration_outbox --channel-id ID --status dead_letter --destination meta_whatsapp`
- `python manage.py requeue_integration_event UUID --kind outbox`
- `python manage.py chatwoot_reconcile_commercial_labels CONVERSATION_ID`

Requeue exige un UUID y afecta exactamente un dead-letter. No editar DB manualmente.

## Backup y restore

Ejecutar `backup/backup.sh` con `BACKUP_DEST` en almacenamiento externo montado. Verifica ambos dumps, media y storage mediante `SHA256SUMS`. `restore/restore.sh` bloquea destinos cuyo nombre contenga `prod` y exige confirmación `ALLOW_RESTORE=YES`.

Prueba local: crear DB descartable, migrar, insertar datos TEST, ejecutar backup, recrear DB, restaurar, ejecutar `manage.py migrate --check` y comparar conteos/constraints. Nunca usar Chatwoot sandbox.

## RPO/RTO

Objetivo: RPO 15 min, RTO 4 h. Estado 10B: scripts de snapshot disponibles; RPO depende de frecuencia configurada y no cumple 15 min por sí solo. Próximo paso productivo: backups continuos WAL/PITR hacia destino externo, monitoreo y simulacro trimestral de restore. RTO 4 h sigue objetivo no demostrado hasta simulacro en VPS.

## HSTS

`SECURE_HSTS_SECONDS=0` deliberado antes de validar HTTPS y dominios reales. Elevar gradualmente después del despliegue verificado; activar subdominios/preload solo tras auditoría.
