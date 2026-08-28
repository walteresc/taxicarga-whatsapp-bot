import { chromium } from '@playwright/test'
import { spawn } from 'child_process';

(async () => {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()

  try {
    console.log('[TEST] GATE 3 Visual - Hybrid approach')
    
    // Load bandeja-entrada
    console.log('[PAGE] Loading bandeja-entrada...')
    await page.goto('http://localhost:5177/dashboard/login/', { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass')
    await page.click('button[type="submit"]')
    await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {})
    
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForSelector('.main-container, [data-testid="conversation-list"]', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(2000)
    
    // Screenshot before
    await page.screenshot({ path: 'test-results/hybrid-before.png' })
    console.log('[SCREENSHOT] hybrid-before.png')
    
    // Send webhook from Python (verified signature)
    console.log('[WEBHOOK] Calling Python webhook sender...')

    const testId = `HYBRID-${Date.now()}`
    
    const pythonScript = `
import os, django, json, hmac, hashlib, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_e2e')
django.setup()

from django.test import Client
from django.conf import settings
from django.utils import timezone

WEBHOOK_SECRET = settings.YCLOUD_WEBHOOK_SECRET

def sign_payload(body_str):
    timestamp = str(int(timezone.now().timestamp()))
    signed_content = f"{timestamp}.{body_str}"
    signature = hmac.new(WEBHOOK_SECRET.encode(), signed_content.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},s={signature}"

payload = {
    "id": "evt_${testId}",
    "type": "whatsapp.inbound_message.received",
    "whatsappInboundMessage": {
        "id": "wamid_${testId}",
        "from": "+5191${Math.floor(Math.random() * 1000000)}",
        "to": "+51967619238",
        "text": {"body": "Test: ${testId}"}
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
print(f"Webhook response: {response.status_code}")
`
    
    await new Promise((resolve, reject) => {
      const python = spawn('python', ['-c', pythonScript], { cwd: '../' })
      let output = ''
      python.stdout.on('data', data => { output += data })
      python.stderr.on('data', data => { console.log('[PYTHON]', data.toString()) })
      python.on('close', code => {
        console.log('[WEBHOOK]', output.trim())
        resolve()
      })
    })
    
    // Refresh page to load new data
    console.log('[PAGE] Refreshing to sync data...')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    
    // Screenshot after refresh
    await page.screenshot({ path: 'test-results/hybrid-after-refresh.png' })
    console.log('[SCREENSHOT] hybrid-after-refresh.png')
    
    // Check DOM
    const msgCount = await page.locator('[data-testid="message-item"], .message-item, [class*="message"]').count().catch(() => 0)

    console.log(`[VISUAL] Message elements found: ${msgCount}`)
    
    // Try to find test ID in page
    const hasTestId = await page.locator(`text="${testId}"`).count().catch(() => 0)

    console.log(`[VISUAL] Test ID in DOM: ${hasTestId > 0 ? 'PASS' : 'FAIL'}`)
    
    console.log('\n[TEST] GATE 3 complete')

  } catch (error) {
    console.error('[ERROR]', error.message)
  } finally {
    await browser.close()
  }
})()
