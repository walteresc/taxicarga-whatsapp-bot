import { chromium } from '@playwright/test';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    console.log('[TEST] GATE 3 - API + Visual verification');
    
    // Auth
    console.log('[AUTH] Login...');
    await page.goto('http://localhost:5177/dashboard/login/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.fill('input[name="username"]', 'e2e_test');
    await page.fill('input[name="password"]', 'e2e_test_pass');
    await page.click('button[type="submit"]');
    await page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {});
    
    // Navigate to bandeja
    console.log('[PAGE] Loading bandeja-entrada...');
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded', timeout: 30000 });
    
    // Intercept API calls
    const apiCalls = [];
    page.on('response', resp => {
      if (resp.url().includes('/api/active/')) {
        resp.json().then(data => {
          console.log(`[API] Response: ${resp.status()} - Conversations: ${data.conversations?.length || 0}`);
          apiCalls.push({ status: resp.status(), convs: data.conversations?.length || 0 });
        }).catch(() => {});
      }
    });
    
    // Wait for page load + API call
    await page.waitForTimeout(5000);
    
    // Check DOM
    const convItems = await page.locator('[data-testid="conversation-item"], .conversation-item').count().catch(() => 0);
    console.log(`[DOM] Conversation items visible: ${convItems}`);
    
    // Screenshot
    await page.screenshot({ path: 'test-results/gate3-api-test.png' });
    console.log('[SCREENSHOT] gate3-api-test.png');
    
    // Result
    if (apiCalls.length > 0) {
      console.log('[RESULT] API called successfully');
    } else {
      console.log('[RESULT] API not called');
    }

  } catch (error) {
    console.error('[ERROR]', error.message);
  } finally {
    await browser.close();
  }
})();
