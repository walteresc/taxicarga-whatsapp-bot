import { test, expect } from '@playwright/test'

test.describe('Gate 3 Diagnostic', () => {
  test('Check ConversationList component rendering', async ({ page }) => {
    console.log('\n=== Gate 3 Diagnostic Start ===')

    // Step 1: Authenticate
    console.log('Step 1: Authenticating...')
    try {
      const loginResponse = await page.request.post('http://localhost:8001/dashboard/api/auth/login/', {
        data: {
          username: 'e2e_test',
          password: 'e2e_test_pass_123',
        },
      })

      const loginData = await loginResponse.json()

      console.log(`Login response status: ${loginResponse.status()}`)
      console.log(`Login response: ${JSON.stringify(loginData).substring(0, 100)}`)

      if (loginResponse.status() !== 200) {
        throw new Error(`Login failed with status ${loginResponse.status()}`)
      }
    } catch (err) {
      console.log(`⚠ Login attempt failed: ${err.message}`)
      console.log('Will attempt to navigate without explicit auth (relying on cookies)')
    }

    // Navigate to bandeja-entrada
    console.log('\nStep 2: Navigating to http://localhost:5177/atencion/bandeja-entrada')
    try {
      await page.goto('http://localhost:5177/atencion/bandeja-entrada', {
        waitUntil: 'networkidle',
        timeout: 30000,
      })
      console.log('✓ Page navigation successful')
    } catch (err) {
      console.log(`✗ Navigation error: ${err.message}`)
      throw err
    }

    // Check current URL and auth status
    const currentUrl = page.url()

    console.log(`Current URL: ${currentUrl}`)

    if (currentUrl.includes('/login')) {
      console.log('✗ Redirected to login page - authentication required')
      throw new Error('Page requires authentication. Run tests with valid session.')
    }

    // Wait for component root with diagnostics
    console.log('Waiting for [data-testid="conversation-list-root"]...')
    try {
      await page.waitForSelector('[data-testid="conversation-list-root"]', { timeout: 8000 })
      console.log('✓ Found conversation-list-root')
    } catch (err) {
      console.log('✗ Timeout waiting for conversation-list-root')

      // Diagnostic checks
      console.log('\nDiagnostic checks:')

      const bodyHTML = await page.content()

      console.log(`Page HTML length: ${bodyHTML.length} chars`)
      console.log(`Contains "conversation-list-root": ${bodyHTML.includes('conversation-list-root')}`)
      console.log(`Contains "conversation-sidebar": ${bodyHTML.includes('conversation-sidebar')}`)

      // Get page structure
      const rootCount = await page.locator('div[data-testid="conversation-list-root"]').count()
      const sidebarCount = await page.locator('.conversation-sidebar').count()
      const anyConv = await page.locator('[class*="conversation"]').count()

      console.log(`Found data-testid="conversation-list-root": ${rootCount}`)
      console.log(`Found .conversation-sidebar: ${sidebarCount}`)
      console.log(`Found elements with "conversation" in class: ${anyConv}`)

      throw err
    }

    // Get diagnostic info
    const rootElement = page.locator('[data-testid="conversation-list-root"]')
    const instanceId = await rootElement.getAttribute('data-component-instance')
    const sourceCount = await rootElement.getAttribute('data-source-count')
    const filteredCount = await rootElement.getAttribute('data-filtered-count')

    console.log('\n=== ConversationList Diagnostic ===')
    console.log(`Instance ID: ${instanceId}`)
    console.log(`Source count (conversations.length): ${sourceCount}`)
    console.log(`Filtered count (filteredConversations.length): ${filteredCount}`)

    // Check diagnostic counter
    const diagnosticCounter = page.locator('[data-testid="diagnostic-count"]')
    const counterText = await diagnosticCounter.textContent()

    console.log(`Diagnostic counter shows: ${counterText}`)

    // Check diagnostic list items
    const diagnosticItems = page.locator('[data-testid="diagnostic-item"]')
    const itemCount = await diagnosticItems.count()

    console.log(`Diagnostic list items: ${itemCount}`)

    if (itemCount > 0) {
      console.log('First diagnostic items:')
      for (let i = 0; i < Math.min(3, itemCount); i++) {
        const text = await diagnosticItems.nth(i).textContent()

        console.log(`  [${i}]: ${text}`)
      }
    }

    // Check actual conversation items (from template v-for)
    const conversationItems = page.locator('[data-testid="conversation-item"], .conversation-item')
    const actualItemCount = await conversationItems.count()

    console.log(`Actual conversation items rendered: ${actualItemCount}`)

    // Get page state
    const pageState = await page.evaluate(() => {
      const root = document.querySelector('[data-testid="conversation-list-root"]')
      
      return {
        rootExists: !!root,
        rootHTML: root ? root.innerHTML.substring(0, 500) : 'NOT FOUND',
        bodyClasses: document.body.className,
        rootClasses: root ? root.className : 'N/A',
      }
    })

    console.log('\nPage State:')
    console.log(`Root exists: ${pageState.rootExists}`)
    console.log(`Root classes: ${pageState.rootClasses}`)

    // Check for any error states or empty states
    const emptyStates = page.locator('[class*="empty"]')
    const emptyCount = await emptyStates.count()
    if (emptyCount > 0) {
      console.log(`\nEmpty states found: ${emptyCount}`)
      for (let i = 0; i < Math.min(2, emptyCount); i++) {
        const text = await emptyStates.nth(i).textContent()

        console.log(`  Empty[${i}]: ${text}`)
      }
    }

    // Check console errors
    const errors = []

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    // Final summary
    console.log('\n=== Summary ===')
    console.log(`Diagnostic shows: ${sourceCount} source / ${filteredCount} filtered`)
    console.log(`DOM shows: ${actualItemCount} actual conversation items`)
    console.log(`Match: ${sourceCount === '0' && filteredCount === '0' ? 'EMPTY' : sourceCount && filteredCount ? 'DATA LOADED' : 'MISMATCH'}`)

    // Report findings
    if (sourceCount === '0' && filteredCount === '0') {
      console.log('\n❌ GATE 3 BLOCKER: API data not loaded')
    } else if (sourceCount !== '0' && actualItemCount === '0') {
      console.log('\n❌ GATE 3 BLOCKER: Data loaded but template not rendering')
      console.log(`  Source: ${sourceCount}, Filtered: ${filteredCount}, Rendered: ${actualItemCount}`)
    } else {
      console.log('\n✅ GATE 3: Data loading and rendering correctly')
    }
  })
})
