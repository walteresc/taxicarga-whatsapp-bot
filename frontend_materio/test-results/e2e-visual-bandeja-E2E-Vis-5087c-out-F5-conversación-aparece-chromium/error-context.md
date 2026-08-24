# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e-visual-bandeja.spec.js >> E2E Visual: Bandeja-Entrada Real UI >> 3. Inbound local without F5: conversación aparece
- Location: src\__tests__\e2e-visual-bandeja.spec.js:20:3

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false
```

# Page snapshot

```yaml
- generic [ref=e9]:
  - generic [ref=e10]:
    - heading "TaxiCarga" [level=1] [ref=e11]
    - paragraph [ref=e12]: Bandeja de entrada
  - generic [ref=e13]:
    - generic [ref=e19]:
      - generic: Usuario
      - textbox "Usuario Usuario" [ref=e20]:
        - /placeholder: Ingresa tu usuario
    - generic [ref=e23]:
      - generic [ref=e26]:
        - generic: Contraseña
        - textbox "Contraseña Contraseña" [ref=e27]:
          - /placeholder: Ingresa tu contraseña
      - button "Contraseña appended action" [ref=e29] [cursor=pointer]
    - button "Iniciar sesión" [ref=e30] [cursor=pointer]
    - alert [ref=e33]:
      - generic [ref=e36]:
        - strong [ref=e37]: "Demo:"
        - text: testadmin / testpass123
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
  15  |     // Load bandeja-entrada
  16  |     await page.goto(`${VITE_URL}/atencion/bandeja-entrada`)
  17  |     await page.waitForLoadState('networkidle')
  18  |   })
  19  | 
  20  |   test('3. Inbound local without F5: conversación aparece', async ({ page, context }) => {
  21  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  22  |     const testId = `INBOUND-${Date.now()}`
  23  | 
  24  |     // Capture initial conversation count
  25  |     const convsBefore = await page.locator('[class*="conversation"], [class*="bandeja"], [class*="item"]').count()
  26  |     console.log(`[VISUAL] Conversaciones iniciales: ${convsBefore}`)
  27  | 
  28  |     // Send webhook
  29  |     const payload = {
  30  |       object: 'whatsapp_business_account',
  31  |       entry: [{
  32  |         changes: [{
  33  |           value: {
  34  |             messaging_product: 'whatsapp',
  35  |             metadata: {
  36  |               phone_number_id: 'webhook-test',
  37  |               display_phone_number: '51967619238',
  38  |             },
  39  |             messages: [{
  40  |               from: testPhone,
  41  |               id: `wamid_${testId}`,
  42  |               timestamp: Math.floor(Date.now() / 1000).toString(),
  43  |               type: 'text',
  44  |               text: { body: `Test: ${testId}` },
  45  |             }],
  46  |           },
  47  |         }],
  48  |       }],
  49  |     }
  50  | 
  51  |     const res = await context.request.post(WEBHOOK_URL, { data: payload })
  52  |     console.log(`[WEBHOOK] Inbound POST -> ${res.status()}`)
  53  |     expect(res.status()).toBe(200)
  54  | 
  55  |     // Wait max 10s for UI update via SSE or polling
  56  |     const appeared = await page.locator('body').locator(`text="${testId}"`).first().waitFor({ timeout: 10000 }).catch(() => null)
  57  | 
  58  |     if (!appeared) {
  59  |       // Try broader search
  60  |       const bodyText = await page.locator('body').textContent()
  61  |       const found = bodyText.includes(testId)
  62  |       console.log(`[VISUAL] Message found in DOM: ${found}`)
  63  | 
  64  |       if (!found) {
  65  |         // Screenshot for debugging
  66  |         await page.screenshot({ path: 'test-results/inbound-visual-fail.png' })
  67  |         console.log(`[SCREENSHOT] Saved to test-results/inbound-visual-fail.png`)
  68  |       }
> 69  |       expect(found).toBe(true)
      |                     ^ Error: expect(received).toBe(expected) // Object.is equality
  70  |     } else {
  71  |       console.log(`[VISUAL] Conversación aparecio sin F5`)
  72  |     }
  73  | 
  74  |     // Verify no reload
  75  |     const reloadCount = await page.evaluate(() => window.performance.navigation.type === 1 ? 1 : 0)
  76  |     expect(reloadCount).toBe(0)
  77  | 
  78  |     // Verify exactly one instance
  79  |     const instances = (await page.locator('body').textContent()).split(testId).length - 1
  80  |     console.log(`[DEDUP] Instancias del mensaje: ${instances}`)
  81  |     expect(instances).toBeLessThanOrEqual(2)  // Allow 1 or 2 (once per textContent, once in DOM)
  82  |   })
  83  | 
  84  |   test('4. Echo local without F5: takeover visible', async ({ page, context }) => {
  85  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  86  |     const testIdInbound = `ECHO_IN_${Date.now()}`
  87  |     const testIdEcho = `ECHO_ADVISOR_${Date.now()}`
  88  | 
  89  |     // Inbound first
  90  |     const inbound = {
  91  |       object: 'whatsapp_business_account',
  92  |       entry: [{
  93  |         changes: [{
  94  |           value: {
  95  |             messaging_product: 'whatsapp',
  96  |             metadata: {
  97  |               phone_number_id: 'webhook-test',
  98  |               display_phone_number: '51967619238',
  99  |             },
  100 |             messages: [{
  101 |               from: testPhone,
  102 |               id: `wamid_in_${Date.now()}`,
  103 |               timestamp: Math.floor(Date.now() / 1000).toString(),
  104 |               type: 'text',
  105 |               text: { body: `Inbound: ${testIdInbound}` },
  106 |             }],
  107 |           },
  108 |         }],
  109 |       }],
  110 |     }
  111 | 
  112 |     let res = await context.request.post(WEBHOOK_URL, { data: inbound })
  113 |     expect(res.status()).toBe(200)
  114 |     console.log(`[ECHO TEST] Inbound: ${res.status()}`)
  115 | 
  116 |     await page.waitForTimeout(1000)
  117 | 
  118 |     // Echo (advisor takeover)
  119 |     const echo = {
  120 |       object: 'whatsapp_business_account',
  121 |       entry: [{
  122 |         changes: [{
  123 |           value: {
  124 |             messaging_product: 'whatsapp',
  125 |             metadata: {
  126 |               phone_number_id: 'webhook-test',
  127 |               display_phone_number: '51967619238',
  128 |             },
  129 |             messages: [{
  130 |               from: 'business_number',
  131 |               to: testPhone,
  132 |               id: `wamid_echo_${Date.now()}`,
  133 |               timestamp: (Math.floor(Date.now() / 1000) + 5).toString(),
  134 |               type: 'text',
  135 |               text: { body: `Echo/Takeover: ${testIdEcho}` },
  136 |             }],
  137 |           },
  138 |         }],
  139 |       }],
  140 |     }
  141 | 
  142 |     res = await context.request.post(WEBHOOK_URL, { data: echo })
  143 |     expect(res.status()).toBe(200)
  144 |     console.log(`[ECHO TEST] Echo: ${res.status()}`)
  145 | 
  146 |     await page.waitForTimeout(2000)
  147 | 
  148 |     // Verify both appeared
  149 |     const bodyText = await page.locator('body').textContent()
  150 |     expect(bodyText.includes(testIdInbound)).toBe(true)
  151 |     expect(bodyText.includes(testIdEcho)).toBe(true)
  152 |     console.log(`[ECHO TEST] Both messages in DOM`)
  153 |   })
  154 | 
  155 |   test('5. Dos pestañas: ambas reciben, ninguna duplica', async ({ browser }) => {
  156 |     const context1 = await browser.newContext()
  157 |     const context2 = await browser.newContext()
  158 | 
  159 |     const page1 = await context1.newPage()
  160 |     const page2 = await context2.newPage()
  161 | 
  162 |     await page1.goto(`${VITE_URL}/atencion/bandeja-entrada`)
  163 |     await page2.goto(`${VITE_URL}/atencion/bandeja-entrada`)
  164 | 
  165 |     await page1.waitForLoadState('networkidle')
  166 |     await page2.waitForLoadState('networkidle')
  167 | 
  168 |     console.log(`[TABS] Dos pestañas cargadas`)
  169 | 
```