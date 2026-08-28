/**
 * Event Store for FASE 5B real-time updates - WITH STATE MACHINE (FASE A)
 *
 * States: idle | loading_snapshot | connecting_sse | sse_open | polling | reconnect_wait | stopped
 *
 * Invariants:
 * 1. Max one EventSource per store
 * 2. If EventSource exists in CONNECTING/OPEN, connect() returns
 * 3. initialize() is idempotent
 * 4. cleanup() closes EventSource, timers, polling
 * 5. Only one pollTimerId
 * 6. Only one reconnectTimerId
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useEventStore = defineStore('events', () => {
  // State
  const events = ref([])
  const lastCursor = ref('0')
  const state = ref('idle') // STATE MACHINE
  const sseError = ref(null)
  const pollError = ref(null)
  const lastEventTime = ref(null)
  const eventSource = ref(null)

  // Timers (SINGLE instances)
  let pollTimerId = null
  let reconnectTimerId = null

  // Intervals
  const pollInterval = ref(15000)
  const maxPollInterval = ref(30000)
  const reconnectBaseDelay = ref(1000) // 1s, backoff 2s, 5s, 10s, max 30s
  let reconnectAttempts = 0

  // FASE A1 DIAGNOSTICS
  const instanceId = Math.random().toString(36).substring(7)
  const connectionLog = ref([])
  const stateTransitions = ref([])

  const logConnection = (action, reason, details = {}) => {
    const timestamp = new Date().toISOString()
    const stack = new Error().stack?.split('\n').slice(2, 4).join(' | ') || ''

    connectionLog.value.push({
      instanceId,
      timestamp,
      action,
      reason,
      cursor: lastCursor.value,
      state: state.value,
      eventSourceReadyState: eventSource.value?.readyState ?? 'null',
      stack: stack.substring(0, 100),
      ...details,
    })
    console.log(`[CONN-${instanceId}] ${action} (${reason})`, details)
  }

  const transitionState = (newState, reason) => {
    const oldState = state.value
    if (oldState === newState) return
    state.value = newState
    stateTransitions.value.push({
      from: oldState,
      to: newState,
      reason,
      timestamp: new Date().toISOString(),
    })
    console.log(`[STATE] ${oldState} → ${newState} (${reason})`)
  }

  /**
   * FASE A2: Connect with guards
   */
  const connect = () => {
    logConnection('connect_entry', 'method_called', { currentState: state.value })

    // Guard: if SSE exists and is open/connecting, don't create another
    if (eventSource.value) {
      const readyState = eventSource.value.readyState
      if (readyState === EventSource.CONNECTING || readyState === EventSource.OPEN) {
        logConnection('connect_guard', 'sse_already_open', { readyState })
        console.warn(`[SSE] Guard: EventSource already ${readyState === 0 ? 'CONNECTING' : 'OPEN'}, skip`)
        
        return
      }
    }

    // Guard: idempotent - if state is not idle/reconnect_wait, return
    if (state.value !== 'idle' && state.value !== 'reconnect_wait') {
      logConnection('connect_guard', 'invalid_state', { currentState: state.value })
      console.warn(`[SSE] Guard: Invalid state ${state.value}, expected idle/reconnect_wait`)
      
      return
    }

    // Check cursor is valid
    if (lastCursor.value === '0') {
      logConnection('connect_blocked', 'cursor_is_zero')
      console.warn('[SSE] Cannot connect: cursor is 0, snapshot not loaded')
      
      return
    }

    transitionState('connecting_sse', 'connect_called')
    openSSE()
  }

  /**
   * FASE A4: Open SSE with cursor parameter (safe, not credential)
   */
  const openSSE = () => {
    if (eventSource.value) {
      logConnection('openSSE_skip', 'already_exists')
      
      return
    }

    try {
      const cursor = lastCursor.value
      const url = `/dashboard/whatsapp/api/events/stream/?cursor=${cursor}`

      logConnection('openSSE_create', 'creating_new', { cursor, url })
      console.log(`[SSE] Creating EventSource: cursor=${cursor}`)

      eventSource.value = new EventSource(url)

      // onopen: browser has received HTTP 200, connection stable
      eventSource.value.onopen = () => {
        logConnection('sse_onopen', 'connection_opened')
        transitionState('sse_open', 'sse_onopen_fired')
        sseError.value = null
        stopPolling() // Stop polling fallback when SSE recovers
        console.log('[SSE CP10] EventSource opened, readyState=1')
      }

      // Event listeners
      eventSource.value.addEventListener('message.created', handleSSEEvent)
      eventSource.value.addEventListener('conversation.created', handleSSEEvent)
      eventSource.value.addEventListener('conversation.updated', handleSSEEvent)
      eventSource.value.addEventListener('resync.required', handleResyncRequired)

      // Error handler: DOES NOT create new EventSource
      eventSource.value.onerror = () => {
        logConnection('sse_onerror', 'error_event_fired', {
          readyState: eventSource.value?.readyState,
        })

        sseOpen.value = false
        sseError.value = 'SSE disconnected'

        // DO NOT immediately create new EventSource
        // Let browser's native reconnection attempt work
        // Only close if completely failed
        if (eventSource.value && eventSource.value.readyState === EventSource.CLOSED) {
          logConnection('sse_closed', 'native_close', { readyState: 2 })
          eventSource.value.close()
          eventSource.value = null

          transitionState('polling', 'sse_failed_start_polling')
          startPolling()

          // Schedule manual reconnect with backoff
          scheduleReconnect()
        }
      }

    } catch (error) {
      logConnection('openSSE_error', 'exception', { error: error.message })
      console.error('[SSE] Exception opening EventSource:', error)
      sseError.value = error.message
      transitionState('polling', 'opensse_exception')
      startPolling()
    }
  }

  /**
   * FASE A3: Controlled reconnection with backoff
   */
  const scheduleReconnect = () => {
    if (reconnectTimerId) {
      logConnection('reconnect_already_scheduled', 'skip')
      
      return
    }

    const delays = [1000, 2000, 5000, 10000, 30000] // 1s, 2s, 5s, 10s, 30s max
    const delay = delays[Math.min(reconnectAttempts, delays.length - 1)]

    reconnectAttempts++

    logConnection('reconnect_scheduled', 'backoff', {
      attempt: reconnectAttempts,
      delayMs: delay,
    })

    transitionState('reconnect_wait', `reconnect_scheduled_in_${delay}ms`)

    reconnectTimerId = setTimeout(() => {
      logConnection('reconnect_timeout_fired', 'retrying')
      reconnectTimerId = null
      reconnectAttempts = 0

      if (state.value === 'reconnect_wait') {
        transitionState('connecting_sse', 'manual_reconnect')
        openSSE()
      }
    }, delay)
  }

  /**
   * Handle SSE event
   */
  const handleSSEEvent = event => {
    try {
      const data = JSON.parse(event.data)

      addEvent(data)
      lastEventTime.value = new Date()
    } catch (error) {
      console.error('Error parsing SSE event:', error)
    }
  }

  const handleResyncRequired = event => {
    console.warn('Server requesting resync - cursor too old')
    reconcileFromREST()
  }

  /**
   * Add event (deduped by ID)
   */
  const addEvent = event => {
    const exists = events.value.some(e => e.id === event.id)
    if (exists) {
      return
    }
    events.value.push(event)
    lastCursor.value = event.id
  }

  /**
   * REST polling fallback (SINGLE timer)
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
        },
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      if (data.events && data.events.length > 0) {
        data.events.forEach(addEvent)
      }

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
   * Start polling (ONLY ONE timer)
   */
  const startPolling = () => {
    if (pollTimerId || state.value === 'sse_open') {
      logConnection('polling_skip', 'already_polling_or_sse_open')
      
      return
    }

    transitionState('polling', 'start_polling')
    logConnection('polling_start', 'fallback_activated')

    const poll = async () => {
      try {
        await fetchEventsPoll()

        if (pollTimerId && state.value === 'polling') {
          pollTimerId = setTimeout(poll, pollInterval.value)
        }
      } catch (error) {
        if (pollTimerId && state.value === 'polling') {
          const nextInterval = Math.min(
            pollInterval.value * 1.5,
            maxPollInterval.value,
          )

          pollInterval.value = nextInterval
          pollTimerId = setTimeout(poll, nextInterval)
        }
      }
    }

    poll()
  }

  /**
   * Stop polling (SINGLE)
   */
  const stopPolling = () => {
    if (pollTimerId) {
      logConnection('polling_stop', 'requested')
      clearTimeout(pollTimerId)
      pollTimerId = null
      pollInterval.value = 15000 // Reset interval
      if (state.value === 'polling') {
        transitionState('sse_open', 'polling_stopped_sse_recovered')
      }
    }
  }

  /**
   * Reconcile state from REST (full sync)
   */
  const reconcileFromREST = async () => {
    try {
      const response = await fetch(
        `/dashboard/whatsapp/api/events/poll/?cursor=0`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          },
        },
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      const eventMap = new Map(events.value.map(e => [e.id, e]))

      data.events?.forEach(event => {
        eventMap.set(event.id, event)
      })

      events.value = Array.from(eventMap.values())

      if (data.latest_cursor) {
        lastCursor.value = data.latest_cursor
      }

      console.log('Reconciled from REST')
    } catch (error) {
      console.error('Reconciliation error:', error)
    }
  }

  /**
   * Close SSE
   */
  const closeSSE = () => {
    if (eventSource.value) {
      logConnection('sse_close', 'requested')
      eventSource.value.close()
      eventSource.value = null
    }
    sseOpen.value = false
  }

  /**
   * Initialize: IDEMPOTENT
   */
  const initialize = async () => {
    if (state.value !== 'idle') {
      logConnection('initialize_skip', 'not_idle', { currentState: state.value })
      console.log(`[Init] Already initialized (state=${state.value})`)
      
      return
    }

    transitionState('loading_snapshot', 'initialize_called')

    try {
      const response = await fetch('/dashboard/whatsapp/conversaciones/api/active/')
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      if (data.snapshot_cursor && data.snapshot_cursor !== '0') {
        lastCursor.value = data.snapshot_cursor
        logConnection('snapshot_loaded', 'cursor_set', { cursor: data.snapshot_cursor })
        console.log(`[Init] Snapshot cursor: ${data.snapshot_cursor}`)
      } else {
        throw new Error('No valid snapshot_cursor')
      }

      transitionState('idle', 'snapshot_loaded')
      connect()

    } catch (error) {
      logConnection('initialize_error', 'failed', { error: error.message })
      console.error('[Init] Error:', error)
      transitionState('idle', 'initialize_error')
    }
  }

  /**
   * Cleanup: IDEMPOTENT, closes everything
   */
  const cleanup = () => {
    logConnection('cleanup', 'called')

    closeSSE()
    stopPolling()

    if (reconnectTimerId) {
      clearTimeout(reconnectTimerId)
      reconnectTimerId = null
    }

    transitionState('stopped', 'cleanup_complete')
  }

  /**
   * Disconnect
   */
  const disconnect = () => {
    cleanup()
  }

  /**
   * Clear
   */
  const clear = () => {
    cleanup()
    events.value = []
    lastCursor.value = '0'
    sseError.value = null
    pollError.value = null
  }

  const sseOpen = computed(() => state.value === 'sse_open')
  const isPolling = computed(() => state.value === 'polling')
  const eventCount = computed(() => events.value.length)

  return {
    // State
    events,
    lastCursor,
    state,
    sseOpen,
    isPolling,
    sseError,
    pollError,
    lastEventTime,
    eventCount,

    // Methods
    initialize,
    connect,
    openSSE,
    closeSSE,
    cleanup,
    disconnect,
    clear,
    addEvent,
    startPolling,
    stopPolling,
    reconcileFromREST,

    // Diagnostics
    connectionLog,
    stateTransitions,
    instanceId,
  }
})
