import { chromium } from '@playwright/test';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const logs = [];
  const errors = [];
  
  page.on('console', msg => {
    const text = `[${msg.type()}] ${msg.text()}`;
    console.log(text);
    logs.push(text);
    if (msg.type() === 'error') errors.push(msg.text());
  });
  
  page.on('pageerror', err => {
    const text = `[pageerror] ${err.message}`;
    console.log(text);
    errors.push(text);
  });

  try {
    console.log('[TEST] Console + Error capture');
    
    // Auth
    await page.goto('http://localhost:5177/dashboard/login/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.fill('input[name="username"]', 'e2e_test');
    await page.fill('input[name="password"]', 'e2e_test_pass');
    await page.click('button[type="submit"]');
    await page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {});
    
    // Load bandeja
    console.log('\n[PAGE] Navigating to bandeja-entrada...');
    await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'domcontentloaded', timeout: 30000 });
    
    // Wait for data load
    await page.waitForTimeout(6000);
    
    // Check state
    const convCount = await page.evaluate(() => {
      return document.querySelectorAll('[data-testid="conversation-item"], .conversation-item').length;
    }).catch(() => 0);
    
    console.log(`\n[DOM] Conversation items: ${convCount}`);
    console.log(`[LOGS] Total console messages: ${logs.length}`);
    console.log(`[ERRORS] Total errors: ${errors.length}`);
    
    if (errors.length > 0) {
      console.log('\n[ERRORS CAPTURED]:');
      errors.forEach(e => console.log(`  - ${e}`));
    }

  } catch (error) {
    console.error('[ERROR]', error.message);
  } finally {
    await browser.close();
  }
})();
