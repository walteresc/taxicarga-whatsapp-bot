import { chromium } from '@playwright/test'

const VITE_URL = 'http://localhost:5177'
const DJANGO_URL = 'http://localhost:8001'

export default async function globalAuthSetup() {
  console.log('[SETUP] Auth debug - instrumentar requests/responses/logs\n')

  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  // Arrays para capturar eventos
  const requests = []
  const responses = []
  const consoleLogs = []
  const pageErrors = []
  const failedRequests = []

  // Instrumentar
  page.on('request', req => {
    const url = req.url()
    const method = req.method()

    requests.push({ method, url, timestamp: new Date().toISOString() })
    console.log(`[REQ] ${method} ${url.replace(DJANGO_URL, '').replace(VITE_URL, '')}`)
  })

  page.on('response', res => {
    const url = res.url()
    const status = res.status()
    const headers = res.headers()

    responses.push({
      url,
      status,
      headers: { 'content-type': headers['content-type'] || '' },
      timestamp: new Date().toISOString(),
      hasCookie: 'set-cookie' in headers || false,
    })
    console.log(`[RES] ${status} ${url.replace(DJANGO_URL, '').replace(VITE_URL, '')}`)
  })

  page.on('requestfailed', req => {
    failedRequests.push({ url: req.url(), failure: req.failure().errorText })
    console.log(`[FAIL] ${req.url().replace(DJANGO_URL, '')} - ${req.failure().errorText}`)
  })

  page.on('console', msg => {
    const text = msg.text()

    consoleLogs.push(text)
    console.log(`[CONSOLE] ${text}`)
  })

  page.on('pageerror', err => {
    pageErrors.push(err.message)
    console.log(`[ERROR] ${err.message}`)
  })

  try {
    // Step 1: Cargar login
    console.log('\n[1] Navegando a /dashboard/login/\n')
    await page.goto(`${VITE_URL}/dashboard/login/`, { waitUntil: 'networkidle' })

    // Step 2: Esperar hidratación Vue
    console.log('\n[2] Esperando hidratación Vue\n')
    await page.waitForSelector('input[name="username"]', { timeout: 5000 }).catch(() => {
      console.log('[WARN] Username input no encontrado\n')
    })

    // Step 3: Rellenar form
    console.log('\n[3] Rellenando formulario\n')
    await page.fill('input[name="username"]', 'e2e_test')
    await page.fill('input[name="password"]', 'e2e_test_pass')
    console.log('[OK] Username + password filled\n')

    // Step 4: Capturar referencias antes de submit
    const csrfField = await page.evaluate(() => {
      const token = document.querySelector('input[name="csrfmiddlewaretoken"]')
      
      return token ? 'csrf_present' : 'csrf_missing'
    })

    console.log(`[CSRF] ${csrfField}\n`)

    // Step 5: Intentar submit
    console.log('[4] Ejecutando form.submit()\n')

    const urlBefore = page.url()

    console.log(`[URL_BEFORE] ${urlBefore}\n`)

    await page.evaluate(() => {
      const form = document.querySelector('form')
      if (form) {
        console.log('[JS] Form found, submitting...')
        form.submit()
      } else {
        console.log('[JS] ERROR: Form not found!')
      }
    })

    // Esperar a que pase algo
    console.log('\n[5] Esperando respuesta (5s max)\n')
    await new Promise(resolve => setTimeout(resolve, 2000))

    const urlAfter = page.url()

    console.log(`[URL_AFTER] ${urlAfter}\n`)
    console.log(`[URL_CHANGED] ${urlBefore !== urlAfter ? 'SI' : 'NO'}\n`)

    // Step 6: Verificar cookies
    console.log('[6] Verificando cookies\n')

    const cookies = await context.cookies()
    const cookieNames = cookies.map(c => c.name)

    console.log(`[COOKIES] ${cookieNames.join(', ')}\n`)

    const sessionCookie = cookies.find(c => c.name.includes('sessionid'))
    if (sessionCookie) {
      console.log(`[SESSION] Presente (${sessionCookie.name})\n`)
    } else {
      console.log(`[SESSION] AUSENTE\n`)
    }

    // Step 7: Resumen de requests
    console.log('\n[RESUMEN]\n')
    console.log(`Total requests: ${requests.length}`)

    const postRequests = requests.filter(r => r.method === 'POST')

    console.log(`POST requests: ${postRequests.length}`)
    postRequests.forEach(r => {
      console.log(`  - ${r.url.replace(DJANGO_URL, '').replace(VITE_URL, '')}`)
    })

    console.log(`\nConsole logs: ${consoleLogs.length}`)
    consoleLogs.slice(-5).forEach(l => console.log(`  - ${l}`))

    console.log(`\nPage errors: ${pageErrors.length}`)
    pageErrors.forEach(e => console.log(`  - ${e}`))

    // Step 8: Guardar state
    console.log('\n[7] Guardando storageState\n')
    await context.storageState({ path: '.auth.json' })
    console.log('[OK] State saved to .auth.json\n')

    console.log('[SETUP] Debug complete\n')
  } catch (error) {
    console.error('[SETUP ERROR]', error.message)
    throw error
  } finally {
    await browser.close()
  }
}
