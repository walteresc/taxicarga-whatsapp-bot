/**
 * Complete context validation for Playwright
 */

import { chromium } from 'playwright'
import fs from 'fs'

async function diagnose() {
  const browser = await chromium.launch({ headless: false })
  const page = await browser.newPage()

  console.log('[CONTEXT] === NAVEGACIÓN ===')

  // Navigate
  const url = 'http://localhost:8001/dashboard/whatsapp/conversaciones/'
  console.log('[CONTEXT] URL:', url)

  const response = await page.goto(url, { waitUntil: 'networkidle' }).catch(e => null)
  console.log('[CONTEXT] Response status:', response?.status())
  console.log('[CONTEXT] Actual URL:', page.url())

  // === CONTEXTO PAGE ===
  console.log('\n[CONTEXT] === PAGE PROPERTIES ===')

  const title = await page.title()
  console.log('[CONTEXT] Document title:', title)

  const bodyText = await page.evaluate(() => document.body.innerText)
  console.log('[CONTEXT] Body text (first 300 chars):')
  console.log(bodyText.substring(0, 300))

  const htmlContent = await page.evaluate(() => document.documentElement.outerHTML.substring(0, 500))
  console.log('\n[CONTEXT] HTML (first 500 chars):')
  console.log(htmlContent)

  // === BÚSQUEDAS POR TEXTO ===
  console.log('\n[CONTEXT] === BÚSQUEDAS POR TEXTO ===')

  const hasBandeja = await page.locator('text=Bandeja de entrada').isVisible().catch(() => false)
  console.log('[CONTEXT] "Bandeja de entrada" visible:', hasBandeja)

  const hasWalter = await page.locator('text=Walter').isVisible().catch(() => false)
  console.log('[CONTEXT] "Walter" visible:', hasWalter)

  const hasReal0010 = await page.locator('text=REAL-0010').isVisible().catch(() => false)
  console.log('[CONTEXT] "REAL-0010" visible:', hasReal0010)

  const hasMensaje = await page.locator('text=Mensaje de prueba').isVisible().catch(() => false)
  console.log('[CONTEXT] "Mensaje de prueba" visible:', hasMensaje)

  const hasTomarConv = await page.locator('text=Tomar conversación').isVisible().catch(() => false)
  console.log('[CONTEXT] "Tomar conversación" visible:', hasTomarConv)

  const hasLogin = await page.locator('input[name="username"]').isVisible().catch(() => false)
  console.log('[CONTEXT] Login form visible:', hasLogin)

  // === ELEMENTOS PRINCIPALES ===
  console.log('\n[CONTEXT] === ELEMENTOS PRINCIPALES ===')

  const hasConversationPanel = await page.locator('[class*="conversation-panel"]').isVisible().catch(() => false)
  console.log('[CONTEXT] ConversationPanel visible:', hasConversationPanel)

  const hasConversationList = await page.locator('[class*="conversation-list"]').isVisible().catch(() => false)
  console.log('[CONTEXT] ConversationList visible:', hasConversationList)

  const hasTimeline = await page.locator('.message-timeline').isVisible().catch(() => false)
  console.log('[CONTEXT] .message-timeline visible:', hasTimeline)

  // === VUETIFY COMPONENTS ===
  console.log('\n[CONTEXT] === VUETIFY ELEMENTS ===')

  const buttons = await page.locator('button').count()
  console.log('[CONTEXT] Total buttons:', buttons)

  const buttonTexts = await page.locator('button').allTextContents()
  console.log('[CONTEXT] Button texts:', buttonTexts.slice(0, 5))

  // === VERIFICAR SI ESTÁ LOGUEADO ===
  console.log('\n[CONTEXT] === AUTENTICACIÓN ===')

  const cookies = await page.context().cookies()
  const hasSessions = cookies.some(c => c.name.includes('session') || c.name.includes('auth'))
  console.log('[CONTEXT] Session cookies found:', hasSessions)
  console.log('[CONTEXT] Cookies count:', cookies.length)

  // === NETWORK REQUESTS ===
  console.log('\n[CONTEXT] === NETWORK ===')

  page.on('response', response => {
    if (response.url().includes('conversaciones') || response.url().includes('mensajes') || response.url().includes('api')) {
      console.log('[NETWORK]', response.status(), response.url())
    }
  })

  // Try to find conversation ID=1
  console.log('\n[CONTEXT] === BUSCAR WALTER (ID=1) ===')

  const allText = await page.locator('body').textContent()
  const hasWalterText = allText.includes('Walter')
  console.log('[CONTEXT] Walter en body text:', hasWalterText)

  // List all divs with Walter
  const walterElements = await page.locator('text=Walter').count()
  console.log('[CONTEXT] Elements with "Walter" text:', walterElements)

  // === INTENTAR HACER CLIC ===
  console.log('\n[CONTEXT] === INTENTAR INTERACCIÓN ===')

  // Try clicking Walter text
  if (walterElements > 0) {
    try {
      const walterButton = page.locator('text=Walter').first()
      await walterButton.click({ timeout: 2000 })
      console.log('[CONTEXT] ✓ Clicked Walter element')
      await page.waitForTimeout(1500)

      // Check if API was called
      const msgResponse = await page.waitForResponse(
        r => r.url().includes('/mensajes/'),
        { timeout: 5000 }
      ).catch(() => null)
      console.log('[CONTEXT] /mensajes/ API called:', msgResponse?.status())

      // Check timeline now
      const timelineAfter = await page.locator('.message-timeline').isVisible().catch(() => false)
      console.log('[CONTEXT] Timeline visible after click:', timelineAfter)

      const bubblesAfter = await page.locator('.message-bubble').count()
      console.log('[CONTEXT] Message bubbles after click:', bubblesAfter)

    } catch (e) {
      console.log('[CONTEXT] ✗ Click failed:', e.message)
    }
  }

  // === SCREENSHOT ===
  console.log('\n[CONTEXT] Saving screenshot...')
  await page.screenshot({ path: 'timeline-context.png', fullPage: true })
  console.log('[CONTEXT] Screenshot saved')

  // === CONCLUSIÓN ===
  console.log('\n[CONTEXT] === CONCLUSIÓN ===')

  if (hasLogin) {
    console.log('[RESULT] A: NOT AUTHENTICATED - Login form visible')
  } else if (!hasBandeja && !hasWalter) {
    console.log('[RESULT] E: WRONG PAGE - No bandeja/conversation elements')
  } else if (hasWalter && !hasConversationPanel) {
    console.log('[RESULT] B: PARTIALLY MOUNTED - Walter visible but no ConversationPanel')
  } else if (hasConversationPanel && !hasTimeline) {
    console.log('[RESULT] D: SELECTOR OBSOLETE - Panel mounted but .message-timeline missing')
  } else if (hasTimeline && !hasReal0010) {
    console.log('[RESULT] C: TIMELINE V-IF HIDDEN - Timeline mounted but messages not rendering')
  } else if (hasReal0010) {
    console.log('[RESULT] SUCCESS: Timeline rendering correctly')
  } else {
    console.log('[RESULT] F: UNKNOWN - Unable to classify')
  }

  await browser.close()
  process.exit(0)
}

diagnose().catch(err => {
  console.error('[ERROR]', err)
  process.exit(1)
})
