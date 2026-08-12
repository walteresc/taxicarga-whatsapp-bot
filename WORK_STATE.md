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

## Ajuste UX accesos (2026-08-10)

- Fallback `collect_access` pregunta pisos y ascensores de ambos extremos; agrega
  cercanía del camión solo cuando contrato de faltantes la requiere.
- Focales afectados: 25/25 OK.
- Respuesta TEST del mensaje 15 sustituida sobre misma generación/mensaje lógico;
  outbox único preservado pending, attempts=0. Meta sends=0. Worker detenido.

## Fix semántico Message 17 (2026-08-11)

- Corregida propagación de evidencia de ascensor entre extremos: una negación
  asociada al destino ya no completa también el origen.
- Pregunta de accesos usa distritos conocidos y aclara estacionamiento ambiguo sin
  volver a pedir pisos ni asumir acceso del camión.
- Regresión exacta MessageWhatsApp 17 agregada. Suite completa: 604/604 OK; 33
  omitidas. Cero llamadas externas en tests.
- Lead 106: Surco piso 3/ascensor desconocido; Miraflores piso 2/sin ascensor.
  Estacionamiento a una cuadra conservado como observación, ubicación por aclarar.
- Dead-letter obsoleto conservado sin reencolar. Nueva generación/outbox canónicos
  creados idempotentemente; segundo procesamiento creó cero registros.
- Contexto Chatwoot proyectado: control Bot, precio vacío, labels vacíos. Token
  Meta y Phone Number ID TEST 7 validados mediante GET. Worker general detenido.

## IA-first Fase 0/1 shadow (2026-08-11)

- Causa del 401 de Message 19: proceso Django antiguo heredó la variable global
  OpenAI antes de eliminarla; `python-decouple` priorizó process environment sobre
  `.env`. No existía cliente IA singleton, pero settings quedaban fijos al arranque.
- Django reiniciado sin variable heredada; credencial tomada de `.env` TaxiCarga.
  Prueba por el provider real: OpenAI + `gpt-4.1-mini` autenticaron correctamente.
- Contrato delta Pydantic estricto, snapshot canónico versionado, contexto compacto,
  referencias de ubicación, validación semántica y auditoría sanitizada agregados.
- Shadow durable: webhook solo encola evento interno idempotente; worker procesa el
  evento exacto. Nunca aplica el delta ni altera Lead, pricing o decisiones.
- Flags: `AI_DELTA_EXTRACTION_ENABLED=false`, `AI_DELTA_SHADOW_MODE=true`. Pipeline
  operativo permanece legacy; servidor vivo no fue reiniciado con el nuevo código.
- Focales IA: 40/40 OK, fake provider, cero APIs. Suite completa intentada: 619;
  bloqueada por 220 errores preexistentes de registro duplicado `drf_format_suffix`
  entre routers y 1 aserción Chatwoot posterior; 33 omitidas.
- Migraciones sin drift; `git diff --check` OK. Meta sends: 0. Worker detenido.

## P0 entorno URL/DRF + flags shadow (2026-08-11)

- Bloqueo `drf_format_suffix` no provenía del código ni de `d9f1a1b`: comandos
  corrieron por error con Python global (Django 6.0.8, DRF 3.14.0, sin WhiteNoise).
- Entorno correcto `.venv`: Python 3.14.0, Django 6.0.6, DRF 3.17.1 y dependencias
  de `requirements.txt`. No fue necesario modificar URLConf ni paquetes.
- `manage.py check`: OK. URL/API 30/30; IA-first 42/42; Chatwoot aislado 1/1;
  integrations 170/170; suite completa 621/621 OK, 33 PostgreSQL-only omitidos.
- Fallo Chatwoot previo fue cascada/contaminación del entorno incorrecto.
- Flags desacoplados: `AI_DELTA_SHADOW_MODE=true` encola auditoría shadow aunque
  `AI_DELTA_EXTRACTION_ENABLED=false`; delta nunca se aplica a Lead, pricing,
  ConversationDecision ni respuesta. Meta sends: 0. Worker detenido.

## Fase 2 comparación shadow (2026-08-11)

- Harness no persistente + dataset anonimizado de 20 casos agregados. Legacy medido
  con `extract_lead_data` determinístico; autorización OpenAI usada solo para delta.
- Legacy: 4/20 casos, precision 0.7368, recall 0.4000, F1 0.5185, 16/20 seguros.
- IA-first: 13/20 casos, precision 0.6875, recall 0.9429, F1 0.7952, 13/20 seguros;
  20/20 schemas válidos, cero API errors.
- IA-first ganó comprensión, pero perdió semantic safety: sobreinfirió 15 campos y
  falló Message 17 al propagar ascensor/acceso/100 m sin evidencia ni ambigüedad.
- Message 19 real, sin persistir: origin elevator=true, destination elevator=false,
  observación de estacionamiento lejano en destination; delta repitió estado conocido.
- Uso dataset: 18,571 input + 2,208 output = 20,779 tokens; latencia media 6.62 s,
  mediana 3.68 s, p95/máxima 24.06 s. Costo estimado USD 0.0109612 usando tarifas
  oficiales GPT-4.1 mini; USD 0.54806 por 1,000 extracciones.
- Recomendación: revisar arquitectura/contrato delta antes de ampliar shadow; no
  activar operativo. Suite 623/623 OK; 33 omitidas. Meta sends 0. Worker detenido.

## Fase 3 IA-first Delta V2 (2026-08-11)

- Contrato V2 exige valor, evidencia anclada y tipo `explicit`,
  `explicit_contextual` o `inferred`; validador acepta las dos primeras y rechaza
  inferencias, referencias ambiguas, normalizaciones no sustentadas y no-ops.
- Dataset ampliado de 20 a 40 casos. Benchmark real GPT-4.1-mini: raw precision,
  recall y F1 0.9016; seguridad 37/40. Accepted: precision 1.0000, recall 0.9492,
  F1 0.9739 y seguridad 40/40. Legacy: F1 0.4651 y seguridad 36/40.
- Message 15/17/19 pasan. Message 17 conserva estacionamiento como ambigüedad;
  Message 19 acepta solo ascensor origen y observación acceso destino.
- Rechazos: `AMBIGUOUS_REF` 7, `NO_OP` 15, `INFERRED_NOT_ALLOWED` 6. Cero valores
  numéricos inventados y cero propagaciones a endpoint incorrecto tras validador.
- 40 requests: 59,206 input + 6,974 output = 66,180 tokens; costo estimado USD
  0.0348408. Provider avg 8.46 s, mediana 4.15 s, p95 24.03 s, máxima 43.35 s;
  validador avg 0.0842 ms en replay final.
- Flags siguen `AI_DELTA_EXTRACTION_ENABLED=false` y `AI_DELTA_SHADOW_MODE=true`.
  Meta sends 0. Worker detenido. Recomendación: ampliar shadow; no activar aún.

## Fase 4 holdout ciego: bloqueada por OpenAI 401 (2026-08-11)

- Tooling holdout agregado: 100 casos distintos de Fase 3, 40 mensajes históricos
  anonimizados y 60 sintéticos; 45 casos multiturno. Expected/forbidden/IDs nunca
  entran al payload del modelo ni al validador, cubierto por test automático.
- Primera corrida mantuvo prompt, schema y validator V2 congelados. Los 100 requests
  holdout y 30 requests de repetición devolvieron `AuthenticationError` HTTP 401.
  Cero respuestas exitosas, tokens observados o costo estimable; generalización y
  latencia quedaron no determinables. No se cambió credencial, provider ni modelo.
- Auditoría cliente: se crea `OpenAI` nuevo por request, por tanto no reutiliza pool
  entre extracciones; SDK usa `max_retries=2` por defecto y timeout configurado 30 s.
  Retry real por request no es observable con instrumentación actual.
- Focales holdout/V2: 15/15 OK; IA, integrations y suite completa verdes. Meta sends
  0, worker detenido. Requiere restaurar credencial OpenAI antes de repetir Fase 4.

## V2 evidence run para diseño V3 (2026-08-11)

- Harness inmutable JSONL agregado. Run completo:
  `reports/ai_eval/20260811T192932Z_delta_v2_evidence/` (ignorado por Git, no
  eliminado). Dataset SHA-256 inicial/final:
  `95eadd86d6875bdec3e7b3f8d315c363c8c719d8bfdc9a9178504ba39f5c7364`.
- 100/100 API y schemas válidos. Raw: precision 0.8919, recall 0.8250, F1 0.8571,
  safety 88/100. V2 accepted: precision 0.9074, recall 0.8167, F1 0.8596,
  safety 90/100.
- Evidencia reconstruible: 10 accepted unsafe (7 attribute/field closure, 2
  contextual specificity, 1 endpoint ambiguity) y 1 false rejection por propuesta
  contextual correcta etiquetada por modelo como `inferred`. Validator bloqueó 2
  falsos positivos y agregó ese falso negativo.
- Tokens run completo: 147,152 input + 12,802 output = 159,954. Latencia avg 4.44 s,
  p50 3.11 s, p95 7.20 s, max 35.25 s. Validator V3 no implementado.

## Validator V3 offline + QuestionTarget (2026-08-11)

- `QuestionTarget(field, ref, operation)` nace en `ConversationDecision`, viaja en
  metadata de generación/mensaje y se persiste en `MensajeWhatsApp.question_targets`;
  `DeltaContext` lo consume sin parsear la pregunta visible.
- V3 clasifica fields, cierra respuestas contextuales al target, bloquea derivados,
  evita modalidad específica ante target `packing_required`, normaliza `inferred` a
  contextual solo cuando field/ref coinciden y conserva acceso sin endpoint como
  ambigüedad.
- Replay offline sobre run `20260811T192932Z_delta_v2_evidence`, cero APIs. Histórico
  no tenía targets: 0/100 disponibles; 45 casos contextuales afectados. V3 with s02:
  precision 0.9351, recall 0.6050, F1 0.7347, safety 95/100. Without s02: precision
  0.9333, recall 0.6034, F1 0.7330, safety 94/99.
- Unsafe aceptados bajan 10→5: 3 cierres de atributo pendientes y 2 especificidades
  de packing. Wrong endpoint aceptado 0; derived/numeric aceptado 0. Caída de recall
  es esperada al no inventar targets históricos. Requiere nuevo run GPT con metadata
  V3 real antes de juzgar recall o activación.
# FASE 6 - V3 model run preparation (2026-08-11)

- 100 casos anteriores reclasificados como `V3_DEVELOPMENT_SET`.
- `QuestionTarget` curado desde objetivo original: 45/100 disponible; 55 no aplicable; 0 contextual unavailable.
- Expected labels no usados para crear targets. `s02` sigue `LABEL_REVIEW_REQUIRED`.
- Prompt/schema/harness V3 preparados. Packing separado en `packing_required` y `packing_mode`.
- Fake V3: 15/15. Suites completas verdes antes del smoke.
- Smoke real detenido en caso 1/3: HTTP 401 `invalid_api_key`; 1 llamada intentada, 0 schema-valid.
- Casos 2 y 3 no ejecutados. V3 development run 100 no autorizado hasta corregir auth y repetir smoke.
- Runtime sigue legacy: `AI_DELTA_EXTRACTION_ENABLED=false`, `AI_DELTA_SHADOW_MODE=true`.

# P0 local environment isolation + V3 smoke (2026-08-11)

- Shell actual: process key presente, `.env` presente, igualdad confirmada; causa stale no reproducida.
- `run_local.ps1` elimina solo `OPENAI_API_KEY` heredada del proceso local y fija `.venv`.
- Precedencia de producción, `VAR_FILE` y Docker Compose sin cambios.
- Stale-parent fake test verde. Auth real por launcher: HTTP 200, `gpt-4.1-mini`.
- V3 smoke `20260811T205214Z_v3_smoke`: 3/3 schema y artifacts; 5311 tokens.
- s17 y s54 semánticamente correctos. s47 conserva observaciones, pero evaluator/label legacy
  exige `origin.truck_access=true`; gate medido queda 2/3. Run 100 todavía NO listo.

# FASE 6A - s47 access adjudication (2026-08-11)

- `truck_access` reclasificado como direct fact condicionado por procedencia; inferred sigue rechazado.
- `carry_distance_m` permanece derived/prohibido. Validator no interpreta español.
- s47 target corregido desde objetivo original a `truck_access/both`; expected no cambió.
- Observación asimétrica permitida como respuesta segura a target de acceso, sin fabricar boolean.
- Contrato fake: 20/20. Suite completa verde antes del único smoke real.
- Smoke real s47 `20260811T212154Z_v3_smoke`: PASS, TP=2, FP=0, FN=0,
  schema válido, 1833 tokens, costo estimado USD 0.0009828.
- READY para autorizar development run 100; todavía no ejecutado.

# FASE 6B/6C - V3 development + offline adjudication (2026-08-11)

- Development run `20260811T213255Z_v3_development_100`: 100/100 API y schema OK,
  174211 tokens, costo estimado USD 0.085414; runtime flags intactos.
- Original accepted: P 81.05%, R 64.17%, F1 71.63%, safety 82/100.
- Canonical evaluator offline: packing legacy/V3 normalizado sin mutar labels ni runtime.
- Canonical raw: P 89.34%, R 83.85%, F1 86.51%, safety 87/100.
- Canonical accepted: P 90.53%, R 66.15%, F1 76.44%, safety 91/100.
- Human review: s02, s16, s25, s53. Excluding: accepted P 91.21%, R 66.94%,
  F1 77.21%, safety 88/96.
- Rejections adjudicados: 18 correctos, 16 falsos. V3.1 todavía no implementado.
- FASE 6C nuevas API calls: 0.

# FASE A-D - IA-first V3.1 release candidate (2026-08-11)

- Contrato V3.1 exige `evidence_quote` literal del mensaje actual; separa tipo de
  evidencia, dependencia contextual, provenance de endpoint y origen de medidas.
- Snapshot no es evidencia. Delta mínimo, NO_OP y corrections independientes.
- QuestionTarget prioriza respuesta contextual sin bloquear hechos explícitos extra.
- Guards fail-closed: evidencia parafraseada, endpoint no verificable, claims
  ambiguos, medidas derivadas y colisiones contextuales se rechazan.
- Service/load/staff y packing required/mode permanecen separados. `service_date`
  soportado sin volver fecha requisito de cotización.
- Smoke final: 10/10 schema, 9/10 semántica, cero autoridad comercial.
- Development 100 real final: 100/100 API/schema. Raw P 92.25%, R 91.54%,
  F1 91.89%. Validator final re-evaluado offline sobre mismos raw: P 98.29%,
  R 89.15%, F1 93.50%, safety 98/100. Unsafe restantes pertenecen únicamente a
  HUMAN_REVIEW; wrong endpoint, numeric invention y commercial authority: 0.
- Runtime sigue sin activar: `AI_DELTA_EXTRACTION_ENABLED=false`,
  `AI_DELTA_SHADOW_MODE=true`. Meta sends 0; worker detenido.
- Candidata congelada antes de crear holdout ciego nuevo. Sin push.

## Holdout ciego V3.1 ronda 1 - FAIL / DEVELOPMENT EVIDENCE

- Dataset congelado antes de API: 100 sintéticos/adversariales nuevos, 50
  contextuales, 12 HUMAN_REVIEW, SHA-256
  `523df082a49d41ea1cadbdc6c7c7518ad4e9c0a4813a40ed56fd15bcb72b0849`.
- Históricos locales realmente disponibles: 7, todos ligados a pruebas previas;
  insuficientes/no ciegos para cuota de 40. No se reutilizaron como holdout.
- Run `20260811T234244Z_v31_blind_holdout_100`: schema 100/100; accepted P
  95.97%, R 77.30%, F1 85.63%, safety 94/100. HOLDOUT FAIL.
- Desde primera corrida, dataset deja de ser ciego. Solo se usó como development
  evidence. Causas generales: endpoint específico expandido a both, acceso de
  camión inferido desde estacionamiento, corrections contextuales rechazadas y
  service inferido desde lista de objetos.
- Guards posteriores: endpoint/polaridad/evidencia de service fail-closed;
  correcciones independientes; rechazo se promueve a ambiguity segura.
- Development raw más reciente revalidado con candidata actual: P 99.12%, R
  88.28%, F1 93.39%, safety 99/100; único unsafe pertenece a HUMAN_REVIEW.
- Se requiere holdout ciego ronda 2 distinto antes de integrar runtime.

## Holdouts V3.1 rondas 2/3 - FAIL (2026-08-12)

- Ronda 2: 100 casos disjuntos exactos, hash
  `fe71ab017d3cfffb4d719e0db60c95806c0bb3d74c8c250b7fb021a7318aba4d`.
  Accepted original P 98.68%, R 81.87%, F1 89.49%, safety 98/100; FAIL.
- Ronda 3: 100 casos disjuntos exactos, hash
  `8e5d729bd1d1c26147a0bdb4ef250941509af8ac7cd7b0e2266ba40fe8a461d8`.
  Accepted P 99.33%, R 81.32%, F1 89.43%, safety 99/100; FAIL.
- Ambos datasets dejan de ser ciegos y quedan solo como development evidence.
- Guards nuevos reducen endpoint/numeric invention; problema dominante es recall
  variable del modelo con respuestas contextuales y mensajes multi-field.
- Checklist general logró smoke 9/10, pero development real posterior quedó P
  98.18%, R 84.38%, F1 90.76%, safety 98/100 y 1 endpoint crítico: gate FAIL.
- IA-first runtime NO integrado/activado. Flags siguen OFF/shadow. Meta sends 0.
- Costo acumulado aproximado desde master: USD 1.43; límite autorizado USD 2.00.

## Holdouts V3.1 rondas 4-7 y bloqueo de presupuesto (2026-08-12)

- Rondas 4-6: FAIL; desde su primera corrida son development evidence. Ronda 6
  accepted P 98.82%, R 83.17%, F1 90.32%, safety 99/100, 1 unsafe crítico.
- Corrección general posterior: packing-only no puede fijar staff; refs
  `ambiguous` se conservan como ambiguity; complemento `both` + extremo
  específico se valida estructuralmente sin interpretar texto libre.
- Tests V3.1: 34/34. Smoke real `20260812T004425Z_v31_smoke`: schema 10/10,
  accepted P 100%, R 92.86%, F1 96.30%, safety 10/10, críticos 0.
- Development real `20260812T004508Z_v31_development_100`; replay offline con
  validator congelado: P 99.12%, R 88.19%, F1 93.33%, safety 99/100. Gate PASS.
- Holdout 7 congelado antes de API: 100 casos, 50 contextuales, 14 HUMAN_REVIEW,
  SHA-256 `473eefe54a1b42b5b3c4c76b03be8af07c0fd73bb333046829bc44fd1d2ac3d3`.
- Run `20260812T005436Z_v31_blind_holdout_round7_100`: schema 100/100;
  accepted P 100%, R 85.57%, F1 92.22%, safety 100/100; critical unsafe,
  wrong endpoint, numeric invention y commercial authority: 0. HOLDOUT FAIL.
- Ronda 7 deja de ser ciega y queda como development evidence. Runtime IA-first
  NO integrado ni activado; Meta sends 0; no push.
- Costo acumulado estimado desde master: USD 1.8487868 / USD 2.00. Restan
  USD 0.1512132. El siguiente ciclo obligatorio (smoke + development + nuevo
  holdout) costaría aproximadamente USD 0.26 y superaría el límite.
- HARD BLOCKER: ampliar presupuesto de evaluación antes de continuar FASE E.

### Auditoría offline posterior al bloqueo

- Holdout 7 no es evidencia válida de generalización: heredó labels de ronda 5
  después de reescribir superficies semánticas (ej. `veladores`/`mesas de
  noche`, números en palabras/dígitos). No se declara PASS ni se modifican sus
  expected post-run.
- Corrección arquitectónica offline: una `correction` con evidencia válida se
  materializa como delta atómico solo cuando field/ref se resuelve por path,
  marcador explícito o QuestionTarget. Ambigüedad sigue fail-closed.
- Tests V3.1 posteriores: 37/37 PASS. Nuevas llamadas API: 0.
- Holdout 8 preparado, todavía NO ejecutado ni congelado como examen: 100 casos,
  50 contextuales, 14 HUMAN_REVIEW, labels/superficie consistentes, disjunto de
  development y rondas 1-7. Hash provisional:
  `ebfe95c7a07fe065b170bed33ef3c82c13bd5dde629d95f14aa53ef85b84546b`.
- Sigue requerido ampliar presupuesto: el ciclo correcto incluye smoke,
  development y luego congelar/ejecutar holdout 8.

## Presupuesto USD 2.50 - holdouts 8/9 (2026-08-12)

- Usuario amplió presupuesto acumulado a USD 2.50. Holdout 7 formalmente
  `INVALIDATED_FOR_LABEL_INCONSISTENCY`; artifacts conservados.
- Smoke `20260812T012253Z_v31_smoke`: 9/10, safety 10/10, críticos 0.
- Dos development runs parciales terminaron en caso 90 por corrección vacía;
  artifacts de 89 casos conservados. Causa corregida fail-closed y testada.
- Development completo `20260812T013759Z_v31_development_100`: accepted P
  99.15%, R 91.34%, F1 95.08%, safety 99/100; críticos 0. PASS.
- Holdout 8 SHA-256
  `ebfe95c7a07fe065b170bed33ef3c82c13bd5dde629d95f14aa53ef85b84546b`,
  run `20260812T014422Z_v31_blind_holdout_round8_100`: P 95.83%, R 94.85%,
  F1 95.34%, safety 97/100, 2 critical unsafe. FAIL; consumido.
- Clasificación holdout 8: MODEL_ERROR (service inferido desde verbo genérico),
  HUMAN_REVIEW (endpoint ambiguo), TARGET_METADATA_ERROR (`required` legacy),
  EVALUATOR/LABEL_ERROR (equivalencias de carga) y omisiones del modelo.
- Guards generales: traslado pequeño exige marcador de alcance; ambiguity domina
  observación compatible; correction explícita no depende de target legacy.
- Holdout 9 SHA-256
  `116c5ce39f35e11358b05a99caac76b9120f1e67e8b6c197cb1c7438fd522f4f`,
  run `20260812T015355Z_v31_blind_holdout_round9_100`: P 97.85%, R 93.81%,
  F1 95.79%, safety 98/100, 2 critical/wrong-endpoint. No PASS.
- Holdout 9 contiene además label inconsistente en h39_055: mensaje declara
  destino=false pero expected heredado lo omite. No se corrigió post-run ni se
  reutiliza como examen. El error real restante (distrito con ref incorrecta)
  se cerró exigiendo provenance también para distrito; pares de ruta explícitos
  origin/destination siguen permitidos estructuralmente.
- Tests V3.1: 42/42 PASS. Development replay post-fix: P 99.12%, R 88.98%,
  F1 93.78%, safety 99/100. Smoke final
  `20260812T020244Z_v31_smoke`: 10/10, P/R/F1 100%, safety 10/10, críticos 0.
- Holdout 10 candidato preparado, NO ejecutado: 100 casos, 50 contextuales,
  14 HUMAN_REVIEW, hash provisional
  `0635a3210bedaa72b2ccbed5af4ae3b2340d508220db0a79d73a25c6ddfa93c2`.
- Costo acumulado exacto estimado: USD 2.4938976 / USD 2.50. Restante USD
  0.0061024; insuficiente para holdout 10 (~USD 0.126).
- IA-first runtime sigue NO integrado/activado por gate obligatorio sin PASS.
  Meta sends 0; worker detenido; no push; producción intacta.

# Request lifecycle + recovery fixes (2026-08-12)

- **Bugs encontrados en prueba manual**:
  1. Msg 35 "buen dia quiero cotizar una mudanza" heredó Surco→Miraflores de Lead anterior
  2. Msg 39 "is" incomprensible saltó a truck_access/origin sin aclarar elevator/destination

- **Root causes identificadas**:
  1. OpenAI 401 `invalid_api_key` en classify_request_intent() → fallback retornaba NO_REQUEST_SIGNAL (continúa silencioso)
  2. last_question_resolution() retornaba WAITING porque buscaba inbound solo del último bot; no detectaba msg 38 sin resolver

- **Fixes implementados**:
  - Commit `134498b`: request_lifecycle fallback → UNCERTAIN + pending_request_switch en caso de GPT failure
  - Commit `9c1f474`: last_question_resolution() ahora busca en prior 3 bots para detectar targets sin resolver
  - Commit `d165c61`: conversation_engine preparado para contexto en _rephrase_if_unanswered (future use)

- **Tests agregados y verificados**:
  - test_gpt_failure_on_new_request_message_triggers_uncertain: PASS
  - test_unintelligible_answer_stays_on_current_context: PASS
  - test_target_resolved: PASS

- **Pendiente**: validar credencial OpenAI antes de prueba manual. Credential fue observada inválida en turnos reales (401).

# AI-led conversation orchestration (2026-08-12)

- Orquestación primaria simplificada: Django persiste/recarga estado, calcula
  requirements/readiness y GPT conversación elige `reply_text + asked_targets`.
- `QuestionTarget` registra lo realmente preguntado. Targets inválidos o
  comerciales invalidan la salida y activan fallback conservador.
- `QuoteRequirements` separa required/conditional/optional/booking-only sin
  cambiar readiness ni pricing. Pisos siguen required por regla legacy y quedan
  marcados `BUSINESS_RULE_REVIEW_REQUIRED` para revisión comercial separada.
- Extracción V3.1, evidencia, validator, atomicidad, outbox, ownership, pricing y
  booking determinísticos permanecen sin cambios.
- Regresión IA + integrations: 394 PASS, 31 skipped. Simulación contractual
  free-form: 10/10 PASS. Meta sends: 0.

# LOCAL RELEASE CANDIDATE V3.1 (2026-08-12)

- Holdout 10 congelado antes de API: 100 casos, 50 contextuales, 14 HUMAN_REVIEW,
  SHA-256 `0635a3210bedaa72b2ccbed5af4ae3b2340d508220db0a79d73a25c6ddfa93c2`.
- Run `20260812T021711Z_v31_blind_holdout_round10_100`: schema 100/100;
  accepted P 100%, R 92.78%, F1 96.26%, safety 100/100. Excluyendo
  HUMAN_REVIEW: P 100%, R 93.75%, F1 96.77%, safety 86/86. Critical unsafe,
  wrong endpoint, numeric invention y commercial authority: 0. HOLDOUT PASS.
- Costo acumulado estimado desde master: USD 2.6203284 / USD 2.80.
- Runtime V3.1 fuera del webhook mediante internal outbox/worker, validator
  evidence-bound, lock transaccional del Lead y persistencia idempotente. Legacy
  permanece disponible.
- Policy DB por canal: `off|shadow|active`; activación rechaza canales no TEST.
  Rollback real TEST `active -> off -> active` probado. Canal 7 TEST queda
  `active`; otros canales activos: 0. Flags globales permanecen
  `AI_DELTA_EXTRACTION_ENABLED=false`, `AI_DELTA_SHADOW_MODE=true`.
- Shadow replay read-only: 20/20, critical 0, state writes 0, pricing authority
  fields 0, Meta sends 0.
- E2E IA/WhatsApp/Chatwoot/quote/booking/failures: 562 PASS, 33 skips
  PostgreSQL-only esperados bajo SQLite.
- PostgreSQL local aislado: 33/33 PASS, incluyendo locks, ownership, outbox,
  idempotencia, cotización, booking y concurrencia.
- Suite completa: 712 PASS, 33 skips PostgreSQL-only; esos 33 fueron ejecutados
  y aprobados separadamente en PostgreSQL. Check, migration check y diff: PASS.
- Seguridad: datos de pago removidos del código y externalizados; fallback deriva
  al asesor. `.env` no versionado; scan tracked sin secretos confirmados.
- Django limpio operativo en 127.0.0.1:8001; Chatwoot local HTTP 200; mapping TEST
  presente. Integration worker detenido. Meta physical sends desde master: 0.
- No push, VPS, producción ni ETAPA 10C. Archivos ajenos intactos.
- LOCAL RELEASE CANDIDATE READY. Pendiente único: aceptación manual de inbound
  originado por propietario en WhatsApp TEST; no bloquea RC local.
