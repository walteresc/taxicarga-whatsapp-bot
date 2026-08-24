import { chromium } from '@playwright/test'

const authFile = 'auth.json'

export default async function globalSetup() {
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  console.log('[SETUP] Logging in to get authenticated session...')

  // Navigate to login page
  await page.goto('http://localhost:5177/dashboard/login/')
  await page.waitForLoadState('domcontentloaded')

  // Look for login form fields
  const usernameField = page.locator('input[name="username"], input[type="text"]').first()
  const passwordField = page.locator('input[name="password"], input[type="password"]').first()
  const submitButton = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Iniciar")').first()

  // Fill credentials
  await usernameField.fill('e2e_test')
  console.log('[SETUP] Username entered')

  await passwordField.fill('e2e_test_pass')
  console.log('[SETUP] Password entered')

  // Submit form
  await submitButton.click()
  console.log('[SETUP] Form submitted')

  // Wait for redirect - should go to bandeja or dashboard
  await page.waitForNavigation({ waitUntil: 'networkidle' }).catch(() => {
    console.log('[SETUP] No navigation detected (may already be logged in)')
  })

  // Verify we're logged in by checking for logout link or dashboard content
  const isLoggedIn = await page.locator('text="Logout", text="Cerrar sesion", text="bandeja"').first().isVisible().catch(() => false)
  console.log(`[SETUP] Logged in: ${isLoggedIn ? 'YES' : 'checking...'}`)

  // Navigate to bandeja to ensure session is set
  await page.goto('http://localhost:5177/atencion/bandeja-entrada')
  await page.waitForLoadState('networkidle')

  // Save authentication state
  await context.storageState({ path: authFile })
  console.log(`[SETUP] Session saved to ${authFile}`)

  // Verify sessionid cookie exists
  const cookies = await context.cookies()
  const sessionCookie = cookies.find(c => c.name.includes('session') || c.name.includes('sessionid'))
  if (sessionCookie) {
    console.log(`[SETUP] Session cookie: ${sessionCookie.name}=${sessionCookie.value.substring(0, 20)}...`)
  } else {
    console.log('[SETUP] WARNING: No session cookie found')
  }

  await browser.close()
  console.log('[SETUP] Complete')
}
