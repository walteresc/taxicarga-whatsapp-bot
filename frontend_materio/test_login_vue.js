import { chromium } from 'playwright'

async function testLogin() {
  const browser = await chromium.launch()
  const page = await browser.newPage()

  // Enable logging
  page.on('console', msg => console.log(`[${msg.type()}] ${msg.text()}`))
  page.on('response', res => {
    if (res.status() >= 400) {
      console.log(`[HTTP ${res.status()}] ${res.url()}`)
    }
  })

  console.log('\n=== OPENING http://localhost:8001/login ===')
  await page.goto('http://localhost:8001/login')

  console.log('\n=== WAITING FOR FORM ===')
  await page.waitForSelector('input[type="text"], input[name*="username"], input[name*="user"]', { timeout: 10000 })

  console.log('\n=== FILLING CREDENTIALS ===')

  const usernameField = await page.$('input[type="text"], input[name*="username"], input[type="email"]')
  const passwordField = await page.$('input[type="password"]')

  if (usernameField && passwordField) {
    await usernameField.fill('testadmin')
    await passwordField.fill('testpass123')
    console.log('✓ Credentials entered')
  } else {
    console.log('✗ Could not find form fields')
    await page.screenshot({ path: 'test_login_form_not_found.png' })
    await browser.close()
    
    return
  }

  console.log('\n=== SUBMITTING ===')

  const submitBtn = await page.$('button[type="submit"], button:has-text("Iniciar sesión"), button:has-text("Sign in"), button:has-text("Login")')
  if (submitBtn) {
    await submitBtn.click()
  } else {
    console.log('✗ Could not find submit button')
  }

  console.log('\n=== WAITING FOR REDIRECT ===')
  try {
    await page.waitForURL('**/atencion/bandeja-entrada', { timeout: 10000 })
    console.log('✓ Redirected to bandeja-entrada')
  } catch (e) {
    console.log(`✗ Did not redirect: ${e.message}`)
    console.log(`Current URL: ${page.url()}`)
  }

  console.log('\n=== CHECKING SESSION ===')

  const cookies = await page.context().cookies()
  const sessionCookie = cookies.find(c => c.name === 'sessionid')
  if (sessionCookie) {
    console.log(`✓ sessionid cookie present`)
  } else {
    console.log(`✗ No sessionid cookie`)
  }

  console.log('\n=== CHECKING BANDEJA ===')

  const conversationRows = await page.$$('tr, [role="row"], .conversation, [data-testid*="conversation"]')

  console.log(`Found ${conversationRows.length} conversation elements`)

  console.log('\n=== SCREENSHOT ===')
  await page.screenshot({ path: 'test_login_final.png' })

  await browser.close()
}

testLogin().catch(console.error)
