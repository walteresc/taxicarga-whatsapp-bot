/**
 * FASE 5B: E2E test para inspeccionar renderizado real del timeline
 * Ejecutar DESPUÉS de recarga del navegador
 */

import { test, expect } from '@playwright/test'

test.describe('ConversationPanel timeline render', () => {
  test('should render 6 messages in DOM', async ({ page }) => {
    // Login
    await page.goto('http://localhost:8001/dashboard/login/')
    await page.fill('input[name="username"]', 'admin')
    await page.fill('input[name="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForNavigation()

    // Navigate to bandeja
    await page.goto('http://localhost:8001/dashboard/bandeja/')
    await page.waitForLoadState('networkidle')

    // Wait for conversations to load
    await page.waitForSelector('[data-testid="conversation-list"] button', { timeout: 5000 })

    // Click on Walter (first conversation)
    const firstConv = await page.locator('[data-testid="conversation-list"] button').first()
    await firstConv.click()

    // Wait for timeline to load
    await page.waitForSelector('.message-timeline', { timeout: 5000 })

    // Wait for messages API call
    await page.waitForResponse(response => {
      return response.url().includes('/mensajes/') && response.status() === 200
    })

    // Give computed time to update
    await page.waitForTimeout(500)

    // **INSPECCIÓN 1: Elemento .message-timeline**
    const timelineElement = await page.locator('.message-timeline')
    console.log('[E2E] Timeline element found:', await timelineElement.isVisible())

    // **INSPECCIÓN 2: Contenedores de grupos**
    const messageGroups = await page.locator('.message-group')
    const groupCount = await messageGroups.count()
    console.log('[E2E] Message groups count:', groupCount)

    // **INSPECCIÓN 3: Elementos individuales de mensaje**
    const messages = await page.locator('.message-timeline > div > div > div')
    const messageCount = await messages.count()
    console.log('[E2E] Message elements count:', messageCount)

    // **INSPECCIÓN 4: Componentes burbuja (MensajeMedia o MessageBubble)**
    const bubbles = await page.locator('[class*="message-bubble"], [class*="mensaje-media"]')
    const bubbleCount = await bubbles.count()
    console.log('[E2E] Bubble components count:', bubbleCount)

    // **INSPECCIÓN 5: Textos de mensajes**
    const real0010Text = await page.locator('text=FASE5B-SSE-WALTER-REAL-0010')
    const hasReal0010 = await real0010Text.isVisible({ timeout: 1000 }).catch(() => false)
    console.log('[E2E] REAL-0010 visible:', hasReal0010)

    // **INSPECCIÓN 6: Styles computados**
    const timelineStyle = await timelineElement.evaluate(el => {
      const computed = window.getComputedStyle(el)
      return {
        display: computed.display,
        visibility: computed.visibility,
        opacity: computed.opacity,
        height: computed.height,
        width: computed.width,
        minHeight: computed.minHeight,
        maxHeight: computed.maxHeight,
        overflow: computed.overflow,
        overflowY: computed.overflowY,
        flex: computed.flex,
        flexGrow: computed.flexGrow,
        flexShrink: computed.flexShrink,
        flexBasis: computed.flexBasis,
      }
    })
    console.log('[E2E] Timeline computed styles:', timelineStyle)

    // **INSPECCIÓN 7: BoundingClientRect**
    const timelineRect = await timelineElement.boundingBox()
    console.log('[E2E] Timeline bounding box:', timelineRect)

    // **INSPECCIÓN 8: Empty state visible?**
    const emptyState = await page.locator('.empty-state').first()
    const emptyVisible = await emptyState.isVisible({ timeout: 1000 }).catch(() => false)
    console.log('[E2E] Empty state visible:', emptyVisible)

    // **INSPECCIÓN 9: Verificar loading state**
    const loadingState = await page.locator('.loading-state')
    const loadingVisible = await loadingState.isVisible({ timeout: 500 }).catch(() => false)
    console.log('[E2E] Loading state visible:', loadingVisible)

    // **INSPECCIÓN 10: Capturar screenshot**
    await page.screenshot({ path: 'timeline-render.png', fullPage: false })
    console.log('[E2E] Screenshot saved: timeline-render.png')

    // **VERIFICACIÓN DE ESCENARIO:**
    if (bubbleCount === 0 && !hasReal0010) {
      console.log('[E2E DIAGNOSIS] G1-G3: No message bubbles rendered in DOM')
    } else if (bubbleCount > 0 && !hasReal0010) {
      console.log('[E2E DIAGNOSIS] G4-G8: Bubbles exist but REAL-0010 not visible (hidden/clipped/behind)')
    } else if (hasReal0010) {
      console.log('[E2E DIAGNOSIS] SUCCESS: REAL-0010 visible, timeline rendered correctly')
    }

    // Assertions
    expect(messageGroups.count()).toBeGreaterThan(0)
    expect(real0010Text).toBeVisible()
  })

  test('capture console logs during timeline load', async ({ page, context }) => {
    const logs = []
    page.on('console', msg => {
      if (msg.text().includes('[ConversationPanel')) {
        logs.push(msg.text())
      }
    })

    // Navigate
    await page.goto('http://localhost:8001/dashboard/login/')
    await page.fill('input[name="username"]', 'admin')
    await page.fill('input[name="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForNavigation()

    await page.goto('http://localhost:8001/dashboard/bandeja/')
    await page.waitForLoadState('networkidle')

    // Click first conversation
    const firstConv = await page.locator('[data-testid="conversation-list"] button').first()
    await firstConv.click()

    // Wait for render
    await page.waitForTimeout(1000)

    console.log('[E2E] ConversationPanel logs captured:')
    logs.forEach(log => console.log('  ', log))

    // Verify ENTRY and RESULT logs exist
    const hasEntry = logs.some(l => l.includes('[ConversationPanel computed] ENTRY'))
    const hasResult = logs.some(l => l.includes('[ConversationPanel computed] RESULT: count=6'))

    console.log('[E2E] Has ENTRY log:', hasEntry)
    console.log('[E2E] Has RESULT log with count=6:', hasResult)

    expect(hasEntry).toBeTruthy()
    expect(hasResult).toBeTruthy()
  })
})
