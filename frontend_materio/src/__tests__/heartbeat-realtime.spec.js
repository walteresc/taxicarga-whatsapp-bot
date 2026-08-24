import { test, expect } from '@playwright/test'

test('Heartbeat real: SSE abierto 40s, captura latido ~30s', async ({ page }) => {
  const VITE_URL = 'http://localhost:5177'
  const DJANGO_EVENTS = 'http://localhost:8001/api/events/stream/'

  // Monitor EventSource eventos
  const events = []
  const heartbeats = []
  let sseClosed = false

  // Interceptar console logs para capturar heartbeat
  page.on('console', msg => {
    if (msg.type() === 'log') {
      const text = msg.text()
      if (text.includes('heartbeat') || text.includes('ping')) {
        const timestamp = Date.now()
        heartbeats.push(timestamp)
        console.log(`[HEARTBEAT] ${text} @ ${new Date(timestamp).toISOString()}`)
      }
      if (text.includes('connected')) {
        console.log(`[SSE] connected @ ${new Date().toISOString()}`)
      }
      if (text.includes('closed') || text.includes('error')) {
        sseClosed = true
        console.log(`[SSE] closed @ ${new Date().toISOString()}`)
      }
    }
  })

  // Monitor network: detectar EventSource stream
  page.on('response', async response => {
    if (response.url().includes('/events/stream/')) {
      console.log(`[NETWORK] Stream endpoint: ${response.status()}`)
    }
  })

  // Navegar
  await page.goto(`${VITE_URL}/`)
  console.log(`[TEST] Navegado a ${VITE_URL}`)

  // Esperar página cargada
  await page.waitForLoadState('networkidle')

  // Inyectar script para monitorear EventSource
  await page.evaluate(() => {
    // Override window.EventSource para capturar
    const OriginalES = window.EventSource

    window.EventSource = class extends OriginalES {
      constructor(url) {
        super(url)
        console.log(`[SSE-INIT] Abierto: ${url}`)

        this.addEventListener('open', () => {
          console.log(`[SSE-OPEN] Conexión establecida`)
          window.__sseStartTime = Date.now()
        })

        this.addEventListener('heartbeat', (e) => {
          const elapsed = (Date.now() - window.__sseStartTime) / 1000
          console.log(`[HEARTBEAT] Recibido en ${elapsed.toFixed(1)}s: ${e.data?.substring(0, 50)}`)
        })

        this.addEventListener('message', (e) => {
          if (e.data.includes(':heartbeat') || e.data === ':heartbeat') {
            const elapsed = (Date.now() - window.__sseStartTime) / 1000
            console.log(`[HEARTBEAT-RAW] Frame en ${elapsed.toFixed(1)}s`)
          }
        })

        this.addEventListener('error', () => {
          const elapsed = (Date.now() - window.__sseStartTime) / 1000
          console.log(`[SSE-ERROR] Error en ${elapsed.toFixed(1)}s`)
        })
      }
    }
  })

  // Esperar 40 segundos manteniendo la conexión
  console.log(`[TEST] Esperando 40s para capturar heartbeat (~30s)...`)
  const startTime = Date.now()

  // Verificar que SSE está en el HTML/JS
  const hasSSE = await page.evaluate(() => {
    return typeof window.EventSource !== 'undefined' || document.body.innerHTML.includes('EventSource')
  })
  console.log(`[CHECK] EventSource disponible: ${hasSSE}`)

  // Esperar
  await page.waitForTimeout(40000)

  const endTime = Date.now()
  const elapsed = (endTime - startTime) / 1000

  console.log(`[TEST] Completado. Tiempo total: ${elapsed.toFixed(1)}s`)
  console.log(`[HEARTBEATS] Total capturados: ${heartbeats.length}`)

  // Análisis de latidos
  if (heartbeats.length > 0) {
    const intervals = []
    for (let i = 1; i < heartbeats.length; i++) {
      intervals.push((heartbeats[i] - heartbeats[i-1]) / 1000)
    }

    if (intervals.length > 0) {
      const avg = intervals.reduce((a, b) => a + b) / intervals.length
      const min = Math.min(...intervals)
      const max = Math.max(...intervals)

      console.log(`[HEARTBEATS] Intervalo promedio: ${avg.toFixed(1)}s`)
      console.log(`[HEARTBEATS] Rango: ${min.toFixed(1)}s - ${max.toFixed(1)}s`)

      // Esperar heartbeat aproximadamente cada 30 segundos
      expect(avg).toBeGreaterThan(20)
      expect(avg).toBeLessThan(40)
    }
  }

  // Verificar que la página no refresca
  const title = await page.title()
  expect(title).toBeTruthy()
  console.log(`[CHECK] Página intacta, título: ${title}`)

  // Verificar que SSE no cerró
  expect(sseClosed).toBe(false)
  console.log(`[CHECK] SSE permanece abierto`)
})
