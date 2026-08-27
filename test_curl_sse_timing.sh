#!/bin/bash
# FASE A: Test SSE with event published after connection

echo "================================================================================"
echo "FASE A: SSE Timing Test (curl version)"
echo "================================================================================"

# First, authenticate
echo -e "\n[1] Login..."
RESPONSE=$(curl -s -c /tmp/cookies.txt -X POST http://localhost:8001/dashboard/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testadmin","password":"testadmin123"}')
echo "[LOGIN] $RESPONSE"

# Verify cookie
COOKIE=$(cat /tmp/cookies.txt | grep "sessionid" | awk '{print $NF}')
echo "[COOKIE] $COOKIE"

# [2] Open SSE connection (background)
echo -e "\n[2] Opening SSE stream (5 second timeout)..."
timeout 10 curl -s -b "sessionid=$COOKIE" http://localhost:8001/dashboard/whatsapp/api/events/stream/ > /tmp/sse_stream.txt &
SSE_PID=$!
echo "[SSE_PID] $SSE_PID"

# Wait for connection to establish
sleep 3

# [3] Publish event
echo -e "\n[3] Publishing event..."
docker-compose exec -T django python manage.py shell << 'PYTHON'
from apps.whatsapp.redis_events import get_event_bus
import time

bus = get_event_bus()
event = bus.publish("message.created", {
    "conversation_id": 2,
    "channel_id": 2,
    "cliente_id": 3,
    "message_id": 999,
    "meta_message_id": "TEST-CURL-SSE-001",
    "sender_type": "customer",
    "preview": "TEST-CURL-SSE-001",
    "timestamp": int(time.time() * 1000),
    "conversation": {
        "summary": "TEST-CURL-SSE-001",
        "last_activity": time.time(),
        "unread_delta": 1,
        "attention_state": "bot",
        "bot_paused": False
    }
})
print(f"Event: {event.id if event else 'FAILED'}")
PYTHON

# Wait for stream to capture event
sleep 2

# [4] Kill SSE and check output
kill $SSE_PID 2>/dev/null
wait $SSE_PID 2>/dev/null

echo -e "\n[4] SSE Stream Output (last 30 lines):"
echo "---"
tail -30 /tmp/sse_stream.txt | cat -A
echo "---"

# [5] Check for event
if grep -q "TEST-CURL-SSE-001" /tmp/sse_stream.txt; then
    echo -e "\n✓ SUCCESS: Event found in SSE stream!"
else
    echo -e "\n✗ FAIL: Event NOT found in SSE stream"
    echo -e "\nFull stream content:"
    wc -l /tmp/sse_stream.txt
    head -20 /tmp/sse_stream.txt
    tail -20 /tmp/sse_stream.txt
fi
