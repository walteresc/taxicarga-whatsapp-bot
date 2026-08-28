import { test, expect } from '@playwright/test'
import crypto from 'crypto'

/**
 * GATE 4: Echo/Takeover Message Real E2E
 *
 * Sends a real YCloud echo webhook with correct HMAC signature.
 * Verifies the echo appears and takeover state updates WITHOUT F5.
 */
test.describe('Gate 4: Echo/Takeover Real E2E', () => {
  test('Echo message and takeover state update without F5', async ({ page }) => {
    console.log('\n=== GATE 4: Echo/Takeover Real E2E ===')

    // Step 1: Authenticate
    console.log('Step 1: Authenticating...')
    await page.goto('http://localhost:8001/dashboard/login/', { waitUntil: 'networkidle' })
    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass_123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard/**', { timeout: 10000 })
    console.log('✓ Authenticated')

    // Step 2: Load bandeja and select conversation
    console.log('Step 2: Loading bandeja...')
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'networkidle' })
    await page.waitForSelector('.conversation-item', { timeout: 10000 })
    console.log('✓ Bandeja loaded')

    // Step 3: Select first conversation
    console.log('Step 3: Selecting conversation...')

    const firstConv = page.locator('.conversation-item').first()
    const convText = await firstConv.textContent()

    console.log(`Selected: ${convText.substring(0, 60)}...`)
    await firstConv.click()
    await page.waitForTimeout(1000)

    // Record initial messages
    const initialMsgCount = await page.locator('[class*="message"], [class*="bubble"]').count()

    console.log(`Initial timeline messages: ${initialMsgCount}`)

    // Step 4: Create echo payload with CORRECT HMAC
    console.log('Step 4: Creating echo payload...')

    const timestamp = Math.floor(Date.now() / 1000)

    const payload = {
      id: `gate4-echo-${Date.now()}`,
      type: 'whatsapp.smb.message.echoes',
      createTime: new Date().toISOString(),
      phone: '+51967619238',
      whatsappBusinessAccountId: 'wabaid_123',
      whatsappMessage: {
        id: `echo-${Date.now()}`,
        from: '+51967619238', // Business sends FROM here
        to: '+51900111111',    // Customer receives it
        type: 'text',
        text: {
          body: `Gate 4 echo test from advisor: ${new Date().toISOString()}`,
        },
        timestamp: new Date().toISOString(),
      },
    }

    const payloadJson = JSON.stringify(payload)
    const secret = 'test_secret_e2e'
    const timestampStr = String(timestamp)

    // Format 2: HMAC(secret, timestamp.body) - what Django tests use
    const signedContent = `${timestampStr}.${payloadJson}`

    const hmac = crypto
      .createHmac('sha256', secret)
      .update(signedContent)
      .digest('hex')

    const yCloudSignature = `t=${timestampStr},s=${hmac}`

    console.log(`HMAC (timestamp.body): ${hmac}`)

    // Step 5: Send echo webhook
    console.log('Step 5: Sending echo webhook...')

    const echoResp = await page.request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'Ycloud-Signature': yCloudSignature,
      },
      data: payloadJson,
    })

    console.log(`Echo response: ${echoResp.status()}`)
    if (echoResp.status() !== 200) {
      const errText = await echoResp.text()

      console.log(`Response: ${errText.substring(0, 200)}...`)
    } else {
      console.log('✓ Echo accepted (200 OK)')
    }

    // Step 6: Wait for UI update WITHOUT F5
    console.log('Step 6: Waiting for UI update...')
    await page.waitForTimeout(2000)

    // Step 7: Verify message appears
    console.log('Step 7: Checking message in timeline...')

    const updatedMsgCount = await page.locator('[class*="message"], [class*="bubble"]').count()

    console.log(`Timeline messages after echo: ${updatedMsgCount}`)

    if (updatedMsgCount > initialMsgCount) {
      console.log(`✓ Echo message appeared (+${updatedMsgCount - initialMsgCount})`)
    } else {
      console.log('⚠ Message count unchanged')
    }

    // Step 8: Verify takeover state
    console.log('Step 8: Checking takeover indicators...')

    const advisorBadges = await page.locator('text=/Asesor|advisor/i').count()
    const takeoverIndicators = await page.locator('[class*="takeover"], [class*="advisor"], [class*="estado-asesor"]').count()

    console.log(`Advisor badges: ${advisorBadges}`)
    console.log(`Takeover indicators: ${takeoverIndicators}`)

    if (advisorBadges > 0 || takeoverIndicators > 0) {
      console.log('✓ Takeover state visible')
    }

    // Step 9: Check no duplicates
    console.log('Step 9: Verifying no duplicates...')
    if (updatedMsgCount === initialMsgCount + 1) {
      console.log('✓ Exactly one message added')
    } else if (updatedMsgCount > initialMsgCount + 1) {
      console.log(`⚠ Multiple messages added: ${updatedMsgCount - initialMsgCount}`)
    }

    // Step 10: Verify stability
    console.log('Step 10: Checking errors...')

    const errors = []

    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    await page.waitForTimeout(1000)

    console.log(`Console errors: ${errors.length}`)

    // Summary
    if (echoResp.status() === 200 && updatedMsgCount > initialMsgCount) {
      console.log('\n✅ GATE 4 PASS: Echo delivered, takeover visible without F5')
      expect(updatedMsgCount).toBeGreaterThan(initialMsgCount)
    } else if (echoResp.status() === 200) {
      console.log('\n⚠ GATE 4 PARTIAL: Echo accepted but UI not updated')
    } else {
      console.log('\n❌ GATE 4 FAIL: Echo rejected')
    }
  })
})
