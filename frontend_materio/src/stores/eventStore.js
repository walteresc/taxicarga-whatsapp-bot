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

  // RECONNECTION STATE (MANUAL strategy)
  let reconnectionTimer = null
  let reconnectionAttempt = 0
  let isDisconnecting = false // Flag to distinguish logout/unmount from error

  // FASE 1 DIAGNOSTICS: Track all EventSource instances
  const instanceId = Math.random().toString(36).substring(7)
  const connectionLog = ref([])

  // TRABAJO A: Real-time event diagnostics
  const diagnostics = {
    instanceId,
    connectionState: 'initial',
    lastCursor: '0',
    receivedEvents: [],      // All events received from SSE
    dispatchedEvents: [],    // Events dispatched to subscribers
    handledEvents: [],       // Events successfully handled by processEvent
    subscriberCount: 0,
    sseConnectionCount: 0,
    upsertCount: 0,          // Counter of messagesStore.upsertMessage calls
    // Runtime state (updated live)
    sseOpen: false,
    isPolling: false,
    sseError: null,
    pollError: null,
    eventSourceUrl: null,
    eventSourceReadyState: null,
  }

  // Expose diagnostics globally
  if (typeof window !== 'undefined') {
    if (!window.__WHATSAPP_REALTIME_DIAGNOSTICS__) {
      window.__WHATSAPP_REALTIME_DIAGNOSTICS__ = {}
    }
    window.__WHATSAPP_REALTIME_DIAGNOSTICS__[instanceId] = diagnostics
  }

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
      ...details,
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

      // Expose URL and readyState to diagnostics
      diagnostics.eventSourceUrl = url
      diagnostics.eventSourceReadyState = eventSource.value.readyState

      console.log(`[SSE] EventSource created, readyState=${eventSource.value.readyState}`)

      // SSE event types from backend
      // CP16 FIX: Create typed handlers to preserve event.type in data
      const createEventHandler = eventType => {
        return event => {
          try {
            const data = JSON.parse(event.data)


            // CP16: Add event type to data so subscribers know which event it is
            data.type = eventType
            data.event_id = event.lastEventId || '0'  // Rename: event_id (not id) to avoid confusion with conversation_id
            console.log(`[CP16-Handler] ${eventType} received, event_id=${data.event_id}`)
            addEvent(data)
            lastEventTime.value = new Date()
          } catch (error) {
            console.error(`[CP16-Handler] Error parsing ${eventType}:`, error)
          }
        }
      }

      eventSource.value.addEventListener('message.created', createEventHandler('message.created'))
      // message.updated: published when async media (inbound download or CRM
      // upload) finishes AFTER the message.created snapshot already went out
      // without it. EventSource requires its own explicit listener per named
      // SSE event — without this line these events are silently dropped.
      eventSource.value.addEventListener('message.updated', createEventHandler('message.updated'))
      eventSource.value.addEventListener('conversation.created', createEventHandler('conversation.created'))
      eventSource.value.addEventListener('conversation.updated', createEventHandler('conversation.updated'))

      // SSE event: resync.required
      eventSource.value.addEventListener('resync.required', handleResyncRequired)

      // SSE event: error (will fire if 401, 403, 500, etc.)
      eventSource.value.addEventListener('error', handleSSEError)

      // Standard SSE open (fires when HTTP 200 + Content-Type: text/event-stream received)
      eventSource.value.onopen = () => {
        sseOpen.value = true
        sseError.value = null
        diagnostics.sseOpen = true
        diagnostics.sseError = null
        diagnostics.eventSourceReadyState = 1

        // Cancel any pending reconnection timer (since we're now connected)
        if (reconnectionTimer) {
          clearTimeout(reconnectionTimer)
          reconnectionTimer = null
        }

        // Reset reconnection attempt counter on successful connection
        reconnectionAttempt = 0

        stopPolling() // CRITICAL: Stop polling when SSE connects
        diagnostics.isPolling = false
        logConnection('openSSE', 'onopen_called')
        console.log('[REALTIME CP10] SSE connection opened, readyState=1, polling stopped, attempt counter reset')
      }
    } catch (error) {
      console.error('Failed to open SSE:', error)
      sseError.value = error.message
      logConnection('openSSE', 'exception_caught', { error: error.message })
      startPolling() // Fall back to polling
    }
  }

  /**
   * Handle resync request from server
   */
  const handleResyncRequired = event => {
    console.warn('Server requesting resync - cursor too old')

    // Fetch full state from REST
    reconcileFromREST()
  }

  /**
   * Handle SSE errors (MANUAL RECONNECTION STRATEGY)
   */
  const handleSSEError = error => {
    console.error('[handleSSEError] SSE error:', error)
    sseOpen.value = false
    sseError.value = 'SSE disconnected'
    diagnostics.sseOpen = false
    diagnostics.sseError = error?.message || 'SSE disconnected'
    diagnostics.eventSourceReadyState = eventSource.value?.readyState ?? 2
    logConnection('handleSSEError', 'error_event_fired', { error: error?.message, isDisconnecting })

    // If this is a deliberate disconnect (logout/unmount), don't reconnect
    if (isDisconnecting) {
      console.log('[handleSSEError] Deliberate disconnect detected, not reconnecting')
      if (eventSource.value) {
        eventSource.value.close()
        eventSource.value = null
      }
      
      return
    }

    // Close the broken connection
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
    }

    // Clear any pending connection promise/in-progress state
    connectionPromise = null
    connectionInProgress = false

    // Cancel any pending reconnection timer
    if (reconnectionTimer) {
      clearTimeout(reconnectionTimer)
      reconnectionTimer = null
    }

    // Schedule reconnection with exponential backoff
    const backoffMs = Math.min(1000 * Math.pow(2, reconnectionAttempt), 30000)

    reconnectionAttempt += 1

    console.log(`[handleSSEError] Scheduling reconnection attempt ${reconnectionAttempt} after ${backoffMs}ms`)
    logConnection('handleSSEError', 'scheduling_reconnect', { attempt: reconnectionAttempt, backoffMs })

    reconnectionTimer = setTimeout(() => {
      if (!isDisconnecting && !sseOpen.value) {
        console.log('[handleSSEError] Executing reconnection attempt', { attempt: reconnectionAttempt, cursor: lastCursor.value })
        logConnection('handleSSEError', 'executing_reconnect', { attempt: reconnectionAttempt })

        connect().catch(err => {
          console.error('[handleSSEError] Reconnect failed:', err)

          // Don't start polling yet, let error handler schedule next retry
          // This will trigger handleSSEError again, which schedules next retry
        })
      }
      reconnectionTimer = null
    }, backoffMs)
  }

  /**
   * Subscriber management (PASO 3: explicit subscription instead of watch)
   */
  const subscribers = new Set()

  const subscribe = handler => {
    subscribers.add(handler)
    diagnostics.subscriberCount = subscribers.size
    console.log(`[eventStore.subscribe] Added handler, total subscribers: ${subscribers.size}`)

    // Return unsubscribe function
    return () => {
      subscribers.delete(handler)
      diagnostics.subscriberCount = subscribers.size
      console.log(`[eventStore.subscribe] Removed handler, total subscribers: ${subscribers.size}`)
    }
  }

  const notifySubscribers = event => {
    console.log(`[eventStore.notifySubscribers] Event ${event.type} (event_id=${event.event_id}) to ${subscribers.size} subscribers`)

    // TRABAJO A: Record dispatch
    diagnostics.dispatchedEvents.push({
      id: event.event_id,
      type: event.type,
      message_id: event.message_id,
      conversation_id: event.conversation_id,
      replay_of: event.replay_of,
      timestamp: new Date().toISOString(),
    })

    for (const handler of subscribers) {
      try {
        handler(event)
      } catch (error) {
        console.error('[eventStore.notifySubscribers] Handler failed:', error.message, error.stack)

        // Record handler errors in diagnostics for debugging
        if (!diagnostics.handlerErrors) diagnostics.handlerErrors = []
        diagnostics.handlerErrors.push({
          event_id: event.event_id,
          event_type: event.type,
          error_message: error.message,
          error_stack: error.stack?.substring(0, 200),
          timestamp: new Date().toISOString(),
        })
      }
    }
  }

  /**
   * Add event (deduped by ID)
   */
  const addEvent = event => {
    // TRABAJO A: Record received event
    diagnostics.receivedEvents.push({
      id: event.event_id,
      type: event.type,
      message_id: event.message_id,
      conversation_id: event.conversation_id,
      replay_of: event.replay_of,
      timestamp: new Date().toISOString(),
    })

    // BUG 2 FIX: Protect against events with null/undefined/empty IDs
    if (!event.event_id || event.event_id === '' || event.event_id === '0') {
      console.warn('[eventStore.addEvent] Event without valid id (undefined/null/empty), processing anyway for diagnostics')
      if (!diagnostics.nullIdEvents) diagnostics.nullIdEvents = []
      diagnostics.nullIdEvents.push({
        type: event.type,
        message_id: event.message_id,
        conversation_id: event.conversation_id,
        timestamp: new Date().toISOString(),
      })
      // Don't dedup: process it anyway
      events.value.push(event)
      notifySubscribers(event)
      return
    }

    // Check if event already exists (dedup by event_id)
    const exists = events.value.some(e => e.event_id === event.event_id)
    if (exists) {
      console.log(`[eventStore.addEvent] Duplicate event ${event.event_id}, skipping`)

      return
    }

    console.log(`[eventStore.addEvent] Adding event ${event.event_id} type=${event.type} message_id=${event.message_id} replay_of=${event.replay_of || 'N/A'}`)
    events.value.push(event)
    // BUG 3 FIX: Update cursor with event_id so it advances
    lastCursor.value = event.event_id
    diagnostics.lastCursor = event.event_id

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
        },
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
      diagnostics.pollError = null
      lastEventTime.value = new Date()

      return data.events?.length || 0
    } catch (error) {
      pollError.value = error.message
      diagnostics.pollError = error.message
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
    diagnostics.isPolling = true
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
            maxPollInterval.value,
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
    diagnostics.isPolling = false
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
        },
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      // Rebuild event list (dedup by event_id)
      const eventMap = new Map(events.value.map(e => [e.event_id, e]))

      data.events?.forEach(event => {
        eventMap.set(event.event_id, event)
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

    // Reset disconnect flag when connecting (allows reconnection after logout/unmount)
    isDisconnecting = false

    // IDEMPOTENT: If connection is in progress, return existing promise
    if (connectionPromise) {
      console.log('[eventStore.connect] Connection in progress, returning existing promise')
      logConnection('connect', 'idempotent_return_existing_promise')
      
      return await connectionPromise
    }

    // IDEMPOTENT: If already connected (SSE OPEN), return immediately
    // Note: isPolling.value alone should NOT block, since polling is fallback
    if (sseOpen.value) {
      console.log('[eventStore.connect] Already connected via SSE (readyState=OPEN), returning')
      logConnection('connect', 'idempotent_already_connected_sse')
      
      return Promise.resolve()
    }

    // Allow reconnection even if polling is active (will stop polling on SSE open)
    if (isPolling.value && eventSource.value && eventSource.value.readyState !== 2) {
      console.log('[eventStore.connect] Polling active but EventSource not CLOSED, returning')
      logConnection('connect', 'idempotent_polling_active')
      
      return Promise.resolve()
    }

    // Guard: cursor must be valid (allow '0' for fresh start, require digits-digits format otherwise)
    if (lastCursor.value === null || lastCursor.value === undefined || lastCursor.value === '') {
      const error = 'Cursor is null, undefined, or empty'

      console.error('[eventStore.connect] REJECTED: cursor invalid:', lastCursor.value)
      logConnection('connect', 'rejected_invalid_cursor', { cursor: lastCursor.value })
      
      return Promise.reject(new Error(error))
    }

    // Allow '0' as valid (fresh start, server treats as "from beginning")
    // Also allow 'digits-digits' format (normal Redis Stream IDs)
    if (lastCursor.value !== '0' && !/^\d+-\d+$/.test(lastCursor.value)) {
      const error = `Cursor format invalid: ${lastCursor.value}`

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
        await new Promise(resolve => {
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
  const setSnapshotCursor = cursor => {
    const oldCursor = lastCursor.value

    lastCursor.value = cursor || '0'
    console.log('[eventStore.setSnapshotCursor] Set from "' + oldCursor + '" to "' + lastCursor.value + '"')
  }

  /**
   * Shutdown: clean up connections completely (logout/unmount)
   * This is DELIBERATE disconnect, not an error
   */
  const disconnect = () => {
    logConnection('disconnect', 'called')
    console.log('[eventStore.disconnect] Shutting down all connections (deliberate)')

    // Signal that this is intentional disconnect (not error-triggered)
    isDisconnecting = true

    // Cancel any pending reconnection timer
    if (reconnectionTimer) {
      clearTimeout(reconnectionTimer)
      reconnectionTimer = null
    }

    // Close SSE (will NOT trigger handleSSEError due to isDisconnecting flag)
    closeSSE()

    // Stop polling
    stopPolling()

    // Reset connection state
    connectionPromise = null
    connectionInProgress = false
    reconnectionAttempt = 0

    console.log('[eventStore.disconnect] All connections closed')
  }

  /**
   * Get events of specific type
   */
  const getEventsByType = type => {
    return events.value.filter(e => e.type === type)
  }

  /**
   * Get conversation-related events
   */
  const getConversationEvents = conversationId => {
    return events.value.filter(
      e => e.data?.conversation_id === conversationId,
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
