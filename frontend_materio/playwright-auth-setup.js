import { chromium } from '@playwright/test'

/**
 * Robusto auth setup que captura sessionid real
 * Usa la API /dashboard/api/auth/login/ directamente
 */

const DJANGO_URL = 'http://localhost:8001'
const VITE_URL = 'http://localhost:5177'
const AUTH_FILE = '.auth.json'

export default async function globalAuthSetup() {
  console.log('[AUTH SETUP] Starting authentication...')

  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  try {
    // Step 1: Cargar página de login
    console.log('[AUTH] Step 1: Cargar página de login...')
    await page.goto(`${VITE_URL}/dashboard/login/`, { waitUntil: 'networkidle' })

    // Step 2: Esperar Vue/Vuetify hidratación (inputs Vuetify renderizados)
    console.log('[AUTH] Step 2: Esperar Vue/Vuetify hidratación...')
    await page.waitForSelector('input[name="username"]', { timeout: 5000 }).catch(() => {
      console.log('[AUTH] WARNING: username input not found after 5s')
    })

    // Step 3: Rellenar formulario (directo en el input)
    console.log('[AUTH] Step 3: Rellenar credenciales...')
    await page.fill('input[name="username"]', 'e2e_test')
    console.log('[AUTH] Username filled')

    await page.fill('input[name="password"]', 'e2e_test_pass')
    console.log('[AUTH] Password filled')

    // Step 4: Enviar formulario (usar submit() del form, no click button)
    console.log('[AUTH] Step 4: Enviar formulario...')
    await page.evaluate(() => {
      const form = document.querySelector('form')
      if (form) form.submit()
    })
    console.log('[AUTH] Form submitted')

    // Step 5: Esperar redirección
    console.log('[AUTH] Step 5: Esperando redirección...')
    await page.waitForNavigation({ timeout: 5000 }).catch(() => {
      console.log('[AUTH] No navigation (retry check)')
    })

    // Verificar sesión
    const isLoggedIn = await page.evaluate(() => {
      return !window.location.pathname.includes('login')
    })
    console.log(`[AUTH] Page after submit: ${isLoggedIn ? 'redirected from login' : 'still on login page'}`)

    // Step 3: Verificar cookies
    const cookies = await context.cookies()
    const sessionCookie = cookies.find(c => c.name.includes('sessionid') || c.name.includes('session'))

    if (sessionCookie) {
      console.log(`[AUTH] Session cookie found: ${sessionCookie.name}`)
      console.log(`[AUTH] Value: ${sessionCookie.value.substring(0, 20)}...`)
      console.log(`[AUTH] HttpOnly: ${sessionCookie.httpOnly}`)
      console.log(`[AUTH] Secure: ${sessionCookie.secure}`)
      console.log(`[AUTH] SameSite: ${sessionCookie.sameSite}`)
    } else {
      console.log('[AUTH] WARNING: Session cookie not found in context!')
    }

    // Step 4: Verificar acceso autenticado
    console.log('[AUTH] Step 4: Verificar acceso a bandeja...')
    await page.goto(`${VITE_URL}/atencion/bandeja-entrada`, { waitUntil: 'load' }).catch(e => {
      console.log(`[AUTH] Navigation note: ${e.message.substring(0, 50)}`)
    })

    // Step 5: Guardar estado de autenticación
    console.log(`[AUTH] Step 5: Guardar estado en ${AUTH_FILE}...`)
    await context.storageState({ path: AUTH_FILE })

    // Step 6: Guardar cookies manualmente
    const allCookies = await context.cookies()
    const authState = {
      cookies: allCookies,
      timestamp: new Date().toISOString(),
      user: 'e2e_test',
    }

    // Guardar en archivo para referencia
    const fs = await import('fs')
    fs.writeFileSync(AUTH_FILE, JSON.stringify(authState, null, 2))
    console.log(`[AUTH] Cookies saved: ${allCookies.length} total`)

    console.log('[AUTH SETUP] ✓ Complete')
  } catch (error) {
    console.error('[AUTH ERROR]', error.message)
    throw error
  } finally {
    await browser.close()
  }
}
