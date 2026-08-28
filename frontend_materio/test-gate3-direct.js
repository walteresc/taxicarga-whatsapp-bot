import { chromium } from '@playwright/test';

(async () => {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()

  try {
    const CONV_ID = '253'
    const TEST_BODY = 'Visual test 2026-08-24T14:00:54.386953+00:00'
    
    console.log('[TEST] GATE 3 - Direct visual verification')
    console.log(`[DB] Conv ID: ${CONV_ID}, Body: ${TEST_BODY}`)
    
    // Auth
    console.log('[AUTH] Login...')
    await page.goto('http://localhost:5177/dashboard/login/', { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass')
    await page.click('button[type="submit"]')
    await page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {})
    
    // Load bandeja
    console.log('[PAGE] Loading bandeja-entrada...')
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForSelector('.main-container, [data-testid="conversation-list"]', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(4000)  // Vue + SSE hydration
    
    console.log('[DOM] Taking screenshot before interaction...')
    await page.screenshot({ path: 'test-results/gate3-visual-before.png' })
    
    // Look for the test message in page text
    const bodyVisible = await page.locator(`text=${TEST_BODY}`).count().catch(() => 0)

    console.log(`[VISUAL] Message text found: ${bodyVisible > 0 ? 'YES' : 'NO'}`)
    
    // Look for conversation item (alternative selector)
    const convItems = await page.locator('[data-testid="conversation-item"], .conversation-item, [class*="conversation"]').count().catch(() => 0)

    console.log(`[VISUAL] Conversation items in DOM: ${convItems}`)
    
    // Look for message items
    const msgItems = await page.locator('[data-testid="message-item"], .message-item').count().catch(() => 0)

    console.log(`[VISUAL] Message items in DOM: ${msgItems}`)
    
    // Try to click on phone number +51991234567 to open that conversation
    console.log('[ACTION] Searching for phone +51991234567...')

    const phoneVisible = await page.locator('text=+51991234567').count().catch(() => 0)
    if (phoneVisible > 0) {
      console.log('[FOUND] Phone number in DOM, clicking...')
      await page.locator('text=+51991234567').first().click()
      await page.waitForTimeout(2000)
      
      const msgVis = await page.locator(`text=${TEST_BODY}`).count().catch(() => 0)

      console.log(`[AFTER-CLICK] Message visible: ${msgVis > 0 ? 'YES' : 'NO'}`)
    } else {
      console.log('[NOT-FOUND] Phone not in conversation list')
    }
    
    await page.screenshot({ path: 'test-results/gate3-visual-after.png' })
    console.log('[RESULT] Screenshots saved')
    
  } catch (error) {
    console.error('[ERROR]', error.message)
  } finally {
    await browser.close()
  }
})()
