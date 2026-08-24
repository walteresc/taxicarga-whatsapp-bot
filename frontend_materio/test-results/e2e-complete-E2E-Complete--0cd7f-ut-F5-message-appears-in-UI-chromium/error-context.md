# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e-complete.spec.js >> E2E Complete: WhatsApp SSE Streaming >> 1. Inbound without F5: message appears in UI
- Location: src\__tests__\e2e-complete.spec.js:21:3

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e5]:
    - complementary [ref=e6]:
      - generic [ref=e7]:
        - button "Contraer menú" [ref=e8] [cursor=pointer]
        - link [ref=e10] [cursor=pointer]:
          - /url: /
          - heading "Materio" [level=1] [ref=e23]
      - list [ref=e24]:
        - listitem [ref=e25]:
          - generic [ref=e26] [cursor=pointer]: Dashboard
        - listitem [ref=e30]:
          - generic [ref=e31]: ATENCIÓN
        - listitem [ref=e33]:
          - generic [ref=e34] [cursor=pointer]: Bandeja de entrada
        - listitem [ref=e38]:
          - generic [ref=e39] [cursor=pointer]: Leads
        - listitem [ref=e43]:
          - generic [ref=e44]: COMERCIAL
        - listitem [ref=e46]:
          - generic [ref=e47] [cursor=pointer]: Por Cotizar
          - generic:
            - list:
              - listitem [ref=e52]:
                - generic [ref=e53] [cursor=pointer]: Lista
        - listitem [ref=e57]:
          - generic [ref=e58] [cursor=pointer]: Cotizaciones
          - generic:
            - list:
              - listitem [ref=e63]:
                - generic [ref=e64] [cursor=pointer]: Historial
        - listitem [ref=e68]:
          - generic [ref=e69] [cursor=pointer]: Clientes
        - listitem [ref=e73]:
          - generic [ref=e74] [cursor=pointer]: Reservas
        - listitem [ref=e78]:
          - generic [ref=e79]: OPERACIONES
        - listitem [ref=e81]:
          - generic [ref=e82] [cursor=pointer]: Pizarra
          - generic:
            - list:
              - listitem [ref=e87]:
                - generic [ref=e88] [cursor=pointer]: Programación Visual
        - listitem [ref=e92]:
          - generic [ref=e93] [cursor=pointer]: Programación
        - listitem [ref=e97]:
          - generic [ref=e98] [cursor=pointer]: Servicios
        - listitem [ref=e102]:
          - generic [ref=e103]: PERSONAL DE CAMPO
        - listitem [ref=e105]:
          - generic [ref=e106] [cursor=pointer]: Personal
          - generic:
            - list:
              - listitem [ref=e111]:
                - generic [ref=e112] [cursor=pointer]: Conductores
              - listitem [ref=e116]:
                - generic [ref=e117] [cursor=pointer]: Ayudantes
        - listitem [ref=e121]:
          - generic [ref=e122] [cursor=pointer]: Equipos
        - listitem [ref=e126]:
          - generic [ref=e127]: FLOTA
        - listitem [ref=e129]:
          - generic [ref=e130] [cursor=pointer]: Vehículos
          - generic:
            - list:
              - listitem [ref=e135]:
                - generic [ref=e136] [cursor=pointer]: Inventario
        - listitem [ref=e140]:
          - generic [ref=e141] [cursor=pointer]: Mantenimientos
        - listitem [ref=e145]:
          - generic [ref=e146]: AUTOMATIZACIÓN
        - listitem [ref=e148]:
          - generic [ref=e149] [cursor=pointer]: Bot WhatsApp
          - generic:
            - list:
              - listitem [ref=e154]:
                - generic [ref=e155] [cursor=pointer]: Bots
              - listitem [ref=e159]:
                - generic [ref=e160] [cursor=pointer]: Flujos
              - listitem [ref=e164]:
                - generic [ref=e165] [cursor=pointer]: Respuestas
              - listitem [ref=e169]:
                - generic [ref=e170] [cursor=pointer]: Canales
        - listitem [ref=e174]:
          - generic [ref=e175]: ANALÍTICA
        - listitem [ref=e177]:
          - generic [ref=e178] [cursor=pointer]: Reportes
          - generic:
            - list:
              - listitem [ref=e183]:
                - generic [ref=e184] [cursor=pointer]: Reportes
              - listitem [ref=e188]:
                - generic [ref=e189] [cursor=pointer]: Rendimiento
        - listitem [ref=e193]:
          - generic [ref=e194]: SISTEMA
        - listitem [ref=e196]:
          - generic [ref=e197] [cursor=pointer]: Administración
          - generic:
            - list:
              - listitem [ref=e202]:
                - generic [ref=e203] [cursor=pointer]: Usuarios
              - listitem [ref=e207]:
                - generic [ref=e208] [cursor=pointer]: Integraciones
              - listitem [ref=e212]:
                - generic [ref=e213] [cursor=pointer]: Configuración
    - generic [ref=e219]:
      - banner [ref=e220]:
        - generic [ref=e222]:
          - generic [ref=e223] [cursor=pointer]:
            - button [ref=e224]
            - generic [ref=e227]:
              - generic [ref=e228]: Search
              - generic [ref=e229]: ⌘K
          - link [ref=e230] [cursor=pointer]:
            - /url: https://github.com/themeselection/materio-vuetify-vuejs-admin-template-free
          - button [ref=e233] [cursor=pointer]
          - button [ref=e236] [cursor=pointer]
          - generic [ref=e240]:
            - generic [ref=e241] [cursor=pointer]
            - status "Badge" [ref=e244]
      - main [ref=e245]:
        - generic [ref=e247]:
          - heading "Dashboard" [level=1] [ref=e248]
          - paragraph [ref=e249]: Página principal del CRM TaxiCarga
      - contentinfo [ref=e250]:
        - generic [ref=e252]:
          - generic [ref=e253]:
            - text: © 2026 Made With By
            - link "ThemeSelection" [ref=e255] [cursor=pointer]:
              - /url: https://themeselection.com
          - generic [ref=e256]:
            - link "License" [ref=e257] [cursor=pointer]:
              - /url: https://themeselection.com/license/
            - link "More Themes" [ref=e258] [cursor=pointer]:
              - /url: https://themeselection.com/
            - link "Documentation" [ref=e259] [cursor=pointer]:
              - /url: https://demos.themeselection.com/materio-vuetify-vuejs-admin-template/documentation/
            - link "Support" [ref=e260] [cursor=pointer]:
              - /url: https://themeselection.com/support/
  - generic:
    - tooltip
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test'
  2   | 
  3   | const VITE_URL = 'http://localhost:5177'
  4   | const DJANGO_API = 'http://localhost:8001'
  5   | const WEBHOOK_URL = `${DJANGO_API}/webhook/whatsapp/`
  6   | const STREAM_URL = `${DJANGO_API}/whatsapp/api/events/stream/`
  7   | const POLL_URL = `${DJANGO_API}/whatsapp/api/events/poll/`
  8   | 
  9   | /**
  10  |  * E2E Complete Suite for FASE 5B
  11  |  * Tests inbound, echo, two tabs, fallback, idempotency, logout
  12  |  */
  13  | 
  14  | test.describe('E2E Complete: WhatsApp SSE Streaming', () => {
  15  |   test.beforeEach(async ({ page }) => {
  16  |     // Navigate to app
  17  |     await page.goto(VITE_URL)
  18  |     await page.waitForLoadState('networkidle')
  19  |   })
  20  | 
  21  |   test('1. Inbound without F5: message appears in UI', async ({ page, context }) => {
  22  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  23  |     const testId = `INBOUND-${Date.now()}`
  24  | 
  25  |     const payload = {
  26  |       from: testPhone,
  27  |       to: '51967619238',
  28  |       wamid: `wamid_${testId}`,
  29  |       text: `Test ${testId}`,
  30  |       timestamp: Math.floor(Date.now() / 1000).toString(),
  31  |       type: 'text',
  32  |     }
  33  | 
  34  |     // Send webhook
  35  |     const webhookRes = await context.request.post(WEBHOOK_URL, { data: payload })
  36  |     expect(webhookRes.ok()).toBe(true)
  37  | 
  38  |     // Wait for message to appear (SSE or polling)
  39  |     await page.waitForTimeout(2000)
  40  | 
  41  |     // Check: message visible somewhere on page
  42  |     const textElement = page.locator(`text="${testId}"`)
  43  |     const isVisible = await textElement.first().isVisible().catch(() => false)
> 44  |     expect(isVisible || (await page.locator('body').textContent()).includes(testId)).toBe(true)
      |                                                                                      ^ Error: expect(received).toBe(expected) // Object.is equality
  45  | 
  46  |     // Verify no reload
  47  |     const reloadCount = await page.evaluate(() => window.performance.navigation.type === 1 ? 1 : 0)
  48  |     expect(reloadCount).toBe(0)
  49  |   })
  50  | 
  51  |   test('2. Echo (advisor): bot_pausado set, takeover visible', async ({ page, context }) => {
  52  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  53  | 
  54  |     // First: inbound message
  55  |     const inboundPayload = {
  56  |       from: testPhone,
  57  |       to: '51967619238',
  58  |       wamid: `wamid_inbound_${Date.now()}`,
  59  |       text: 'Customer request',
  60  |       timestamp: Math.floor(Date.now() / 1000).toString(),
  61  |       type: 'text',
  62  |     }
  63  | 
  64  |     await context.request.post(WEBHOOK_URL, { data: inboundPayload })
  65  |     await page.waitForTimeout(1000)
  66  | 
  67  |     // Second: echo from advisor
  68  |     const echoPayload = {
  69  |       from: '51967619238', // Business number
  70  |       to: testPhone,       // Customer
  71  |       wamid: `wamid_echo_${Date.now()}`,
  72  |       text: 'Advisor taking over',
  73  |       timestamp: (Math.floor(Date.now() / 1000) + 10).toString(),
  74  |       type: 'text',
  75  |     }
  76  | 
  77  |     await context.request.post(WEBHOOK_URL, { data: echoPayload })
  78  |     await page.waitForTimeout(1000)
  79  | 
  80  |     // Check: conversation shows takeover state (UI-specific)
  81  |     const bodyText = await page.locator('body').textContent()
  82  |     expect(bodyText.includes('Advisor taking over')).toBe(true)
  83  |   })
  84  | 
  85  |   test('3. Two tabs: independent SSE, no duplicates', async ({ browser }) => {
  86  |     const context1 = await browser.newContext()
  87  |     const context2 = await browser.newContext()
  88  | 
  89  |     const page1 = await context1.newPage()
  90  |     const page2 = await context2.newPage()
  91  | 
  92  |     await page1.goto(VITE_URL)
  93  |     await page2.goto(VITE_URL)
  94  |     await page1.waitForLoadState('networkidle')
  95  |     await page2.waitForLoadState('networkidle')
  96  | 
  97  |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  98  |     const testId = `TWO-TAB-${Date.now()}`
  99  | 
  100 |     const payload = {
  101 |       from: testPhone,
  102 |       to: '51967619238',
  103 |       wamid: `wamid_${testId}`,
  104 |       text: `Test ${testId}`,
  105 |       timestamp: Math.floor(Date.now() / 1000).toString(),
  106 |       type: 'text',
  107 |     }
  108 | 
  109 |     // Send webhook once
  110 |     await page1.context().request.post(WEBHOOK_URL, { data: payload })
  111 |     await page1.waitForTimeout(2000)
  112 |     await page2.waitForTimeout(2000)
  113 | 
  114 |     // Both pages should see the message
  115 |     const text1 = await page1.locator('body').textContent()
  116 |     const text2 = await page2.locator('body').textContent()
  117 | 
  118 |     expect(text1.includes(testId)).toBe(true)
  119 |     expect(text2.includes(testId)).toBe(true)
  120 | 
  121 |     // Close
  122 |     await page1.close()
  123 |     await page2.close()
  124 |     await context1.close()
  125 |     await context2.close()
  126 |   })
  127 | 
  128 |   test('4. Idempotency: same event_id never duplicates', async ({ page, context }) => {
  129 |     const testPhone = `+5191${Date.now().toString().slice(-6)}`
  130 |     const wamid = `wamid_idempotent_${Date.now()}`
  131 | 
  132 |     const payload = {
  133 |       from: testPhone,
  134 |       to: '51967619238',
  135 |       wamid: wamid,
  136 |       text: 'Idempotent test message',
  137 |       timestamp: Math.floor(Date.now() / 1000).toString(),
  138 |       type: 'text',
  139 |     }
  140 | 
  141 |     // Send same event 3 times
  142 |     for (let i = 0; i < 3; i++) {
  143 |       await context.request.post(WEBHOOK_URL, { data: payload })
  144 |       await page.waitForTimeout(500)
```