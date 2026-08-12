# Latency Investigation & Instrumentation — Complete

## Summary
Implemented comprehensive telemetry infrastructure for latency tracking across bot generation pipeline. OpenAI calls are now fully instrumented with real measurements.

## Completed Work

### 1. Request Lifecycle Status (ACTIVE/DORMANT/CLOSED)
- `RequestLifecycleStatus` enum with three states
- `_determine_lifecycle_status()` evaluates lead state + inactivity
- `INACTIVITY_THRESHOLD = 2 hours` (configurable, marked BUSINESS_RULE_REVIEW_REQUIRED)
- Prevents historical lead contamination in GPT classification

### 2. Telemetry Infrastructure
**File:** `apps/ia/latency_telemetry.py`
- `GenerationTelemetry` class: centralized latency tracking
- Context managers: `@telemetry.measure(step_name)` for each pipeline step
- `mark_from_ai_result()`: captures OpenAI call data from AIResult
- Structured metadata export for storage in `BotGeneration.conversation_metadata`

### 3. OpenAI Instrumentation
**Files Modified:**
- `apps/ia/providers.py`: Added retry logic (2 attempts), `attempt_count`/`retry_count` tracking in AIResult
- `apps/ia/request_lifecycle.py`: Pass telemetry to `classify_request_intent()`
- `apps/ia/conversation_orchestrator.py`: Pass telemetry to `orchestrate_conversation()`
- `apps/ia/conversation_engine.py`: Accept telemetry in `handle_incoming_message()`
- `apps/integrations/services/bot_generation_worker.py`: Wire telemetry through pipeline

**Measured Steps:**
- `request_lifecycle` (classify_request_intent)
- `build_bot_context` (static context construction)
- `handle_incoming_message` (orchestrator + strategy)
- `finalize_generation` (outbox/metadata storage)

### 4. Smoke Test Results
**File:** `apps/ia/smoke_latency.py` (3 test cases, local, no Meta)

```
Case 1: Clean request (null lead)      →  140ms  (no OpenAI calls)
Case 2: Active lead continuation       → 3664ms  (classify_request_intent: 3654ms)
Case 3: Active lead ambiguous          → 2053ms  (classify_request_intent: 2044ms)

Average: 1952ms | StdDev: 1764ms
```

**Bottleneck Identified:** `classify_request_intent` GPT calls (3-4 seconds for structured output)

### 5. Test Suite
**File:** `apps/ia/tests_lifecycle_status.py` (9 comprehensive tests)
- Lifecycle status determination (null, closed, lost, recent, inactive)
- Integration: null lead → NEW_REQUEST, dormant lead → NEW_REQUEST without contamination
- Active lead clarification (UNCERTAIN with request switch)

## Instrumentation Details

### OpenAI Call Tracking
Each call now records:
- **duration_ms**: End-to-end latency (perf_counter precision)
- **model**: Model identifier (gpt-4-mini, deepseek, etc.)
- **input_tokens**: Prompt tokens
- **output_tokens**: Completion tokens
- **retries**: Number of retry attempts (0 = single attempt)

### Example Metadata Storage
```json
{
  "total_ms": 3654,
  "steps": {
    "request_lifecycle": 3654,
    "openai_classify_request_intent": {
      "count": 1,
      "calls": [{
        "duration_ms": 3654,
        "model": "gpt-4-mini",
        "input_tokens": 410,
        "output_tokens": 20,
        "retries": 0
      }]
    }
  }
}
```

## Database State
- Pending outbox events: **0**
- Conversations without activity: **0**
- Active leads: **38**
- Closed/Lost leads: **2**

## Commits
- **61aff21**: Telemetry infrastructure + smoke test + tests_lifecycle_status
  - 3 new files, 8 files modified, 568 insertions

## Ready For
✓ Physical WhatsApp test (telemetry now active in production pipeline)
✓ Latency profiling (each bot generation logs step-by-step timing)
✓ OpenAI optimization (data on input/output tokens, retry rates, models used)

## Business Rules Pending
- `INACTIVITY_THRESHOLD` = 2 hours (marked BUSINESS_RULE_REVIEW_REQUIRED)
  - Current implementation: lead inactive >2h → DORMANT status
  - User to confirm: should this be 1h? 4h? configurable per-channel?

## Not Yet Optimized
- GPT response latency (3-4s per classify_request_intent call)
  - Could reduce input tokens in payload
  - Could cache common request classifications
  - Could use cheaper/faster model for classification
  - Requires separate optimization pass (not part of telemetry scope)

## Next Steps
1. Physical WhatsApp test with real users (telemetry now active)
2. Collect production latency data for 5-10 real conversations
3. Analyze bottlenecks: is 3s classify time acceptable? any timeouts?
4. Optional optimization: reduce token count, model selection, caching
