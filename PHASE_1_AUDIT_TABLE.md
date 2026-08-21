# PHASE 1: AUDIT TABLE — Data Source Mapping

## Current Data Flow

| **Function** | **Source (Model)** | **Field(s)** | **API Returns** | **Frontend Uses** | **Status** |
|---|---|---|---|---|---|
| **Timeline (messages)** | MensajeWhatsApp | `contenido`, `tipo`, `fecha_mensaje`, `origen`, `estado` | `GET /conversation_messages` | ChatTimeline.vue renders `v-for="msg in messages"` | ✓ Works after F5 |
| **Preview text** | ConversacionWhatsApp | `resumen` | `api_active_conversations.preview` | ConversationList: `{{ conv.preview }}` | ⚠️ May diverge from last message |
| **Last activity time** | ConversacionWhatsApp | `ultima_actividad` | `api_active_conversations.last_activity` | ConversationList: `{{ formatTime(conv.lastActivity) }}` | ❌ Stays at old timestamp |
| **Conversation order (list)** | ConversacionWhatsApp | ORDER BY `-ultima_actividad` | Endpoint sorts DESC | Frontend displays in received order | ❌ Doesn't reorder on update |
| **Unread count** | ConversacionReadState | `count(messages after last_read_timestamp)` | `api_unread_counts` + list | `{{ conv.unread }}` badge | ✓ Per-user accurate |
| **Attention mode** | ConversacionWhatsApp | `estado_atencion` (bot/asesor/cerrada) | `estado_atencion` | Badges: bot/asesor/closed | ✓ Updates on takeover |
| **Message author** | MensajeWhatsApp | `origen` (cliente/bot/asesor/sistema) + `sender_type` (customer/bot/advisor/system) | `origen` in timeline | CSS class for styling | ⚠️ Dual taxonomy (legacy + new) |
| **Multimedia** | MensajeWhatsApp | `ycloud_media_id`, `mime_type`, `filename`, `media_status` | Media fields in message | img/video/audio tags | ✓ Renders after F5 |
| **Message status** | MensajeWhatsApp | `estado` (recibido/pendiente/enviado/entregado/leido/error) | `estado` | Status icon (✓/clock/!) | ✓ Reflects DB state |

---

## Critical Misalignments

### 1. **Preview diverges from last message**
- **Current**: `resumen` field updated when `ultima_actividad` updates
- **Problem**: Resumen value may be extracted from event["text"] but last message might be multimedia
- **Fix needed**: Preview should always be derived from last message (text extraction for type)

### 2. **ultima_actividad stuck at old timestamp**
- **Current**: Only updates if `created=True AND message_timestamp > current`
- **Problem**: Second message from same client doesn't trigger update if both have same source
- **Evidence**: Conv 201: 12 messages, ultima_actividad stuck at first message
- **Fix needed**: ALWAYS update to max timestamp of any new/updated message

### 3. **Timeline stale after webhook but before F5**
- **Current**: Webhook inserts message, frontend polls every 10s
- **Problem**: Object.refresh_from_db() not called, Python object remains cached
- **Fix needed**: Ensure DB reflects changes before API response; frontend fetches immediately via SSE

### 4. **Dual author taxonomy**
- **Current**: `origen` (cliente/bot/asesor/sistema) + `sender_type` (customer/bot/advisor/system)
- **Problem**: Two fields for same concept, different values, confusing logic
- **Solution**: Use single `sender_type` field (the canonical contract), derive `origen` for backward compat

### 5. **Order doesn't update in frontend without poll**
- **Current**: Frontend caches list, polling every 10s
- **Problem**: Even with SSE event, Vue component doesn't re-sort by -ultima_actividad
- **Fix needed**: SSE event should trigger re-fetch AND resort, not just append

---

## Required Canonical Contract

Each message should have EXACTLY:

```python
{
    "conversation_id": int,
    "wamid": str,  # YCloud message ID (unique per provider)
    "direction": "inbound" | "outbound",
    "sender_type": "customer" | "bot" | "advisor" | "system",
    "source": "whatsapp_customer" | "whatsapp_business_app" | "crm" | "bot" | "system",
    "message_type": "text" | "image" | "audio" | "document" | "location",
    "text": str,
    "caption": str,  # For media
    "timestamp": datetime,  # Actual message time
    "status": "received" | "pending" | "sent" | "delivered" | "read" | "error",
    "media_id": str,  # If applicable
    "media_status": "pending" | "ready" | "failed",
}
```

**NO inference from text content.**
**Direction determines basic intent, sender_type refines.**
**Source identifies origin system (for audit trail + human takeover detection).**

---

## Next: Phase 2 Implementation

- Unify `origen` → `sender_type` (canonical)
- Ensure preview always derives from last message
- Ensure ultima_actividad ALWAYS updates (not just on created=True)
- Add refresh_from_db() or DB read after webhook atomicity
- Wire SSE event → list re-fetch + resort
