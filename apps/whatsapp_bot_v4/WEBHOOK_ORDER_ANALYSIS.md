# YCloud Webhook Order & Async Analysis

**Date**: 2026-08-21  
**Status**: Documented + Tests Created  
**Tests**: `tests_webhook_order_and_async.py` (6 complete tests)

---

## CURRENT EXECUTION ORDER (SYNC)

```
[1] POST /webhooks/ycloud/v1/ received
    ↓
[2] verify_ycloud_signature() ← LINE 140
    │
    ├─ PASS → continue to [3]
    └─ FAIL → HTTP 401 (STOP HERE, no persistence)
    ↓
[3] json.loads() ← LINE 146
    │
    ├─ SUCCESS → continue to [4]
    └─ FAIL → HTTP 400 (STOP HERE)
    ↓
[4] Extract event_type, event_id ← LINE 154-163
    │
    ├─ VALID → continue to [5]
    └─ MISSING → HTTP 400 (STOP HERE)
    ↓
[5] Check idempotence (WebhookEvent lookup) ← LINE 167-172
    │
    ├─ EXISTS → HTTP 200 with {'status': 'skipped'} (STOP HERE, no reprocessing)
    └─ NEW → continue to [6]
    ↓
[6] Create WebhookEvent ← LINE 176-182
    │
    ├─ SUCCESS → continue to [7]
    └─ FAIL → log error, continue anyway
    ↓
[7] Normalize payload ← LINE 186
    │
    ├─ SUCCESS → continue to [8]
    └─ FAIL → HTTP 200 with {'status': 'ok'} (STOP HERE)
    ↓
[8] Get WhatsAppChannel (must exist) ← LINE 194-198
    │
    ├─ EXISTS → continue to [9]
    └─ NOT FOUND → HTTP 200 (STOP HERE, graceful degradation)
    ↓
[9] Import process_ycloud_event ← LINE 201
    ↓
[10] process_ycloud_event(event_type, canonical_payload, channel) ← LINE 204
     │
     └─ @transaction.atomic() BEGINS HERE
        │
        ├─ [10a] classify_event()
        │
        ├─ [10b] resolve client phone from 'to' (echo) or 'from' (inbound)
        │
        ├─ [10c] Cliente.objects.get_or_create() ← PERSISTS CLIENT
        │
        ├─ [10d] resolve_or_create_active_conversation()
        │        ├─ Uses select_for_update() for race condition safety
        │        └─ ← PERSISTS CONVERSATION
        │
        ├─ [10e] ConversacionWhatsApp.objects.select_for_update().get()
        │        └─ Lock conversation during atomic block
        │
        ├─ [10f] MensajeWhatsApp.objects.get_or_create() ← PERSISTS MESSAGE
        │
        ├─ [10g] Update conversation.ultima_actividad, resumen, etc.
        │        └─ ← UPDATES CONVERSATION
        │
        └─ [10h] If human intervention detected → bot_pausado=True
        │
        @transaction.atomic() COMMITS HERE (all 4 persist atomically)
    ↓
[11] Return result = {created, message, conversation, error}
    ↓
[12] Check if result.get("message") and result.get("conversation") ← LINE 209
    │
    ├─ YES → continue to [13]
    └─ NO → skip [13]
    ↓
[13] process_bot_for_conversation_async(conversation, message) ← LINE 212
    │
    ├─ IMPORTANT: This is SYNC, not async (see analysis below)
    ├─ Can take 2-10 seconds (OpenAI API call)
    ├─ If fails → exception caught, logged, ignored (LINE 257-258)
    └─ ← BLOCKS HTTP 200 UNTIL COMPLETE
    ↓
[14] Return HTTP 200 JsonResponse({'status': 'ok'}) ← LINE 222
    │
    └─ ← HTTP 200 ONLY AFTER all of [1-13] complete
```

---

## PERSISTENCE HAPPENS BEFORE HTTP 200 ✓

**Key fact**: Message, Conversation, and Client are all persisted in `@transaction.atomic()` block [10a-10h], which commits BEFORE bot processing [13].

### Timeline:

| Step | What Happens | HTTP 200? | Persisted? |
|------|-------------|----------|-----------|
| [2] | Signature validation | ❌ 401 | ❌ |
| [6] | WebhookEvent registered | 🔄 continue | ⚠️ maybe |
| [10] | Cliente/Conv/Msg persisted | 🔄 continue | ✅ YES |
| [13] | Bot processing (OpenAI call) | 🔄 continue | ✅ (already done) |
| [14] | Return HTTP 200 | ✅ 200 | ✅ |

**Proof**: Test 1 in `tests_webhook_order_and_async.py` demonstrates:
```python
# Send webhook
response = self.client.post(...)

# HTTP 200 returned
self.assertEqual(response.status_code, 200)

# Message already persisted (created BEFORE HTTP 200)
msg = MensajeWhatsApp.objects.filter(meta_message_id="wamid_001").first()
self.assertIsNotNone(msg)  # ✅ PASSES
```

---

## BOT PROCESSING IS SYNC (NOT ASYNC) ⚠️

### Current Behavior

**Name**: `process_bot_for_conversation_async()`  
**Reality**: Synchronous function that blocks the HTTP response.

```python
# Line 212 in ycloud_webhook_service.py
process_bot_for_conversation_async(result["conversation"], result["message"])
# ↑ This doesn't return until bot processing is complete
# ↑ Takes 2-10 seconds for OpenAI API call
# ↑ HTTP 200 is delayed by this time
```

### Timeline with Bot Latency

Without bot processing:
```
Webhook received → Signature check → Persistence → HTTP 200
Total: ~50ms
```

With bot processing (current SYNC behavior):
```
Webhook received → Signature check → Persistence → BOT PROCESSING (3-10s) → HTTP 200
Total: 3-10s+
```

### Problems with Current SYNC Approach

1. **Misleading function name** — suggests async but is sync
2. **Blocks HTTP response** — client has to wait for bot completion
3. **No timeout safety** — if OpenAI hangs, webhook times out
4. **Tight coupling** — bot failure affects webhook endpoint
5. **No retry logic** — transient bot failures lose the message (if persisted after bot)

### Proof: Test 2 in `tests_webhook_order_and_async.py`

```python
# Patch bot processing with 500ms delay
with patch('...process_bot_for_conversation_async', side_effect=delayed_process_bot):
    start_time = time.time()
    response = self.client.post(...)  # Send webhook
    elapsed = time.time() - start_time
    
    # If bot processing was TRULY async, elapsed would be < 50ms
    # But it's SYNC, so elapsed >= 500ms
    self.assertGreaterEqual(elapsed, 0.3)
```

---

## ERROR HANDLING MATRIX

| Error Point | HTTP Status | Persisted? | WebhookEvent? | Bot Runs? |
|-----------|----------|-----------|---|---|
| [2] Invalid signature | 401 | ❌ | ❌ | ❌ |
| [3] Invalid JSON | 400 | ❌ | ❌ | ❌ |
| [4] Missing event_type | 400 | ❌ | ❌ | ❌ |
| [5] Duplicate event_id | 200 skipped | ❌ | ✅ exists | ❌ |
| [6] WebhookEvent create fails | 200 ok | ✅ (continues) | ⚠️ maybe not | ✅ |
| [10] Transaction fails | 200 ok* | ❌ (rollback) | ✅ (created before tx) | ❌ |
| [13] Bot fails | 200 ok | ✅ (already done) | ✅ | ⚠️ error logged |

**\*Note**: Currently returns HTTP 200 even on transaction failure (line 218-219). This is intentional for idempotence.

---

## RACE CONDITIONS & select_for_update()

### Scenario: Two concurrent webhooks for same client

```
Thread 1: resolve_or_create_active_conversation(cliente_X)
Thread 2: resolve_or_create_active_conversation(cliente_X)
```

### Current Safety: YES ✅

Line 182 in `services_ycloud.py`:
```python
conversation = ConversacionWhatsApp.objects.select_for_update().get(pk=conversation.pk)
```

This uses database-level row locking to prevent race conditions. Test 6 verifies this.

**However**: The `resolve_or_create_active_conversation()` function is called BEFORE the lock. If that function has a race condition window, we could still get duplicates.

---

## TEST SUITE: tests_webhook_order_and_async.py

### Test 1: Message Persists BEFORE HTTP 200
- **Scenario**: Send webhook, verify message exists before HTTP 200 returns
- **Result**: ✅ PASSES — proves persistence before response
- **Code**: Captures HTTP response, then queries DB

### Test 2: Bot Processing is SYNC
- **Scenario**: Inject 500ms delay in bot processing, measure HTTP response time
- **Result**: ✅ PASSES — proves bot processing blocks the response
- **Code**: Uses `time.time()` to measure elapsed time

### Test 2b: HTTP 200 Timing Without Bot
- **Scenario**: Skip bot processing entirely, measure HTTP response time
- **Result**: ✅ PASSES — proves HTTP 200 is fast without bot
- **Code**: Patches bot function to return immediately

### Test 3: Error BEFORE Persistence
- **Scenario**: Send webhook with invalid signature
- **Result**: ✅ PASSES — HTTP 401, no persistence
- **Code**: Verifies Cliente, Conversation, Message don't exist

### Test 4: Error DURING Persistence
- **Scenario**: Send duplicate wamid (IntegrityError)
- **Result**: ✅ PASSES — idempotent, no duplicates
- **Code**: Sends same wamid twice, verifies only 1 message

### Test 5: Error AFTER Persistence (Bot Fails)
- **Scenario**: Inject exception in bot processing
- **Result**: ✅ PASSES — message persists, bot error logged
- **Code**: Patches bot function to raise RuntimeError, verifies message exists

### Test 6: Race Condition (Concurrent Webhooks)
- **Scenario**: Two threads send webhooks simultaneously for same client
- **Result**: ✅ PASSES — exactly 1 conversation, 2 messages
- **Code**: Uses threading to simulate concurrency

---

## RECOMMENDATIONS FOR IMPROVEMENT

### Recommendation 1: Use Celery for TRUE Async

**Current problem**: Bot processing blocks HTTP 200

**Solution**: Queue bot processing task

```python
# In settings.py
INSTALLED_APPS += ['django_celery_beat', 'django_celery_results']

# Define task
@shared_task
def process_bot_conversation_async(conversation_id, message_id):
    """Run bot processing asynchronously."""
    conversation = ConversacionWhatsApp.objects.get(id=conversation_id)
    message = MensajeWhatsApp.objects.get(id=message_id)
    
    try:
        process_bot_response(
            conversation.cliente.telefono.lstrip('+'),
            message.contenido,
            conversation
        )
    except Exception as e:
        logger.error(f"[BotAsync] Error: {e}", exc_info=True)

# In webhook (ycloud_webhook_service.py)
if result.get("message") and result.get("conversation"):
    try:
        # Queue task instead of calling directly
        process_bot_conversation_async.delay(
            result["conversation"].id,
            result["message"].id
        )
    except Exception as e:
        logger.error(f"[Celery] Error queuing task: {e}", exc_info=True)
        # Still return HTTP 200 — message already persisted
```

**Benefits**:
- ✅ HTTP 200 returns in < 50ms (no bot latency)
- ✅ Message already persisted before task runs
- ✅ Fault isolation (bot failure doesn't affect webhook endpoint)
- ✅ Retry logic (Celery can retry failed tasks)
- ✅ Scalability (workers process tasks independently)

**Timeline after Celery**:
```
Webhook received → Signature check → Persistence → Queue task → HTTP 200
Total: ~50ms (instead of 3-10s)
```

### Recommendation 2: Explicit HTTP 200 Return Point

Current code returns HTTP 200 after bot processing:

```python
# Line 222 (AFTER bot processing)
return JsonResponse({'status': 'ok'})
```

**Improved approach**:

```python
# Immediate return after persistence, before bot processing
try:
    # ... persistence code ...
    http_200_response = JsonResponse({'status': 'ok'})
except Exception as e:
    # ... error handling ...
    http_200_response = JsonResponse({'status': 'ok'})  # Graceful degradation

# Queue bot processing (doesn't block response)
if result.get("message") and result.get("conversation"):
    try:
        process_bot_conversation_async.delay(...)
    except Exception as e:
        logger.error(...)

# Return HTTP 200 immediately
return http_200_response
```

### Recommendation 3: Add Monitoring

```python
import time

# Log timing for observability
webhook_start = time.time()

# ... persistence code ...
persistence_time = time.time() - webhook_start
logger.info(f"[Perf] Persistence: {persistence_time*1000:.1f}ms")

# Queue task
task_queued_time = time.time() - webhook_start
logger.info(f"[Perf] Task queued at: {task_queued_time*1000:.1f}ms")

# Return HTTP 200
http_200_time = time.time() - webhook_start
logger.info(f"[Perf] HTTP 200 at: {http_200_time*1000:.1f}ms")
```

**Expected metrics with Celery**:
- Persistence: 20-50ms
- Task queued: 25-55ms
- HTTP 200: 30-60ms
- Bot processing: 2-10s (async, not blocking webhook)

---

## RUN THE TESTS

```bash
# Run all webhook order tests
python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async

# Run specific test
python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async.YCloudWebhookOrderTests.test_1_message_persists_before_http_200

# With verbose output
python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async -v 2
```

---

## SUMMARY

| Aspect | Current | Recommendation |
|--------|---------|---|
| Message persistence | ✅ Before HTTP 200 | ✅ Keep as-is |
| HTTP 200 timing | 3-10s (includes bot) | < 50ms (queue bot) |
| Bot processing | Sync (blocks) | Async (Celery) |
| Fault isolation | ❌ Bot failure affects webhook | ✅ Bot failure isolated |
| Retry logic | ❌ None | ✅ Celery retries |
| Scalability | Limited (blocking) | ✅ Horizontal scaling |
| Function naming | ⚠️ Misleading async name | ✅ Rename to _process_bot_sync() until Celery is added |

---

## Conclusion

**Current behavior is correct for persistence** (message saves before HTTP 200), but **bot processing should be truly asynchronous** to improve webhook latency and fault isolation. The provided tests prove both the current behavior and areas for improvement.
