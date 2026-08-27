/**
 * Direct DOM inspection using Playwright
 * Ejecutar: node diagnose.mjs
 */

import { chromium } from 'playwright'
import fs from 'fs'

async function diagnose() {
  const browser = await chromium.launch({ headless: false })

  // Capture console logs
  const consoleLogs = []

  const page = await browser.newPage()
  page.on('console', msg => {
    const text = msg.text()
    if (text.includes('[ConversationPanel') || text.includes('[TEST]') || text.includes('[E2E]')) {
      consoleLogs.push(text)
      console.log('[CONSOLE]', text)
    }
  })

  page.on('response', response => {
    if (response.url().includes('/mensajes/')) {
      console.log('[NETWORK]', response.status(), response.url())
    }
  })

  // Login
  console.log('\n[DIAGNOSE] Step 1: Login')
  await page.goto('http://localhost:8001/dashboard/login/')
  await page.fill('input[name="username"]', 'admin')
  await page.fill('input[name="password"]', 'admin123')
  await page.click('button[type="submit"]')
  await page.waitForNavigation()
  console.log('[DIAGNOSE] ✓ Logged in')

  // Go to bandeja
  console.log('[DIAGNOSE] Step 2: Navigate to bandeja')
  await page.goto('http://localhost:8001/dashboard/bandeja/')
  await page.waitForLoadState('networkidle')
  console.log('[DIAGNOSE] ✓ Bandeja loaded')

  // Wait for conversations
  console.log('[DIAGNOSE] Step 3: Wait for conversations')
  try {
    await page.waitForSelector('[class*="conversation"]', { timeout: 5000 })
    console.log('[DIAGNOSE] ✓ Conversations visible')
  } catch (e) {
    console.log('[DIAGNOSE] ✗ No conversations found')
  }

  // Click first conversation (Walter)
  console.log('[DIAGNOSE] Step 4: Click first conversation')
  try {
    const firstButton = await page.locator('button').first()
    await firstButton.click()
    console.log('[DIAGNOSE] ✓ Clicked first conversation')
  } catch (e) {
    console.log('[DIAGNOSE] ✗ Failed to click:', e.message)
  }

  // Wait for timeline
  console.log('[DIAGNOSE] Step 5: Wait for timeline')
  try {
    await page.waitForSelector('.message-timeline', { timeout: 5000 })
    console.log('[DIAGNOSE] ✓ Timeline element found')
  } catch (e) {
    console.log('[DIAGNOSE] ✗ Timeline not found')
  }

  // Wait for messages API
  console.log('[DIAGNOSE] Step 6: Wait for API response')
  try {
    await page.waitForResponse(
      response => response.url().includes('/mensajes/') && response.status() === 200,
      { timeout: 5000 }
    )
    console.log('[DIAGNOSE] ✓ API response received')
  } catch (e) {
    console.log('[DIAGNOSE] ✗ API not called or failed')
  }

  // Give time for rendering
  await page.waitForTimeout(1000)

  // **INSPECCIÓN 1: Count message groups**
  console.log('\n[DIAGNOSE] === DOM INSPECTION ===')
  const messageGroupCount = await page.locator('.message-group').count()
  console.log(`[DIAGNOSE] .message-group elements: ${messageGroupCount}`)

  // **INSPECCIÓN 2: Count message bubbles/components**
  const bubbleCount = await page.locator('.message-bubble, [class*="mensaje-media"]').count()
  console.log(`[DIAGNOSE] Message bubbles/media count: ${bubbleCount}`)

  // **INSPECCIÓN 3: Timeline visibility and styles**
  const timelineLocator = page.locator('.message-timeline')
  const timelineVisible = await timelineLocator.isVisible().catch(() => false)
  console.log(`[DIAGNOSE] Timeline visible: ${timelineVisible}`)

  const timelineRect = await timelineLocator.boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] Timeline boundingBox:`, timelineRect)

  const timelineStyles = await timelineLocator.evaluate(el => ({
    display: window.getComputedStyle(el).display,
    visibility: window.getComputedStyle(el).visibility,
    opacity: window.getComputedStyle(el).opacity,
    height: window.getComputedStyle(el).height,
    minHeight: window.getComputedStyle(el).minHeight,
    maxHeight: window.getComputedStyle(el).maxHeight,
    overflow: window.getComputedStyle(el).overflow,
    overflowY: window.getComputedStyle(el).overflowY,
  })).catch(() => null)
  console.log(`[DIAGNOSE] Timeline computed styles:`, timelineStyles)

  // **INSPECCIÓN 4: Empty state**
  const emptyStateVisible = await page.locator('.empty-state').first().isVisible().catch(() => false)
  console.log(`[DIAGNOSE] Empty state visible: ${emptyStateVisible}`)

  // **INSPECCIÓN 5: Loading state**
  const loadingStateVisible = await page.locator('.loading-state').first().isVisible().catch(() => false)
  console.log(`[DIAGNOSE] Loading state visible: ${loadingStateVisible}`)

  // **INSPECCIÓN 6: Search for REAL-0010**
  const real0010Visible = await page.locator('text=REAL-0010').isVisible().catch(() => false)
  console.log(`[DIAGNOSE] REAL-0010 text visible: ${real0010Visible}`)

  // **INSPECCIÓN 7: Check for any text content**
  const textContent = await page.locator('.message-timeline').textContent().catch(() => '')
  console.log(`[DIAGNOSE] Timeline text content (first 200 chars):`, textContent.substring(0, 200))

  // **INSPECCIÓN 8: Check parent flex container**
  const chatContentRect = await page.locator('.chat-content').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] .chat-content boundingBox:`, chatContentRect)

  // **INSPECCIÓN 9: Check header**
  const headerRect = await page.locator('.conversation-header').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] .conversation-header boundingBox:`, headerRect)

  // **INSPECCIÓN 10: Check composer**
  const composerRect = await page.locator('.chat-composer').boundingBox().catch(() => null)
  console.log(`[DIAGNOSE] .chat-composer boundingBox:`, composerRect)

  // **INSPECCIÓN 11: Scroll timeline to reveal messages**
  console.log(`[DIAGNOSE] Scrolling timeline...`)
  await timelineLocator.evaluate(el => {
    el.scrollTop = 0
  }).catch(() => null)
  await page.waitForTimeout(500)

  // Check again after scroll
  const bubbleCountAfterScroll = await page.locator('.message-bubble, [class*="mensaje-media"]').count()
  console.log(`[DIAGNOSE] Message bubbles after scroll: ${bubbleCountAfterScroll}`)

  // **INSPECCIÓN 12: Console logs captured**
  console.log(`\n[DIAGNOSE] === CONSOLE LOGS (${consoleLogs.length} captured) ===`)
  consoleLogs.forEach(log => console.log('[LOG]', log))

  // **SCREENSHOT**
  console.log(`\n[DIAGNOSE] Saving screenshot...`)
  await page.screenshot({ path: 'timeline-diagnose.png', fullPage: false })
  console.log('[DIAGNOSE] Screenshot saved: timeline-diagnose.png')

  // **DIAGNOSE CONCLUSION**
  console.log(`\n[DIAGNOSE] === DIAGNOSIS ===`)
  if (bubbleCount === 0) {
    console.log('[DIAGNOSE] G1-G3: No message bubbles in DOM - template not rendering')
  } else if (bubbleCount > 0 && !real0010Visible) {
    console.log('[DIAGNOSE] G4-G8: Bubbles exist but REAL-0010 not visible - hidden/clipped/behind')
  } else if (real0010Visible) {
    console.log('[DIAGNOSE] SUCCESS: Timeline rendering correctly')
  }

  // Close
  await browser.close()
}

diagnose().catch(console.error)
