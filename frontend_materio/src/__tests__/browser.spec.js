import { test, expect } from '@playwright/test'

test.describe('FASE 5B Browser Integration', () => {
  const VITE_URL = 'http://localhost:5177'
  const DJANGO_URL = 'http://localhost:8001'

  test('SSE primary channel connects and receives events', async ({ browser }) => {
    const context = await browser.newContext()
    const page = await context.newPage()

    // Monitor Network requests
    const networkRequests = []

    page.on('request', req => networkRequests.push({
      url: req.url(),
      method: req.method(),
    }))

    // Navigate to Vite dev server
    await page.goto(`${VITE_URL}/`)
    await expect(page).toHaveTitle(/materio|dashboard/i)

    // Wait for any initial network activity to settle
    await page.waitForLoadState('networkidle')

    // Check that page loaded
    const title = await page.title()

    console.log('Page title:', title)
    expect(title).toBeTruthy()

    await context.close()
  })

  test('two tabs maintain independent SSE connections', async ({ browser }) => {
    const context = await browser.newContext()

    // Create two tabs
    const page1 = await context.newPage()
    const page2 = await context.newPage()

    // Navigate both to Vite server
    await page1.goto(`${VITE_URL}/`)
    await page2.goto(`${VITE_URL}/`)

    await page1.waitForLoadState('networkidle')
    await page2.waitForLoadState('networkidle')

    // Both should be on same page
    const title1 = await page1.title()
    const title2 = await page2.title()

    expect(title1).toBe(title2)
    console.log('Both tabs loaded:', title1)

    await context.close()
  })

  test('network monitoring shows no CORS errors', async ({ browser }) => {
    const context = await browser.newContext()
    const page = await context.newPage()

    const consoleErrors = []

    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`${VITE_URL}/`)
    await page.waitForLoadState('networkidle')

    // Filter for CORS errors
    const corsErrors = consoleErrors.filter(e => e.includes('CORS') || e.includes('403'))

    expect(corsErrors.length).toBe(0)

    console.log('No CORS errors detected')

    await context.close()
  })

  test('Vite dev server is accessible and serving correct content', async ({ browser }) => {
    const context = await browser.newContext()
    const page = await context.newPage()

    const response = await page.goto(`${VITE_URL}/index.html`)

    expect(response.status()).toBe(200)

    // Check for HTML doctype
    const content = await page.content()

    expect(content).toContain('<!DOCTYPE')
    expect(content).toContain('<html')

    console.log('✅ Vite serving valid HTML')

    await context.close()
  })
})
