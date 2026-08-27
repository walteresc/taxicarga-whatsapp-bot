/**
 * Diagnóstico con autenticación
 */

import { chromium } from 'playwright'

async function diagnose() {
  const browser = await chromium.launch({ headless: false })
  const page = await browser.newPage()

  console.log('[AUTH] === LOGIN ===')

  // Go to login
  console.log('[AUTH] Navigating to login...')
  await page.goto('http://localhost:8001/dashboard/login/', { waitUntil: 'networkidle' })
  console.log('[AUTH] ✓ Login page loaded')

  // Fill credentials
  console.log('[AUTH] Attempting login...')
  await page.fill('[name="username"]', 'admin')
  await page.fill('[name="password"]', 'admin123')

  // Click submit
  const submitButton = page.locator('button[type="submit"]').first()
  await submitButton.click()

  // Wait for navigation
  console.log('[AUTH] Waiting for authentication...')
  await page.waitForNavigation({ waitUntil: 'networkidle', timeout: 10000 }).catch(() => null)

  const currentUrl = page.url()
  console.log('[AUTH] ✓ Current URL after login:', currentUrl)

  // === VERIFICAR SESIÓN ===
  console.log('\n[AUTH] === VERIFICAR SESIÓN ===')

  const cookies = await page.context().cookies()
  const hasSession = cookies.some(c => c.name.includes('session') || c.name.includes('sessionid'))
  console.log('[AUTH] Session cookies:', hasSession)

  // === NAVEGAR A BANDEJA ===
  console.log('\n[AUTH] === NAVEGAR A BANDEJA ===')

  const bandejaUrl = 'http://localhost:8001/dashboard/whatsapp/conversaciones/'
  console.log('[AUTH] Navigating to:', bandejaUrl)

  const response = await page.goto(bandejaUrl, { waitUntil: 'networkidle' })
  console.log('[AUTH] Status:', response?.status())

  // === CONTEXTO DESPUÉS DE AUTENTICACIÓN ===
  console.log('\n[AUTH] === PAGE CONTEXT ===')

  const title = await page.title()
  console.log('[AUTH] Title:', title)

  const bodyText = await page.evaluate(() => document.body.innerText)
  const hasWalter = bodyText.includes('Walter')
  const hasBandeja = bodyText.includes('Bandeja')
  console.log('[AUTH] Body has "Walter":', hasWalter)
  console.log('[AUTH] Body has "Bandeja":', hasBandeja)

  // === BÚSQUEDAS POR TEXTO ===
  console.log('\n[AUTH] === BÚSQUEDAS ===')

  const walterVisible = await page.locator('text=Walter').isVisible().catch(() => false)
  console.log('[AUTH] "Walter" visible:', walterVisible)

  const real0010Visible = await page.locator('text=REAL-0010').isVisible().catch(() => false)
  console.log('[AUTH] "REAL-0010" visible:', real0010Visible)

  const tomarConvVisible = await page.locator('text=Tomar conversación').isVisible().catch(() => false)
  console.log('[AUTH] "Tomar conversación" visible:', tomarConvVisible)

  // === ELEMENTOS ===
  console.log('\n[AUTH] === ELEMENTOS ===')

  const panelVisible = await page.locator('[class*="conversation-panel"]').isVisible().catch(() => false)
  console.log('[AUTH] ConversationPanel visible:', panelVisible)

  const timelineVisible = await page.locator('.message-timeline').isVisible().catch(() => false)
  console.log('[AUTH] Timeline visible:', timelineVisible)

  // === BUTTONS ===
  const buttonCount = await page.locator('button').count()
  console.log('[AUTH] Button count:', buttonCount)

  // === HACER CLIC EN WALTER ===
  if (walterVisible) {
    console.log('\n[AUTH] === CLIC EN WALTER ===')
    try {
      const walterButton = page.locator('text=Walter').first()
      await walterButton.click()
      console.log('[AUTH] ✓ Clicked Walter')
      await page.waitForTimeout(2000)

      // Check timeline after click
      const timelineAfterClick = await page.locator('.message-timeline').isVisible().catch(() => false)
      console.log('[AUTH] Timeline after click:', timelineAfterClick)

      const bubblesCount = await page.locator('.message-bubble').count()
      console.log('[AUTH] Message bubbles:', bubblesCount)

      const real0010After = await page.locator('text=REAL-0010').isVisible().catch(() => false)
      console.log('[AUTH] REAL-0010 after click:', real0010After)

    } catch (e) {
      console.log('[AUTH] ✗ Click failed:', e.message)
    }
  }

  // === SCREENSHOT ===
  console.log('\n[AUTH] Saving screenshot...')
  await page.screenshot({ path: 'timeline-auth.png', fullPage: true })
  console.log('[AUTH] Screenshot saved')

  // === RESULTADO FINAL ===
  console.log('\n[AUTH] === RESULTADO FINAL ===')

  if (currentUrl.includes('/login')) {
    console.log('[RESULT] LOGIN FALLIDO - Aún en login')
  } else if (!walterVisible) {
    console.log('[RESULT] BANDEJA NO CARGÓ - No hay Walter')
  } else if (!timelineVisible) {
    console.log('[RESULT] TIMELINE NO MONTADO')
  } else if (!real0010Visible) {
    console.log('[RESULT] TIMELINE VACÍO - No hay REAL-0010')
  } else {
    console.log('[RESULT] SUCCESS - Todo funciona')
  }

  await browser.close()
  process.exit(0)
}

diagnose().catch(err => {
  console.error('[ERROR]', err)
  process.exit(1)
})
