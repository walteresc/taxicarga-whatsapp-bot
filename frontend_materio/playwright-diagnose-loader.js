import { chromium } from 'playwright'
import fs from 'fs'

const results = {
  console: [],
  errors: [],
  requests: [],
  screenshots: [],
}

async function diagnose() {
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  // Capture all console messages
  page.on('console', msg => {
    results.console.push({
      type: msg.type(),
      text: msg.text(),
      args: msg.args().length,
      timestamp: new Date().toISOString(),
    })
    console.log(`[${msg.type()}] ${msg.text()}`)
  })

  // Capture page errors
  page.on('pageerror', err => {
    results.errors.push({
      message: err.message,
      stack: err.stack?.split('\n').slice(0, 3),
      timestamp: new Date().toISOString(),
    })
    console.error('[PAGE_ERROR]', err.message)
  })

  // Capture failed requests
  page.on('requestfailed', req => {
    results.requests.push({
      url: req.url(),
      failure: req.failure()?.errorText,
      method: req.method(),
      timestamp: new Date().toISOString(),
    })
    console.error('[FAILED_REQUEST]', req.url(), req.failure()?.errorText)
  })

  // Capture all responses
  page.on('response', res => {
    if (res.status() >= 400) {
      results.requests.push({
        url: res.url(),
        status: res.status(),
        contentType: res.headers()['content-type'],
        method: res.request().method(),
        timestamp: new Date().toISOString(),
      })
      console.warn(`[HTTP ${res.status()}]`, res.url())
    }
  })

  console.log('\n=== OPENING http://localhost:8001/login ===\n')
  const startTime = Date.now()

  try {
    await page.goto('http://localhost:8001/login', { waitUntil: 'networkidle' })
  } catch (e) {
    console.warn('Navigation timeout (networkidle):', e.message)
  }

  console.log('\n=== WAITING 3 SECONDS ===\n')
  await page.waitForTimeout(3000)

  // Screenshot at 3s
  let html = await page.content()
  results.screenshots.push({
    time: '3s',
    hasLoader: html.includes('loading-bg') || html.includes('loader'),
    hasLoginForm: html.includes('Iniciar sesión'),
  })

  if (html.includes('loading-bg')) {
    console.log('[3s] Still showing loader')
    await page.screenshot({ path: '/tmp/loader-3s.png' })
  }

  console.log('\n=== WAITING 10 SECONDS ===\n')
  await page.waitForTimeout(7000)

  html = await page.content()
  results.screenshots.push({
    time: '10s',
    hasLoader: html.includes('loading-bg') || html.includes('loader'),
    hasLoginForm: html.includes('Iniciar sesión'),
  })

  if (html.includes('loading-bg')) {
    console.log('[10s] Still showing loader - FAIL')
    await page.screenshot({ path: '/tmp/loader-10s.png' })
  } else {
    console.log('[10s] Login form appeared - PASS')
  }

  console.log('\n=== CHECKING NETWORK ===\n')
  const requests = page.context().storageState?.cookies || []

  // Get all pending requests (we can't directly, but check sessionStorage)
  try {
    const sessionData = await page.evaluate(() => ({
      localStorage: Object.keys(localStorage),
      sessionStorage: Object.keys(sessionStorage),
    }))
    console.log('Storage:', sessionData)
  } catch (e) {
    console.warn('Could not read storage:', e.message)
  }

  console.log('\n=== RESULTS ===\n')
  console.log('Console messages:', results.console.length)
  console.log('Page errors:', results.errors.length)
  console.log('Failed requests:', results.requests.filter(r => r.failure).length)
  console.log('HTTP >=400:', results.requests.filter(r => r.status >= 400).length)
  console.log('Screenshots:', results.screenshots)

  if (results.errors.length > 0) {
    console.log('\n[ERRORS]')
    results.errors.forEach(e => console.log('  -', e.message))
  }

  if (results.requests.filter(r => r.status >= 400).length > 0) {
    console.log('\n[HTTP ERRORS]')
    results.requests.filter(r => r.status >= 400).forEach(r => {
      console.log(`  - ${r.status} ${r.url}`)
    })
  }

  await browser.close()

  // Write report
  fs.writeFileSync('/tmp/playwright-diagnose.json', JSON.stringify(results, null, 2))
  console.log('\nFull report: /tmp/playwright-diagnose.json')
}

diagnose().catch(console.error)
