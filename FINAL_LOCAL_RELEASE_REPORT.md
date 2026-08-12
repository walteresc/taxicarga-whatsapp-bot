# TAXICARGA WHATSAPP BOT - LOCAL RELEASE CANDIDATE

## RESULTADO GENERAL

READY. IA-first V3.1 integrada y limitada al canal TEST 7. Producción intacta.

## IA

- Versión: IA-FIRST V3.1 RC, OpenAI `gpt-4.1-mini`.
- Development final: precision 99.12%, recall 88.98%, F1 93.78%, safety 99%.
- Fresh blind holdout: `20260812T021711Z_v31_blind_holdout_round10_100`.
- Hash: `0635a3210bedaa72b2ccbed5af4ae3b2340d508220db0a79d73a25c6ddfa93c2`.
- Casos/schema: 100/100.
- Accepted: precision 100%, recall 92.78%, F1 96.26%, safety 100%.
- Critical unsafe, wrong endpoint, invented numeric, commercial authority: 0.
- Costo acumulado estimado: USD 2.6203284 / USD 2.80.

## RUNTIME

- IA-first: worker interno, validator V3.1, persistencia idempotente y lock atómico.
- Test channel: canal 7 `active`; todos los demás `off`.
- Legacy rollback: probado `active -> off -> active` sin editar código.
- Shadow: 20/20 PASS; 0 critical, 0 writes, 0 Meta sends.

## WHATSAPP Y CHATWOOT

- Inbound, outbound e idempotencia: PASS automatizado.
- Projection, takeover, agent -> WhatsApp, return-to-bot y private notes: PASS.
- Chatwoot local: HTTP 200; mapping TEST presente.
- Meta physical sends desde MASTER PROMPT: 0.

## QUOTING Y BOOKING

- Quote/booking readiness: deterministas en Django; PASS.
- Precio: solo motor Django; IA sin autoridad.
- Distancia sin regla y múltiples paradas: `por_cotizar -> asesor`.
- Reserva: nombre, fecha, hora y direcciones exactas; DNI opcional.
- Servicio, ServicioUbicacion, route snapshots e idempotencia: PASS.
- ProgramacionServicio no se crea automáticamente.

## FAILURE RECOVERY

- OpenAI timeout/schema/provider failure: fallback conservador, sin corrupción.
- Chatwoot retry: no bloquea inbound ni duplica.
- Meta retry/dead-letter: outbox idempotente.
- Worker restart, cancellation y duplicate webhook: PASS.

## POSTGRESQL Y TESTS

- PostgreSQL/concurrency: 33/33 PASS real en DB local aislada.
- E2E relevante: 562 PASS; 33 skips PostgreSQL-only ejecutados aparte.
- Full suite: 712 PASS, 33 skips; failures 0.
- Check, migrations y diff: PASS.

## SECURITY

- Secrets: `.env` no versionado; scan tracked sin secretos confirmados.
- Datos de pago: externalizados; fallback seguro a asesor.
- PII, HMAC, private notes, unknown/inactive channel y channel isolation: PASS.
- Phone Number ID: por canal; sin fallback global operativo peligroso.

## COMMITS LOCALES RC

- `ef29dd5 feat(ia): gate V3.1 runtime per channel`
- `8d0124e fix(ia): serialize V3.1 state updates`
- `c85f1e7 test(ia): add V3.1 shadow replay gate`
- `ff0400e fix(security): externalize payment details`
- Push: NO.

## ESTADO FINAL

- Global: `AI_DELTA_EXTRACTION_ENABLED=false`, `AI_DELTA_SHADOW_MODE=true`.
- Policy TEST 7: `active`; otros canales V3.1: `off`.
- Django: operativo 8001. Chatwoot: operativo. Worker: DETENIDO.
- Meta sends: 0. Producción/ETAPA 10C: NOT STARTED.

## MANUAL ACCEPTANCE REMAINING

Única prueba pendiente: inbound físico originado por propietario en WhatsApp TEST.

1. Enviar: `Hola, quiero una mudanza de Surco a Miraflores. Llevo una cama, una refrigeradora y 15 cajas.`
2. Responder pisos/ascensores/acceso según la pregunta, usando solo datos TEST.
3. Corregir: `Corrección: el destino es San Isidro.`
4. Verificar una sola respuesta por turno en WhatsApp y Chatwoot; no aceptar ni reservar.

## FINAL VERDICT

- BOT LOCAL: READY.
- PRODUCTION: NOT DEPLOYED.
- Siguiente acción: ejecutar aceptación anterior; luego planificar ETAPA 10C separada.
