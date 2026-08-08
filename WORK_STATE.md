# Estado de trabajo

## ETAPAS 1–3

- Implementadas, auditadas y aprobadas por el usuario.
- ETAPA 3 verificada en SQLite y PostgreSQL 16.14 aislado, incluida concurrencia real.
- Integraciones externas y feature flags apagados.

## ETAPA 4

- Estado: COMPLETADA.
- Implementada la base del cliente Django para Chatwoot Application API.
- Incluye configuración segura, operaciones de account/inbox, health check y creación o reutilización de una inbox API sandbox.
- Incluye comandos `chatwoot_check` y `chatwoot_setup_sandbox`.
- Pruebas locales con HTTP simulado aprobadas.
- Smoke test real Django → Chatwoot aprobado contra Account 1 (`Taxi Carga`).
- Inbox API `TaxiCarga Sandbox`, ID 1, creada y reutilizada idempotentemente.
- Sin llamadas a Meta, mensajes, contactos ni conversaciones reales. Sin activación operativa.

## Límites vigentes

- `CHATWOOT_ENABLED` permanece apagado por defecto en configuración versionada; habilitado solo en `.env` local para ETAPA 4.
- No se implementó webhook Chatwoot, sincronización completa, envío al cliente ni control bot/asesor.
- ETAPA 6 iniciada; estado detallado abajo.

## ETAPA 6

- Estado: COMPLETADA.
- Endpoint `POST /webhooks/chatwoot/` firmado con HMAC-SHA256 sobre timestamp y raw body.
- Replay protegido por `X-Chatwoot-Delivery` y por identidad `message_created:<message_id>` usando `IntegrationInboxEvent`.
- Clasificaciones validadas: `django_projection`, `human_agent`, `private_note`, `unmapped_conversation`, scopes incorrectos y eventos no soportados.
- Webhook sandbox real `TaxiCarga Django Sandbox`, suscrito solo a `message_created`; setup ejecutado idempotentemente y secret guardado solo en `.env` local.
- Smoke real `django_projection`: evento ignorado, cero mensajes de asesor y cero outbox Meta.
- Smoke manual UI Chatwoot `human_agent` validado: un `IntegrationMessage` para el message ID verificado, un `IntegrationInboxEvent` logico, cero outbox Meta y cero envios WhatsApp.
- Carrera webhook validada en PostgreSQL 16.14 aislado: dos deliveries concurrentes para el mismo message producen un evento y un mensaje logico.
- Sin modelos ni migraciones nuevas. Constraints existentes suficientes.
- Estado local: `CHATWOOT_ENABLED=true`, `CHATWOOT_SYNC_ENABLED=false`, `CHATWOOT_WEBHOOK_ENABLED=true` para sandbox.
- Meta y webhook WhatsApp intactos. ETAPA 7 no iniciada.

## ETAPA 5

- Estado: COMPLETADA.
- Proyección unidireccional Django → Chatwoot implementada; Django conserva autoridad canónica.
- Smoke test real limitado a datos `TEST`: Cliente Django 89 y conversación Django 46.
- Contacto Chatwoot 1, conversación Chatwoot 1 y dos mensajes de texto proyectados en `TaxiCarga Sandbox`.
- Segunda ejecución: 0 contactos, 0 conversaciones y 0 mensajes nuevos.
- Mappings persistentes e idempotencia bajo carrera validados en PostgreSQL 16.14.
- Recuperación tras fallo parcial validada por tests.
- `CHATWOOT_SYNC_ENABLED` apagado por defecto en configuración versionada; habilitado localmente solo para smoke test.
- Meta y webhook WhatsApp intactos. Ningún mensaje WhatsApp enviado.
- ETAPA 6 completada.
