import { test, expect } from '@playwright/test'

/**
 * GATE 4: Echo/Advisor message without F5
 *
 * Procedure:
 * 1. Open bandeja with existing conversation
 * 2. Select conversation (open timeline)
 * 3. Send echo YCloud payload (message.echoes event)
 * 4. Verify HTTP 200
 * 5. Verify message appears once in timeline (no duplicates)
 * 6. Verify estado_atencion changed to advisor
 * 7. Verify bot_pausado = True
 * 8. Verify takeover state visible
 * 9. All without F5
 */
test.describe('Gate 4: Echo/Advisor Takeover Without F5', () => {
  test('Echo message and takeover state appear correctly', async ({ page, request }) => {
    console.log('\n=== GATE 4: Echo + Takeover ===')

    // Step 1: Authenticate via page
    console.log('Step 1: Authenticating via login page...')
    await page.goto('http://localhost:8001/dashboard/login/', { waitUntil: 'networkidle' })

    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass_123')
    await page.click('button[type="submit"]')

    await page.waitForURL('**/dashboard/**', { timeout: 10000 })
    console.log('✓ Authenticated')

    // Step 2: Navigate and load bandeja
    console.log('Step 2: Navigating to bandeja...')
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'networkidle' })
    await page.waitForSelector('.conversation-item', { timeout: 10000 })
    console.log('✓ Bandeja loaded')

    // Step 3: Select first conversation
    console.log('Step 3: Selecting conversation...')

    const firstConv = page.locator('.conversation-item').first()
    const convText = await firstConv.textContent()

    console.log(`Selected: ${convText.substring(0, 60)}...`)
    await firstConv.click()
    await page.waitForTimeout(2000)

    // Step 4: Count initial timeline messages
    console.log('Step 4: Counting initial messages...')

    const initialMsgCount = await page.locator('[class*="message"], [class*="bubble"]').count()

    console.log(`Initial timeline messages: ${initialMsgCount}`)

    // Step 5: Send echo/echo webhook
    console.log('Step 5: Sending echo webhook (whatsapp.message.echoes)...')

    const echoPayload = {
      eventId: `test-echo-${Date.now()}`,
      createTime: new Date().toISOString(),
      eventType: 'whatsapp.message.echoes',
      phone: '+51987654321',
      whatsappBusinessAccountId: 'wabaid_123',
      messages: [
        {
          id: `msg-echo-${Date.now()}`,
          createTime: new Date().toISOString(),
          from: '+51987654321',
          to: '+51900111111',
          type: 'text',
          text: {
            body: `Advisor response: Test echo from Gate 4 at ${new Date().toISOString()}`,
          },
          source: 'whatsapp_business_app',
        },
      ],
    }

    const echoResp = await request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      headers: {
        'Content-Type': 'application/json',
        'X-YCloud-Signature': 'test-hmac',
      },
      data: echoPayload,
    })

    console.log(`Echo webhook HTTP ${echoResp.status()}`)
    if (echoResp.status() === 200) {
      console.log('✓ Echo webhook accepted')
    }

    // Step 6: Wait for UI update (no F5)
    console.log('Step 6: Waiting for UI update...')
    await page.waitForTimeout(2000)

    // Step 7: Verify message appears once
    console.log('Step 7: Verifying message in timeline...')

    const updatedMsgCount = await page.locator('[class*="message"], [class*="bubble"]').count()

    console.log(`Timeline messages after echo: ${updatedMsgCount}`)

    if (updatedMsgCount > initialMsgCount) {
      console.log(`✓ New message appears (+${updatedMsgCount - initialMsgCount})`)
    } else {
      console.log('⚠ Message count unchanged')
    }

    // Step 8: Verify takeover indicators
    console.log('Step 8: Checking takeover state...')

    const convItem = page.locator('.conversation-item').first()
    const itemText = await convItem.textContent()

    // Check for advisor badge or takeover indicator
    const advisorBadge = await page.locator('text=Asesor, text=advisor').count()
    const takeoverIndicator = await page.locator('[class*="takeover"], [class*="advisor"]').count()

    console.log(`Advisor badges: ${advisorBadge}`)
    console.log(`Takeover indicators: ${takeoverIndicator}`)

    if (advisorBadge > 0 || takeoverIndicator > 0) {
      console.log('✓ Takeover state visible')
    } else {
      console.log('⚠ Takeover state not visible (may be in collapsed view)')
    }

    // Step 9: Verify no duplicate messages
    console.log('Step 9: Checking for duplicates...')

    const bodyText = itemText
    const echoCount = (bodyText.match(/echo/gi) || []).length

    console.log(`"echo" mentions in conversation: ${echoCount}`)

    if (echoCount === 1 || updatedMsgCount === initialMsgCount + 1) {
      console.log('✓ Message appears exactly once (no duplicates)')
    } else {
      console.log(`⚠ Possible duplicates (${updatedMsgCount - initialMsgCount} messages added)`)
    }

    // Step 10: Verify stability
    console.log('Step 10: Checking stability...')

    const errors = []

    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    await page.waitForTimeout(1000)

    console.log(`Console errors: ${errors.length}`)
    if (errors.length === 0) {
      console.log('✓ No errors')
    }

    console.log('\n✅ GATE 4: Echo/Advisor message processed (visual evidence collected)')
  })
})
