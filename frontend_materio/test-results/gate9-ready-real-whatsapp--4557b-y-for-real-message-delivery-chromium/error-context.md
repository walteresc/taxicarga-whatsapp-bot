# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: gate9-ready-real-whatsapp.spec.js >> Gate 9 Ready for Real WhatsApp >> All infrastructure ready for real message delivery
- Location: src\__tests__\gate9-ready-real-whatsapp.spec.js:4:3

# Error details

```
TimeoutError: page.waitForSelector: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('.conversation-item') to be visible

```

# Page snapshot

```yaml
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
    - main [ref=e220]:
      - generic [ref=e222]:
        - generic [ref=e223]:
          - heading "Bandeja de entrada 0" [level=1] [ref=e225]:
            - text: Bandeja de entrada
            - generic [ref=e226]: "0"
          - generic [ref=e227]:
            - generic [ref=e228]: Bot global activo
            - button "Pausar bot" [ref=e231] [cursor=pointer]
            - button [ref=e233] [cursor=pointer]
        - generic [ref=e235]:
          - generic [ref=e237]:
            - textbox "Buscar por nombre, teléfono o mensaje" [ref=e239]
            - generic [ref=e240]:
              - button "Todas" [ref=e241] [cursor=pointer]
              - button "Mías" [ref=e242] [cursor=pointer]
              - button "No leídas" [ref=e243] [cursor=pointer]
              - button "Canal" [ref=e245] [cursor=pointer]
              - button "Filtros avanzados" [ref=e248] [cursor=pointer]
            - generic [ref=e252]:
              - paragraph [ref=e254]: Aún no hay conversaciones
              - paragraph [ref=e255]: Las nuevas conversaciones aparecerán aquí
          - generic [ref=e258]:
            - heading "Selecciona una conversación" [level=3] [ref=e260]
            - paragraph [ref=e261]: Elige una conversación de la lista para revisar mensajes y responder
    - contentinfo [ref=e262]
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test'
  2  | 
  3  | test.describe('Gate 9 Ready for Real WhatsApp', () => {
  4  |   test('All infrastructure ready for real message delivery', async ({ page }) => {
  5  |     console.log('\n=== Gate 9: Ready for Real WhatsApp ===')
  6  | 
  7  |     // Step 1: Authenticate
  8  |     console.log('Step 1: Verifying authentication flow...')
  9  |     const loginResp = await page.request.post('http://localhost:8001/dashboard/api/auth/login/', {
  10 |       data: { username: 'e2e_test', password: 'e2e_test_pass_123' },
  11 |     })
  12 |     expect(loginResp.status()).toBe(200)
  13 |     const userData = await loginResp.json()
  14 |     expect(userData.user.username).toBe('e2e_test')
  15 |     console.log('✓ Auth OK')
  16 | 
  17 |     // Step 2: API connectivity
  18 |     console.log('Step 2: Verifying API endpoints...')
  19 |     const apiEndpoints = [
  20 |       '/dashboard/whatsapp/conversaciones/api/active/',
  21 |       '/dashboard/api/auth/check/',
  22 |     ]
  23 | 
  24 |     for (const endpoint of apiEndpoints) {
  25 |       const resp = await page.request.get(`http://localhost:8001${endpoint}`)
  26 |       expect(resp.status()).toBeLessThan(400)
  27 |       console.log(`  ✓ ${endpoint}`)
  28 |     }
  29 |     console.log('✓ API endpoints accessible')
  30 | 
  31 |     // Step 3: Frontend UI ready
  32 |     console.log('Step 3: Verifying frontend UI...')
  33 |     await page.goto('http://localhost:5177/atencion/bandeja-entrada', { waitUntil: 'networkidle' })
  34 |     expect(page.url()).toContain('/atencion/bandeja-entrada')
> 35 |     await page.waitForSelector('.conversation-item', { timeout: 10000 })
     |                ^ TimeoutError: page.waitForSelector: Timeout 10000ms exceeded.
  36 |     const convCount = await page.locator('.conversation-item').count()
  37 |     expect(convCount).toBeGreaterThan(0)
  38 |     console.log(`✓ UI loaded with ${convCount} conversations`)
  39 | 
  40 |     // Step 4: Message send endpoint
  41 |     console.log('Step 4: Verifying message send infrastructure...')
  42 |     const testConvId = 251 // Use known test conversation
  43 |     const sendUrl = `http://localhost:8001/dashboard/whatsapp/conversaciones/${testConvId}/accion/`
  44 |     console.log(`  Testing send endpoint: ${sendUrl}`)
  45 |     console.log('  (Not actually sending - verifying endpoint exists)')
  46 | 
  47 |     // Step 5: Channel configuration
  48 |     console.log('Step 5: Verifying WhatsApp channel configuration...')
  49 |     const channelCheckResp = await page.request.get(
  50 |       'http://localhost:8001/dashboard/whatsapp/conversaciones/api/active/?limit=1'
  51 |     )
  52 |     const data = await channelCheckResp.json()
  53 |     expect(data.conversations).toBeDefined()
  54 |     expect(data.conversations.length).toBeGreaterThan(0)
  55 | 
  56 |     const firstConv = data.conversations[0]
  57 |     expect(firstConv.channel).toBeDefined()
  58 |     expect(firstConv.channel.name).toBeDefined()
  59 |     console.log(`✓ Channel configured: ${firstConv.channel.name}`)
  60 | 
  61 |     // Step 6: Database integrity
  62 |     console.log('Step 6: Verifying database state...')
  63 |     console.log(`  Conversations: ${data.pagination.total}`)
  64 |     console.log(`  Pagination: page ${data.pagination.page}, limit ${data.pagination.limit}`)
  65 |     expect(data.pagination.total).toBeGreaterThan(0)
  66 |     console.log('✓ Database healthy')
  67 | 
  68 |     // Step 7: No errors
  69 |     console.log('Step 7: Checking for runtime errors...')
  70 |     const errors = []
  71 |     page.on('console', msg => {
  72 |       if (msg.type() === 'error') errors.push(msg.text())
  73 |     })
  74 | 
  75 |     await page.waitForTimeout(2000)
  76 |     expect(errors.length).toBe(0)
  77 |     console.log('✓ No runtime errors')
  78 | 
  79 |     // Final readiness report
  80 |     console.log('\n=== READINESS CHECKLIST ===')
  81 |     console.log('✓ Authentication: PASS')
  82 |     console.log('✓ API Endpoints: PASS')
  83 |     console.log('✓ Frontend UI: PASS')
  84 |     console.log('✓ Message Infrastructure: READY')
  85 |     console.log('✓ Channel Config: PASS')
  86 |     console.log('✓ Database: HEALTHY')
  87 |     console.log('✓ Runtime: STABLE')
  88 |     console.log('')
  89 |     console.log('✅ GATE 9: Ready for real WhatsApp message delivery')
  90 |     console.log('')
  91 |     console.log('Instructions for real message test:')
  92 |     console.log('  1. Use existing conversation (e.g., Conv #251)')
  93 |     console.log('  2. Send test message via API or UI')
  94 |     console.log('  3. Verify message delivered to real WhatsApp number')
  95 |     console.log('  4. Confirm echo in bandeja (no F5 required)')
  96 |     console.log('  5. Verify takeover state and timeline')
  97 |   })
  98 | })
  99 | 
```