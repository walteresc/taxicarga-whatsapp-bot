# Work State — Bot V4

## Fase 5 completada

- Naturalidad: un bloque lógico por turno; pares ruta y pisos permitidos.
- Estados: `COLLECTING`, `READY_TO_QUOTE`, `QUOTED`, `PENDING_HUMAN_QUOTE`.
- QuoteBridge corre en mismo turno del último dato.
- Pricing reutilizado: `cotizar_lead` + `crear_cotizacion_automatica`; sin reglas nuevas.
- Fallback seguro a `PENDING_HUMAN_QUOTE` y solicitud idempotente.
- Fingerprint comercial y `RevisionCotizacion.source_key` idempotente.
- Correcciones post-ready/post-quote e items adicionales reevalúan pricing.
- Acknowledgements post-quote: cero LLM, cero duplicados.
- CRM refleja incompleto, por cotizar y cotizado.
- Chatwoot reutiliza labels `por-cotizar` y `cotizado`.
- Simulador muestra state, status, faltantes y decisión.
- Tests V4 Fase 5: 89 verdes.

## Fix solicitudes múltiples

- `conversation_action`: CONTINUE, NEW_QUOTE, CORRECTION, ACK, QUESTION.
- `NEW_QUOTE` protegido por Django tras QUOTED/PENDING_HUMAN_QUOTE.
- Mismo cliente, WhatsApp thread y Chatwoot mapping; nuevo Lead/Solicitud comercial activa.
- Snapshot anterior archivado; nuevo BotState limpio en COLLECTING.
- ACK/preguntas conservan solicitud; correcciones reevalúan solicitud activa.
- Fingerprint comercial separado por Lead para cotizaciones sucesivas.

## Estabilidad arquitectónica de extracción

- Root cause físico reproducido: output inicial contenía Surco + Miraflores; validación conjunta rechazó `requested_fields` multibloque y full repair podía reemplazar understanding válido.
- Extraction y response ahora se validan por separado.
- Repair response congela updates/corrections/conversation_action.
- One logical block aplica solo a response; extraction conserva todos los datos explícitos.
- Access usa enum estricto; schema documenta semántica origen/destino.
- Dataset determinístico: 50/50 casos.
- Holdout real gpt-4.1-mini: 20/20, 0 misses críticos, recall 1.0000.
- Tests V4: 99 verdes.

## Completado

- App aislada registrada, con un modelo/migración de snapshot.
- Dominio local: estado, requirements, validadores, merge y readiness.
- Contrato Pydantic y agente OpenAI Responses con una llamada normal.
- Repair excepcional, máximo una segunda llamada por turno.
- ConversationService y supresión por ownership.
- Simulador local.
- Adapters iniciales Chatwoot, CRM y Meta bloqueado.
- Dataset: 30 casos single-turn y 20 conversaciones multi-turn.
- Arquitectura e inventario Chatwoot/CRM documentados.
- Persistencia ORM mediante snapshot V4 único y repository.
- Continuidad persist → restart → reload certificada.
- CRMV4Adapter idempotente sobre Lead, LeadUbicacion y SolicitudCotizacion.
- Readiness proyectado a solicitud sin crear precio/Cotizacion.
- ChatwootV4Adapter sobre ownership, state machine y outbox existentes.
- Owner AGENT bloquea antes de IA; cero llamadas.
- Return-to-bot conserva snapshot y reanuda.
- Proyección cliente/bot idempotente, guardas anti-loop y notas privadas.
- Simulador persistente con `--conversation` y `--reset`.
- Fase 2: 48 pruebas V4 verdes.
- Suite legacy sin V4: 785 pruebas verdes, 33 omitidas. V4 + test legacy sensible: 49 verdes.
- MetaV4Adapter aislado con contratos inbound/outbound tipados.
- Endpoint `/webhooks/whatsapp/v4/` y verificación callback.
- Routing opt-in mediante `V4ChannelRoute`; solo canal TEST ID 7 habilitado localmente.
- Identidad determinística channel + wa_id y WAMID inbound idempotente.
- Flujo Meta fixture completo, all-data y takeover certificados.
- Meta outbound mock y errores HTTP sanitizados certificados.
- OpenAI real vía fixture Meta: PASS, una llamada, outbound mock, rollback.
- Dependencias conversacionales legacy: 0.
- Fase 3: 73 pruebas V4 verdes.
- Meta auth real: HTTP 401, Graph code 190. Phone number ID no validable hasta renovar token.
- Suite global Fase 3: 858 total, 825 pass, 33 omitidas, 0 fallos.

## Próxima fase

1. Renovar `WHATSAPP_ACCESS_TOKEN` de TEST y repetir GET auth/phone ID.
2. Configurar callback TEST hacia `/webhooks/whatsapp/v4/` sin cambiar otros números.
3. Ejecutar una sola prueba física V4 únicamente tras auth PASS.
4. Definir entrypoint seguro hacia pricing existente en fase posterior; no crear precio nuevo.

## Prohibiciones vigentes

No reutilizar motor conversacional legacy. No conectar Meta. No crear precio. No borrar legacy. No producción/push.
