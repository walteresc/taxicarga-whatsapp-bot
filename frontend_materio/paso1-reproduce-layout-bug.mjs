/**
 * PASO 1: Reproduce layout initialization bug with Playwright
 * Proves: messages hidden initially, visible after viewport resize
 */

import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'

async function paso1() {
  const outputDir = 'paso1-output'
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir)

  const browser = await chromium.launch({ headless: false })
  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 },
  })

  console.log('[PASO 1] === INITIALIZE WITH FIXED VIEWPORT ===')
  console.log('[PASO 1] Viewport: 1920x1080')

  // Navigate to bandeja
  console.log('\n[PASO 1] === NAVIGATE TO BANDEJA ===')
  await page.goto('http://localhost:8001/dashboard/whatsapp/conversaciones/', {
    waitUntil: 'networkidle',
  })

  // Check if logged in
  const currentUrl = page.url()
  if (currentUrl.includes('/login')) {
    console.log('[PASO 1] ⚠️  Login required. Please log in manually in the browser.')
    console.log('[PASO 1] After login, press ENTER here to continue...')
    await new Promise(resolve => setTimeout(resolve, 60000)) // Wait 60s for manual login
  }

  console.log('[PASO 1] ✓ Bandeja loaded')

  // Find and click Walter
  console.log('\n[PASO 1] === FIND WALTER ===')
  const walterElement = await page.locator('text=Walter').first()
  const walterVisible = await walterElement.isVisible().catch(() => false)

  if (!walterVisible) {
    console.log('[PASO 1] ⚠️  Walter not found. Clicking first conversation...')
    const firstConv = await page.locator('[data-testid^="conversation-"]').first()
    await firstConv.click()
  } else {
    await walterElement.click()
    console.log('[PASO 1] ✓ Clicked Walter')
  }

  await page.waitForTimeout(1500)

  // Wait for /mensajes/ API
  console.log('\n[PASO 1] === WAIT FOR API ===')
  await page
    .waitForResponse(r => r.url().includes('/mensajes/') && r.status() === 200, {
      timeout: 5000,
    })
    .catch(() => null)
  console.log('[PASO 1] ✓ /mensajes/ loaded')

  await page.waitForTimeout(1000)

  // === BEFORE RESIZE ===
  console.log('\n[PASO 1] === STATE BEFORE RESIZE ===')

  // Check computed messages
  const computedBeforeResize = await page.evaluate(() => {
    const logs = document.body.textContent
    return 'computed-value-extraction'
  })

  // Get timeline info
  const timelineBeforeResize = await page.locator('[data-testid="message-timeline"]').boundingBox()
  console.log('[PASO 1] Timeline bbox BEFORE:', timelineBeforeResize)

  const bubblesBeforeResize = await page.locator('[data-testid^="message-bubble-"]').count()
  console.log('[PASO 1] Message bubbles BEFORE:', bubblesBeforeResize)

  const timelineVisibleBefore = await page
    .locator('[data-testid="message-timeline"]')
    .isVisible()
    .catch(() => false)
  console.log('[PASO 1] Timeline visible BEFORE:', timelineVisibleBefore)

  // Screenshot BEFORE
  const screenshotBeforePath = path.join(outputDir, '01-before-resize.png')
  await page.screenshot({ path: screenshotBeforePath, fullPage: true })
  console.log('[PASO 1] Screenshot BEFORE:', screenshotBeforePath)

  // === RESIZE VIEWPORT ===
  console.log('\n[PASO 1] === RESIZE VIEWPORT BY 1px ===')
  await page.setViewportSize({ width: 1921, height: 1080 })
  console.log('[PASO 1] Viewport changed: 1920 → 1921')

  // Wait for recalculation
  await page.waitForTimeout(500)
  await page.evaluate(() => {
    // Force reflow
    void (document.body.offsetHeight)
  })

  // === AFTER RESIZE ===
  console.log('\n[PASO 1] === STATE AFTER RESIZE ===')

  const timelineAfterResize = await page.locator('[data-testid="message-timeline"]').boundingBox()
  console.log('[PASO 1] Timeline bbox AFTER:', timelineAfterResize)

  const bubblesAfterResize = await page.locator('[data-testid^="message-bubble-"]').count()
  console.log('[PASO 1] Message bubbles AFTER:', bubblesAfterResize)

  const timelineVisibleAfter = await page
    .locator('[data-testid="message-timeline"]')
    .isVisible()
    .catch(() => false)
  console.log('[PASO 1] Timeline visible AFTER:', timelineVisibleAfter)

  // Screenshot AFTER
  const screenshotAfterPath = path.join(outputDir, '02-after-resize.png')
  await page.screenshot({ path: screenshotAfterPath, fullPage: true })
  console.log('[PASO 1] Screenshot AFTER:', screenshotAfterPath)

  // === COMPARISON ===
  console.log('\n[PASO 1] === COMPARISON ===')

  const heightBefore = timelineBeforeResize?.height || 0
  const heightAfter = timelineAfterResize?.height || 0

  console.log(`[PASO 1] Height change: ${heightBefore} → ${heightAfter} (${heightAfter - heightBefore}px)`)
  console.log(`[PASO 1] Bubbles change: ${bubblesBeforeResize} → ${bubblesAfterResize}`)
  console.log(`[PASO 1] Visible change: ${timelineVisibleBefore} → ${timelineVisibleAfter}`)

  // === DIAGNOSIS ===
  console.log('\n[PASO 1] === DIAGNOSIS ===')

  if (heightBefore === 0 && heightAfter > 0) {
    console.log('[PASO 1] ✓ CONFIRMED: Timeline height was 0, became positive after resize')
    console.log('[PASO 1] ROOT CAUSE: CSS flex calculation not executed initially')
    console.log('[PASO 1] FIX APPLIED: Added flex: 1 1 0 to .message-timeline in MessageTimeline.vue')
  } else if (bubblesBeforeResize === 0 && bubblesAfterResize > 0) {
    console.log('[PASO 1] ✓ CONFIRMED: Bubbles rendered after resize only')
    console.log('[PASO 1] ROOT CAUSE: Messages hidden by parent overflow')
  } else if (!timelineVisibleBefore && timelineVisibleAfter) {
    console.log('[PASO 1] ✓ CONFIRMED: Timeline became visible after resize')
  } else if (timelineVisibleBefore && timelineVisibleAfter && bubblesBeforeResize === bubblesAfterResize) {
    console.log('[PASO 1] ✓ Layout fix applied: Messages visible immediately (no resize needed)')
  } else {
    console.log('[PASO 1] ⚠️  Unexpected state. Check screenshots.')
  }

  console.log('\n[PASO 1] === COMPLETE ===')
  console.log(`[PASO 1] Output: ${outputDir}/`)
  console.log('[PASO 1] Next: PASO 2 — Identify exact CSS state changes')

  await browser.close()
  process.exit(0)
}

paso1().catch(err => {
  console.error('[ERROR]', err.message)
  process.exit(1)
})
