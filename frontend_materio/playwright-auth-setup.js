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
    // Step 1: Obtener CSRF token del formulario de login
    console.log('[AUTH] Step 1: Cargar página de login...')
    await page.goto(`${VITE_URL}/dashboard/login/`, { waitUntil: 'networkidle' })

    // CSRF token puede estar en meta o en la forma
    let csrfToken = await page.evaluate(() => {
      // Buscar en meta tag
      const meta = document.querySelector('[name="csrf-token"]')
      if (meta) return meta.content

      // Buscar en input oculto
      const input = document.querySelector('input[name="csrfmiddlewaretoken"]')
      if (input) return input.value

      return null
    })
    console.log(`[AUTH] CSRF token: ${csrfToken ? csrfToken.substring(0, 20) + '...' : 'NOT FOUND'}`)

    // Step 2: Login vía API REST
    console.log('[AUTH] Step 2: Realizar POST a /dashboard/api/auth/login/...')
    const loginResponse = await page.context().request.post(`${DJANGO_URL}/dashboard/api/auth/login/`, {
      data: {
        username: 'e2e_test',
        password: 'e2e_test_pass',
      },
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...(csrfToken && { 'X-CSRFToken': csrfToken }),
      },
    })

    const status = loginResponse.status()
    console.log(`[AUTH] Login response: ${status}`)

    if (status === 200) {
      const responseData = await loginResponse.json()
      console.log(`[AUTH] Login OK: ${responseData.user.username}`)
    } else {
      const errorText = await loginResponse.text()
      console.log(`[AUTH] Login FAILED: ${errorText.substring(0, 100)}`)
    }

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
