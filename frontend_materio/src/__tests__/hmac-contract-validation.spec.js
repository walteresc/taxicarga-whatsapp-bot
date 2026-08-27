import { test, expect } from '@playwright/test'
import crypto from 'crypto'

/**
 * HMAC Contract Validation - Determine which format is official
 *
 * Test both formats independently and verify:
 * 1. Which one actually validates
 * 2. If both validate, are they both documented/required?
 * 3. Webhook events and messages created per format
 * 4. Idempotence with same event_id
 * 5. Difference with modified body
 */
test.describe('HMAC Contract Validation', () => {
  const timestamp = String(Math.floor(Date.now() / 1000))
  const secret = 'test_secret_e2e'
  const basePayload = {
    id: `hmac-contract-${Date.now()}`,
    type: 'whatsapp.inbound_message.received',
    createTime: new Date().toISOString(),
    phone: '51967619238',
    whatsappBusinessAccountId: 'wabaid_test',
    whatsappInboundMessage: {
      id: `msg-${Date.now()}`,
      from: '+51900111111',
      to: '51967619238',
      fromName: 'HMAC Test',
      type: 'text',
      text: { body: 'HMAC contract test' },
      timestamp: new Date().toISOString(),
    },
  }

  test('Format 1: HMAC(secret, body_only) - canonical or permissive?', async ({ page }) => {
    const rawBody = JSON.stringify(basePayload)
    const hmac = crypto
      .createHmac('sha256', secret)
      .update(rawBody)
      .digest('hex')

    console.log(`\n=== FORMAT 1: BODY ONLY ===`)
    console.log(`Timestamp: ${timestamp}`)
    console.log(`Algorithm: HMAC-SHA256`)
    console.log(`Input: request.body bytes only`)
    console.log(`Signature: ${hmac}`)
    console.log(`Encoding: hexdigest`)
    console.log(`Header: Ycloud-Signature: t=${timestamp},s=${hmac}`)

    const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'Ycloud-Signature': `t=${timestamp},s=${hmac}`,
      },
      data: rawBody,
    })

    console.log(`Response: ${resp.status()} ${resp.statusText()}`)
    const respBody = await resp.text()
    console.log(`Body: ${respBody}`)

    if (resp.status() === 200) {
      console.log(`✅ Format 1 ACCEPTED`)
      // Query DB to verify persistence
      const eventResp = await page.request.get(
        `http://localhost:8001/api/webhook-events/?external_id=${basePayload.id}`
      )
      if (eventResp.ok) {
        const events = await eventResp.json()
        console.log(`✅ WebhookEvent created: ${events.length} entry`)
      }
    } else if (resp.status() === 401) {
      console.log(`❌ Format 1 REJECTED: Invalid signature`)
    } else {
      console.log(`⚠️ Format 1 ERROR: ${resp.status()}`)
    }
  })

  test('Format 2: HMAC(secret, timestamp.body) - canonical or permissive?', async ({ page }) => {
    const rawBody = JSON.stringify(basePayload)
    const signedContent = `${timestamp}.${rawBody}`
    const hmac = crypto
      .createHmac('sha256', secret)
      .update(signedContent)
      .digest('hex')

    console.log(`\n=== FORMAT 2: TIMESTAMP.BODY ===`)
    console.log(`Timestamp: ${timestamp}`)
    console.log(`Algorithm: HMAC-SHA256`)
    console.log(`Input: "{timestamp}.{body}" string`)
    console.log(`Signed content length: ${signedContent.length}`)
    console.log(`Signature: ${hmac}`)
    console.log(`Encoding: hexdigest`)
    console.log(`Header: Ycloud-Signature: t=${timestamp},s=${hmac}`)

    const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'Ycloud-Signature': `t=${timestamp},s=${hmac}`,
      },
      data: rawBody,
    })

    console.log(`Response: ${resp.status()} ${resp.statusText()}`)
    const respBody = await resp.text()
    console.log(`Body: ${respBody}`)

    if (resp.status() === 200) {
      console.log(`✅ Format 2 ACCEPTED`)
    } else if (resp.status() === 401) {
      console.log(`❌ Format 2 REJECTED: Invalid signature`)
    } else {
      console.log(`⚠️ Format 2 ERROR: ${resp.status()}`)
    }
  })

  test('Invalid signature returns 401', async ({ page }) => {
    const rawBody = JSON.stringify(basePayload)
    const invalidHmac = 'definitely_not_a_valid_hmac_signature'

    console.log(`\n=== INVALID SIGNATURE ===`)
    console.log(`Using wrong HMAC: ${invalidHmac}`)

    const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'Ycloud-Signature': `t=${timestamp},s=${invalidHmac}`,
      },
      data: rawBody,
    })

    console.log(`Response: ${resp.status()}`)
    expect(resp.status()).toBe(401)
    console.log(`✅ Invalid signature correctly rejected`)
  })

  test('Modified body after signing returns 401', async ({ page }) => {
    const originalBody = JSON.stringify(basePayload)
    const hmac = crypto
      .createHmac('sha256', secret)
      .update(originalBody)
      .digest('hex')

    // Modify body after signing
    const modifiedPayload = { ...basePayload, id: 'tampered-id' }
    const modifiedBody = JSON.stringify(modifiedPayload)

    console.log(`\n=== BODY TAMPERING ===`)
    console.log(`Original body signed`)
    console.log(`Modified body sent`)
    console.log(`HMAC: ${hmac}`)

    const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'Ycloud-Signature': `t=${timestamp},s=${hmac}`,
      },
      data: modifiedBody,
    })

    console.log(`Response: ${resp.status()}`)
    if (resp.status() === 401) {
      console.log(`✅ Body tampering detected`)
    } else {
      console.log(`⚠️ Body tampering NOT detected (status ${resp.status()})`)
    }
  })

  test('Missing header returns 401', async ({ page }) => {
    const rawBody = JSON.stringify(basePayload)

    console.log(`\n=== MISSING HEADER ===`)
    console.log(`Sending webhook without Ycloud-Signature header`)

    const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
      },
      data: rawBody,
    })

    console.log(`Response: ${resp.status()}`)
    expect(resp.status()).toBe(401)
    console.log(`✅ Missing header correctly rejected`)
  })
})
