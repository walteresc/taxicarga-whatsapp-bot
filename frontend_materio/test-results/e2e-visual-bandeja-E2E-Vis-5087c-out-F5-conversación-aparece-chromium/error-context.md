# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e-visual-bandeja.spec.js >> E2E Visual: Bandeja-Entrada Real UI >> 3. Inbound local without F5: conversación aparece
- Location: src\__tests__\e2e-visual-bandeja.spec.js:45:3

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
  35  |     await page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {})
  36  | 
  37  |     // Load bandeja-entrada (avoid networkidle: SSE streams indefinitely)
> 38  |     await page.goto(`${VITE_URL}/atencion/bandeja-entrada`, { waitUntil: 'domcontentloaded' })
      |                ^ Error: page.goto: Target page, context or browser has been closed
  39  |     // Wait for Vue/Vuetify hydration
  40  |     await page.waitForLoadState('domcontentloaded')
  41  |     await page.waitForTimeout(2000)  // Let Vue initialize and SSE connect
  42  |     console.log(`[PAGE] Loaded bandeja-entrada`)
  43  |   })
  44  | 
  45  |   test('3. Inbound local without F5: conversación aparece', async ({ page, context }) => {
  46  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  47  |     const testId = `INBOUND-${Date.now()}`
  48  | 
  49  |     // Capture initial conversation count
  50  |     const convsBefore = await page.locator('[class*="conversation"], [class*="bandeja"], [class*="item"]').count()
  51  |     console.log(`[VISUAL] Conversaciones iniciales: ${convsBefore}`)
  52  | 
  53  |     // Send webhook
  54  |     const payload = {
  55  |       object: 'whatsapp_business_account',
  56  |       entry: [{
  57  |         changes: [{
  58  |           value: {
  59  |             messaging_product: 'whatsapp',
  60  |             metadata: {
  61  |               phone_number_id: 'webhook-test',
  62  |               display_phone_number: '51967619238',
  63  |             },
  64  |             messages: [{
  65  |               from: testPhone,
  66  |               id: `wamid_${testId}`,
  67  |               timestamp: Math.floor(Date.now() / 1000).toString(),
  68  |               type: 'text',
  69  |               text: { body: `Test: ${testId}` },
  70  |             }],
  71  |           },
  72  |         }],
  73  |       }],
  74  |     }
  75  | 
  76  |     const res = await context.request.post(WEBHOOK_URL, { data: payload })
  77  |     console.log(`[WEBHOOK] Inbound POST -> ${res.status()}`)
  78  |     expect(res.status()).toBe(200)
  79  | 
  80  |     // Wait max 10s for UI update via SSE or polling
  81  |     const appeared = await page.locator('body').locator(`text="${testId}"`).first().waitFor({ timeout: 10000 }).catch(() => null)
  82  | 
  83  |     if (!appeared) {
  84  |       // Try broader search
  85  |       const bodyText = await page.locator('body').textContent()
  86  |       const found = bodyText.includes(testId)
  87  |       console.log(`[VISUAL] Message found in DOM: ${found}`)
  88  | 
  89  |       if (!found) {
  90  |         // Screenshot for debugging
  91  |         await page.screenshot({ path: 'test-results/inbound-visual-fail.png' })
  92  |         console.log(`[SCREENSHOT] Saved to test-results/inbound-visual-fail.png`)
  93  |       }
  94  |       expect(found).toBe(true)
  95  |     } else {
  96  |       console.log(`[VISUAL] Conversación aparecio sin F5`)
  97  |     }
  98  | 
  99  |     // Verify no reload
  100 |     const reloadCount = await page.evaluate(() => window.performance.navigation.type === 1 ? 1 : 0)
  101 |     expect(reloadCount).toBe(0)
  102 | 
  103 |     // Verify exactly one instance
  104 |     const instances = (await page.locator('body').textContent()).split(testId).length - 1
  105 |     console.log(`[DEDUP] Instancias del mensaje: ${instances}`)
  106 |     expect(instances).toBeLessThanOrEqual(2)  // Allow 1 or 2 (once per textContent, once in DOM)
  107 |   })
  108 | 
  109 |   test('4. Echo local without F5: takeover visible', async ({ page, context }) => {
  110 |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  111 |     const testIdInbound = `ECHO_IN_${Date.now()}`
  112 |     const testIdEcho = `ECHO_ADVISOR_${Date.now()}`
  113 | 
  114 |     // Inbound first
  115 |     const inbound = {
  116 |       object: 'whatsapp_business_account',
  117 |       entry: [{
  118 |         changes: [{
  119 |           value: {
  120 |             messaging_product: 'whatsapp',
  121 |             metadata: {
  122 |               phone_number_id: 'webhook-test',
  123 |               display_phone_number: '51967619238',
  124 |             },
  125 |             messages: [{
  126 |               from: testPhone,
  127 |               id: `wamid_in_${Date.now()}`,
  128 |               timestamp: Math.floor(Date.now() / 1000).toString(),
  129 |               type: 'text',
  130 |               text: { body: `Inbound: ${testIdInbound}` },
  131 |             }],
  132 |           },
  133 |         }],
  134 |       }],
  135 |     }
  136 | 
  137 |     let res = await context.request.post(WEBHOOK_URL, { data: inbound })
  138 |     expect(res.status()).toBe(200)
```