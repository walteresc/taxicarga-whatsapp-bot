import { test, expect } from '@playwright/test'
import crypto from 'crypto'

/**
 * GATE 3 HMAC Debug - Capture Django logs to diagnose signature mismatch
 *
 * Strategy:
 * 1. Send webhook with calculated HMAC
 * 2. Django logs expected hashes (line 195 in verify_ycloud_signature)
 * 3. Capture stderr/stdout to see what Django calculated
 * 4. Compare with what test calculated
 */
test.describe('Gate 3: HMAC Debug', () => {
  test('Capture HMAC calculation mismatch', async ({ page }) => {
    console.log('\n=== GATE 3: HMAC Debug ===')

    // Step 1: Create payload
    const timestamp = String(Math.floor(Date.now() / 1000))
    const payload = {
      id: `debug-${Date.now()}`,  // Django looks for 'id' or 'event_id'
      type: 'whatsapp.inbound_message.received',  // Django looks for 'type' or 'event'
      createTime: new Date().toISOString(),
      phone: '+51987654321',
      whatsappBusinessAccountId: 'wabaid_123',
      whatsappInboundMessage: {
        id: `msg-${Date.now()}`,
        from: '+51900111111',
        to: '+51987654321',
        fromName: 'Debug',
        type: 'text',
        text: {
          body: 'Debug HMAC test'
        },
        timestamp: new Date().toISOString()
      }
    }

    // CRITICAL: Use ONE raw body variable for both signing and sending
    const rawBody = JSON.stringify(payload)
    const secret = 'test_secret_e2e'

    // Calculate body hash for comparison with Django
    const bodyHashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(rawBody))
    const bodyHashArray = Array.from(new Uint8Array(bodyHashBuffer))
    const bodyHash = bodyHashArray.map(b => b.toString(16).padStart(2, '0')).join('')

    console.log(`Timestamp: ${timestamp}`)
    console.log(`Raw body length: ${rawBody.length}`)
    console.log(`Raw body hash: ${bodyHash}`)
    console.log(`Secret: ${secret} (${secret.length} chars)`)
    console.log(`Raw body (first 200 chars): ${rawBody.substring(0, 200)}`)

    // Calculate both formats
    const bodyBytes = Buffer.from(rawBody, 'utf-8')
    const bodyString = rawBody

    // Format 1: body only
    const hmac1 = crypto
      .createHmac('sha256', secret)
      .update(bodyBytes)
      .digest('hex')

    // Format 2: timestamp.body
    const signedContent2 = `${timestamp}.${bodyString}`
    const hmac2 = crypto
      .createHmac('sha256', secret)
      .update(signedContent2)
      .digest('hex')

    console.log(`\nTest-side HMACs:`)
    console.log(`  Format 1 (body only): ${hmac1}`)
    console.log(`  Format 2 (timestamp.body): ${hmac2}`)
    console.log(`  Signed content 2: "${signedContent2.substring(0, 50)}..."`)

    // Try both signatures
    for (const [format, hmac] of [
      ['Format 1 (body only)', hmac1],
      ['Format 2 (timestamp.body)', hmac2]
    ]) {
      console.log(`\n--- Testing ${format} ---`)
      const yCloudSignature = `t=${timestamp},s=${hmac}`

      const resp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
        headers: {
          'Content-Type': 'application/json',
          'Ycloud-Signature': yCloudSignature
        },
        data: rawBody  // CRITICAL: Send exact raw body, not payload object
      })

      console.log(`Response status: ${resp.status()}`)
      const respText = await resp.text()
      console.log(`Response: ${respText}`)

      if (resp.status() !== 200) {
        console.log(`${format} FAILED`)
      } else {
        console.log(`${format} SUCCEEDED`)
      }
    }

    console.log('\n=== To see Django logs: ===')
    console.log('tail -f django.log | grep YCloud')
    console.log('\nCompare test-side HMACs above with Django log lines:')
    console.log('[YCloud] Hashes - expected1=..., expected2=...')
  })
})
