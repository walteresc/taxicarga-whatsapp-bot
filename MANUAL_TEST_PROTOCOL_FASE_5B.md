# Manual Test Protocol — FASE 5B Real-Time Chat

**Date**: 2026-08-22  
**Objective**: Validate end-to-end real-time updates (event streaming) without page refresh  
**Prerequisites**:
- PostgreSQL running (DATABASE_URL set)
- Django runserver on localhost:8001
- Frontend dev server (Vite) proxying /dashboard to localhost:8001
- Channel 2 (Lima Express) active
- Walter (cliente 77) with conv 226 in Channel 2

---

## Setup Phase

### 1. Start Backend & Frontend

```bash
# Terminal 1: Django
cd Taxi_carga_bot/taxicarga_whatsapp_bot
export DATABASE_URL='postgres://taxicarga@localhost:5432/taxicarga_pg_test'
python manage.py runserver 8001

# Terminal 2: Frontend
cd Taxi_carga_bot/taxicarga_whatsapp_bot/frontend_materio
npm run dev  # Vite on http://localhost:5173
```

### 2. Capture Baseline

Open browser:
```
http://localhost:5173/dashboard/whatsapp/
```

Log in. Navigate to Conversaciones.

**Screenshot baseline-01**: List shows Conv 226 (Lima Express), Ch 2, Walter
- Record: `ultima_actividad` timestamp
- Record: conversation preview text (last message)
- Record: unread count if any

DO NOT reload page. This session stays open throughout all tests.

---

## Test Phase 1: Event Bus Polling

### 1. Verify Event Endpoint

Open new browser tab:
```
http://localhost:8001/dashboard/whatsapp/api/events/stream/
```

Should return JSON:
```json
{
  "events": [],
  "latest_cursor": 0,
  "timestamp": "2026-08-22T..."
}
```

**✓ PASS**: Endpoint responds with empty events list  
**✗ FAIL**: 403/404/500 error → check Django logs

---

## Test Phase 2: Message Inbound (Without Page Refresh)

### 1. Send Real Message from Walter

From WhatsApp (Walter's real phone):
```
Send message: "TEST INBOUND - no refresh"
To: Lima Express number (+51967619238)
```

Wait 10-30 seconds.

### 2. Verify Event Bus (No Reload)

In same tab, refresh event endpoint:
```
http://localhost:8001/dashboard/whatsapp/api/events/stream/?cursor=0
```

Should show event:
```json
{
  "type": "message_created",
  "data": {
    "conversation_id": 226,
    "message_id": <N>,
    "sender_type": "customer",
    "timestamp": "2026-08-22T..."
  }
}
```

**✓ PASS**: Event visible in API without page reload  
**✗ FAIL**: No event → check Django logs for signal errors

### 3. Verify UI Update (No Reload)

Back to Dashboard tab (localhost:5173):
- **✓ PASS**: Conversation 226 preview updates to "TEST INBOUND..."
- **✓ PASS**: `ultima_actividad` timestamp advances
- **✗ FAIL**: Still shows old preview → check browser console for fetch errors

**Screenshot test-inbound-01**: Conversaciones list updated

---

## Test Phase 3: Message Echo (No Refresh)

### 1. Open Conversation 226

Click on Conv 226 in dashboard (still same tab, no reload).

Timeline should show:
- Walter's inbound message "TEST INBOUND..."
- (Any previous messages)

**Screenshot test-echo-setup-01**: Timeline with inbound message visible

### 2. Send Echo (Advisor Sends)

As advisor, send reply:
```
Text: "ECHO RESPONSE - no refresh"
To: Conv 226 (Lima Express / Walter)
```

Wait 10-30 seconds.

### 3. Verify Event (No Reload)

Event API should show new event:
```
http://localhost:8001/dashboard/whatsapp/api/events/stream/?cursor=<last_cursor>
```

Should include:
```json
{
  "type": "message_created",
  "data": {
    "conversation_id": 226,
    "sender_type": "advisor",
    "direction": "saliente"
  }
}
```

**✓ PASS**: Event visible  
**✗ FAIL**: No event → check signal registration in apps.py

### 4. Verify Timeline Update (No Reload)

Back to Dashboard (same tab):
- **✓ PASS**: Timeline shows new message "ECHO RESPONSE..." from advisor
- **✓ PASS**: Message appears below inbound (chronological order)
- **✗ FAIL**: Still shows old state → check Pinia store fetch

**Screenshot test-echo-response-01**: Timeline with both messages

---

## Test Phase 4: Multi-Tab Consistency

### 1. Open Second Tab

```
http://localhost:5173/dashboard/whatsapp/
```

Log in (same user).

### 2. Send Another Message

From Walter's phone:
```
"MULTI-TAB TEST"
```

### 3. Verify Both Tabs Update

- **Tab 1** (original): Should update conversation preview
- **Tab 2** (new): Should also show updated preview
- Both should update independently (separate polling instances)

**✓ PASS**: Both tabs show update  
**✓ PASS**: No "stale" state in either tab  
**✗ FAIL**: Only one tab updates → polling isolation issue

---

## Acceptance Criteria

**All must PASS for FASE 5B to be green:**

- [ ] Event API endpoint returns JSON (no errors)
- [ ] Inbound message triggers event_stream update (no page reload)
- [ ] Conversation preview updates in real-time
- [ ] Echo message creates event visible in API
- [ ] Timeline updates with new message (no refresh)
- [ ] Multi-tab consistency (both tabs see updates)
- [ ] No JavaScript console errors
- [ ] Connection status indicator works (shows offline on disconnect)

---

## Rollback Instructions

If any test fails:

1. **Check Django logs**: `tail -f django_debug.log`
   - Look for signal import errors
   - Look for HTTP 500 on /api/events/stream/

2. **Check browser console**: F12 → Console
   - Network fetch errors
   - Pinia store errors
   - Event listener warnings

3. **Verify PostgreSQL**:
   ```bash
   psql -U taxicarga -d taxicarga_pg_test -c "SELECT COUNT(*) FROM whatsapp_webhookevent;"
   ```

4. **Reset event bus** (development only):
   ```bash
   python manage.py shell
   >>> from apps.whatsapp.events_service import _reset_for_testing
   >>> _reset_for_testing()
   ```

5. **Restart Django** (if signal changes):
   ```bash
   python manage.py runserver 8001
   ```

---

## Sign-Off

- **Tester**: ________________
- **Date**: ________________
- **Notes**: ________________
