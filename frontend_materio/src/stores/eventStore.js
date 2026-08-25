/**
 * Event Store for FASE 5B real-time updates
 *
 * Primary: SSE (Server-Sent Events) for streaming
 * Fallback: REST polling if SSE fails
 * Resync: REST reconciliation if events are missed
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useEventStore = defineStore('events', () => {
  // State
  const events = ref([])
  const lastCursor = ref('0')
  const sseOpen = ref(false)
  const isPolling = ref(false)
  const pollInterval = ref(15000) // Fallback: 15 seconds
  const maxPollInterval = ref(30000) // Max 30 seconds
  const sseError = ref(null)
  const pollError = ref(null)
  const lastEventTime = ref(null)
  const eventSource = ref(null)

  // Polling state (only used as fallback)
  let pollTimerId = null

  // FASE 1 DIAGNOSTICS: Track all EventSource instances
  const instanceId = Math.random().toString(36).substring(7)
  const connectionLog = ref([])

  const logConnection = (action, reason, details = {}) => {
    const timestamp = new Date().toISOString()
    const stack = new Error().stack?.split('\n').slice(2, 5).join(' | ') || ''
    const entry = {
      instanceId,
      timestamp,
      action,
      reason,
      cursor: lastCursor.value,
      eventSourceState: eventSource.value?.readyState ?? 'null',
      isPolling: isPolling.value,
      stack: stack.substring(0, 80),
      ...details
    }
    connectionLog.value.push(entry)
    console.log(`[CONN-LOG] ${action} (${reason})`, entry)
  }

  /**
   * Open SSE connection (FASE A2: with guards)
   */
  const openSSE = () => {
    // FASE A2: Guard against duplicate connections
    if (eventSource.value) {
      const readyState = eventSource.value.readyState
      if (readyState === EventSource.CONNECTING || readyState === EventSource.OPEN) {
        logConnection('openSSE', 'guard_prevented_duplicate', { readyState })
        console.warn(`[SSE] Guard: EventSource exists in state ${readyState}`)
        return
      }
    }

    if (sseOpen.value) {
      logConnection('openSSE', 'guard_sseOpen_true')
      return
    }

    try {
      // Use relative URL so Vite proxy handles as same-origin in dev
      // Production: Vite build outputs static files, nginx proxy handles /dashboard → backend
      const cursor = lastCursor.value || '0'
      const url = `/dashboard/whatsapp/api/events/stream/?cursor=${cursor}`

      logConnection('openSSE', 'creating_new', { cursor })
      console.log(`[SSE] Creating EventSource: cursor=${cursor}, url=${url}`)
      eventSource.value = new EventSource(url, { withCredentials: true })
      console.log(`[SSE] EventSource opened, readyState=${eventSource.value.readyState}`)

      // SSE event types from backend
      eventSource.value.addEventListener('message.created', handleSSEEvent)
      eventSource.value.addEventListener('conversation.created', handleSSEEvent)
      eventSource.value.addEventListener('conversation.updated', handleSSEEvent)

      // SSE event: resync.required
      eventSource.value.addEventListener('resync.required', handleResyncRequired)

      // SSE event: error
      eventSource.value.addEventListener('error', handleSSEError)

      // Standard SSE open
      eventSource.value.onopen = () => {
        sseOpen.value = true
        sseError.value = null
        stopPolling() // Stop polling when SSE connects
        console.log('[REALTIME CP10] SSE connection opened, readyState=1')
        console.log('SSE connected')
      }
    } catch (error) {
      console.error('Failed to open SSE:', error)
      sseError.value = error.message
      startPolling() // Fall back to polling
    }
  }

  /**
   * Handle SSE event
   */
  const handleSSEEvent = (event) => {
    try {
      const data = JSON.parse(event.data)
      addEvent(data)
      lastEventTime.value = new Date()
    } catch (error) {
      console.error('Error parsing SSE event:', error)
    }
  }

  /**
   * Handle resync request from server
   */
  const handleResyncRequired = (event) => {
    console.warn('Server requesting resync - cursor too old')
    // Fetch full state from REST
    reconcileFromREST()
  }

  /**
   * Handle SSE errors
   */
  const handleSSEError = (error) => {
    console.error('SSE error:', error)
    sseOpen.value = false
    sseError.value = 'SSE disconnected'

    // Close connection
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
    }

    // Fall back to polling
    startPolling()
  }

  /**
   * Add event (deduped by ID)
   */
  const addEvent = (event) => {
    // Check if event already exists
    const exists = events.value.some(e => e.id === event.id)
    if (exists) {
      return
    }

    events.value.push(event)
    lastCursor.value = event.id
  }

  /**
   * Fallback: REST polling for events
   */
  const fetchEventsPoll = async () => {
    try {
      const params = new URLSearchParams({
        cursor: lastCursor.value,
      })

      const response = await fetch(
        `/dashboard/whatsapp/api/events/poll/?${params}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          },
        }
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      // Add new events
      if (data.events && data.events.length > 0) {
        data.events.forEach(addEvent)
      }

      // Update cursor
      if (data.latest_cursor) {
        lastCursor.value = data.latest_cursor
      }

      pollError.value = null
      lastEventTime.value = new Date()

      return data.events?.length || 0
    } catch (error) {
      pollError.value = error.message
      console.error('Event polling error:', error)
      throw error
    }
  }

  /**
   * Start polling (only as fallback)
   */
  const startPolling = () => {
    if (isPolling.value || sseOpen.value) {
      return
    }

    isPolling.value = true
    console.log('Starting event polling (SSE fallback)')

    const poll = async () => {
      try {
        await fetchEventsPoll()

        // On success, keep polling at regular interval
        if (isPolling.value) {
          pollTimerId = setTimeout(poll, pollInterval.value)
        }
      } catch (error) {
        // On error, back off gradually
        if (isPolling.value) {
          const nextInterval = Math.min(
            pollInterval.value * 1.5,
            maxPollInterval.value
          )
          pollInterval.value = nextInterval
          pollTimerId = setTimeout(poll, nextInterval)
        }
      }
    }

    // Start immediately, then repeat
    poll()
  }

  /**
   * Stop polling
   */
  const stopPolling = () => {
    if (pollTimerId) {
      clearTimeout(pollTimerId)
      pollTimerId = null
    }
    isPolling.value = false
  }

  /**
   * Reconcile state from REST (full sync)
   */
  const reconcileFromREST = async () => {
    try {
      // Reset cursor to get all events
      const response = await fetch(
        `/dashboard/whatsapp/api/events/poll/?cursor=0`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          },
        }
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      // Rebuild event list (dedup by ID)
      const eventMap = new Map(events.value.map(e => [e.id, e]))

      data.events?.forEach(event => {
        eventMap.set(event.id, event)
      })

      events.value = Array.from(eventMap.values())

      // Update cursor
      if (data.latest_cursor) {
        lastCursor.value = data.latest_cursor
      }

      console.log('Reconciled from REST')
    } catch (error) {
      console.error('Reconciliation error:', error)
    }
  }

  /**
   * Close SSE connection
   */
  const closeSSE = () => {
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
    }
    sseOpen.value = false
  }

  /**
   * Startup: try SSE, fallback to polling
   * PASO 3: Validación estricta del cursor
   * Requiere que caller establezca lastCursor válido antes de llamar connect()
   */
  const connect = () => {
    console.log('[eventStore.connect] Called. lastCursor=' + lastCursor.value)

    // Guard: cursor=0 no permitido
    if (lastCursor.value === '0' || lastCursor.value === '') {
      console.error('[eventStore.connect] REJECTED: cursor is invalid:', lastCursor.value)
      return
    }

    // Guard: cursor debe tener formato válido
    if (!/^\d+-\d+$/.test(lastCursor.value)) {
      console.error('[eventStore.connect] REJECTED: cursor format invalid:', lastCursor.value)
      return
    }

    console.log('[eventStore.connect] Opening SSE with cursor=' + lastCursor.value + '...')
    openSSE()

    // Also start polling as fallback (will stop when SSE connects)
    setTimeout(() => {
      if (!sseOpen.value) {
        console.log('[eventStore.connect] SSE not open after 5s, starting polling fallback')
        startPolling()
      }
    }, 5000)
  }

  /**
   * Set cursor from API snapshot (critical for SSE coherence)
   */
  const setSnapshotCursor = (cursor) => {
    const oldCursor = lastCursor.value
    lastCursor.value = cursor || '0'
    console.log('[eventStore.setSnapshotCursor] Set from "' + oldCursor + '" to "' + lastCursor.value + '"')
  }

  /**
   * Shutdown: clean up connections
   */
  const disconnect = () => {
    closeSSE()
    stopPolling()
  }

  /**
   * Get events of specific type
   */
  const getEventsByType = (type) => {
    return events.value.filter(e => e.type === type)
  }

  /**
   * Get conversation-related events
   */
  const getConversationEvents = (conversationId) => {
    return events.value.filter(
      e => e.data?.conversation_id === conversationId
    )
  }

  /**
   * Clear all events (for testing)
   */
  const clear = () => {
    events.value = []
    lastCursor.value = '0'
    closeSSE()
    stopPolling()
    sseError.value = null
    pollError.value = null
  }

  // Computed
  const eventCount = computed(() => events.value.length)
  const isConnected = computed(() => sseOpen.value || isPolling.value)
  const connectionStatus = computed(() => {
    if (sseOpen.value) return 'connected_sse'
    if (isPolling.value) return 'connected_polling'
    return 'disconnected'
  })

  return {
    // State
    events,
    lastCursor,
    sseOpen,
    isPolling,
    sseError,
    pollError,
    lastEventTime,
    connectionStatus,

    // Computed
    eventCount,
    isConnected,

    // Methods
    addEvent,
    connect,
    disconnect,
    openSSE,
    closeSSE,
    startPolling,
    stopPolling,
    fetchEventsPoll,
    reconcileFromREST,
    getEventsByType,
    getConversationEvents,
    clear,
    setSnapshotCursor,  // NUEVA: establecer cursor desde snapshot API
  }
})
