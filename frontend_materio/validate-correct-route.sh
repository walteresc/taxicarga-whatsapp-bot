#!/bin/bash

# Validación rápida de que la ruta correcta es accesible

echo "=== VALIDATING CORRECT ROUTE ==="
echo ""

# 1. Check HTTP status
echo "[1] Checking HTTP status..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/atencion/bandeja-entrada/)
echo "    HTTP $STATUS"

if [ "$STATUS" != "200" ]; then
  echo "    ✗ FAIL: Expected 200, got $STATUS"
  exit 1
fi

# 2. Check if page contains Vue app indicators
echo ""
echo "[2] Checking page content..."
RESPONSE=$(curl -s http://localhost:8001/atencion/bandeja-entrada/)

if echo "$RESPONSE" | grep -q "atencion/bandeja-entrada"; then
  echo "    ✓ Route path found in HTML"
else
  echo "    ⚠️  Route path NOT in initial HTML (may load via Vue)"
fi

if echo "$RESPONSE" | grep -q "id=\"app\"\|class=\"app\"\|data-v-"; then
  echo "    ✓ Vue app indicators found"
else
  echo "    ⚠️  Vue app indicators not in initial HTML (expected - SPA)"
fi

# 3. Check legacy route still exists (for documentation)
echo ""
echo "[3] Checking legacy route..."
LEGACY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/dashboard/whatsapp/conversaciones/)
echo "    HTTP $LEGACY_STATUS (legacy route /dashboard/whatsapp/conversaciones/)"

if [ "$LEGACY_STATUS" = "200" ]; then
  echo "    ℹ️  Legacy route still serves content (Django template, not Vue)"
fi

# 4. Summary
echo ""
echo "=== SUMMARY ==="
echo "✓ Vue app route: http://localhost:8001/atencion/bandeja-entrada/"
echo "✓ HTTP 200 confirmed"
echo "✓ Ready for Playwright tests"
echo ""
echo "IMPORTANT:"
echo "- Next: Run paso1-reproduce-layout-bug.mjs with manual login"
echo "- Browser will open at: /atencion/bandeja-entrada/ (CORRECT route)"
echo "- Do NOT use: /dashboard/whatsapp/conversaciones/ (legacy)"

exit 0
