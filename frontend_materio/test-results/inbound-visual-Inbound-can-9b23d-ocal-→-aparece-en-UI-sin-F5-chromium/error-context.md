# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: inbound-visual.spec.js >> Inbound canónico: webhook local → aparece en UI sin F5
- Location: src\__tests__\inbound-visual.spec.js:3:1

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
  3   | test('Inbound canónico: webhook local → aparece en UI sin F5', async ({ page, context }) => {
  4   |   const VITE_URL = 'http://localhost:5177'
  5   |   const WEBHOOK_URL = 'http://localhost:8001/webhook/whatsapp/'
  6   |   const TIMESTAMP = new Date().toISOString().replace(/[:.]/g, '')
  7   | 
  8   |   const testId = `INBOUND-${TIMESTAMP}`
  9   |   const testPhone = '+51919999001'
  10  | 
  11  |   console.log(`[TEST] ${testId}`)
  12  | 
  13  |   // 1. Navegar a UI
  14  |   await page.goto(`${VITE_URL}/`)
  15  |   await page.waitForLoadState('networkidle')
  16  |   console.log(`[UI] Cargada`)
  17  | 
  18  |   // Capturar lista de conversaciones inicial
  19  |   const convCountBefore = await page.locator('[data-test="conversation-item"]').count()
  20  |   console.log(`[UI] Conversaciones antes: ${convCountBefore}`)
  21  | 
  22  |   // 2. Enviar webhook inbound Meta format
  23  |   const webhookPayload = {
  24  |     object: 'whatsapp_business_account',
  25  |     entry: [{
  26  |       changes: [{
  27  |         value: {
  28  |           messaging_product: 'whatsapp',
  29  |           metadata: {
  30  |             phone_number_id: 'e2e_channel_2',
  31  |             display_phone_number: '51967619238',
  32  |           },
  33  |           messages: [{
  34  |             from: testPhone,
  35  |             id: `wamid_${testId}`,
  36  |             timestamp: Math.floor(Date.now() / 1000).toString(),
  37  |             type: 'text',
  38  |             text: { body: `Test ${testId}` },
  39  |           }],
  40  |         },
  41  |       }],
  42  |     }],
  43  |   }
  44  | 
  45  |   console.log(`[WEBHOOK] Enviando inbound desde ${testPhone}`)
  46  |   const webhookResponse = await page.context().request.post(WEBHOOK_URL, {
  47  |     data: webhookPayload,
  48  |   })
  49  | 
  50  |   console.log(`[WEBHOOK] Response: ${webhookResponse.status()}`)
  51  |   expect(webhookResponse.ok()).toBe(true)
  52  | 
  53  |   // 3. Esperar que aparezca en la UI (SSE o polling)
  54  |   console.log(`[WAIT] Esperando que aparezca conversación...`)
  55  | 
  56  |   // Estrategia: monitorear cambios en el DOM
  57  |   let conversationAppeared = false
  58  |   let messageAppeared = false
  59  | 
  60  |   // Esperar hasta 5 segundos por el nuevo mensaje
  61  |   const startWait = Date.now()
  62  |   const maxWait = 5000
  63  | 
  64  |   while (!conversationAppeared && Date.now() - startWait < maxWait) {
  65  |     const convCount = await page.locator('[data-test="conversation-item"]').count()
  66  | 
  67  |     if (convCount > convCountBefore) {
  68  |       conversationAppeared = true
  69  |       console.log(`[UI] Nueva conversación detectada (${convCountBefore} → ${convCount})`)
  70  | 
  71  |       // Verificar que contiene el texto del test
  72  |       const conversationText = await page.textContent('[data-test="conversation-item"]')
  73  |       expect(conversationText).toContain(testId)
  74  |       console.log(`[UI] Texto correcto: ${testId}`)
  75  | 
  76  |       break
  77  |     }
  78  | 
  79  |     await page.waitForTimeout(200)
  80  |   }
  81  | 
  82  |   if (!conversationAppeared) {
  83  |     // Fallback: buscar por preview
  84  |     const preview = await page.locator(`text="${testId}"`).first()
  85  |     if (await preview.isVisible()) {
  86  |       conversationAppeared = true
  87  |       console.log(`[UI] Conversación encontrada por preview`)
  88  |     }
  89  |   }
  90  | 
> 91  |   expect(conversationAppeared).toBe(true)
      |                                ^ Error: expect(received).toBe(expected) // Object.is equality
  92  | 
  93  |   // 4. Verificar que no hubo F5
  94  |   const reloadCount = await page.evaluate(() => {
  95  |     return window.performance.navigation.type === 1 ? 1 : 0
  96  |   })
  97  |   expect(reloadCount).toBe(0)
  98  |   console.log(`[CHECK] No hay F5/reload`)
  99  | 
  100 |   // 5. Verificar que SSE está conectado
  101 |   const sseConnected = await page.evaluate(() => {
  102 |     return window.__eventSource?.readyState === 0 || // CONNECTING
  103 |            window.__eventSource?.readyState === 1 || // OPEN
  104 |            document.body.innerHTML.includes('EventSource')
  105 |   })
  106 |   console.log(`[CHECK] SSE conectado: ${sseConnected}`)
  107 | 
  108 |   // 6. Verificar preview y hora
  109 |   const convItem = page.locator('[data-test="conversation-item"]').first()
  110 |   const preview = await convItem.locator('[data-test="preview"]').textContent()
  111 |   const timestamp_el = await convItem.locator('[data-test="timestamp"]').textContent()
  112 | 
  113 |   console.log(`[MESSAGE] Preview: "${preview}"`)
  114 |   console.log(`[MESSAGE] Hora: ${timestamp_el}`)
  115 | 
  116 |   // El preview debe contener el mensaje
  117 |   expect(preview).toContain(testId)
  118 | 
  119 |   // La hora debe ser cercana a ahora
  120 |   if (timestamp_el) {
  121 |     const messageTime = new Date(timestamp_el)
  122 |     const now = new Date()
  123 |     const diff = (now - messageTime) / 1000
  124 |     console.log(`[TIME-CHECK] Diferencia: ${diff.toFixed(1)}s`)
  125 |     expect(diff).toBeLessThan(60) // Menos de 1 minuto
  126 |   }
  127 | 
  128 |   // 7. Abrir conversación y verificar timeline
  129 |   await convItem.click()
  130 |   await page.waitForLoadState('networkidle')
  131 | 
  132 |   const msgInTimeline = page.locator(`text="${testId}"`)
  133 |   const timelineVisible = await msgInTimeline.isVisible()
  134 |   console.log(`[TIMELINE] Mensaje visible: ${timelineVisible}`)
  135 |   expect(timelineVisible).toBe(true)
  136 | 
  137 |   // 8. Verificar que aparece una sola vez
  138 |   const msgCount = await msgInTimeline.count()
  139 |   console.log(`[DEDUP] Instancias del mensaje: ${msgCount}`)
  140 |   expect(msgCount).toBe(1)
  141 | 
  142 |   // 9. Verificar unread cambió
  143 |   const unreadBadge = page.locator('[data-test="unread-count"]').first()
  144 |   const hasUnread = await unreadBadge.isVisible()
  145 |   console.log(`[UNREAD] Badge visible: ${hasUnread}`)
  146 | 
  147 |   console.log(`[RESULT] PASS: Inbound canónico sin F5`)
  148 | })
  149 | 
```