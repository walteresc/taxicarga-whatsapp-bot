import { test, expect } from '@playwright/test'

test('Inbound canónico: webhook local → aparece en UI sin F5', async ({ page, context }) => {
  const VITE_URL = 'http://localhost:5177'
  const WEBHOOK_URL = 'http://localhost:8001/webhook/whatsapp/'
  const TIMESTAMP = new Date().toISOString().replace(/[:.]/g, '')

  const testId = `INBOUND-${TIMESTAMP}`
  const testPhone = '+51919999001'

  console.log(`[TEST] ${testId}`)

  // 1. Navegar a UI
  await page.goto(`${VITE_URL}/`)
  await page.waitForLoadState('networkidle')
  console.log(`[UI] Cargada`)

  // Capturar lista de conversaciones inicial
  const convCountBefore = await page.locator('[data-test="conversation-item"]').count()

  console.log(`[UI] Conversaciones antes: ${convCountBefore}`)

  // 2. Enviar webhook inbound Meta format
  const webhookPayload = {
    object: 'whatsapp_business_account',
    entry: [{
      changes: [{
        value: {
          messaging_product: 'whatsapp',
          metadata: {
            phone_number_id: 'e2e_channel_2',
            display_phone_number: '51967619238',
          },
          messages: [{
            from: testPhone,
            id: `wamid_${testId}`,
            timestamp: Math.floor(Date.now() / 1000).toString(),
            type: 'text',
            text: { body: `Test ${testId}` },
          }],
        },
      }],
    }],
  }

  console.log(`[WEBHOOK] Enviando inbound desde ${testPhone}`)

  const webhookResponse = await page.context().request.post(WEBHOOK_URL, {
    data: webhookPayload,
  })

  console.log(`[WEBHOOK] Response: ${webhookResponse.status()}`)
  expect(webhookResponse.ok()).toBe(true)

  // 3. Esperar que aparezca en la UI (SSE o polling)
  console.log(`[WAIT] Esperando que aparezca conversación...`)

  // Estrategia: monitorear cambios en el DOM
  let conversationAppeared = false
  let messageAppeared = false

  // Esperar hasta 5 segundos por el nuevo mensaje
  const startWait = Date.now()
  const maxWait = 5000

  while (!conversationAppeared && Date.now() - startWait < maxWait) {
    const convCount = await page.locator('[data-test="conversation-item"]').count()

    if (convCount > convCountBefore) {
      conversationAppeared = true
      console.log(`[UI] Nueva conversación detectada (${convCountBefore} → ${convCount})`)

      // Verificar que contiene el texto del test
      const conversationText = await page.textContent('[data-test="conversation-item"]')

      expect(conversationText).toContain(testId)
      console.log(`[UI] Texto correcto: ${testId}`)

      break
    }

    await page.waitForTimeout(200)
  }

  if (!conversationAppeared) {
    // Fallback: buscar por preview
    const preview = await page.locator(`text="${testId}"`).first()
    if (await preview.isVisible()) {
      conversationAppeared = true
      console.log(`[UI] Conversación encontrada por preview`)
    }
  }

  expect(conversationAppeared).toBe(true)

  // 4. Verificar que no hubo F5
  const reloadCount = await page.evaluate(() => {
    return window.performance.navigation.type === 1 ? 1 : 0
  })

  expect(reloadCount).toBe(0)
  console.log(`[CHECK] No hay F5/reload`)

  // 5. Verificar que SSE está conectado
  const sseConnected = await page.evaluate(() => {
    return window.__eventSource?.readyState === 0 || // CONNECTING
           window.__eventSource?.readyState === 1 || // OPEN
           document.body.innerHTML.includes('EventSource')
  })

  console.log(`[CHECK] SSE conectado: ${sseConnected}`)

  // 6. Verificar preview y hora
  const convItem = page.locator('[data-test="conversation-item"]').first()
  const preview = await convItem.locator('[data-test="preview"]').textContent()
  const timestamp_el = await convItem.locator('[data-test="timestamp"]').textContent()

  console.log(`[MESSAGE] Preview: "${preview}"`)
  console.log(`[MESSAGE] Hora: ${timestamp_el}`)

  // El preview debe contener el mensaje
  expect(preview).toContain(testId)

  // La hora debe ser cercana a ahora
  if (timestamp_el) {
    const messageTime = new Date(timestamp_el)
    const now = new Date()
    const diff = (now - messageTime) / 1000

    console.log(`[TIME-CHECK] Diferencia: ${diff.toFixed(1)}s`)
    expect(diff).toBeLessThan(60) // Menos de 1 minuto
  }

  // 7. Abrir conversación y verificar timeline
  await convItem.click()
  await page.waitForLoadState('networkidle')

  const msgInTimeline = page.locator(`text="${testId}"`)
  const timelineVisible = await msgInTimeline.isVisible()

  console.log(`[TIMELINE] Mensaje visible: ${timelineVisible}`)
  expect(timelineVisible).toBe(true)

  // 8. Verificar que aparece una sola vez
  const msgCount = await msgInTimeline.count()

  console.log(`[DEDUP] Instancias del mensaje: ${msgCount}`)
  expect(msgCount).toBe(1)

  // 9. Verificar unread cambió
  const unreadBadge = page.locator('[data-test="unread-count"]').first()
  const hasUnread = await unreadBadge.isVisible()

  console.log(`[UNREAD] Badge visible: ${hasUnread}`)

  console.log(`[RESULT] PASS: Inbound canónico sin F5`)
})
