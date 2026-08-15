# WhatsApp Bot V4 Simple

## Fase 5: estados y QuoteBridge

Estados mínimos: `COLLECTING`, `READY_TO_QUOTE`, `QUOTED`, `PENDING_HUMAN_QUOTE`.

Flujo: `merge -> required_missing -> READY_TO_QUOTE -> QuoteBridge -> QUOTED | PENDING_HUMAN_QUOTE -> reply`. `READY_TO_QUOTE` es transitorio: no espera confirmación del cliente. `ConversationAgent` nunca calcula ni modifica precio.

`QuoteBridge` reutiliza `cotizar_lead`, `crear_cotizacion_automatica`, `Cotizacion`, `CotizacionComercial`, `RevisionCotizacion` y `SolicitudCotizacion`. Pricing histórico/fallback existente se clasifica `ADAPT`; no se añadió fórmula comercial. Error o precio no positivo deriva a humano sin cotización ficticia.

Idempotencia: SHA-256 canónico sobre distritos, pisos, accesos e items. Mismo input reutiliza `RevisionCotizacion.source_key`; cambio comercial genera nueva evaluación y conserva historial.

CRM: `COLLECTING` mantiene solicitud incompleta; `PENDING_HUMAN_QUOTE` conserva solicitud activa y estado `por_cotizar`; `QUOTED` proyecta precio real y termina solicitud activa. Chatwoot reutiliza outbox de labels `por-cotizar` y `cotizado`.

Post-quote: acknowledgements breves no llaman LLM ni reabren collector. Correcciones e items modificados pasan nuevamente por agente, merge, fingerprint y QuoteBridge.

Simulador muestra `STATE`, `STATUS`, `REQUIRED_MISSING`, `QUOTE_DECISION` y precio cuando existe. Usa CRM local; no usa Meta ni Chatwoot.

## Alcance

V4 cotiza únicamente mudanzas. Core vive en `apps/whatsapp_bot_v4` y no importa motor `apps.ia`, Meta ni modelos Django. Persistencia e integraciones quedan tras adapters.

## Flujo

`customer message + BotState + required_missing + recent context` → una llamada `ConversationAgent` → `AgentOutput` estructurado → validación mecánica → merge determinístico → `ready_to_quote`.

Segunda llamada existe solo para reparar salida que viola schema o reglas duras. Django no elige siguiente pregunta ni redacta respuesta normal.

## Responsabilidades

IA: comprensión contextual, extracción, correcciones, preguntas reales, selección natural de requisito pendiente y texto final.

Django: tipos, campos permitidos, merge, integridad, requisitos, readiness, precio futuro, CRM, ownership e integraciones.

## Estado

- `origin_district`, `destination_district`
- `origin_floor`, `destination_floor`
- `origin_access`, `destination_access`: `ascensor`, `escaleras`, `NOT_APPLICABLE`
- `items`: lista de descripciones libres

Piso 1 fuerza acceso `NOT_APPLICABLE`. Piso superior requiere `ascensor` o `escaleras`. Ausencia permanece desconocida.

## Contrato IA

`AgentOutput`: `updates`, `corrections`, `requested_fields`, `customer_question`, `conversation_action`, `reply`, `handoff_requested`. No contiene precio. `conversation_action` distingue `CONTINUE`, `NEW_QUOTE`, `CORRECTION`, `ACK` y `QUESTION`; Django solo permite `NEW_QUOTE` desde `QUOTED` o `PENDING_HUMAN_QUOTE`.

`updates` no sobrescribe valor conocido. `corrections` permite overwrite explícito. Valores nulos nunca borran estado.

### Invariantes de extracción

1. **CONTEXT GUIDES EXTRACTION. CONTEXT NEVER LIMITS EXTRACTION.** Historia y última pregunta resuelven contexto de respuestas cortas; datos nuevos siempre deben estar sustentados por mensaje actual.
2. **ASK ONE LOGICAL BLOCK. EXTRACT ALL EXPLICIT DATA.** Un bloque limita únicamente `reply/requested_fields`; `updates/corrections` incluye todos los datos explícitos, aunque crucen ruta, pisos, accesos y carga.
3. `requested_fields` y `required_missing` nunca filtran understanding/extraction.
4. **REPLY REPAIR NEVER MUTATES VALID EXTRACTION.** Validación de extraction ocurre primero. Snapshot de `updates`, `corrections` y `conversation_action` queda congelado antes de repair de response.
5. **POST-MERGE STATE IS AUTHORITATIVE FOR RESPONSE CONSISTENCY.** Response se valida contra `required_missing_after`. Repair de response solo cambia copy conversacional.

Turno normal conserva una llamada. Segunda llamada existe solo ante fallo de extraction o response. Fallo de response no reejecuta ni reemplaza understanding. En desarrollo `strict_repairs` falla explícitamente; en runtime fallback seguro emite telemetry estructurada (`fallback_reason`, `agent_output_valid`, `extraction_present`, `repair_attempted`).

## Persistencia

`BotConversationState` es única tabla V4. Guarda `conversation_key`, `service_type=mudanza`, snapshot JSON de `BotState`, `status`, `version` y `updated_at`. No duplica CRM ni historia de mensajes.

`BotStateRepository` desacopla servicio de ORM. Implementaciones: `DjangoBotStateRepository` para continuidad real e `InMemoryBotStateRepository` para pruebas unitarias. `PersistentConversationService` carga antes del turno, verifica ownership antes de IA, persiste merge y sincroniza CRM.

Un thread WhatsApp mantiene una solicitud comercial activa. Al recibir `NEW_QUOTE`, snapshot cotizado anterior se archiva bajo clave de request, clave canónica recibe `BotState` limpio y conversación conserva mismo cliente/thread/Chatwoot mapping. CRM crea nuevo `Lead` y nueva `SolicitudCotizacion`; cotización y Lead anteriores permanecen intactos. Idempotencia QuoteBridge incluye `lead_id`, evitando reutilizar revisión de otra solicitud con datos iguales.

## CRMV4Adapter

- distritos, pisos, accesos e items → `Lead`
- origen/destino → dos `LeadUbicacion` idempotentes
- requisitos pendientes → `SolicitudCotizacion.datos_faltantes`
- estado completo → solicitud activa con faltantes vacíos y motivo `lista para cotizar`

No crea `Cotizacion`, precio ni datos de booking. Repetir sync actualiza mismas entidades.

## ChatwootV4Adapter

Facade sobre `ConversationControl`, state machine y outbox existentes. Expone owner, permiso bot, handoff, return-to-bot y proyección idempotente de mensajes cliente/bot. Mensajes de asesor y notas privadas no entran como proyección pública V4. Owner `AGENT_ACTIVE` corta antes del agente: cero llamadas LLM.

## Límites

- `ChatwootV4Adapter`: consulta ownership y encola proyección usando infraestructura existente.
- `CRMV4Adapter`: sincroniza Lead/ubicaciones/solicitud sin fabricar cotización.
- `MetaV4Adapter`: bloqueado explícitamente en esta fase.
- Una tabla y una migración V4 para snapshot conversacional.

## Integraciones inventariadas

REUSE: `apps.integrations` mappings de cuenta/inbox/contacto/conversación/mensaje, outbox, idempotencia, live sync, webhook, mensajes privados, labels, takeover, return-to-bot y `ConversationControl.owner_state`.

ADAPTER: `is_bot_allowed` y `project_message`; luego bridge de persistencia hacia CRM.

DO_NOT_REUSE: `apps.ia` conversation engine, extractors, renderers, policies, rephrasing, historical reactivation, request lifecycle conversacional y fallbacks legacy.

CRM REUSE: `Cliente`, `Conversacion`, `Lead`, `LeadUbicacion`, `SolicitudCotizacion`, `Cotizacion`, `CotizacionComercial`, `RevisionCotizacion`, `EnvioCotizacion`, `ServicioHistorico` y servicios comerciales existentes. V4 no inventa precio.

## Simulador

`python manage.py simulate_bot_v4 --conversation demo001 --show-state`. Reanuda snapshot tras cerrar proceso. `--reset` reinicia solo clave seleccionada. Requiere `OPENAI_API_KEY`; no usa Meta, Chatwoot ni CRM.

## MetaV4Adapter

Endpoint aislado: `GET|POST /webhooks/whatsapp/v4/`. El callback legacy no participa.

Inbound normalizado: `InboundMessage(external_message_id, channel_id, customer_id, text, timestamp, message_type)`. Solo `text` entra al turno; eventos sin mensaje y tipos multimedia se ignoran.

Outbound normalizado: `OutboundMessage(customer_id, text, conversation_id)`. `MetaV4Adapter` construye payload Cloud API, aplica timeout explícito y devuelve `MetaSendResult` con WAMID o error sanitizado.

Routing: `V4ChannelRoute` es opt-in OneToOne sobre `WhatsAppChannel`. Solo canales activos con `enabled=True` llegan a V4. Identidad estable: `channel + wa_id` reutiliza `Cliente + Lead + ConversacionWhatsApp`; snapshot usa `whatsapp:<conversation_id>`.

Idempotencia: WAMID inbound usa restricción única existente de `MensajeWhatsApp.meta_message_id`. Duplicado termina antes de ownership, IA, CRM y outbound.

Diseño Fase TEST: síncrono y lineal (`webhook → persist inbound → ownership → V4 → state/CRM → Meta send → Chatwoot projection`). Sin worker V4 ni generation pipeline legacy. Fallo Chatwoot se aísla después de persistencia; fallo Meta queda registrado en mensaje outbound.

Canal local opt-in: únicamente `TEST Meta Stage 7` (ID 7). Auth Graph devolvió HTTP 401/code 190; requiere renovar credencial antes de prueba física.
