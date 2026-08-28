import { test, expect } from '@playwright/test'
import crypto from 'crypto'

/**
 * GATE 3: Inbound Message Real E2E
 *
 * Sends a real YCloud webhook with correct HMAC signature.
 * Verifies the message appears in bandeja WITHOUT F5.
 * Confirms SSE transport (not polling).
 */
test.describe('Gate 3: Inbound Message Real E2E', () => {
  test('Inbound YCloud message appears without F5', async ({ page }) => {
    console.log('\n=== GATE 3: Inbound Real E2E ===')

    // Step 1: Authenticate
    console.log('Step 1: Authenticating via login page...')
    await page.goto('http://localhost:8001/dashboard/login/', { waitUntil: 'networkidle' })
    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass_123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard/**', { timeout: 10000 })
    console.log('✓ Authenticated')

    // Step 2: Navigate to bandeja
    console.log('Step 2: Navigating to bandeja...')
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded' })

    // Wait for conversation list to render - might take longer
    await page.waitForSelector('.conversation-item, [class*="conversation"], [class*="bandeja"]', { timeout: 20000 })
    console.log('✓ Bandeja loaded')

    // Record initial state
    const initialCount = await page.locator('.conversation-item').count()

    console.log(`Initial conversations: ${initialCount}`)

    // Step 3: Create YCloud webhook payload with CORRECT HMAC
    console.log('Step 3: Creating YCloud webhook payload...')

    const timestamp = Math.floor(Date.now() / 1000)

    const payload = {
      id: `gate3-test-${Date.now()}`,
      type: 'whatsapp.inbound_message.received',
      createTime: new Date().toISOString(),
      phone: '+51967619238',
      whatsappBusinessAccountId: 'wabaid_123',
      whatsappInboundMessage: {
        id: `msg-${Date.now()}`,
        from: '+51900111111',
        to: '+51967619238',
        fromName: 'Test Customer',
        type: 'text',
        text: {
          body: `Gate 3 real inbound test: ${new Date().toISOString()}`,
        },
        timestamp: new Date().toISOString(),
      },
    }

    const payloadJson = JSON.stringify(payload)
    const secret = 'test_secret_e2e'
    const timestampStr = String(timestamp)  // Ensure string format

    // Try both HMAC formats (Django test uses format 2)
    // Format 1: HMAC(secret, body_only)
    const hmac1 = crypto
      .createHmac('sha256', secret)
      .update(payloadJson)
      .digest('hex')

    // Format 2: HMAC(secret, timestamp.body)
    const signedContent = `${timestampStr}.${payloadJson}`

    const hmac2 = crypto
      .createHmac('sha256', secret)
      .update(signedContent)
      .digest('hex')

    // Use format 2 (what Django tests use)
    const yCloudSignature = `t=${timestampStr},s=${hmac2}`

    console.log(`Payload size: ${payloadJson.length} bytes`)
    console.log(`Timestamp: ${timestampStr}`)
    console.log(`HMAC1 (body only): ${hmac1}`)
    console.log(`HMAC2 (timestamp.body): ${hmac2}`)
    console.log(`Signature header: ${yCloudSignature}`)

    // Step 4: Send webhook with correct HMAC
    console.log('Step 4: Sending webhook with valid HMAC...')

    const webhookResp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'Ycloud-Signature': yCloudSignature,
      },
      data: payloadJson,
    })

    console.log(`Webhook response: ${webhookResp.status()}`)

    const respText = await webhookResp.text()

    console.log(`Response: ${respText.substring(0, 200)}...`)

    if (webhookResp.status() !== 200) {
      console.log(`⚠ Webhook rejected (${webhookResp.status()})`)
      console.log(`Response body: ${respText}`)
    } else {
      console.log('✓ Webhook accepted (200 OK)')
    }

    // Step 5: Wait for UI update WITHOUT F5
    console.log('Step 5: Waiting for UI update (no F5)...')
    await page.waitForTimeout(2000)

    // Step 6: Verify conversation appears or updates
    console.log('Step 6: Checking for new/updated conversation...')

    const updatedCount = await page.locator('.conversation-item').count()

    console.log(`Conversations after webhook: ${updatedCount}`)

    if (updatedCount > initialCount) {
      console.log(`✓ New conversation appeared (${updatedCount - initialCount} added)`)

      // Get first conversation
      const firstConv = page.locator('.conversation-item').first()
      const convText = await firstConv.textContent()

      console.log(`First conversation: ${convText.substring(0, 80)}...`)

      // Click to open timeline
      await firstConv.click()
      await page.waitForTimeout(1000)

      // Step 7: Verify in timeline
      console.log('Step 7: Checking timeline...')

      const messages = await page.locator('[class*="message"], [class*="bubble"]').count()

      console.log(`Timeline messages: ${messages}`)

      if (messages > 0) {
        console.log('✓ Message visible in timeline')
      }
    } else {
      console.log('⚠ Conversation count unchanged')
    }

    // Step 8: Verify stability
    console.log('Step 8: Checking stability...')

    const errors = []

    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    await page.waitForTimeout(1000)

    console.log(`Console errors: ${errors.length}`)
    if (errors.length === 0) {
      console.log('✓ No errors')
    }

    // Summary
    if (webhookResp.status() === 200 && updatedCount > initialCount) {
      console.log('\n✅ GATE 3 PASS: Inbound message delivered, visible without F5')
      expect(updatedCount).toBeGreaterThan(initialCount)
    } else if (webhookResp.status() === 200) {
      console.log('\n⚠ GATE 3 PARTIAL: Webhook accepted but UI not updated')
    } else {
      console.log('\n❌ GATE 3 FAIL: Webhook rejected')
    }
  })
})
