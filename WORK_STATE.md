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

## ETAPA 7 — PARCIAL / BLOQUEADA PARA SMOKE REAL

- Takeover Chatwoot, pausa segura, outbox Meta, sender idempotente, gate legacy y proyección live TEST implementados.
- Carreras críticas validadas en PostgreSQL 16 aislado: 4/4 OK.
- Sin migración nueva; constraints existentes reutilizadas.
- Smoke real bloqueado: `CHATWOOT_STAGE7_TEST_CHANNEL_ID` no está configurado y no existe evidencia objetiva de un recipient WhatsApp TEST seguro.
- Flags peligrosos permanecen apagados; no hubo envío Meta real ni uso de cliente real.
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

## ETAPA 7 — PARCIAL: corrección de identidad WhatsApp

- Takeover real Chatwoot `message_id=11`: conversación 47 pasó de `BOT_ACTIVO` a `ASESOR_ACTIVO`; permanece en asesor y con bot pausado.
- Meta aceptó outbound humano y luego informó `failed`, error `131047` (`Re-engagement message`); outbox histórica no fue alterada ni reintentada.
- Inbound TEST `Ok` llegó con formato sin `+`, mientras Cliente 90 estaba almacenado en E.164.
- Bug creó Cliente 91, Lead 101 y conversación 48 en estado bot; identidad duplicada produjo respuesta automática después del takeover.
- Corrección: identidad comparativa solo dígitos, escritura E.164 y resolución transaccional por canal; PostgreSQL usa advisory lock por identidad.
- Artefactos TEST reconciliados: inbound y registro legacy conservados y repuntados a Cliente 90/conversación 47; duplicados 91/101/48 eliminados tras auditar relaciones.
- Flags peligrosos apagados durante corrección. ETAPA 7 continúa PARCIAL hasta nuevo smoke autorizado.

## ETAPA 7 — COMPLETADA

- Takeover humano, pausa segura del bot, Chatwoot → Meta y live sync validados de extremo a extremo con Cliente TEST 90, canal 7 y conversación Django 47 / Chatwoot 2.
- Ownership final conservado: `ASESOR_ACTIVO`, `control_version=3`, `estado_atencion=asesor`, `bot_pausado=true`.
- Entregas humanas físicas confirmadas al WhatsApp TEST terminado en 320 para Chatwoot `message_id=12` y `message_id=14`; un outbox y un Meta send por mensaje, con provider message ID persistido.
- Replay de ambos mensajes Chatwoot: cero IntegrationMessage, outbox y Meta sends adicionales.
- Inbound post-takeover `TEST CLIENTE DESPUES TAKEOVER 2` resolvió Cliente 90 / conversación 47, sin identidad ni conversación paralela, sin IA, BotGeneration, bot outbox o bot HTTP Meta.
- Live sync proyectó únicamente ese inbound como `incoming` a Chatwoot conversation 2; mapping único y webhook de retorno clasificado `django_projection` / `ignored`.
- Defecto descubierto y corregido durante smoke: live sync ahora reutiliza account/inbox del `ConversationMapping` activo en vez del inbox global; regresión focal incluida.
- Gate físico legacy BOT validado: bloqueo antes de HTTP mientras ownership pertenece al asesor; outbound humano permanece permitido.
- PostgreSQL 16.14 aislado: suite focal 8/8 OK, carreras Stage 7 4/4 OK, identidad concurrente 2/2 OK y deadlocks finales 0.
- Sin migraciones nuevas. Sin commit ni push. ETAPA 8 no iniciada.
- Estado seguro final: takeover, agent-to-WhatsApp, live sync, Meta outbox y sync general apagados; Chatwoot y webhook permanecen habilitados.

## ETAPA 8 — COMPLETADA

- Implementada devolución explícita `ASESOR_ACTIVO → BOT_ACTIVO` mediante custom attribute de conversación `taxicarga_attention_control` (`Asesor` / `Bot`).
- Transición atómica directa: `control_version` incrementa una vez, `returned_at` se actualiza y estado operativo/Lead legacy vuelven a bot.
- Return bloqueado ante outbox humano `pending`, `retry` o `sending`; UI vuelve a reflejar `Asesor`. Estados terminales no bloquean.
- Contexto canónico usa `MensajeWhatsApp`, conserva autores cliente/bot/asesor, excluye sistema/private notes y separa historial de trigger nuevo.
- Ruta sandbox bot usa `IntegrationMessage → BotGeneration → IntegrationOutboxEvent → meta_sender`; generación IA fuera de locks.
- Webhook idempotente ampliado a `message_created` y `conversation_updated`; Django permanece source of truth y espejo no produce loop.
- Chatwoot local 4.16.2: definición custom attribute creada/reutilizada idempotentemente; una definición final y un webhook con ambas subscriptions.
- SQLite: 215/215 OK, 25 omitidas PostgreSQL-only. PostgreSQL 16 aislado: 24/24 focales OK; carreras Stage 8 5/5 OK.
- Defecto PostgreSQL hallado y corregido: lock de `ConversationControl` limitado a `self` para no bloquear relación nullable `conversation__lead`.
- Compatibilidad Chatwoot 4.16.2 validada con payload `conversation_updated` raíz, actor desconocido y cambio explícito `Asesor → Bot`.
- Smoke real sandbox aprobado: `ASESOR_ACTIVO → BOT_ACTIVO`, versión incrementada una vez, sin respuesta retroactiva ni loop.
- Inbound post-return fue trigger único; creó una generación y un outbox BOT. Respuesta Meta recibida físicamente en el WhatsApp TEST.
- Replay del return y del inbound: cero transiciones, generaciones, outboxes o envíos adicionales. Proyección Chatwoot regresó como `django_projection` ignorada.
- Sin migraciones nuevas. ETAPA 9 no iniciada.
- Estado seguro final requerido: return-to-bot, takeover, agent-to-WhatsApp, live sync, Meta outbox y sync general apagados; Chatwoot y webhook habilitados.

## ETAPA 9 — COMPLETADA

- Estado comercial canónico preservado en `ConversacionWhatsApp.estado_cotizacion`.
- Modelos comerciales existentes reutilizados; no se creó otro sistema de cotizaciones.
- Cotización automática y humana producen evidencia estructurada y un outbox Meta idempotente por revisión.
- Envío humano garantiza takeover; envío bot conserva barreras de ownership/version de ETAPAS 7/8.
- Éxito Meta sincroniza revisión, cotización, solicitud, conversación y Lead compatible; fallo no marca `precio_enviado`.
- Labels `por-cotizar` y `cotizado` se proyectan Django → Chatwoot preservando labels ajenas; cambios manuales no son authoritative.
- Migración `cotizador.0010_stage9_commercial_flow` validada reversible en PostgreSQL 16.14 aislado.
- Smoke sandbox real completado con Cliente TEST 90, canal 7 y conversación 47.
- Caso humano: revisiones preservadas; takeover único; cotización recibida físicamente; replay sin duplicados.
- Caso automático: pricing existente, estructura comercial y BOT outbox; cotización recibida físicamente; replay sin duplicados.
- Reconciliación Chatwoot corregida para reprocesar proyecciones previamente enviadas y restaurar drift de labels.
- Migración `0010` aplicada solo en SQLite local dev; backup temporal fuera del repositorio.
- Flags peligrosos apagados al cierre. ETAPA 10 no iniciada.
