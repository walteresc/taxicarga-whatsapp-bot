/**
 * Simple DOM inspection - assumes browser already logged in
 */

import { chromium } from 'playwright'

async function diagnose() {
  const browser = await chromium.launch({ headless: false })
  const page = await browser.newPage()

  const consoleLogs = []
  page.on('console', msg => {
    if (msg.text().includes('[ConversationPanel') || msg.text().includes('ENTRY')) {
      consoleLogs.push(msg.text())
      console.log('[CONSOLE]', msg.text())
    }
  })

  // Navigate directly to whatsapp conversaciones (assuming authenticated)
  console.log('[DIAGNOSE] Navigating to /dashboard/whatsapp/conversaciones/...')
  await page.goto('http://localhost:8001/dashboard/whatsapp/conversaciones/', { waitUntil: 'networkidle' })
  console.log('[DIAGNOSE] ✓ Page loaded')

  // Wait for conversations to appear
  console.log('[DIAGNOSE] Waiting for conversations...')
  try {
    await page.waitForSelector('button', { timeout: 3000 })
    const buttons = await page.locator('button').count()
    console.log(`[DIAGNOSE] ✓ Found ${buttons} buttons`)
  } catch (e) {
    console.log('[DIAGNOSE] ✗ No buttons found')
  }

  // Click first button (should be a conversation)
  console.log('[DIAGNOSE] Clicking first button (conversation)...')
  try {
    await page.locator('button').first().click()
    console.log('[DIAGNOSE] ✓ Clicked')
    await page.waitForTimeout(1500)
  } catch (e) {
    console.log('[DIAGNOSE] ✗ Click failed:', e.message)
  }

  // === INSPECTIONS ===
  console.log('\n[DIAGNOSE] === DOM INSPECTION ===')

  // 1. Message groups
  const messageGroupCount = await page.locator('.message-group').count()
  console.log(`[DIAGNOSE] 1. Message groups: ${messageGroupCount}`)

  // 2. Message bubbles
  const bubbleCount = await page.locator('.message-bubble').count()
  const mediaCount = await page.locator('[class*="mensaje-media"]').count()
  console.log(`[DIAGNOSE] 2. Message bubbles: ${bubbleCount}, Media: ${mediaCount}`)

  // 3. Empty state
  const emptyState = await page.locator('.empty-state').isVisible().catch(() => false)
  console.log(`[DIAGNOSE] 3. Empty state visible: ${emptyState}`)

  // 4. Loading state
  const loadingState = await page.locator('.loading-state').isVisible().catch(() => false)
  console.log(`[DIAGNOSE] 4. Loading state visible: ${loadingState}`)

  // 5. REAL-0010 text
  const real0010 = await page.locator('text=REAL-0010').isVisible().catch(() => false)
  console.log(`[DIAGNOSE] 5. REAL-0010 visible: ${real0010}`)

  // 6. Timeline boundingBox
  const timelineBox = await page.locator('.message-timeline').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] 6. Timeline boundingBox:`, timelineBox)

  // 7. Timeline styles
  const timelineStyles = await page.locator('.message-timeline')
    .evaluate(el => ({
      display: window.getComputedStyle(el).display,
      height: window.getComputedStyle(el).height,
      minHeight: window.getComputedStyle(el).minHeight,
      overflow: window.getComputedStyle(el).overflowY,
    }))
    .catch(() => null)
  console.log(`[DIAGNOSE] 7. Timeline styles:`, timelineStyles)

  // 8. Header boundingBox
  const headerBox = await page.locator('.conversation-header').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] 8. Header boundingBox:`, headerBox)

  // 9. Composer boundingBox
  const composerBox = await page.locator('.chat-composer').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] 9. Composer boundingBox:`, composerBox)

  // 10. Chat content flex layout
  const chatContentBox = await page.locator('.chat-content').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] 10. Chat content boundingBox:`, chatContentBox)

  // 11. First message text
  const firstMessageText = await page.locator('.message-bubble').first().textContent().catch(() => null)
  console.log(`[DIAGNOSE] 11. First message text:`, firstMessageText?.substring(0, 50))

  // 12. Any text in timeline
  const timelineText = await page.locator('.message-timeline').textContent().catch(() => '')
  console.log(`[DIAGNOSE] 12. Timeline text content length: ${timelineText.length}`)
  if (timelineText) {
    console.log(`[DIAGNOSE]    First 150 chars:`, timelineText.substring(0, 150))
  }

  // 13. All divs under message-timeline
  const timelineChildren = await page.locator('.message-timeline > *').count()
  console.log(`[DIAGNOSE] 13. Direct children of .message-timeline: ${timelineChildren}`)

  // 14. Check if messages are in store (via computed)
  const checkStoreScript = `
    const store = window.__PINIA_STORE
    if (store && store.state.messages) {
      return {
        store_exists: true,
        messages_state: store.state.messages
      }
    }
    return { store_exists: false }
  `
  const storeData = await page.evaluate(checkStoreScript).catch(() => null)
  console.log(`[DIAGNOSE] 14. Store data:`, storeData)

  // 15. Check console errors
  console.log(`\n[DIAGNOSE] === CONSOLE LOGS ===`)
  console.log(`[DIAGNOSE] Captured ${consoleLogs.length} logs:`)
  consoleLogs.forEach(log => console.log(`  ${log}`))

  // Screenshot
  console.log(`\n[DIAGNOSE] Saving screenshot...`)
  await page.screenshot({ path: 'timeline-simple.png', fullPage: false })
  console.log('[DIAGNOSE] Screenshot saved: timeline-simple.png')

  // Diagnosis
  console.log(`\n[DIAGNOSE] === DIAGNOSIS ===`)
  if (bubbleCount === 0 && mediaCount === 0) {
    console.log('[RESULT] G1-G3: No bubbles rendered in DOM')
  } else if ((bubbleCount + mediaCount) > 0 && !real0010) {
    console.log('[RESULT] G4-G8: Bubbles exist but REAL-0010 hidden')
  } else if (real0010) {
    console.log('[RESULT] SUCCESS: Timeline working')
  }

  await browser.close()
  process.exit(0)
}

diagnose().catch(err => {
  console.error('[ERROR]', err)
  process.exit(1)
})
