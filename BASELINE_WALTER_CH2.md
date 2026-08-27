# FASE 5B: Walter/Channel 2 Baseline — Pre-Real Test

**Captured**: 2026-08-24 17:18 UTC  
**State**: Docker PostgreSQL + Redis + Nginx + Django all running  
**Two browser tabs prepared**: Both logged in, SSE active

---

## Baseline State (Channel 2 → Client 77 / Walter Escobar)

### Conversation Details
| Field | Value |
|-------|-------|
| **Conversation ID** | 226 |
| **Cliente ID** | 77 |
| **Cliente Nombre** | Walter Escobar |
| **Cliente Teléfono** | +51995403320 |
| **Channel ID** | 2 |
| **Channel Status** | Activo (true) |
| **estado_atencion** | asesor |
| **bot_pausado** | true |
| **ultima_actividad** | 2026-08-22 00:52:15.535487+00 (UTC) |

### Message History (Current)
| ID | Dirección | Tipo | Timestamp (UTC) |
|----|-----------|------|-----------------|
| 802 | entrante | texto | 2026-08-22 00:44:54.124767+00 |
| 803 | entrante | texto | 2026-08-22 00:50:07.909294+00 |
| 804 | saliente | texto | 2026-08-22 00:52:15.536682+00 |
| **Total** | — | — | **3 messages** |

### Unread State (Current)
| Metric | Value |
|--------|-------|
| **Unread Records** | 1 |
| **Unread Count (UI)** | Should display: 1 |

### Latest Webhook Events
| Status | Value |
|--------|-------|
| **Recent webhooks for Channel 2** | None (last activity was 2026-08-22) |
| **Expected next webhook ID** | 968 (current max: 967) |

---

## Expected Changes After Inbound Real Test

**When Walter sends ONE real message from WhatsApp:**

### PostgreSQL Changes Expected
```
whatsapp_mensajewhatsapp:
  + 1 new message (ID 962)
  - direccion: 'entrante'
  - tipo: 'texto' (or media type)
  - creado_en: Current timestamp
  - conversacion_id: 226
  - meta_message_id: <wamid from YCloud>
  
whatsapp_bot_v4_webhookevent:
  + 1 new event (ID 968)
  - event_type: 'whatsapp.inbound_message.received'
  - processed_at: Current timestamp
  - source: '+51995403320' or equivalent
  
whatsapp_conversacionwhatsapp (conversation 226):
  - ultima_actividad: Updated to event timestamp
  - unread count: Should increment to 2
  
whatsapp_conversationreadstate:
  - New/updated unread record
```

### Redis Changes Expected
```
Event Bus:
  + New SSE event for conversation 226
  - Type: 'message.created' or 'conversation.updated'
  - Data includes message ID 962
  - Broadcasts to both tabs simultaneously
```

### Vue UI Changes Expected (Both Tabs)
```
Bandeja (Inbox List):
  - Conversation 226 timestamp updates
  - Unread badge changes (1 → 2)
  - Preview text shows new message
  - No F5 required (SSE pushes update)
  
Conversation Timeline:
  - New message appears at bottom
  - Timestamp is current
  - Direction is "entrante" (inbound)
  - Status shows as "delivered" (if applicable)
```

---

## Verification Checklist for Inbound Test

### API & Backend (Verify in PostgreSQL)
- [ ] Message count increased: 3 → 4
- [ ] Newest message ID: 962 (or higher)
- [ ] Newest message direction: 'entrante'
- [ ] Conversation 226 ultima_actividad updated
- [ ] Webhook event count increased: 952 → 953
- [ ] New event type: 'whatsapp.inbound_message.received'

### Redis & SSE (Verify in Browser)
- [ ] SSE stream receives message event (no errors)
- [ ] DevTools Network shows `/events/stream/` with 200 status
- [ ] Message appears in Tab 1 timeline (no F5)
- [ ] Message appears in Tab 2 timeline (no F5)
- [ ] Unread badge updates in both tabs
- [ ] No console errors in either tab

### Vue UI (Manual Visual Check)
- [ ] Timeline shows new message at bottom
- [ ] Message timestamp is current (recent minutes)
- [ ] Message direction is "entrante" (inbound)
- [ ] Message text visible (not truncated)
- [ ] Both tabs synchronized (same UI state)
- [ ] No infinite loader
- [ ] No 404/500 errors

### Database Integrity (Post-Test Query)
```sql
-- Run after test
SELECT COUNT(*) FROM whatsapp_mensajewhatsapp WHERE conversacion_id = 226;
-- Expected: 4

SELECT estado_atencion, bot_pausado FROM whatsapp_conversacionwhatsapp WHERE id = 226;
-- Expected: asesor | t (no change)
```

---

## Test Execution Steps

### Preparation (ALREADY DONE)
- ✓ Docker infrastructure running
- ✓ PostgreSQL baseline captured
- ✓ Two browser tabs open and logged in
- ✓ SSE streaming active in both tabs
- ✓ No manual refresh planned

### Inbound Test: FASE5B-SSE-WALTER-REAL-001

**Action**: Send ONE message from Walter's WhatsApp to Lima Express (Channel 2)

**Expected Behavior**:
1. YCloud webhook received by Django (HTTP 200)
2. Message stored in PostgreSQL (1 second)
3. WebhookEvent created
4. Redis event broadcast (< 100ms)
5. SSE event received by both browser tabs (< 2 seconds)
6. UI updates in both tabs without F5 refresh
7. Unread badge increments
8. Message visible in timeline

**Success Criteria**: All verification checks pass in both tabs

**Failure Criteria**: Any of the following
- API does not return 200
- Message not stored in PostgreSQL
- Redis event not broadcast
- SSE event not received (timeout > 5 sec)
- UI does not update without F5
- Unread badge does not change
- Message missing from timeline
- Console errors in either tab

---

## After Test Confirmation

**When verification passes**:
1. Close one of the two tabs
2. Wait for next user instruction (echo test)
3. Do NOT send another message yet

**When verification fails**:
1. Diagnose issue from logs
2. Check database state
3. Provide error details
4. Do NOT proceed to echo test

---

**Status**: Ready for real inbound test  
**Database Snapshot**: 945 messages, 952 webhooks  
**Browser State**: 2 tabs, SSE active, testadmin logged in  
**Next Action**: User sends FASE5B-SSE-WALTER-REAL-001 message from Walter
