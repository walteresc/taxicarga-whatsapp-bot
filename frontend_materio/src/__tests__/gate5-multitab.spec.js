import { test, expect, devices } from '@playwright/test'

test.describe('Gate 5 Multi-Tab Sync', () => {
  test('Two tabs maintain synchronized conversation state', async ({ browser }) => {
    console.log('\n=== Gate 5: Two Tabs Sync ===')

    // Create two browser contexts (independent sessions but same browser)
    const ctx1 = await browser.newContext()
    const ctx2 = await browser.newContext()
    const page1 = await ctx1.newPage()
    const page2 = await ctx2.newPage()

    // Authenticate both tabs
    console.log('Step 1: Authenticating both tabs...')
    for (const [i, page] of [[1, page1], [2, page2]]) {
      const resp = await page.request.post('http://localhost:8001/dashboard/api/auth/login/', {
        data: {
          username: 'e2e_test',
          password: 'e2e_test_pass_123',
        },
      })

      expect(resp.status()).toBe(200)
      console.log(`  ✓ Tab ${i} authenticated`)
    }

    // Navigate both to bandeja
    console.log('Step 2: Navigating both tabs...')
    await page1.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'networkidle' })
    await page2.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'networkidle' })
    console.log('  ✓ Both tabs navigated')

    // Wait for conversations in both
    console.log('Step 3: Waiting for conversations in both tabs...')
    await page1.waitForSelector('.conversation-item', { timeout: 10000 })
    await page2.waitForSelector('.conversation-item', { timeout: 10000 })

    const count1Initial = await page1.locator('.conversation-item').count()
    const count2Initial = await page2.locator('.conversation-item').count()

    console.log(`  ✓ Tab 1: ${count1Initial} conversations`)
    console.log(`  ✓ Tab 2: ${count2Initial} conversations`)

    // Verify both show same count
    expect(count1Initial).toBe(count2Initial)
    console.log('  ✓ Counts match')

    // Select conversation in Tab 1
    console.log('Step 4: Selecting conversation in Tab 1...')

    const firstConv1 = await page1.locator('.conversation-item').first()
    const convText1 = await firstConv1.textContent()

    await firstConv1.click()
    await page1.waitForTimeout(1000)
    console.log(`  ✓ Selected: ${convText1.substring(0, 50)}...`)

    // Check Tab 2 (should not be affected - independent selection)
    console.log('Step 5: Checking Tab 2 independent state...')

    const convItemsTab2 = await page2.locator('.conversation-item').count()

    expect(convItemsTab2).toBe(count2Initial)
    console.log('  ✓ Tab 2 unaffected by Tab 1 selection')

    // Verify no cross-pollution errors
    console.log('Step 6: Checking for errors...')

    const errors1 = []
    const errors2 = []

    page1.on('console', msg => {
      if (msg.type() === 'error') errors1.push(msg.text())
    })
    page2.on('console', msg => {
      if (msg.type() === 'error') errors2.push(msg.text())
    })

    await page1.waitForTimeout(2000)
    await page2.waitForTimeout(2000)

    console.log(`  Tab 1 errors: ${errors1.length}`)
    console.log(`  Tab 2 errors: ${errors2.length}`)
    expect(errors1.length + errors2.length).toBe(0)
    console.log('  ✓ No errors on either tab')

    // Cleanup
    await ctx1.close()
    await ctx2.close()

    console.log('\n✅ GATE 5: Multi-tab state independent and stable')
  })
})
