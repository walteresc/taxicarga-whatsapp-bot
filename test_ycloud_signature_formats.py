#!/usr/bin/env python
"""
Test script to validate YCloud webhook signature formats.
Helps diagnose which format YCloud actually uses.
"""
import hmac
import hashlib
import json

# Minimal test payload (Walter message to Lima Express)
test_payload = {
    "id": "evt_test_probando11",
    "timestamp": 1724172420,
    "whatsappInboundMessage": {
        "from": "+51995403320",
        "to": "+51967619238",
        "id": "wamid_test_probando11",
        "text": {
            "body": "probando11"
        }
    }
}

# Convert to JSON (same as what Django receives)
payload_json = json.dumps(test_payload, separators=(',', ':'), ensure_ascii=False)
payload_bytes = payload_json.encode('utf-8')

SECRET = "test_secret_e2e"
TIMESTAMP = "1724172420"

print("=" * 80)
print("YCloud Webhook Signature Format Testing")
print("=" * 80)

print(f"\nPayload JSON:\n{payload_json}\n")
print(f"Payload bytes length: {len(payload_bytes)}")
print(f"Secret: {SECRET}")
print(f"Timestamp: {TIMESTAMP}\n")

# Format 1: HMAC-SHA256 of raw body only
sig1 = hmac.new(
    SECRET.encode(),
    payload_bytes,
    hashlib.sha256
).hexdigest()
print(f"Format 1 (body only):")
print(f"  Signed content: <raw_body>")
print(f"  Signature: {sig1}")
print(f"  YCloud header would be: Ycloud-Signature: t={TIMESTAMP},s={sig1}\n")

# Format 2: HMAC-SHA256 of timestamp.body
signed_content2 = f"{TIMESTAMP}.{payload_json}"
sig2 = hmac.new(
    SECRET.encode(),
    signed_content2.encode(),
    hashlib.sha256
).hexdigest()
print(f"Format 2 (timestamp.body):")
print(f"  Signed content: {TIMESTAMP}.<json_body>")
print(f"  Signature: {sig2}")
print(f"  YCloud header would be: Ycloud-Signature: t={TIMESTAMP},s={sig2}\n")

# Format 3: HMAC-SHA256 of timestamp.body_bytes (alternative)
signed_content3 = f"{TIMESTAMP}".encode() + b"." + payload_bytes
sig3 = hmac.new(
    SECRET.encode(),
    signed_content3,
    hashlib.sha256
).hexdigest()
print(f"Format 3 (timestamp_bytes.body_bytes):")
print(f"  Signed content: <timestamp_as_bytes>.<body_bytes>")
print(f"  Signature: {sig3}")
print(f"  YCloud header would be: Ycloud-Signature: t={TIMESTAMP},s={sig3}\n")

# Format 4: HMAC with sorted keys (some APIs do this)
payload_sorted = json.dumps(test_payload, separators=(',', ':'), ensure_ascii=False, sort_keys=True)
sig4 = hmac.new(
    SECRET.encode(),
    payload_sorted.encode(),
    hashlib.sha256
).hexdigest()
print(f"Format 4 (body with sorted keys):")
print(f"  Signed content: <json_with_sorted_keys>")
print(f"  Signature: {sig4}")
print(f"  YCloud header would be: Ycloud-Signature: t={TIMESTAMP},s={sig4}\n")

print("=" * 80)
print("INSTRUCTIONS:")
print("=" * 80)
print("""
1. Open YCloud Delivery Log for the "probando11" event
2. Find the exact signature value in the "Signature" or "Ycloud-Signature" field
3. Compare against the signatures above:
   - If it matches Format 1 → YCloud uses raw body only
   - If it matches Format 2 → YCloud uses timestamp.body (CURRENT IMPLEMENTATION)
   - If it matches Format 3 → YCloud uses timestamp_bytes.body_bytes
   - If it matches Format 4 → YCloud sorts JSON keys before signing
   - If it matches none → Unknown format (may need documentation from YCloud)

4. Report which format matches
5. If Format 2 matches, the issue is likely:
   - Wrong timestamp extraction
   - Body encoding/decoding mismatch
   - Secret mismatch (different secret in YCloud config than test_secret_e2e)
""")
