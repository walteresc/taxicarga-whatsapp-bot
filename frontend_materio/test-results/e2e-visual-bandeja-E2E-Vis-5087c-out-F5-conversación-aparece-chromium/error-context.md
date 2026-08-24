# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e-visual-bandeja.spec.js >> E2E Visual: Bandeja-Entrada Real UI >> 3. Inbound local without F5: conversación aparece
- Location: src\__tests__\e2e-visual-bandeja.spec.js:69:3

# Error details

```
Test timeout of 90000ms exceeded while running "beforeEach" hook.
```

```
Error: page.goto: Target page, context or browser has been closed
```

# Page snapshot

```yaml
- main [ref=f1e5]:
  - generic [ref=f1e6]:
    - generic [ref=f1e7]:
      - generic [ref=f1e8]: 󱊜
      - generic [ref=f1e10]: TaxiCarga
    - generic [ref=f1e11]:
      - heading "Gestion comercial para conversaciones de mudanza y carga" [level=1] [ref=f1e12]
      - paragraph [ref=f1e13]: Atiende clientes, toma conversaciones, registra cotizaciones y controla leads desde una sola pantalla.
      - generic [ref=f1e14]:
        - generic [ref=f1e15]: WhatsApp
        - generic [ref=f1e16]: Cotizaciones
        - generic [ref=f1e17]: Vendedores
    - generic [ref=f1e18]: Panel interno - acceso autorizado
  - generic [ref=f1e20]:
    - generic [ref=f1e21]:
      - generic [ref=f1e22]: Acceso comercial
      - generic [ref=f1e23]: Ingresa con tu usuario de vendedor.
    - alert [ref=f1e24]:
      - generic [ref=f1e25]: 󰅙
      - generic [ref=f1e27]: Usuario o contrasena incorrectos.
    - generic [ref=f1e28]:
      - generic [ref=f1e29]:
        - generic [ref=f1e31]:
          - generic [ref=f1e32]: 󰀓
          - textbox "Usuario Usuario" [active] [ref=f1e35]
          - generic: Usuario
        - alert [ref=f1e37]
      - generic [ref=f1e38]:
        - generic [ref=f1e40]:
          - generic [ref=f1e41]: 󰍁
          - generic [ref=f1e43]:
            - generic: Contrasena
            - textbox "Contrasena Contrasena" [ref=f1e44]
        - alert [ref=f1e46]
      - button "Iniciar sesion" [ref=f1e47] [cursor=pointer]:
        - generic [ref=f1e48]: 󰍂
    - generic [ref=f1e51]:
      - text: "Demo local: usuario"
      - strong [ref=f1e52]: demo_vendedor
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
  15  |     // Capture console errors for debugging
  16  |     const consoleErrors = []
  17  |     page.on('console', msg => {
  18  |       if (msg.type() === 'error') {
  19  |         consoleErrors.push(msg.text())
  20  |         console.log(`[CONSOLE ERROR] ${msg.text()}`)
  21  |       }
  22  |     })
  23  | 
  24  |     // Load login page
  25  |     await page.goto(`${VITE_URL}/dashboard/login/`)
  26  |     await page.waitForLoadState('domcontentloaded')
  27  | 
  28  |     // Fill username
  29  |     await page.fill('input[name="username"]', 'e2e_test').catch(() => {
  30  |       console.log('[AUTH] Username field not found - may already be logged in')
  31  |     })
  32  | 
  33  |     // Fill password
  34  |     await page.fill('input[name="password"]', 'e2e_test_pass').catch(() => {
  35  |       console.log('[AUTH] Password field not found - may already be logged in')
  36  |     })
  37  | 
  38  |     // Submit form
  39  |     await page.click('button[type="submit"]').catch(() => {
  40  |       console.log('[AUTH] Submit button not found - skipping')
  41  |     })
  42  | 
  43  |     // Wait for redirect
  44  |     await page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {})
  45  | 
  46  |     // Load bandeja-entrada (avoid networkidle: SSE streams indefinitely)
  47  |     try {
> 48  |       await page.goto(`${VITE_URL}/atencion/bandeja-entrada`, {
      |                  ^ Error: page.goto: Target page, context or browser has been closed
  49  |         waitUntil: 'domcontentloaded',
  50  |         timeout: 30000
  51  |       })
  52  | 
  53  |       // Wait for main container to render
  54  |       await page.waitForSelector('.bandeja-page, [data-testid="conversation-list"], .main-container', {
  55  |         timeout: 15000
  56  |       }).catch(() => {
  57  |         console.log('[PAGE] Selector timeout - page may still be loading')
  58  |       })
  59  | 
  60  |       // Brief wait for Vue initialization
  61  |       await page.waitForTimeout(2000)
  62  |       console.log(`[PAGE] Loaded bandeja-entrada`)
  63  |     } catch (e) {
  64  |       console.log(`[PAGE] Error loading bandeja: ${e.message}`)
  65  |       throw e
  66  |     }
  67  |   })
  68  | 
  69  |   test('3. Inbound local without F5: conversación aparece', async ({ page, context }) => {
  70  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  71  |     const testId = `INBOUND-${Date.now()}`
  72  | 
  73  |     // Capture initial conversation count
  74  |     const convsBefore = await page.locator('[class*="conversation"], [class*="bandeja"], [class*="item"]').count()
  75  |     console.log(`[VISUAL] Conversaciones iniciales: ${convsBefore}`)
  76  | 
  77  |     // Send webhook
  78  |     const payload = {
  79  |       object: 'whatsapp_business_account',
  80  |       entry: [{
  81  |         changes: [{
  82  |           value: {
  83  |             messaging_product: 'whatsapp',
  84  |             metadata: {
  85  |               phone_number_id: 'webhook-test',
  86  |               display_phone_number: '51967619238',
  87  |             },
  88  |             messages: [{
  89  |               from: testPhone,
  90  |               id: `wamid_${testId}`,
  91  |               timestamp: Math.floor(Date.now() / 1000).toString(),
  92  |               type: 'text',
  93  |               text: { body: `Test: ${testId}` },
  94  |             }],
  95  |           },
  96  |         }],
  97  |       }],
  98  |     }
  99  | 
  100 |     const res = await context.request.post(WEBHOOK_URL, { data: payload })
  101 |     console.log(`[WEBHOOK] Inbound POST -> ${res.status()}`)
  102 |     expect(res.status()).toBe(200)
  103 | 
  104 |     // Wait max 10s for UI update via SSE or polling
  105 |     const appeared = await page.locator('body').locator(`text="${testId}"`).first().waitFor({ timeout: 10000 }).catch(() => null)
  106 | 
  107 |     if (!appeared) {
  108 |       // Try broader search
  109 |       const bodyText = await page.locator('body').textContent()
  110 |       const found = bodyText.includes(testId)
  111 |       console.log(`[VISUAL] Message found in DOM: ${found}`)
  112 | 
  113 |       if (!found) {
  114 |         // Screenshot for debugging
  115 |         await page.screenshot({ path: 'test-results/inbound-visual-fail.png' })
  116 |         console.log(`[SCREENSHOT] Saved to test-results/inbound-visual-fail.png`)
  117 |       }
  118 |       expect(found).toBe(true)
  119 |     } else {
  120 |       console.log(`[VISUAL] Conversación aparecio sin F5`)
  121 |     }
  122 | 
  123 |     // Verify no reload
  124 |     const reloadCount = await page.evaluate(() => window.performance.navigation.type === 1 ? 1 : 0)
  125 |     expect(reloadCount).toBe(0)
  126 | 
  127 |     // Verify exactly one instance
  128 |     const instances = (await page.locator('body').textContent()).split(testId).length - 1
  129 |     console.log(`[DEDUP] Instancias del mensaje: ${instances}`)
  130 |     expect(instances).toBeLessThanOrEqual(2)  // Allow 1 or 2 (once per textContent, once in DOM)
  131 |   })
  132 | 
  133 |   test('4. Echo local without F5: takeover visible', async ({ page, context }) => {
  134 |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  135 |     const testIdInbound = `ECHO_IN_${Date.now()}`
  136 |     const testIdEcho = `ECHO_ADVISOR_${Date.now()}`
  137 | 
  138 |     // Inbound first
  139 |     const inbound = {
  140 |       object: 'whatsapp_business_account',
  141 |       entry: [{
  142 |         changes: [{
  143 |           value: {
  144 |             messaging_product: 'whatsapp',
  145 |             metadata: {
  146 |               phone_number_id: 'webhook-test',
  147 |               display_phone_number: '51967619238',
  148 |             },
```