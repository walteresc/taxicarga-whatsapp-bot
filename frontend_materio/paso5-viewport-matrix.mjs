/**
 * PASO 5: Viewport matrix test — verify layout fix works across resolutions
 */

import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'

const VIEWPORTS = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1536x864', width: 1536, height: 864 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1280x720', width: 1280, height: 720 },
  { name: '1024x768', width: 1024, height: 768 },
]

async function paso5() {
  const outputDir = 'paso5-output'
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true })

  const results = []

  for (const viewport of VIEWPORTS) {
    console.log(`\n[PASO 5] === VIEWPORT: ${viewport.name} ===`)

    const browser = await chromium.launch({ headless: false })
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
    })

    try {
      // Navigate
      await page.goto('http://localhost:8001/dashboard/whatsapp/conversaciones/', {
        waitUntil: 'networkidle',
        timeout: 10000,
      })

      // Check login
      const currentUrl = page.url()
      if (currentUrl.includes('/login')) {
        console.log(`[PASO 5] ⚠️  ${viewport.name}: Login required`)
        results.push({
          viewport: viewport.name,
          status: 'LOGIN_REQUIRED',
          bubbles: 0,
          timelineHeight: 0,
        })
        await browser.close()
        continue
      }

      // Find and click Walter
      const walterElement = await page.locator('text=Walter').first()
      const walterVisible = await walterElement.isVisible().catch(() => false)

      if (walterVisible) {
        await walterElement.click()
        await page.waitForTimeout(1500)
      } else {
        const firstConv = await page.locator('[data-testid^="conversation-"]').first()
        await firstConv.click()
        await page.waitForTimeout(1500)
      }

      // Wait for API
      await page
        .waitForResponse(r => r.url().includes('/mensajes/') && r.status() === 200, {
          timeout: 5000,
        })
        .catch(() => null)

      await page.waitForTimeout(800)

      // Measure
      const timeline = await page.locator('[data-testid="message-timeline"]').boundingBox()
      const bubbles = await page.locator('[data-testid^="message-bubble-"]').count()
      const timelineVisible = await page
        .locator('[data-testid="message-timeline"]')
        .isVisible()
        .catch(() => false)

      const status =
        bubbles > 0 && timelineVisible
          ? 'PASS'
          : bubbles > 0 && !timelineVisible
            ? 'FAIL_HIDDEN'
            : bubbles === 0
              ? 'FAIL_NO_BUBBLES'
              : 'UNKNOWN'

      results.push({
        viewport: viewport.name,
        status,
        bubbles,
        timelineHeight: timeline?.height || 0,
      })

      console.log(`[PASO 5] ${viewport.name}: ${status}`)
      console.log(`[PASO 5]   Bubbles: ${bubbles}, Height: ${timeline?.height || 0}px`)

      // Screenshot
      const screenshotPath = path.join(outputDir, `${viewport.width}x${viewport.height}.png`)
      await page.screenshot({ path: screenshotPath })
      console.log(`[PASO 5]   Screenshot: ${screenshotPath}`)
    } catch (error) {
      console.error(`[PASO 5] ${viewport.name} Error:`, error.message)
      results.push({
        viewport: viewport.name,
        status: 'ERROR',
        error: error.message,
      })
    } finally {
      await browser.close()
    }
  }

  // === REPORT ===
  console.log('\n[PASO 5] === MATRIX RESULTS ===')
  console.log('Viewport      | Status       | Bubbles | Height')
  console.log('--------------|--------------|---------|-------')

  let passCount = 0
  results.forEach(r => {
    const statusPad = (r.status || 'UNKNOWN').padEnd(12)
    const bubblesPad = (r.bubbles || 0).toString().padEnd(7)
    const heightPad = (r.timelineHeight || 0).toString().padEnd(6)
    console.log(`${r.viewport.padEnd(14)}| ${statusPad}| ${bubblesPad}| ${heightPad}`)
    if (r.status === 'PASS') passCount++
  })

  console.log('\n[PASO 5] SUMMARY: ' + passCount + '/' + results.length + ' PASS')

  if (passCount === results.length) {
    console.log('[PASO 5] ✓ Layout fix verified across all viewports')
  } else {
    console.log('[PASO 5] ⚠️  Some viewports failed — check screenshots')
  }

  // Save JSON report
  const reportPath = path.join(outputDir, 'results.json')
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2))
  console.log(`[PASO 5] Report: ${reportPath}`)

  process.exit(passCount === results.length ? 0 : 1)
}

paso5().catch(err => {
  console.error('[ERROR]', err.message)
  process.exit(1)
})
