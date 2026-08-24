# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: hmac-contract-validation.spec.js >> HMAC Contract Validation >> Format 1: HMAC(secret, body_only) - canonical or permissive?
- Location: src\__tests__\hmac-contract-validation.spec.js:34:3

# Error details

```
SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test'
  2   | import crypto from 'crypto'
  3   | 
  4   | /**
  5   |  * HMAC Contract Validation - Determine which format is official
  6   |  *
  7   |  * Test both formats independently and verify:
  8   |  * 1. Which one actually validates
  9   |  * 2. If both validate, are they both documented/required?
  10  |  * 3. Webhook events and messages created per format
  11  |  * 4. Idempotence with same event_id
  12  |  * 5. Difference with modified body
  13  |  */
  14  | test.describe('HMAC Contract Validation', () => {
  15  |   const timestamp = String(Math.floor(Date.now() / 1000))
  16  |   const secret = 'test_secret_e2e'
  17  |   const basePayload = {
  18  |     id: `hmac-contract-${Date.now()}`,
  19  |     type: 'whatsapp.inbound_message.received',
  20  |     createTime: new Date().toISOString(),
  21  |     phone: '51967619238',
  22  |     whatsappBusinessAccountId: 'wabaid_test',
  23  |     whatsappInboundMessage: {
  24  |       id: `msg-${Date.now()}`,
  25  |       from: '+51900111111',
  26  |       to: '51967619238',
  27  |       fromName: 'HMAC Test',
  28  |       type: 'text',
  29  |       text: { body: 'HMAC contract test' },
  30  |       timestamp: new Date().toISOString(),
  31  |     },
  32  |   }
  33  | 
  34  |   test('Format 1: HMAC(secret, body_only) - canonical or permissive?', async ({ page }) => {
  35  |     const rawBody = JSON.stringify(basePayload)
  36  |     const hmac = crypto
  37  |       .createHmac('sha256', secret)
  38  |       .update(rawBody)
  39  |       .digest('hex')
  40  | 
  41  |     console.log(`\n=== FORMAT 1: BODY ONLY ===`)
  42  |     console.log(`Timestamp: ${timestamp}`)
  43  |     console.log(`Algorithm: HMAC-SHA256`)
  44  |     console.log(`Input: request.body bytes only`)
  45  |     console.log(`Signature: ${hmac}`)
  46  |     console.log(`Encoding: hexdigest`)
  47  |     console.log(`Header: Ycloud-Signature: t=${timestamp},s=${hmac}`)
  48  | 
  49  |     const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
  50  |       headers: {
  51  |         'Content-Type': 'application/json',
  52  |         'Ycloud-Signature': `t=${timestamp},s=${hmac}`,
  53  |       },
  54  |       data: rawBody,
  55  |     })
  56  | 
  57  |     console.log(`Response: ${resp.status()} ${resp.statusText()}`)
  58  |     const respBody = await resp.text()
  59  |     console.log(`Body: ${respBody}`)
  60  | 
  61  |     if (resp.status() === 200) {
  62  |       console.log(`✅ Format 1 ACCEPTED`)
  63  |       // Query DB to verify persistence
  64  |       const eventResp = await page.request.get(
  65  |         `http://localhost:8001/api/webhook-events/?external_id=${basePayload.id}`
  66  |       )
  67  |       if (eventResp.ok) {
> 68  |         const events = await eventResp.json()
      |                        ^ SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON
  69  |         console.log(`✅ WebhookEvent created: ${events.length} entry`)
  70  |       }
  71  |     } else if (resp.status() === 401) {
  72  |       console.log(`❌ Format 1 REJECTED: Invalid signature`)
  73  |     } else {
  74  |       console.log(`⚠️ Format 1 ERROR: ${resp.status()}`)
  75  |     }
  76  |   })
  77  | 
  78  |   test('Format 2: HMAC(secret, timestamp.body) - canonical or permissive?', async ({ page }) => {
  79  |     const rawBody = JSON.stringify(basePayload)
  80  |     const signedContent = `${timestamp}.${rawBody}`
  81  |     const hmac = crypto
  82  |       .createHmac('sha256', secret)
  83  |       .update(signedContent)
  84  |       .digest('hex')
  85  | 
  86  |     console.log(`\n=== FORMAT 2: TIMESTAMP.BODY ===`)
  87  |     console.log(`Timestamp: ${timestamp}`)
  88  |     console.log(`Algorithm: HMAC-SHA256`)
  89  |     console.log(`Input: "{timestamp}.{body}" string`)
  90  |     console.log(`Signed content length: ${signedContent.length}`)
  91  |     console.log(`Signature: ${hmac}`)
  92  |     console.log(`Encoding: hexdigest`)
  93  |     console.log(`Header: Ycloud-Signature: t=${timestamp},s=${hmac}`)
  94  | 
  95  |     const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
  96  |       headers: {
  97  |         'Content-Type': 'application/json',
  98  |         'Ycloud-Signature': `t=${timestamp},s=${hmac}`,
  99  |       },
  100 |       data: rawBody,
  101 |     })
  102 | 
  103 |     console.log(`Response: ${resp.status()} ${resp.statusText()}`)
  104 |     const respBody = await resp.text()
  105 |     console.log(`Body: ${respBody}`)
  106 | 
  107 |     if (resp.status() === 200) {
  108 |       console.log(`✅ Format 2 ACCEPTED`)
  109 |     } else if (resp.status() === 401) {
  110 |       console.log(`❌ Format 2 REJECTED: Invalid signature`)
  111 |     } else {
  112 |       console.log(`⚠️ Format 2 ERROR: ${resp.status()}`)
  113 |     }
  114 |   })
  115 | 
  116 |   test('Invalid signature returns 401', async ({ page }) => {
  117 |     const rawBody = JSON.stringify(basePayload)
  118 |     const invalidHmac = 'definitely_not_a_valid_hmac_signature'
  119 | 
  120 |     console.log(`\n=== INVALID SIGNATURE ===`)
  121 |     console.log(`Using wrong HMAC: ${invalidHmac}`)
  122 | 
  123 |     const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
  124 |       headers: {
  125 |         'Content-Type': 'application/json',
  126 |         'Ycloud-Signature': `t=${timestamp},s=${invalidHmac}`,
  127 |       },
  128 |       data: rawBody,
  129 |     })
  130 | 
  131 |     console.log(`Response: ${resp.status()}`)
  132 |     expect(resp.status()).toBe(401)
  133 |     console.log(`✅ Invalid signature correctly rejected`)
  134 |   })
  135 | 
  136 |   test('Modified body after signing returns 401', async ({ page }) => {
  137 |     const originalBody = JSON.stringify(basePayload)
  138 |     const hmac = crypto
  139 |       .createHmac('sha256', secret)
  140 |       .update(originalBody)
  141 |       .digest('hex')
  142 | 
  143 |     // Modify body after signing
  144 |     const modifiedPayload = { ...basePayload, id: 'tampered-id' }
  145 |     const modifiedBody = JSON.stringify(modifiedPayload)
  146 | 
  147 |     console.log(`\n=== BODY TAMPERING ===`)
  148 |     console.log(`Original body signed`)
  149 |     console.log(`Modified body sent`)
  150 |     console.log(`HMAC: ${hmac}`)
  151 | 
  152 |     const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
  153 |       headers: {
  154 |         'Content-Type': 'application/json',
  155 |         'Ycloud-Signature': `t=${timestamp},s=${hmac}`,
  156 |       },
  157 |       data: modifiedBody,
  158 |     })
  159 | 
  160 |     console.log(`Response: ${resp.status()}`)
  161 |     if (resp.status() === 401) {
  162 |       console.log(`✅ Body tampering detected`)
  163 |     } else {
  164 |       console.log(`⚠️ Body tampering NOT detected (status ${resp.status()})`)
  165 |     }
  166 |   })
  167 | 
  168 |   test('Missing header returns 401', async ({ page }) => {
```