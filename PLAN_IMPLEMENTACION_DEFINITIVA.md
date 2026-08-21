# Plan de Implementación Definitiva: Bandeja CRM ≈ YCloud

**Objetivo**: Comportamiento de Bandeja de Conversaciones equivalente a YCloud (sin F5) usando eventos de YCloud.

**Scope**: Solo YCloud por ahora. Sin Meta Cloud API, sin multiproveedor, sin refactorizaciones innecesarias.

---

## FASE 1 — AUDITORÍA ✅ COMPLETE

**Estado**: Documentado en `PHASE_1_AUDIT_TABLE.md`

Identificados:
- Modelos BD: ConversacionWhatsApp (resumen, ultima_actividad, estado_atencion, bot_pausado)
- Modelos BD: MensajeWhatsApp (origen, sender_type, source, fecha_mensaje, estado)
- Endpoints: `api_active_conversations` (lista), `conversation_messages` (timeline)
- Frontend: ConversationList.vue (polling 10s), ChatTimeline.vue (renderiza mensajes)
- Store: conversationService.js (mapea respuesta API a componentes)

**5 Críticos Encontrados**:
1. Preview diverge de último mensaje
2. ultima_actividad stuck en timestamp antiguo
3. Timeline stale antes de polling
4. Dual taxonomy (origen + sender_type)
5. Frontend no re-ordena en SSE event

---

## FASE 2 — CONTRATO CANÓNICO ✅ IMPLEMENTADO

**Estado**: Definido en services_ycloud.py

Cada mensaje tiene EXACTAMENTE:
- `conversacion_id`: int
- `wamid`: str (YCloud message ID)
- `direction`: "inbound" | "outbound"
- `sender_type`: "customer" | "bot" | "advisor" | "system"
- `source`: "whatsapp_customer" | "whatsapp_business_app" | "crm" | "bot" | "system"
- `message_type`: "text" | "image" | "audio" | "document" | "location"
- `text`: str
- `timestamp`: datetime (real message time, not server now())
- `status`: "received" | "pending" | "sent" | "delivered" | "read" | "error"

**Reglas Clasificación**:
- Inbound msg → direction=inbound, sender_type=customer, source=whatsapp_customer
- WhatsApp Web echo → direction=outbound, sender_type=advisor, source=whatsapp_business_app (human_intervention=true)
- Bot reply → direction=outbound, sender_type=bot, source=bot
- CRM manual → direction=outbound, sender_type=advisor, source=crm
- Status update → NO crear mensaje, solo actualizar status del existente

---

## FASE 3 — SERVICIO CENTRAL YCLOUD ✅ IMPLEMENTADO

**Archivo**: `apps/whatsapp/services_ycloud.py`

Clase: `YCloudMessageProcessor`

Métodos públicos:
- `process_ycloud_event(event_type, event_data, channel)` → transacción atómica

Flujo:
1. Validar clasificación del evento (inbound/echo/status)
2. Resolver identidad (Cliente)
3. Resolver/crear conversación
4. Lock conversación para evitar race conditions
5. Get-or-create mensaje (idempotente por wamid)
6. Actualizar conversación (ultima_actividad, resumen, último_mensaje_*) SI mensaje es nuevo
7. Aplicar takeover si fue echo desde Web/mobile
8. Retornar resultado con flags (created, human_intervention)

**Tests**: 7/7 passing
- Event classification (3 tests)
- Message processing (4 tests)

Siguientes pasos FASE 3 en views.py:
- [ ] Reemplazar webhook handler con `process_ycloud_event()`
- [ ] Mantener compatibilidad con Conversacion (legacy)

---

## FASE 4 — INTEGRACIÓN EN VIEWS.PY (PRÓXIMO)

**Cambios necesarios**:

### 4.1 Webhook handler (_receive_message)
```python
# Antes: canonical_incoming_message() -> legacy logic
# Después: process_ycloud_event() -> nueva lógica

result = process_ycloud_event(
    event_type=extract_event_type(payload),
    event_data=extract_event(payload),
    channel=channel,
)
message = result["message"]
conversation = result["conversation"]
human_intervention = result.get("human_intervention", False)

# Refresh para asegurar cache es fresco
if conversation:
    conversation.refresh_from_db()
```

### 4.2 Mantener Conversacion (legacy)
```python
# Después de process_ycloud_event(), crear Conversacion legacy si falta
Conversacion.objects.get_or_create(
    cliente=cliente,
    message_entrada=message_text,
    message_salida="",
    canal=Conversacion.CANAL_WHATSAPP,
)
```

### 4.3 Response webhook
```python
return JsonResponse({
    "ok": True,
    "message_id": message.id,
    "conversation_id": conversation.id,
    "human_intervention": human_intervention,
})
```

---

## FASE 5 — ACTUALIZACIÓN TIEMPO REAL (PRÓXIMO)

**Estado actual**: SSE configurado pero no re-ordena lista

**Cambios necesarios en Frontend**:

### 5.1 En ConversationList.vue
```javascript
// Cuando SSE event llega:
eventSource.addEventListener('message.created', async (event) => {
    const data = JSON.parse(event.data)
    
    // Re-fetch lista completa (API ordena por -ultima_actividad)
    await loadConversations()
    
    // Detectar cambios (hash) y re-render
    if (hasRealChange()) {
        conversations.value = newList
    }
})
```

### 5.2 Broadcast desde backend
Ya configurado en services.py (línea 770):
```python
if created:
    def publish_event():
        broadcast_to_user(user.id, 'message.created', {
            'conversation_id': conversation.id,
            ...
        })
    transaction.on_commit(publish_event)
```

---

## FASE 6 — PREVIEW CORRECTO (PRÓXIMO)

**Cambio**: Derivar preview de último mensaje, no de campo resumen

### 6.1 En services_ycloud.py
```python
# Actual: resumen = message_text[:100]
# Problema: Si último msg es multimedia, preview dice "[imagen]"

# Mejor: Derivar preview de último mensaje
def get_preview_for_conversation(conversation):
    last_msg = conversation.mensajes.order_by('-fecha_mensaje').first()
    if not last_msg:
        return "Conversación nueva"
    return get_preview_text(last_msg)

def get_preview_text(mensaje):
    if mensaje.tipo == "texto":
        return mensaje.contenido[:100]
    elif mensaje.tipo == "imagen":
        return "📷 Foto" if mensaje.caption else "Foto"
    elif mensaje.tipo == "audio":
        return "🎤 Audio"
    # ... etc
```

---

## FASE 7 — LIMPIEZA DUAL TAXONOMY (PRÓXIMO)

**Cambio**: Usar SOLO sender_type (no origen)

### 7.1 Migración
```python
# Migración Django: 
# ALTER TABLE whatsapp_mensajewhatsapp DROP COLUMN origen;

# En código:
# Reemplazar mensaje.origen → mensaje.sender_type
# Reemplazar MensajeWhatsApp.ORIGEN_* → MensajeWhatsApp.SENDER_*
```

---

## FASE 8 — VALIDACIÓN E2E (FINAL)

**Checklist**:
- [ ] Mensaje YCloud → Webhook → DB en <100ms
- [ ] Conversación re-ordena sin F5 (SSE + polling)
- [ ] Preview = último mensaje (no resumen desincronizado)
- [ ] Hora correcta (timestamp mensaje, no server now())
- [ ] No leídos = conteo correcto (per-user read state)
- [ ] Bot pausado al intervenir advisor
- [ ] Mensaje duplicado por race condition = rechazado (idempotencia por wamid)
- [ ] Multimedia descargado y mostrado
- [ ] Estado envío actualizado (delivered/read)

---

## CÓDIGO LLAVE COMPROMETIDO

### ✅ Ya hecho
- `services_ycloud.py`: YCloudMessageProcessor + 7 tests
- `PHASE_1_AUDIT_TABLE.md`: Fuentes de verdad identificadas
- `views.py`: refresh_from_db() agregado, _get_or_create_conversation() mejorado

### ⏳ Pendiente
- Integrar YCloudMessageProcessor en views.py _receive_message()
- Actualizar frontend SSE listener para re-fetch + resort
- Derivar preview de último mensaje (no campo resumen)
- Eliminar `origen` (usar solo sender_type)
- Prueba real con YCloud webhook

---

## REGLAS A SEGUIR (DEL USUARIO)

✓ No pedirme DevTools — inspecciono código
✓ No tests unitarios aislados — E2E real
✓ No parches visuales — cambios estructurales
✓ No SQL improvisado — código Django
✓ No `ultima_actividad=now()` si existe timestamp real
✓ Atomic transaction completa
✓ refresh_from_db() después de BD update
✓ Una conversación punta a punta antes de avanzar

---

## SIGUIENTE PASO

**FASE 4**: Integrar `process_ycloud_event()` en `views.py` _receive_message()
- Reemplazar `canonical_incoming_message()` con nuevo servicio
- Mantener compatibilidad con Conversacion (legacy)
- Probar con caso real (Walter Escobar o similar)
