import { chromium } from '@playwright/test'
import { spawn, execSync } from 'child_process';


(async () => {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()

  try {
    console.log('[TEST] GATE 3 Isolated - Fixed phone number')
    
    const TEST_PHONE = '+51991234567'
    const TEST_BODY = `Isolated test ${Date.now()}`
    
    // Step 1: Send webhook from Python
    console.log('[SETUP] Sending webhook from Python...')

    const webhookPy = `
import os, django, json, hmac, hashlib
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')
django.setup()

from django.test import Client
from django.conf import settings
from django.utils import timezone
from whatsapp_bot_v4.models import ConversacionWhatsApp

WEBHOOK_SECRET = settings.YCLOUD_WEBHOOK_SECRET

def sign_payload(body_str):
    timestamp = str(int(timezone.now().timestamp()))
    signed_content = f"{timestamp}.{body_str}"
    signature = hmac.new(WEBHOOK_SECRET.encode(), signed_content.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},s={signature}"

payload = {
    "id": "evt_isolated_\${Date.now()}",
    "type": "whatsapp.inbound_message.received",
    "whatsappInboundMessage": {
        "id": "wamid_isolated_\${Date.now()}",
        "from": "${TEST_PHONE}",
        "to": "+51967619238",
        "text": {"body": "${TEST_BODY}"}
    }
}

body = json.dumps(payload)
signature = sign_payload(body)

client = Client()
response = client.post(
    '/webhooks/ycloud/v1/',
    data=body,
    content_type='application/json',
    HTTP_YCLOUD_SIGNATURE=signature
)

conv = ConversacionWhatsApp.objects.filter(telefono="${TEST_PHONE}").first()
if conv:
    print(f"CONV_ID={conv.id}")
else:
    print("CONV_NOT_FOUND")
`

    const result = execSync(`python -c "${webhookPy.replace(/"/g, '\\"')}"`, { cwd: '../', encoding: 'utf8' })
    const convMatch = result.match(/CONV_ID=(\d+)/)
    const convId = convMatch ? convMatch[1] : null
    
    if (!convId) {
      console.log('[FAIL] Conversation not created')
      process.exit(1)
    }
    console.log(`[DB] Conversation created: ${convId}`)
    
    // Step 2: Load Playwright
    console.log('[AUTH] Loading bandeja-entrada...')
    await page.goto('http://localhost:5177/dashboard/login/', { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass')
    await page.click('button[type="submit"]')
    await page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {})
    
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForSelector('.main-container', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(3000)
    
    // Screenshot
    await page.screenshot({ path: 'test-results/isolated-before.png' })
    console.log('[SCREENSHOT] isolated-before.png')
    
    // Verify message
    const found = await page.locator(`text="${TEST_BODY}"`).count().catch(() => 0)

    console.log(`[VISUAL] Message in DOM: ${found > 0 ? 'YES' : 'NO'}`)
    
    if (found === 0) {
      console.log('[FALLBACK] Reloading...')
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(2000)

      const found2 = await page.locator(`text="${TEST_BODY}"`).count().catch(() => 0)

      console.log(`[FALLBACK] After F5: ${found2 > 0 ? 'YES' : 'NO'}`)
    }
    
    await page.screenshot({ path: 'test-results/isolated-after.png' })
    console.log('[SCREENSHOT] isolated-after.png')
    
  } catch (error) {
    console.error('[ERROR]', error.message)
  } finally {
    await browser.close()
  }
})()
