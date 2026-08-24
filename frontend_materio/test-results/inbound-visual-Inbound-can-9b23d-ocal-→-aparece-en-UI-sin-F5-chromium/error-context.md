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
  22  |   // 2. Enviar webhook inbound
  23  |   const webhookPayload = {
  24  |     entry: [
  25  |       {
  26  |         changes: [
  27  |           {
  28  |             value: {
  29  |               messaging_product: 'whatsapp',
  30  |               metadata: {
  31  |                 phone_number_id: '380000000000001', // Canal ID 2 Lima Express
  32  |                 display_phone_number: '+51967619238',
  33  |               },
  34  |               messages: [
  35  |                 {
  36  |                   from: testPhone,
  37  |                   id: `wamid_${testId}`,
  38  |                   timestamp: Math.floor(Date.now() / 1000).toString(),
  39  |                   type: 'text',
  40  |                   text: {
  41  |                     body: `Test ${testId}`,
  42  |                   },
  43  |                 },
  44  |               ],
  45  |             },
  46  |           },
  47  |         ],
  48  |       },
  49  |     ],
  50  |   }
  51  | 
  52  |   console.log(`[WEBHOOK] Enviando inbound desde ${testPhone}`)
  53  |   const webhookResponse = await page.context().request.post(WEBHOOK_URL, {
  54  |     data: webhookPayload,
  55  |   })
  56  | 
  57  |   console.log(`[WEBHOOK] Response: ${webhookResponse.status()}`)
  58  |   expect(webhookResponse.ok()).toBe(true)
  59  | 
  60  |   // 3. Esperar que aparezca en la UI (SSE o polling)
  61  |   console.log(`[WAIT] Esperando que aparezca conversación...`)
  62  | 
  63  |   // Estrategia: monitorear cambios en el DOM
  64  |   let conversationAppeared = false
  65  |   let messageAppeared = false
  66  | 
  67  |   // Esperar hasta 5 segundos por el nuevo mensaje
  68  |   const startWait = Date.now()
  69  |   const maxWait = 5000
  70  | 
  71  |   while (!conversationAppeared && Date.now() - startWait < maxWait) {
  72  |     const convCount = await page.locator('[data-test="conversation-item"]').count()
  73  | 
  74  |     if (convCount > convCountBefore) {
  75  |       conversationAppeared = true
  76  |       console.log(`[UI] Nueva conversación detectada (${convCountBefore} → ${convCount})`)
  77  | 
  78  |       // Verificar que contiene el texto del test
  79  |       const conversationText = await page.textContent('[data-test="conversation-item"]')
  80  |       expect(conversationText).toContain(testId)
  81  |       console.log(`[UI] Texto correcto: ${testId}`)
  82  | 
  83  |       break
  84  |     }
  85  | 
  86  |     await page.waitForTimeout(200)
  87  |   }
  88  | 
  89  |   if (!conversationAppeared) {
  90  |     // Fallback: buscar por preview
  91  |     const preview = await page.locator(`text="${testId}"`).first()
  92  |     if (await preview.isVisible()) {
  93  |       conversationAppeared = true
  94  |       console.log(`[UI] Conversación encontrada por preview`)
  95  |     }
  96  |   }
  97  | 
> 98  |   expect(conversationAppeared).toBe(true)
      |                                ^ Error: expect(received).toBe(expected) // Object.is equality
  99  | 
  100 |   // 4. Verificar que no hubo F5
  101 |   const reloadCount = await page.evaluate(() => {
  102 |     return window.performance.navigation.type === 1 ? 1 : 0
  103 |   })
  104 |   expect(reloadCount).toBe(0)
  105 |   console.log(`[CHECK] No hay F5/reload`)
  106 | 
  107 |   // 5. Verificar que SSE está conectado
  108 |   const sseConnected = await page.evaluate(() => {
  109 |     return window.__eventSource?.readyState === 0 || // CONNECTING
  110 |            window.__eventSource?.readyState === 1 || // OPEN
  111 |            document.body.innerHTML.includes('EventSource')
  112 |   })
  113 |   console.log(`[CHECK] SSE conectado: ${sseConnected}`)
  114 | 
  115 |   // 6. Verificar preview y hora
  116 |   const convItem = page.locator('[data-test="conversation-item"]').first()
  117 |   const preview = await convItem.locator('[data-test="preview"]').textContent()
  118 |   const timestamp_el = await convItem.locator('[data-test="timestamp"]').textContent()
  119 | 
  120 |   console.log(`[MESSAGE] Preview: "${preview}"`)
  121 |   console.log(`[MESSAGE] Hora: ${timestamp_el}`)
  122 | 
  123 |   // El preview debe contener el mensaje
  124 |   expect(preview).toContain(testId)
  125 | 
  126 |   // La hora debe ser cercana a ahora
  127 |   if (timestamp_el) {
  128 |     const messageTime = new Date(timestamp_el)
  129 |     const now = new Date()
  130 |     const diff = (now - messageTime) / 1000
  131 |     console.log(`[TIME-CHECK] Diferencia: ${diff.toFixed(1)}s`)
  132 |     expect(diff).toBeLessThan(60) // Menos de 1 minuto
  133 |   }
  134 | 
  135 |   // 7. Abrir conversación y verificar timeline
  136 |   await convItem.click()
  137 |   await page.waitForLoadState('networkidle')
  138 | 
  139 |   const msgInTimeline = page.locator(`text="${testId}"`)
  140 |   const timelineVisible = await msgInTimeline.isVisible()
  141 |   console.log(`[TIMELINE] Mensaje visible: ${timelineVisible}`)
  142 |   expect(timelineVisible).toBe(true)
  143 | 
  144 |   // 8. Verificar que aparece una sola vez
  145 |   const msgCount = await msgInTimeline.count()
  146 |   console.log(`[DEDUP] Instancias del mensaje: ${msgCount}`)
  147 |   expect(msgCount).toBe(1)
  148 | 
  149 |   // 9. Verificar unread cambió
  150 |   const unreadBadge = page.locator('[data-test="unread-count"]').first()
  151 |   const hasUnread = await unreadBadge.isVisible()
  152 |   console.log(`[UNREAD] Badge visible: ${hasUnread}`)
  153 | 
  154 |   console.log(`[RESULT] PASS: Inbound canónico sin F5`)
  155 | })
  156 | 
```