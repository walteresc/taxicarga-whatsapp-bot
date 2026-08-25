# FASE 5B Real Inbound Test: FASE5B-SSE-WALTER-REAL-001

**Status**: Ready to execute  
**Baseline**: Walter/Channel 2 conversation 226 with 3 messages captured  
**Preparation**: Two tabs open, SSE active, ready for real message

---

## STEP 1: Open Tab 1 (Monitoring)

```
URL: http://localhost:8001/atencion/bandeja-entrada
User: testadmin / testpass123
Goal: Watch for message arrival in conversation list
```

### Tab 1 Setup Instructions

1. **Open Developer Tools**
   - Press: F12 (or Ctrl+Shift+I on Windows)
   - Go to: Network tab
   
2. **Filter for SSE**
   - In Network filter box, type: `events/stream`
   - Confirm you see connection with status "200" (pending/streaming)
   
3. **Verify Connection**
   - Click on `/events/stream/` entry
   - Check: Status = 200
   - Check: Type = fetch
   - Check: Shows "Pending" (streaming active)
   
4. **Keep Open**
   - Do NOT close DevTools Network tab
   - Monitor this connection during test

### Tab 1 Bandeja View

- Scroll to show **Walter's conversation (Channel 2, Cliente 77)**
- Leave conversation LIST visible (not inside timeline yet)
- Note current state: 3 messages, last activity 2026-08-22

---

## STEP 2: Open Tab 2 (Detail View)

```
URL: http://localhost:8001/atencion/bandeja-entrada (same tab group, or new window)
User: testadmin / testpass123
Goal: Watch timeline for new message arrival
```

### Tab 2 Setup Instructions

1. **Open same Bandeja page** (login if needed)
2. **Click into Walter's conversation** (Conversation 226)
3. **Verify timeline shows 3 messages**
   - ID 802 (entrante, 2026-08-22 00:44:54)
   - ID 803 (entrante, 2026-08-22 00:50:07)
   - ID 804 (saliente, 2026-08-22 00:52:15)

4. **Open Developer Tools** (F12)
   - Go to: Console tab
   - Look for any pre-existing errors (should be none)
   
5. **Scroll to bottom of timeline**
   - Position cursor at end of message 804
   - Watch this spot for new message 962 to appear

---

## STEP 3: Real Inbound Message

**ONLY AFTER both tabs are set up (not before):**

### Send from Walter's Phone

Send one text message from Walter Escobar's WhatsApp to the Lima Express Bot:

```
From:  Walter's WhatsApp phone (+51995403320)
To:    Lima Express Bot (Channel 2 business number)
Text:  Any message (test, "Hola", "1", etc.)
Time:  Send NOW
```

### Expected Sequence (Timeline)

```
T+0s    Message sent from Walter's phone
T+1s    YCloud webhook received by Nginx
T+1.5s  Django processes, stores in PostgreSQL
T+2s    Redis event broadcast
T+2.5s  SSE event received by both tabs
T+3s    Tab 1: Unread badge updates, timestamp changes
T+3s    Tab 2: New message appears in timeline
T+5s    Both tabs show message fully rendered
```

**Maximum acceptable latency**: 5 seconds from send to UI update in both tabs

---

## STEP 4: Verify in Tab 1 (Inbox List)

Immediately after message sends, watch Tab 1:

### Visual Checks
- [ ] Conversation 226 moves to top (newest activity)
- [ ] Conversation timestamp updates to current time
- [ ] Unread badge changes from "1" to "2"
- [ ] Preview text shows new message snippet
- [ ] Message direction shows as "Entrante" (inbound)

### Network Checks (Tab 1 DevTools Network)
- [ ] `/events/stream/` connection still shows "200 Pending"
- [ ] NO errors (red) in Network tab
- [ ] POST request to `/dashboard/api/` (message received, if any)

### Timeline Checks (Tab 1 Console)
- [ ] NO error messages
- [ ] NO "Connection closed" messages
- [ ] If you see `[SSE] message received` logs, note the timestamp

---

## STEP 5: Verify in Tab 2 (Conversation Timeline)

Immediately after Tab 1 updates, check Tab 2:

### Visual Checks
- [ ] New message appears at bottom of timeline
- [ ] Message timestamp is current (recent minutes, today)
- [ ] Message direction is "Entrante" (inbound arrow/style)
- [ ] Message text is visible (not empty, not "loading")
- [ ] Message ID is NEW (should be ID 962 or higher, not 804)
- [ ] Unread badge at top of page shows "2" (or appropriate count)

### Network Checks (Tab 2 DevTools Network)
- [ ] NO requests to "localhost:5177" (Vite dev server)
- [ ] NO 404 errors
- [ ] NO 500 errors
- [ ] POST/GET to `/dashboard/whatsapp/` (normal API calls)

### Timeline Checks (Tab 2 Console)
- [ ] NO JavaScript errors
- [ ] NO "Connection lost" or "SSE error" messages
- [ ] Console should be clean

---

## STEP 6: Verify Message in Both Tabs

### Synchronization Check

- [ ] Tab 1 shows updated conversation preview
- [ ] Tab 2 timeline shows same message
- [ ] Both show identical timestamp (within 1 second)
- [ ] Both show identical message text
- [ ] Both show identical direction ("Entrante")

### Refresh Test (Optional)

- [ ] In Tab 1: Press F5 (refresh bandeja)
- [ ] Message count should still show 4 (not revert to 3)
- [ ] In Tab 2: Press F5 (refresh timeline)
- [ ] Message 962 should still be visible
- [ ] Unread count should persist

---

## STEP 7: Database Verification (After Visual Confirmation)

**Only if visual checks pass**, run this query to confirm data persisted:

```bash
curl -s -X POST http://localhost:8001/dashboard/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testadmin","password":"testpass123"}' | jq '.user.id'
# Use sessionid cookie from response

curl -s "http://localhost:8001/dashboard/whatsapp/conversaciones/api/conversaciones/226/" \
  -H "Cookie: sessionid=<COOKIE_FROM_LOGIN>" | jq '.message_count'
# Expected: 4
```

Or use psql:
```bash
docker compose exec postgres psql -U taxicarga -d taxicarga_pg_test -c \
  "SELECT COUNT(*) FROM whatsapp_mensajewhatsapp WHERE conversacion_id = 226;"
# Expected output: 4
```

---

## STEP 8: Report Results

Once test completes, provide:

### If PASS:
```
✓ Message sent at: HH:MM:SS
✓ Tab 1 updated at: HH:MM:SS (latency: X seconds)
✓ Tab 2 updated at: HH:MM:SS (latency: X seconds)
✓ Unread badge changed from 1 to 2
✓ Message text visible in both tabs
✓ No errors in console
✓ Database confirmed: 4 messages in conversation 226
```

### If FAIL:
```
✗ Issue: [describe what did not happen]
✗ Tab 1 status: [UI updated / not updated / error]
✗ Tab 2 status: [UI updated / not updated / error]
✗ Network errors: [yes/no, describe if yes]
✗ Console errors: [yes/no, error text]
✗ Database state: [check with psql query above]
```

---

## Troubleshooting (If Test Fails)

### SSE Connection Dies Before Message Arrives
**Symptom**: `/events/stream/` shows "cancelled" or closes

**Fix**: 
1. Refresh Tab 1: F5
2. Wait for connection to re-establish
3. Try message again
4. If fails twice, check Django logs: `docker compose logs django | tail -100`

### Message Appears in Tab 2 But Not Tab 1
**Symptom**: Timeline updates but inbox list doesn't

**Fix**:
1. Refresh Tab 1 inbox list (F5)
2. Check if unread count updates
3. Likely race condition; try once more

### Message Does Not Appear in Either Tab
**Symptom**: No visual update after 10 seconds

**Fix**:
1. Check Django logs: `docker compose logs django | tail -100`
2. Check PostgreSQL has message: `docker compose exec postgres psql -U taxicarga -d taxicarga_pg_test -c "SELECT COUNT(*) FROM whatsapp_mensajewhatsapp WHERE conversacion_id = 226;"`
3. If count is 3 (unchanged): Webhook not received
4. If count is 4: Message stored but SSE/Redis failed
5. Provide error details before retry

---

## Important Notes

- ✓ **DO NOT send multiple messages** — one test message only
- ✓ **DO NOT refresh yet** — wait for automatic SSE update
- ✓ **DO NOT close tabs** — keep both open for synchronization check
- ✓ **DO NOT advance to echo test** — wait for confirmation
- ✗ **Do NOT modify database** — only query, no inserts/updates
- ✗ **Do NOT restart services** — infrastructure must remain stable

---

## Next Step

**After this inbound test passes**:
1. Confirm results in report above
2. Wait for echo test instructions (FASE5B-SSE-ECHO-REAL-001)
3. Do NOT send echo message yet

**If test fails**:
1. Diagnose from troubleshooting guide
2. Provide error details
3. May need to restart services or debug backend
4. Do NOT proceed to echo until inbound passes

---

**Ready**: Two tabs prepared, SSE monitoring active  
**Test ID**: FASE5B-SSE-WALTER-REAL-001  
**Expected Outcome**: Message ID 962 appears in both tabs within 5 seconds
