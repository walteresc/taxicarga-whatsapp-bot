# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e-visual-bandeja.spec.js >> E2E Visual: Bandeja-Entrada Real UI >> 3. Inbound local without F5: conversación aparece
- Location: src\__tests__\e2e-visual-bandeja.spec.js:43:3

# Error details

```
Test timeout of 120000ms exceeded while running "beforeEach" hook.
```

```
Error: page.goto: Target page, context or browser has been closed
```

# Page snapshot

```yaml
- generic [active] [ref=f1e1]:
  - generic [ref=f1e2]:
    - heading "Prohibido (403)" [level=1] [ref=f1e3]
    - paragraph [ref=f1e4]: La verificación CSRF ha fallado. Solicitud abortada.
  - generic [ref=f1e5]:
    - heading "Help" [level=2] [ref=f1e6]
    - paragraph [ref=f1e7]: "Reason given for failure:"
    - generic [ref=f1e8]: Origin checking failed - http://localhost:5177 does not match any trusted origins.
    - paragraph [ref=f1e9]:
      - text: In general, this can occur when there is a genuine Cross Site Request Forgery, or when
      - link "Django’s CSRF mechanism" [ref=f1e10] [cursor=pointer]:
        - /url: https://docs.djangoproject.com/en/6.0/ref/csrf/
      - text: "has not been used correctly. For POST forms, you need to ensure:"
    - list [ref=f1e11]:
      - listitem [ref=f1e12]: Your browser is accepting cookies.
      - listitem [ref=f1e13]:
        - text: The view function passes a
        - code [ref=f1e14]: request
        - text: to the template’s
        - link [ref=f1e15] [cursor=pointer]:
          - /url: https://docs.djangoproject.com/en/6.0/topics/templates/#django.template.backends.base.Template.render
          - code [ref=f1e16]: render
        - text: method.
      - listitem [ref=f1e17]:
        - text: In the template, there is a
        - code [ref=f1e18]: "{% csrf_token %}"
        - text: template tag inside each POST form that targets an internal URL.
      - listitem [ref=f1e19]:
        - text: If you are not using
        - code [ref=f1e20]: CsrfViewMiddleware
        - text: ", then you must use"
        - code [ref=f1e21]: csrf_protect
        - text: on any views that use the
        - code [ref=f1e22]: csrf_token
        - text: template tag, as well as those that accept the POST data.
      - listitem [ref=f1e23]: The form has a valid CSRF token. After logging in in another browser tab or hitting the back button after a login, you may need to reload the page with the form, because the token is rotated after a login.
    - paragraph [ref=f1e24]:
      - text: You’re seeing the help section of this page because you have
      - code [ref=f1e25]: DEBUG = True
      - text: in your Django settings file. Change that to
      - code [ref=f1e26]: "False"
      - text: ", and only the initial error message will be displayed."
    - paragraph [ref=f1e27]: You can customize this page using the CSRF_FAILURE_VIEW setting.
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test'
  2   | 
  3   | /**
  4   |  * E2E Visual Tests against real bandeja-entrada UI
  5   |  *
  6   |  * Tests inbound, echo, two tabs, fallback/reconnect, logout
  7   |  * All against actual DOM without mocking SSE/polling
  8   |  */
  9   | 
  10  | const VITE_URL = 'http://localhost:5177'
  11  | const WEBHOOK_URL = 'http://localhost:8001/webhook/whatsapp/'
  12  | 
  13  | test.describe.serial('E2E Visual: Bandeja-Entrada Real UI', () => {
  14  |   test.beforeEach(async ({ page }) => {
  15  |     // Load login page
  16  |     await page.goto(`${VITE_URL}/dashboard/login/`)
  17  |     await page.waitForLoadState('domcontentloaded')
  18  | 
  19  |     // Fill username
  20  |     await page.fill('input[name="username"]', 'e2e_test').catch(() => {
  21  |       console.log('[AUTH] Username field not found - may already be logged in')
  22  |     })
  23  | 
  24  |     // Fill password
  25  |     await page.fill('input[name="password"]', 'e2e_test_pass').catch(() => {
  26  |       console.log('[AUTH] Password field not found - may already be logged in')
  27  |     })
  28  | 
  29  |     // Submit form
  30  |     await page.click('button[type="submit"]').catch(() => {
  31  |       console.log('[AUTH] Submit button not found - skipping')
  32  |     })
  33  | 
  34  |     // Wait for redirect
  35  |     await page.waitForNavigation({ waitUntil: 'networkidle' }).catch(() => {})
  36  | 
  37  |     // Load bandeja-entrada
> 38  |     await page.goto(`${VITE_URL}/atencion/bandeja-entrada`)
      |                ^ Error: page.goto: Target page, context or browser has been closed
  39  |     await page.waitForLoadState('networkidle')
  40  |     console.log(`[PAGE] Loaded bandeja-entrada`)
  41  |   })
  42  | 
  43  |   test('3. Inbound local without F5: conversación aparece', async ({ page, context }) => {
  44  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  45  |     const testId = `INBOUND-${Date.now()}`
  46  | 
  47  |     // Capture initial conversation count
  48  |     const convsBefore = await page.locator('[class*="conversation"], [class*="bandeja"], [class*="item"]').count()
  49  |     console.log(`[VISUAL] Conversaciones iniciales: ${convsBefore}`)
  50  | 
  51  |     // Send webhook
  52  |     const payload = {
  53  |       object: 'whatsapp_business_account',
  54  |       entry: [{
  55  |         changes: [{
  56  |           value: {
  57  |             messaging_product: 'whatsapp',
  58  |             metadata: {
  59  |               phone_number_id: 'webhook-test',
  60  |               display_phone_number: '51967619238',
  61  |             },
  62  |             messages: [{
  63  |               from: testPhone,
  64  |               id: `wamid_${testId}`,
  65  |               timestamp: Math.floor(Date.now() / 1000).toString(),
  66  |               type: 'text',
  67  |               text: { body: `Test: ${testId}` },
  68  |             }],
  69  |           },
  70  |         }],
  71  |       }],
  72  |     }
  73  | 
  74  |     const res = await context.request.post(WEBHOOK_URL, { data: payload })
  75  |     console.log(`[WEBHOOK] Inbound POST -> ${res.status()}`)
  76  |     expect(res.status()).toBe(200)
  77  | 
  78  |     // Wait max 10s for UI update via SSE or polling
  79  |     const appeared = await page.locator('body').locator(`text="${testId}"`).first().waitFor({ timeout: 10000 }).catch(() => null)
  80  | 
  81  |     if (!appeared) {
  82  |       // Try broader search
  83  |       const bodyText = await page.locator('body').textContent()
  84  |       const found = bodyText.includes(testId)
  85  |       console.log(`[VISUAL] Message found in DOM: ${found}`)
  86  | 
  87  |       if (!found) {
  88  |         // Screenshot for debugging
  89  |         await page.screenshot({ path: 'test-results/inbound-visual-fail.png' })
  90  |         console.log(`[SCREENSHOT] Saved to test-results/inbound-visual-fail.png`)
  91  |       }
  92  |       expect(found).toBe(true)
  93  |     } else {
  94  |       console.log(`[VISUAL] Conversación aparecio sin F5`)
  95  |     }
  96  | 
  97  |     // Verify no reload
  98  |     const reloadCount = await page.evaluate(() => window.performance.navigation.type === 1 ? 1 : 0)
  99  |     expect(reloadCount).toBe(0)
  100 | 
  101 |     // Verify exactly one instance
  102 |     const instances = (await page.locator('body').textContent()).split(testId).length - 1
  103 |     console.log(`[DEDUP] Instancias del mensaje: ${instances}`)
  104 |     expect(instances).toBeLessThanOrEqual(2)  // Allow 1 or 2 (once per textContent, once in DOM)
  105 |   })
  106 | 
  107 |   test('4. Echo local without F5: takeover visible', async ({ page, context }) => {
  108 |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  109 |     const testIdInbound = `ECHO_IN_${Date.now()}`
  110 |     const testIdEcho = `ECHO_ADVISOR_${Date.now()}`
  111 | 
  112 |     // Inbound first
  113 |     const inbound = {
  114 |       object: 'whatsapp_business_account',
  115 |       entry: [{
  116 |         changes: [{
  117 |           value: {
  118 |             messaging_product: 'whatsapp',
  119 |             metadata: {
  120 |               phone_number_id: 'webhook-test',
  121 |               display_phone_number: '51967619238',
  122 |             },
  123 |             messages: [{
  124 |               from: testPhone,
  125 |               id: `wamid_in_${Date.now()}`,
  126 |               timestamp: Math.floor(Date.now() / 1000).toString(),
  127 |               type: 'text',
  128 |               text: { body: `Inbound: ${testIdInbound}` },
  129 |             }],
  130 |           },
  131 |         }],
  132 |       }],
  133 |     }
  134 | 
  135 |     let res = await context.request.post(WEBHOOK_URL, { data: inbound })
  136 |     expect(res.status()).toBe(200)
  137 |     console.log(`[ECHO TEST] Inbound: ${res.status()}`)
  138 | 
```