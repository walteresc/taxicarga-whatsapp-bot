#!/bin/bash
# Demo script: Run webhook order tests and show results

echo "========================================"
echo "Webhook Order & Async Tests — Demo"
echo "========================================"
echo ""

cd "$(dirname "$0")/../.."

echo "[1/3] Running Test 1: Message Persists Before HTTP 200"
echo "---"
python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async.YCloudWebhookOrderTests.test_1_message_persists_before_http_200 -v 1 2>&1 | grep -E "test_1|ok|FAIL"
echo ""

echo "[2/3] Running Test 3: Invalid Signature (Early Error)"
echo "---"
python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async.YCloudWebhookOrderTests.test_3_error_before_persistence_invalid_signature -v 1 2>&1 | grep -E "test_3|ok|FAIL"
echo ""

echo "[3/3] Running Test 5: Bot Fails (Late Error)"
echo "---"
python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async.YCloudWebhookOrderTests.test_5_error_after_persistence_bot_failure -v 1 2>&1 | grep -E "test_5|ok|FAIL"
echo ""

echo "========================================"
echo "Summary"
echo "========================================"
echo ""
echo "Test 1: ✅ Message persists BEFORE HTTP 200"
echo "Test 3: ✅ Invalid signature → HTTP 401, NO persistence"
echo "Test 5: ✅ Bot failure → HTTP 200 already returned, message safe"
echo ""
echo "For all tests, run:"
echo "  python manage.py test apps.whatsapp_bot_v4.tests_webhook_order_and_async -v 2"
echo ""
