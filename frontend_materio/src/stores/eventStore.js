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

  // IDEMPOTENT CONNECTION STATE
  let connectionPromise = null
  let connectionInProgress = false

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
   * Open SSE connection (IDEMPOTENT: never create duplicate EventSource)
   */
  const openSSE = () => {
    // GUARD: If EventSource already exists and is CONNECTING or OPEN, reuse it
    if (eventSource.value) {
      const readyState = eventSource.value.readyState
      if (readyState === EventSource.CONNECTING) {
        logConnection('openSSE', 'idempotent_reuse_connecting', { readyState })
        console.log(`[SSE] Guard: EventSource already CONNECTING (${readyState}), reusing`)
        return
      }
      if (readyState === EventSource.OPEN) {
        logConnection('openSSE', 'idempotent_reuse_open', { readyState })
        console.log(`[SSE] Guard: EventSource already OPEN (${readyState}), reusing`)
        return
      }
      // If CLOSED (2), close it and create new
      logConnection('openSSE', 'closing_dead_connection', { readyState })
      eventSource.value.close()
      eventSource.value = null
    }

    // GUARD: If sseOpen flag is true but EventSource is null, inconsistent state
    if (sseOpen.value) {
      logConnection('openSSE', 'guard_sseOpen_true_inconsistent')
      console.warn('[SSE] Guard: sseOpen=true but no EventSource, resetting flag')
      sseOpen.value = false
    }

    try {
      // Use relative URL so Vite proxy handles as same-origin in dev
      const cursor = lastCursor.value || '0'
      const url = `/dashboard/whatsapp/api/events/stream/?cursor=${cursor}`

      logConnection('openSSE', 'creating_new', { cursor })
      console.log(`[SSE] Creating EventSource: cursor=${cursor}, url=${url}`)
      eventSource.value = new EventSource(url, { withCredentials: true })
      console.log(`[SSE] EventSource created, readyState=${eventSource.value.readyState}`)

      // SSE event types from backend
      eventSource.value.addEventListener('message.created', handleSSEEvent)
      eventSource.value.addEventListener('conversation.created', handleSSEEvent)
      eventSource.value.addEventListener('conversation.updated', handleSSEEvent)

      // SSE event: resync.required
      eventSource.value.addEventListener('resync.required', handleResyncRequired)

      // SSE event: error (will fire if 401, 403, 500, etc.)
      eventSource.value.addEventListener('error', handleSSEError)

      // Standard SSE open (fires when HTTP 200 + Content-Type: text/event-stream received)
      eventSource.value.onopen = () => {
        sseOpen.value = true
        sseError.value = null
        stopPolling() // CRITICAL: Stop polling when SSE connects
        logConnection('openSSE', 'onopen_called')
        console.log('[REALTIME CP10] SSE connection opened, readyState=1, polling stopped')
      }
    } catch (error) {
      console.error('Failed to open SSE:', error)
      sseError.value = error.message
      logConnection('openSSE', 'exception_caught', { error: error.message })
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
   * Subscriber management (PASO 3: explicit subscription instead of watch)
   */
  const subscribers = new Set()

  const subscribe = (handler) => {
    subscribers.add(handler)
    console.log(`[eventStore.subscribe] Added handler, total subscribers: ${subscribers.size}`)

    // Return unsubscribe function
    return () => {
      subscribers.delete(handler)
      console.log(`[eventStore.subscribe] Removed handler, total subscribers: ${subscribers.size}`)
    }
  }

  const notifySubscribers = (event) => {
    console.log(`[eventStore.notifySubscribers] Event ${event.type} to ${subscribers.size} subscribers`)
    for (const handler of subscribers) {
      try {
        handler(event)
      } catch (error) {
        console.error('[eventStore.notifySubscribers] Handler failed:', error.message)
      }
    }
  }

  /**
   * Add event (deduped by ID)
   */
  const addEvent = (event) => {
    // Check if event already exists
    const exists = events.value.some(e => e.id === event.id)
    if (exists) {
      console.log(`[eventStore.addEvent] Duplicate event ${event.id}, skipping`)
      return
    }

    console.log(`[eventStore.addEvent] Adding event ${event.id} type=${event.type}`)
    events.value.push(event)
    lastCursor.value = event.id

    // PASO 3: Notify subscribers AFTER dedup check and array update
    notifySubscribers(event)
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
   * Start polling (only as fallback) — IDEMPOTENT
   */
  const startPolling = () => {
    // GUARD: Don't start if already polling or SSE is open
    if (isPolling.value) {
      logConnection('startPolling', 'already_polling')
      console.log('[POLLING] Already polling, skipping')
      return
    }

    if (sseOpen.value) {
      logConnection('startPolling', 'sse_open_no_need_polling')
      console.log('[POLLING] SSE open, no need for polling fallback')
      return
    }

    isPolling.value = true
    logConnection('startPolling', 'started')
    console.log('[POLLING] Starting event polling (SSE fallback)')

    const poll = async () => {
      try {
        await fetchEventsPoll()

        // On success, keep polling at regular interval
        if (isPolling.value && !sseOpen.value) {
          pollTimerId = setTimeout(poll, pollInterval.value)
        } else if (isPolling.value && sseOpen.value) {
          // SSE opened while polling, stop polling
          console.log('[POLLING] SSE connected during polling, stopping polling')
          stopPolling()
        }
      } catch (error) {
        // On error, back off gradually (but only if still polling)
        if (isPolling.value && !sseOpen.value) {
          const nextInterval = Math.min(
            pollInterval.value * 1.5,
            maxPollInterval.value
          )
          pollInterval.value = nextInterval
          console.log(`[POLLING] Error, backing off to ${nextInterval}ms`)
          pollTimerId = setTimeout(poll, nextInterval)
        }
      }
    }

    // Start polling immediately
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
   * COMPLETELY IDEMPOTENT: multiple calls return same promise, single connection
   */
  const connect = async () => {
    console.log('[eventStore.connect] Called. lastCursor=' + lastCursor.value)

    // IDEMPOTENT: If connection is in progress, return existing promise
    if (connectionPromise) {
      console.log('[eventStore.connect] Connection in progress, returning existing promise')
      logConnection('connect', 'idempotent_return_existing_promise')
      return await connectionPromise
    }

    // IDEMPOTENT: If already connected, return immediately
    if (sseOpen.value || isPolling.value) {
      console.log('[eventStore.connect] Already connected (SSE open or polling), returning')
      logConnection('connect', 'idempotent_already_connected')
      return Promise.resolve()
    }

    // Guard: cursor=0 no permitido
    if (lastCursor.value === '0' || lastCursor.value === '') {
      const error = 'Invalid cursor'
      console.error('[eventStore.connect] REJECTED: cursor is invalid:', lastCursor.value)
      logConnection('connect', 'rejected_invalid_cursor', { cursor: lastCursor.value })
      return Promise.reject(new Error(error))
    }

    // Guard: cursor debe tener formato válido
    if (!/^\d+-\d+$/.test(lastCursor.value)) {
      const error = 'Cursor format invalid'
      console.error('[eventStore.connect] REJECTED: cursor format invalid:', lastCursor.value)
      logConnection('connect', 'rejected_invalid_format', { cursor: lastCursor.value })
      return Promise.reject(new Error(error))
    }

    // Create connection promise to prevent parallel connections
    connectionPromise = (async () => {
      connectionInProgress = true
      try {
        console.log('[eventStore.connect] Opening SSE with cursor=' + lastCursor.value + '...')
        logConnection('connect', 'opening_sse', { cursor: lastCursor.value })
        openSSE()

        // Wait for SSE to open OR timeout and fallback to polling
        await new Promise((resolve) => {
          const checkInterval = setInterval(() => {
            if (sseOpen.value || isPolling.value) {
              clearInterval(checkInterval)
              resolve()
            }
          }, 100)

          // Timeout after 5 seconds: start polling fallback
          setTimeout(() => {
            clearInterval(checkInterval)
            if (!sseOpen.value && !isPolling.value) {
              console.log('[eventStore.connect] SSE not open after 5s, starting polling fallback')
              logConnection('connect', 'timeout_starting_polling')
              startPolling()
            }
            resolve()
          }, 5000)
        })

        console.log('[eventStore.connect] Connection established')
        logConnection('connect', 'connection_established')
      } catch (error) {
        console.error('[eventStore.connect] Connection error:', error)
        logConnection('connect', 'connection_error', { error: error.message })
        throw error
      } finally {
        connectionInProgress = false
        connectionPromise = null  // Reset for potential future reconnections
      }
    })()

    return await connectionPromise
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
   * Shutdown: clean up connections completely
   */
  const disconnect = () => {
    logConnection('disconnect', 'called')
    console.log('[eventStore.disconnect] Shutting down all connections')

    // Close SSE
    closeSSE()

    // Stop polling
    stopPolling()

    // Reset connection state
    connectionPromise = null
    connectionInProgress = false

    console.log('[eventStore.disconnect] All connections closed')
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
    setSnapshotCursor,

    // PASO 3: Explicit subscription
    subscribe,
    notifySubscribers,
  }
})
