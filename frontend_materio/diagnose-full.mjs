/**
 * FASE 2+4: Full Playwright diagnosis with authentication
 * Measures exact DOM counts, visibility, CSS, and bounding boxes
 */

import { chromium } from 'playwright'
import fs from 'fs'

async function diagnose() {
  const browser = await chromium.launch({ headless: false })
  const page = await browser.newPage()

  console.log('[DIAGNOSE] === LOGIN ===')

  // Navigate to login
  await page.goto('http://localhost:8001/dashboard/login/', { waitUntil: 'networkidle' })

  // Wait for Vue to render login form
  await page.waitForTimeout(2000)

  // Try to find login inputs with multiple strategies
  const usernameInput = await page.locator('input[type="text"], input[name="username"], [placeholder*="user"], [placeholder*="User"]').first()
  const passwordInput = await page.locator('input[type="password"], input[name="password"], [placeholder*="pass"], [placeholder*="Pass"]').first()

  if (!await usernameInput.isVisible().catch(() => false)) {
    console.log('[AUTH] ✗ Login form not found, checking page content...')
    const bodyText = await page.evaluate(() => document.body.innerText)
    console.log('[AUTH] Body text:', bodyText.substring(0, 200))
    await page.screenshot({ path: 'login-page.png', fullPage: true })
    process.exit(1)
  }

  console.log('[AUTH] ✓ Login form found')

  // Fill login
  await usernameInput.fill('admin')
  await passwordInput.fill('admin123')

  // Submit
  const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Iniciar"), button:has-text("Entrar")').first()
  await submitBtn.click()

  console.log('[AUTH] ✓ Login submitted')

  // Wait for redirect
  await page.waitForNavigation({ waitUntil: 'networkidle', timeout: 10000 }).catch(() => null)

  const currentUrl = page.url()
  console.log('[AUTH] Current URL:', currentUrl)

  if (currentUrl.includes('/login')) {
    console.log('[AUTH] ✗ Still on login page')
    process.exit(1)
  }

  console.log('[AUTH] ✓ Authentication success')

  // === NAVIGATE TO BANDEJA ===
  console.log('\n[DIAGNOSE] === NAVIGATE TO BANDEJA ===')

  await page.goto('http://localhost:8001/dashboard/whatsapp/conversaciones/', { waitUntil: 'networkidle' })
  console.log('[DIAGNOSE] ✓ Bandeja loaded')

  // === FIND AND CLICK WALTER ===
  console.log('\n[DIAGNOSE] === FIND WALTER ===')

  const walterElement = await page.locator('text=Walter').first()
  const walterVisible = await walterElement.isVisible().catch(() => false)
  console.log('[DIAGNOSE] Walter visible:', walterVisible)

  if (walterVisible) {
    await walterElement.click()
    console.log('[DIAGNOSE] ✓ Clicked Walter')
    await page.waitForTimeout(1500)

    // Wait for API
    await page.waitForResponse(
      r => r.url().includes('/mensajes/') && r.status() === 200,
      { timeout: 5000 }
    ).catch(() => null)
    console.log('[DIAGNOSE] ✓ /mensajes/ API called')
  }

  // === MEASUREMENTS ===
  console.log('\n[DIAGNOSE] === DOM ELEMENT COUNTS ===')

  const conversationPanel = page.locator('[data-testid="conversation-panel"]')
  const conversationPanelCount = await conversationPanel.count()
  console.log('[MEASURE] conversation-panel count:', conversationPanelCount)

  const chatContent = page.locator('[data-testid="chat-content"]')
  const chatContentCount = await chatContent.count()
  console.log('[MEASURE] chat-content count:', chatContentCount)

  const messageTimeline = page.locator('[data-testid="message-timeline"]')
  const messageTimelineCount = await messageTimeline.count()
  console.log('[MEASURE] message-timeline count:', messageTimelineCount)

  const groupsContainer = page.locator('[data-testid="groups-container"]')
  const groupsContainerCount = await groupsContainer.count()
  console.log('[MEASURE] groups-container count:', groupsContainerCount)

  const messageGroups = page.locator('[data-testid^="message-group-"]')
  const messageGroupsCount = await messageGroups.count()
  console.log('[MEASURE] message-group-* count:', messageGroupsCount)

  const messageBubbles = page.locator('[data-testid^="message-bubble-"]')
  const messageBubblesCount = await messageBubbles.count()
  console.log('[MEASURE] message-bubble-* count:', messageBubblesCount)

  const emptyState = page.locator('[data-testid="empty-state"]')
  const emptyStateVisible = await emptyState.isVisible().catch(() => false)
  console.log('[MEASURE] empty-state visible:', emptyStateVisible)

  // === VISIBILITY ===
  console.log('\n[DIAGNOSE] === VISIBILITY ===')

  const timelineVisible = await messageTimeline.isVisible().catch(() => false)
  console.log('[VISIBILITY] message-timeline visible:', timelineVisible)

  // === BOUNDING BOXES ===
  console.log('\n[DIAGNOSE] === BOUNDING BOXES ===')

  const panelBox = await conversationPanel.boundingBox().catch(() => null)
  console.log('[BBOX] conversation-panel:', panelBox)

  const contentBox = await chatContent.boundingBox().catch(() => null)
  console.log('[BBOX] chat-content:', contentBox)

  const timelineBox = await messageTimeline.boundingBox().catch(() => null)
  console.log('[BBOX] message-timeline:', timelineBox)

  // === CSS STYLES ===
  console.log('\n[DIAGNOSE] === CSS STYLES ===')

  const timelineStyles = await messageTimeline.evaluate(el => ({
    display: window.getComputedStyle(el).display,
    visibility: window.getComputedStyle(el).visibility,
    opacity: window.getComputedStyle(el).opacity,
    height: window.getComputedStyle(el).height,
    width: window.getComputedStyle(el).width,
    minHeight: window.getComputedStyle(el).minHeight,
    maxHeight: window.getComputedStyle(el).maxHeight,
    overflow: window.getComputedStyle(el).overflow,
    overflowY: window.getComputedStyle(el).overflowY,
    position: window.getComputedStyle(el).position,
    flex: window.getComputedStyle(el).flex,
    flexGrow: window.getComputedStyle(el).flexGrow,
    flexShrink: window.getComputedStyle(el).flexShrink,
    flexBasis: window.getComputedStyle(el).flexBasis,
  })).catch(() => null)
  console.log('[STYLE] message-timeline:', timelineStyles)

  // === TEXT CONTENT ===
  console.log('\n[DIAGNOSE] === TEXT CONTENT ===')

  const bubbleTexts = await messageBubbles.allTextContents().catch(() => [])
  console.log('[TEXT] Bubble texts count:', bubbleTexts.length)
  bubbleTexts.forEach((text, idx) => {
    console.log(`[TEXT] Bubble ${idx}: "${text.substring(0, 50)}"`)
  })

  const real0010Found = bubbleTexts.some(t => t.includes('REAL-0010'))
  console.log('[TEXT] REAL-0010 found:', real0010Found)

  // === CLASSIFICATION ===
  console.log('\n[DIAGNOSE] === CLASSIFICATION ===')

  if (messageGroupsCount === 0) {
    console.log('[CLASSIFY] G1: No groups rendered despite messageGroups=2')
  } else if (messageGroupsCount > 0 && messageBubblesCount === 0) {
    console.log('[CLASSIFY] G2: Groups exist but no bubbles')
  } else if (messageBubblesCount > 0 && bubbleTexts.length === 0) {
    console.log('[CLASSIFY] G3: Bubbles exist but no text')
  } else if (messageBubblesCount > 0 && !timelineVisible) {
    console.log('[CLASSIFY] G4-G9: Bubbles exist but timeline not visible')
    if (timelineStyles?.display === 'none') {
      console.log('[CLASSIFY] → G4: display:none')
    } else if (timelineBox?.height === 0) {
      console.log('[CLASSIFY] → G5: height=0')
    } else if (timelineStyles?.overflow === 'hidden' && timelineBox?.height === 0) {
      console.log('[CLASSIFY] → G6: overflow:hidden + height=0')
    }
  } else if (real0010Found) {
    console.log('[CLASSIFY] SUCCESS: Timeline rendering correctly')
  } else {
    console.log('[CLASSIFY] UNKNOWN: Unable to classify')
  }

  // === SCREENSHOT ===
  console.log('\n[DIAGNOSE] Saving full screenshot...')
  await page.screenshot({ path: 'timeline-full-diagnose.png', fullPage: true })
  console.log('[DIAGNOSE] Screenshot saved')

  await browser.close()
  process.exit(0)
}

diagnose().catch(err => {
  console.error('[ERROR]', err.message)
  process.exit(1)
})
