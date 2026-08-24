// Direct Playwright test without test framework
import { chromium } from '@playwright/test';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    console.log('[TEST] Starting GATE 3/4 visual tests');

    // Navigate to login
    console.log('[AUTH] Going to login page...');
    await page.goto('http://localhost:5177/dashboard/login/', { waitUntil: 'domcontentloaded', timeout: 30000 });

    // Login
    await page.fill('input[name="username"]', 'e2e_test');
    await page.fill('input[name="password"]', 'e2e_test_pass');
    await page.click('button[type="submit"]');

    // Wait for navigation
    await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});

    // Go to bandeja
    console.log('[PAGE] Going to bandeja-entrada...');
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded', timeout: 30000 });

    // Wait for container
    console.log('[PAGE] Waiting for page to render...');
    await page.waitForSelector('.main-container, [data-testid="conversation-list"], .bandeja-page', { timeout: 15000 }).catch(() => {
      console.log('[PAGE] Selector not found, but continuing');
    });

    await page.waitForTimeout(2000);

    // Screenshot before webhook
    await page.screenshot({ path: 'test-results/gate3-before-webhook.png' });
    console.log('[SCREENSHOT] gate3-before-webhook.png');

    // Get initial message count
    const countBefore = await page.locator('[data-testid="message-item"], .message-item').count().catch(() => 0);
    console.log(`[VISUAL] Messages before webhook: ${countBefore}`);

    // Send inbound webhook (via separate context with proper signature)
    console.log('[WEBHOOK] Sending inbound message...');
    const testId = `GATE3-${Date.now()}`;
    const testPhone = `+5191${Math.floor(Math.random() * 1000000)}`;

    const payload = {
      id: `evt_${testId}`,
      type: 'whatsapp.inbound_message.received',
      whatsappInboundMessage: {
        id: `wamid_${testId}`,
        from: testPhone,
        to: '+51967619238',
        text: { body: `Test: ${testId}` }
      }
    };

    // Use browser context directly (not page context) to avoid session issues
    const freshContext = await browser.newContext();
    const freshPage = await freshContext.newPage();

    const response = await freshPage.context().request.post('http://localhost:8001/webhooks/ycloud/v1/', {
      data: JSON.stringify(payload),
      headers: {
        'Content-Type': 'application/json',
        'X-YCloud-Signature': 't=test_secret_e2e,s=test'  // E2E secret
      }
    });

    await freshContext.close();
    console.log(`[WEBHOOK] Response: ${response.status()}`);

    // Wait for message to appear
    console.log('[VISUAL] Waiting for message in DOM...');
    try {
      await page.waitForSelector(`text="${testId}"`, { timeout: 10000 });
      console.log('[PASS] Message appeared without F5');
    } catch (e) {
      console.log('[FAIL] Message did NOT appear after 10s');
    }

    // Screenshot after webhook
    await page.screenshot({ path: 'test-results/gate3-after-webhook.png' });
    console.log('[SCREENSHOT] gate3-after-webhook.png');

    // Count final
    const countAfter = await page.locator('[data-testid="message-item"], .message-item').count().catch(() => 0);
    console.log(`[VISUAL] Messages after webhook: ${countAfter}`);
    console.log(`[VISUAL] Change: ${countAfter - countBefore} new messages`);

    console.log('\n[TEST] GATE 3/4 visual test complete');

  } catch (error) {
    console.error('[ERROR]', error.message);
  } finally {
    await browser.close();
  }
})();
