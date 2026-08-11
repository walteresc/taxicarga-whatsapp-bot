# Estado de trabajo

## PLAN FUNCIONAL LOCAL - FASES 1-16 COMPLETADAS

- Ruta canonica `LeadUbicacion`: origen, 0..N paradas y destino; orden y extremos
  unicos. Campos legacy permanecen como espejo de compatibilidad controlado.
- Migracion `leads.0013` incluye backfill sin inventar valores. PostgreSQL 16.9:
  apply, rollback y reapply OK.
- Accesos persisten por ubicacion. Extractor soporta rutas 2..N, datos agrupados y
  eliminacion inequivoca de parada.
- Carga tiene API canonica compatible. Operarios conservan booleano y cantidad.
  Embalaje, desarmado y armado son independientes; defaults mudanza aplicados.
- Multiparada permanece `por_cotizar`/asesor: no existe regla comercial autorizada.
  `_distance_cost()` sigue cero: no hay tarifa historica inferible sin inventar.
- Aceptacion se liga idempotentemente a ultima revision realmente enviada.
- Reserva bot exige revision enviada/aceptada y booking completo; crea `Servicio`
  transaccional e idempotente. `ServicioUbicacion` conserva snapshot operativo.
- `ProgramacionServicio` no se crea: requiere asignacion operativa humana existente.
- Dashboard muestra ruta, accesos, carga, operarios, adicionales y reserva.
- Chatwoot recibe proyeccion por outbox y `ConversationMapping`; Django manda.
- Migracion `servicios.0005`: PostgreSQL apply, rollback y reapply OK.
- PostgreSQL focal: 3/3 OK. Focal dominio/dashboard/IA: 245/245 OK.
- Suite completa: 580/580 OK; 33 omitidas PostgreSQL-only.
- Quality gate completo OK.
- Externas: Meta=0, OpenAI tests=0, VPS/DNS/deploy/push=0. ETAPA 10C no iniciada.

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

## ETAPA 10A — COMPLETADA

- Política de integración tipada y fail-closed por `WhatsAppChannel`; flags globales conservados como kill switches.
- Runtime Chatwoot resuelve account/inbox mediante mapping activo; runtime Meta exige canal activo y su `phone_number_id`, sin fallbacks globales.
- Inbound desconocido o inactivo se confirma sin procesar, crear identidad o enviar; logs operativos sanitizados.
- Ownership, outbox, takeover, return-to-bot, labels e identidad validados con aislamiento entre canales A/B.
- SQLite: 555/555 OK, 33 omitidas PostgreSQL-only. PostgreSQL 16.14 aislado: 31/31 focales OK, deadlocks 0 y contaminación cruzada 0.
- Migración `integrations.0004_channelintegrationpolicy` validada apply/rollback/reapply; no crea políticas habilitadas.
- Ningún canal real activado; cero llamadas reales Meta/Chatwoot. ETAPA 10B no iniciada.

## ETAPA 10B — COMPLETADA

- Infraestructura productiva reproducible bajo `infra/production`: Caddy 2.10.0, Django/Gunicorn, worker Django, PostgreSQL TaxiCarga 16.9, Chatwoot 4.16.2, PostgreSQL Chatwoot 16 y Redis 7.4.5.
- Solo Caddy publica 80/443; bases, Redis, Django y Chatwoot permanecen privados en redes separadas.
- `config.settings_production` exige `DEBUG=False`, clave, PostgreSQL, hosts, orígenes CSRF y versión Meta; soporta secretos `VAR`/`VAR_FILE` y conserva flags/policies OFF.
- Worker permanente con batch/intervalo configurables, señales SIGTERM/SIGINT, recuperación de locks, aislamiento por evento y heartbeat PostgreSQL (`integrations.0005_workerheartbeat`).
- Health `/health/live` y `/health/ready`; 404 real; static con WhiteNoise/collectstatic y media persistente.
- Operaciones seguras: status, listado filtrado de outbox, requeue individual por UUID y reconciliación existente por conversación/canal.
- Logging productivo solo stdout/stderr, rotación Docker y filtro de teléfono/tokens.
- Backups para ambas bases, media y Chatwoot storage con timestamp/checksum; restore exige destino explícito y bloquea nombres productivos.
- Restore PostgreSQL TaxiCarga probado en DB descartable: checksum válido y 69/69 migraciones restauradas.
- RPO objetivo 15 min y RTO objetivo 4 h documentados; snapshots no demuestran todavía objetivos. WAL/PITR y simulacro VPS quedan pendientes.
- Permisos P0 productivos endurecidos con `STRICT_ADMIN_OPERATIONS=True`; desarrollo legacy conserva compatibilidad.
- Migración heartbeat validada en PostgreSQL 16.9: apply/rollback/reapply OK.
- `check --deploy`: solo warning HSTS esperado; `SECURE_HSTS_SECONDS=0` deliberado antes de HTTPS real.
- `docker compose config` OK; única publicación 80/443. Dry-run aislado OK: build, Gunicorn, PostgreSQL, migrate, collectstatic, worker, health y Caddy.
- Chatwoot productivo validado por Compose; no levantado para proteger sandbox existente.
- Suite focal 10B 6/6 OK; regresiones 7/8/9/10A 42/42 OK; suite completa 561/561 OK, 33 PostgreSQL-only omitidas.
- Acciones externas: Meta sends=0, Chatwoot productivo calls=0, DNS/VPS=0. Canales/policies habilitados=0.
- Checkpoint Git 10B preparado sin push. ETAPA 10C no iniciada.

## PLAN FUNCIONAL LOCAL — FASE 0 COMPLETADA

- Bot conversacional separado en extractor, estado Django, policy determinística,
  pricing y generador de respuesta.
- `quote_missing_fields` y `booking_missing_fields` son contratos canónicos.
- Mudanza aplica defaults efectivos: operarios sí, embalaje no, desarmado no y
  armado no conceptual; afirmaciones explícitas prevalecen.
- Preguntas agrupadas por objetivo semántico; fecha, nombre, DNI, hora y
  direcciones exactas no bloquean cotización.
- Correcciones de ruta simple y rutas con paradas detectadas; multiparada se
  deriva de forma segura mientras no exista modelo canónico.
- Reserva no afirma creación operacional inexistente.
- Telemetría sanitizada sin prompts, teléfonos completos ni chain-of-thought.
- SQLite: IA 89/89 OK; suite completa 573/573 OK, 33 PostgreSQL-only omitidas.
- Sin migraciones. Acciones externas 0. ETAPA 10C no iniciada.
- Siguiente fase: modelo canónico de ubicaciones y snapshots operacionales.
# P0 webhook resiliente / Chatwoot asíncrono (2026-08-10)

- Webhook ya no ejecuta HTTP Chatwoot. Inbound canónico crea outbox durable e idempotente.
- Worker procesa `sync_inbound_message`; HTTP ocurre fuera de transacciones/locks Django.
- BotGeneration fallida o abandonada puede reclamarse; error guardado solo como clase sanitizada.
- Tests P0 y regresiones focales: 33 verdes. Suite: 584 descubiertos; 1 fallo histórico sensible a fecha en `test_dia_de_semana_se_confirma_antes_de_reservar`.
- PostgreSQL TaxiCarga dedicado no disponible; contenedores 5432 pertenecen a Mionca/Chatwoot y quedaron intactos.
- MensajeWhatsApp 15 recuperado en Lead TEST 106. Ruta Surco→Miraflores, carga y ubicaciones persistidas; generación publicada.
- Meta outbox nuevo queda `pending`, attempts=0. Envíos Meta durante fix: 0. Worker detenido para impedir despacho.
- Mensaje inbound y contexto proyectados a Chatwoot correctamente.

# Corrección previa a prueba manual (2026-08-10)

- Corregida confusión semántica: cantidades (`15 cajas`, operarios, peso) ya no
  se aceptan como piso sin evidencia explícita de piso/planta/nivel.
- Extracción IA de pisos también queda protegida por evidencia textual.
- Detalle de carga canónico para el caso TEST: `Cama, refrigeradora y aprox. 15 cajas`.
- Lead 106 reparado: Surco a Miraflores; pisos vacíos; faltan pisos y accesos de
  ambos extremos. Respuesta BOT preparada, no enviada.
- Contexto Chatwoot TEST reproyectado y label comercial obsoleto `cotizado` retirado.
- Conversación Chatwoot existente preservada: la identidad productiva reutiliza la
  conversación abierta del mismo cliente/canal; no se borró evidencia histórica.
- Regresión P0 corregida: ownership humano se evalúa antes de return-to-bot.
- Suite completa: 587/587 OK; 33 omitidas PostgreSQL-only. `check`, migraciones y
  `git diff --check`: OK.
- Meta sends durante corrección: 0. Worker Meta detenido. Sin push.

# Multi-provider IA + harness A/B (2026-08-10)

- Abstracción `AIProvider` implementada para OpenAI y DeepSeek mediante Responses API.
- OpenAI conserva `gpt-4.1-mini` y comportamiento previo; provider principal,
  extracción y conversación permanecen en `openai`.
- DeepSeek preparado con `deepseek-v4-flash`, base oficial y thinking deshabilitado;
  reasoning no se expone ni persiste.
- Extracción y conversación pueden seleccionar provider/modelo independientemente.
- Fallos usan fallback determinístico local; no existe fallback cross-provider.
- Harness local protegido por `--confirm-real-api`; dataset TEST anonimizado: 20
  casos de extracción y 8 conversacionales. Costos usan tarifas configurables.
- Tests provider 13/13 OK. Suite completa 600/600 OK; 33 omitidas.
- A/B real no ejecutado. Llamadas externas IA: 0. Secretos expuestos: 0. Sin push.

## A/B real ejecutado (2026-08-10)

- Dataset sin cambios: 20 extracción + 8 conversación por proveedor.
- Corrida válida: OpenAI F1 exacto 0.875; DeepSeek 0.8781. Ambos 0 schema/API errors.
- OpenAI: latencia media 3297.92 ms, 22,448 tokens, costo estimado USD 0.013466.
- DeepSeek: latencia media 9523.91 ms, 55,329 tokens, costo estimado USD 0.01230656.
- DeepSeek devolvió 32,575 output tokens pese a `thinking.type=disabled`; Responses API
  parece seguir contabilizando reasoning. No apto aún para cambio operativo.
- Ambos evitaron `15 cajas`, operarios y `800 kg` como pisos; ambos fallaron acceso
  de camión y multidato ambiguo. OpenAI perdió negación contextual; DeepSeek añadió
  `refri` como objeto pesado y usó lenguaje de precio sin `pricing_result`.
- Primera corrida completó APIs pero falló al serializar una fecha; se corrigió
  `default=str` y se repitió. Costo total incurrido estimado: USD 0.05154512.
- Recomendación: mantener OpenAI; no híbrido; ampliar/corregir dataset y resolver
  non-thinking DeepSeek antes de otra decisión. Providers operativos no cambiaron.
- Tests focales harness/providers: 13/13 OK. Worker detenido. Sin WhatsApp ni push.

# Cierre pipeline real `15 cajas` (2026-08-10)

- Causa confirmada: regex de piso aceptaba números desnudos dentro del segmento de
  destino; `15 cajas` terminó como piso 15. Merge IA también carecía de barrera de
  evidencia semántica. Fix funcional está en `dc6e65b`.
- Test E2E nuevo pasa el mensaje físico exacto por webhook y simula además una IA
  que propone `piso_destino=15`; merge lo rechaza, persiste ruta/carga/defaults y
  crea `LeadUbicacion` sin pisos.
- Lead 106 verificado: mudanza Surco→Miraflores, carga limpia, pisos/accesos vacíos,
  defaults correctos, precio vacío y respuesta preparada natural.
- Chatwoot conversation TEST 2 verificada por lectura real: atributos correctos,
  accesos/precio vacíos y labels `[]`; `cotizado` era residuo sandbox ya conciliado,
  no bug comercial activo. Evidencia histórica conservada.
- Regresiones focales: 435/435 OK; 33 omitidas. Suite completa: 601/601 OK;
  33 PostgreSQL-only omitidas.
- Meta sends: 0. Outbox permanece pending, attempts=0. Worker detenido. Sin push.
