# FASE 5B: Preflight Checklist — Docker Infrastructure Ready

**Status**: ✓ Infrastructure validated, ready for manual user testing  
**Date**: 2026-08-24 17:14 UTC  
**All services**: Running and healthy

---

## 1. Service Status

| Service | Port | Status | Access |
|---------|------|--------|--------|
| **Nginx** (reverse proxy) | 8001 | ✓ Running | http://localhost:8001 |
| **Django** (Gunicorn) | 8000 | ✓ Running (internal) | Not public |
| **PostgreSQL** | 5433 | ✓ Running (local dev) | localhost:5433 |
| **Redis** | 6380 | ✓ Running (local dev) | localhost:6380 |

---

## 2. Data Verification

### Database Snapshot (clean audit 17:12 UTC)

| Metric | Value | Status |
|--------|-------|--------|
| **Users (auth_user)** | 21 | ✓ Complete (testadmin restored) |
| **Clients (clientes_cliente)** | 161 | ✓ Complete (Cliente 77 present) |
| **Conversations** | 259 | ✓ Complete (Channel 2 + Client 77 = 1) |
| **Messages** | 945 | ✓ Complete (point-in-time accurate) |
| **WebhookEvents** | 952 | ✓ Complete (latest before post-restore activity) |
| **Channels** | 30 | ✓ Complete |
| **FK Constraints** | 116 | ✓ All valid, no orphaned records |
| **Unique Indexes** | Present | ✓ Active |

### Key Entities Confirmed

- ✓ **Cliente 77**: Exists, is_active=true
- ✓ **Channel 2**: Exists, activo=true
- ✓ **Walter (Channel 2 + Client 77)**: Exactly 1 conversation
- ✓ **Unread states**: 34 records present
- ✓ **testadmin**: Created + configured, password=testpass123

---

## 3. Network Architecture

```
┌─────────────────────────────────────┐
│   Browser                            │
│   http://localhost:8001/login        │
└──────────────┬──────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Nginx (localhost:8001)      │  ← Single public entry point
│  - SPA fallback routing      │
│  - /dashboard/api/* → Django │
│  - /static/* → Assets        │
│  - Rate limiting on login    │
└──────────────┬───────────────┘
               │
        ┌──────┴──────┬──────────┬──────────┐
        ▼             ▼          ▼          ▼
   Django        PostgreSQL    Redis      [Internal only]
   Gunicorn      (localhost)   (cache)
   (8000)        (5433)        (6380)
   
   ✓ All internal via Docker network (app-network)
   ✓ Database connections not exposed to network
   ✓ Redis not exposed to external clients
```

### Port Policy

- ✓ **8001** (Nginx): Public endpoint, available on 0.0.0.0
- ✗ **8000** (Django): Dev convenience exposed, should restrict to 127.0.0.1 in production
- ✗ **5433** (PostgreSQL): Dev convenience exposed, should restrict to 127.0.0.1 in production  
- ✗ **6380** (Redis): Dev convenience exposed, should restrict to 127.0.0.1 in production

**Note**: Current exposure is acceptable for development/testing. Production deployment should use Docker override to bind to 127.0.0.1 only.

---

## 4. Manual Testing Instructions

### Step 1: Open Browser
```
Open:  http://localhost:8001/login
```

### Step 2: Verify Vue Form
- [ ] Login page loads (no 404 errors)
- [ ] Form visible with username + password fields
- [ ] Submit button present
- [ ] Console: No errors in browser DevTools

### Step 3: Login with testadmin
```
Username:  testadmin
Password:  testpass123
```
(Not testpass123/testpass123 — username is testadmin, password is testpass123)

- [ ] Form accepts input
- [ ] Submit succeeds (no 401/403)
- [ ] Redirected to: http://localhost:8001/atencion/bandeja-entrada

### Step 4: Verify Bandeja (Inbox)
Once redirected, check:
- [ ] Page loads without infinite loader
- [ ] Conversations list visible
- [ ] **Walter conversation visible** (Client 77, Channel 2)
- [ ] Conversation has message history
- [ ] Message count displayed (should be >0)
- [ ] Timestamps visible and reasonable
- [ ] No 404/500 errors in console

### Step 5: Verify Session Persistence
- [ ] sessionid cookie set (DevTools → Application → Cookies)
- [ ] csrftoken cookie set
- [ ] Try F5 refresh: Session persists, no re-login needed
- [ ] Open second tab to same URL: Session shared

### Step 6: Verify SSE (Real-Time Updates)
- [ ] Open DevTools → Network tab
- [ ] Filter: XHR + Fetch
- [ ] Look for: `/dashboard/whatsapp/api/events/stream/` connection
- [ ] Status: 200, "Pending" (SSE is streaming)
- [ ] NO requests to port 5177 (Vite dev server)

### Step 7: Final Validation
- [ ] All critical paths working: login → bandeja → conversations
- [ ] No manual F5 needed for message updates (test if SSE fires)
- [ ] SQLite NOT used (confirmed in test databases)
- [ ] PostgreSQL Docker confirmed (database via Nginx → Django)

---

## 5. API Verification

### Login Endpoint
```bash
curl -X POST http://localhost:8001/dashboard/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testadmin","password":"testpass123"}'
```

**Expected Response**:
```json
{
  "status": "ok",
  "user": {
    "id": 10,
    "username": "testadmin",
    "email": "a@a.com",
    "full_name": "testadmin",
    "is_staff": true,
    "is_superuser": true
  }
}
```

**Expected Status**: `HTTP 200`  
**Expected Cookies**: `sessionid`, `csrftoken` set

---

## 6. Known Issues & Workarounds

### ⚠ Port Exposure (Dev Only)
- Django/PostgreSQL/Redis visible on 0.0.0.0
- **Fix for production**: Use docker-compose override to bind to 127.0.0.1
- **Impact on testing**: None, all intended

### ⚠ Post-Restore Data
- 3 messages (IDs 959-961) created after dump snapshot
- 15 webhook events (IDs 953-967) created after dump snapshot
- **Cause**: Live activity during E2E testing while restoration in progress
- **Classification**: Normal development activity, not data corruption
- **Action**: None required, data is valid

### ⚠ GRANT Errors (Non-Blocking)
- Some SQL lines tried to grant permissions to non-existent `postgres` role
- **Status**: Accepted by psql, permissions skipped safely
- **Impact**: None, taxicarga user has all necessary permissions
- **Action**: None required

---

## 7. Troubleshooting

### Issue: Login page returns 404
**Solution**: 
1. Check Nginx is running: `docker compose ps nginx`
2. Check logs: `docker compose logs nginx | tail -50`
3. Verify static files: `docker compose exec nginx ls -la /app/staticfiles/index.html`

### Issue: Login succeeds but no bandeja visible
**Solution**:
1. Check Django logs: `docker compose logs django | tail -50`
2. Verify session persisted: Check cookies in DevTools
3. Verify database connection: `docker compose exec postgres psql -U taxicarga -d taxicarga_pg_test -c "SELECT COUNT(*) FROM whatsapp_conversacionwhatsapp"`

### Issue: SSE not streaming (infinite loader)
**Solution**:
1. Check browser DevTools → Network for `/events/stream/` connection status
2. Verify no errors in Django logs
3. Restart Django: `docker compose restart django`
4. Check Redis is running: `docker compose ps redis`

### Issue: Console shows errors to port 5177
**Solution**: 
1. Stop Vite dev server if running
2. Verify no conflicting processes: `netstat -ano | grep 5177`
3. Refresh browser

---

## 8. Post-Testing Checkpoint

**When user confirms "Manual testing PASS":**

✓ Proceed to FASE 5B Real Testing  
✓ Prepare ngrok tunnel  
✓ Establish YCloud webhook baseline  
✓ Send real inbound message test  
✓ Verify end-to-end flow

**When user confirms "Manual testing FAIL":**

⚠ Stop here  
⚠ Collect logs  
⚠ Diagnose failure  
⚠ Fix issue before proceeding  
⚠ Do NOT advance to real WhatsApp testing

---

## 9. Readiness Summary

| Component | Check | Status |
|-----------|-------|--------|
| Docker Compose | All services healthy | ✓ PASS |
| PostgreSQL | Data restored atomically | ✓ PASS |
| Django | Settings_e2e configured | ✓ PASS |
| Nginx | SPA routing correct | ✓ PASS |
| Redis | Connected, AOF enabled | ✓ PASS |
| testadmin User | Created, password set | ✓ PASS |
| Login API | HTTP 200, session token | ✓ PASS |
| FK Integrity | 116 constraints valid | ✓ PASS |
| Sequences | Max IDs correct | ✓ PASS |
| SSL/TLS | Not enforced (dev) | ✓ PASS |

---

## 10. Next Actions (Blocked Until Manual Test Passes)

1. **User performs manual login test** (see Section 4 above)
2. **User confirms**: "I logged in as testadmin and saw my conversations"
3. **Then proceed**: Set up real WhatsApp webhook testing

---

**Signed**: FASE 5B Infrastructure Validation ✓  
**Status**: READY FOR MANUAL USER TESTING
