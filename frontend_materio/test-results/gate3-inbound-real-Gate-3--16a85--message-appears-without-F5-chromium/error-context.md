# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: gate3-inbound-real.spec.js >> Gate 3: Inbound Message Real E2E >> Inbound YCloud message appears without F5
- Location: src\__tests__\gate3-inbound-real.spec.js:12:3

# Error details

```
Error: page.goto: Target page, context or browser has been closed
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test'
  2   | import crypto from 'crypto'
  3   | 
  4   | /**
  5   |  * GATE 3: Inbound Message Real E2E
  6   |  *
  7   |  * Sends a real YCloud webhook with correct HMAC signature.
  8   |  * Verifies the message appears in bandeja WITHOUT F5.
  9   |  * Confirms SSE transport (not polling).
  10  |  */
  11  | test.describe('Gate 3: Inbound Message Real E2E', () => {
  12  |   test('Inbound YCloud message appears without F5', async ({ page }) => {
  13  |     console.log('\n=== GATE 3: Inbound Real E2E ===')
  14  | 
  15  |     // Step 1: Authenticate
  16  |     console.log('Step 1: Authenticating via login page...')
> 17  |     await page.goto('http://localhost:8001/dashboard/login/', { waitUntil: 'networkidle' })
      |                ^ Error: page.goto: Target page, context or browser has been closed
  18  |     await page.fill('input[name="username"]', 'e2e_test')
  19  |     await page.fill('input[name="password"]', 'e2e_test_pass_123')
  20  |     await page.click('button[type="submit"]')
  21  |     await page.waitForURL('**/dashboard/**', { timeout: 10000 })
  22  |     console.log('✓ Authenticated')
  23  | 
  24  |     // Step 2: Navigate to bandeja
  25  |     console.log('Step 2: Navigating to bandeja...')
  26  |     await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded' })
  27  |     // Wait for conversation list to render - might take longer
  28  |     await page.waitForSelector('.conversation-item, [class*="conversation"], [class*="bandeja"]', { timeout: 20000 })
  29  |     console.log('✓ Bandeja loaded')
  30  | 
  31  |     // Record initial state
  32  |     const initialCount = await page.locator('.conversation-item').count()
  33  |     console.log(`Initial conversations: ${initialCount}`)
  34  | 
  35  |     // Step 3: Create YCloud webhook payload with CORRECT HMAC
  36  |     console.log('Step 3: Creating YCloud webhook payload...')
  37  | 
  38  |     const timestamp = Math.floor(Date.now() / 1000)
  39  |     const payload = {
  40  |       id: `gate3-test-${Date.now()}`,
  41  |       type: 'whatsapp.inbound_message.received',
  42  |       createTime: new Date().toISOString(),
  43  |       phone: '+51967619238',
  44  |       whatsappBusinessAccountId: 'wabaid_123',
  45  |       whatsappInboundMessage: {
  46  |         id: `msg-${Date.now()}`,
  47  |         from: '+51900111111',
  48  |         to: '+51967619238',
  49  |         fromName: 'Test Customer',
  50  |         type: 'text',
  51  |         text: {
  52  |           body: `Gate 3 real inbound test: ${new Date().toISOString()}`,
  53  |         },
  54  |         timestamp: new Date().toISOString(),
  55  |       },
  56  |     }
  57  | 
  58  |     const payloadJson = JSON.stringify(payload)
  59  |     const secret = 'test_secret_e2e'
  60  |     const timestampStr = String(timestamp)  // Ensure string format
  61  | 
  62  |     // Try both HMAC formats (Django test uses format 2)
  63  |     // Format 1: HMAC(secret, body_only)
  64  |     const hmac1 = crypto
  65  |       .createHmac('sha256', secret)
  66  |       .update(payloadJson)
  67  |       .digest('hex')
  68  | 
  69  |     // Format 2: HMAC(secret, timestamp.body)
  70  |     const signedContent = `${timestampStr}.${payloadJson}`
  71  |     const hmac2 = crypto
  72  |       .createHmac('sha256', secret)
  73  |       .update(signedContent)
  74  |       .digest('hex')
  75  | 
  76  |     // Use format 2 (what Django tests use)
  77  |     const yCloudSignature = `t=${timestampStr},s=${hmac2}`
  78  | 
  79  |     console.log(`Payload size: ${payloadJson.length} bytes`)
  80  |     console.log(`Timestamp: ${timestampStr}`)
  81  |     console.log(`HMAC1 (body only): ${hmac1}`)
  82  |     console.log(`HMAC2 (timestamp.body): ${hmac2}`)
  83  |     console.log(`Signature header: ${yCloudSignature}`)
  84  | 
  85  |     // Step 4: Send webhook with correct HMAC
  86  |     console.log('Step 4: Sending webhook with valid HMAC...')
  87  |     const webhookResp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
  88  |       headers: {
  89  |         'Content-Type': 'application/json',
  90  |         'Ycloud-Signature': yCloudSignature,
  91  |       },
  92  |       data: payloadJson,
  93  |     })
  94  | 
  95  |     console.log(`Webhook response: ${webhookResp.status()}`)
  96  |     const respText = await webhookResp.text()
  97  |     console.log(`Response: ${respText.substring(0, 200)}...`)
  98  | 
  99  |     if (webhookResp.status() !== 200) {
  100 |       console.log(`⚠ Webhook rejected (${webhookResp.status()})`)
  101 |       console.log(`Response body: ${respText}`)
  102 |     } else {
  103 |       console.log('✓ Webhook accepted (200 OK)')
  104 |     }
  105 | 
  106 |     // Step 5: Wait for UI update WITHOUT F5
  107 |     console.log('Step 5: Waiting for UI update (no F5)...')
  108 |     await page.waitForTimeout(2000)
  109 | 
  110 |     // Step 6: Verify conversation appears or updates
  111 |     console.log('Step 6: Checking for new/updated conversation...')
  112 |     const updatedCount = await page.locator('.conversation-item').count()
  113 |     console.log(`Conversations after webhook: ${updatedCount}`)
  114 | 
  115 |     if (updatedCount > initialCount) {
  116 |       console.log(`✓ New conversation appeared (${updatedCount - initialCount} added)`)
  117 | 
```