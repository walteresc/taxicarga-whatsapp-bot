/**
 * FASE 5B Real-time composable
 *
 * Integrates event streaming (SSE + fallback polling) with local state management.
 * Handles: SSE connection, event deduplication, state updates, error recovery.
 *
 * PRIORIDADES 5-7: Real-time bandeja/timeline updates + visual sync
 * PRIORIDADES 8-9: SSE/fallback + multi-tab
 */

import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { useEventStore } from '@/stores/eventStore'

function isValidRedisCursor(cursor) {
  if (!cursor || typeof cursor !== 'string') return false
  if (cursor === '' || cursor === '0') return false
  // Valid Redis Stream ID format: "timestamp-sequence"
  // Examples: "1234567890-0", "1-0" (synthetic), "1234-5"
  return /^\d+-\d+$/.test(cursor)
}

export function useWhatsAppRealtime(conversationsStore, messagesStore) {
  const eventStore = useEventStore()
  const isInitialized = ref(false)
  const syncInProgress = ref(false)
  let initializationPromise = null
  let unsubscribeEvents = null  // PASO 4: Explicit subscription cleanup
  let isSubscribed = false  // Track if subscription is active

  /**
   * PASO 2: Orden obligatorio de inicialización
   * 1. REST snapshot
   * 2. Validar cursor
   * 3. Establecer cursor
   * 4. Registrar listeners
   * 5. Connect SSE (con cursor válido)
   */
  const initialize = async () => {
    console.log('[REALTIME CP1] initialize entered')

    // Idempotent: si ya se inicializó o está en progreso, retornar
    if (isInitialized.value) {
      console.log('[REALTIME CP2] Already initialized, return')
      return
    }

    if (initializationPromise) {
      console.log('[REALTIME CP2B] Initialization in progress, await existing promise')
      return await initializationPromise
    }

    // Crear promesa de inicialización única
    initializationPromise = (async () => {
      syncInProgress.value = true

      try {
        console.log('[REALTIME CP3] REST snapshot: GET /dashboard/whatsapp/conversaciones/api/active/')
        const fetchUrl = '/dashboard/whatsapp/conversaciones/api/active/'
        const fetchResponse = await fetch(fetchUrl)

        if (!fetchResponse.ok) {
          const errorBody = await fetchResponse.text()
          throw new Error(`HTTP ${fetchResponse.status}: ${errorBody.substring(0, 200)}`)
        }

        const parsedData = await fetchResponse.json()
        console.log('[REALTIME CP4] Response received. Keys:', Object.keys(parsedData))

        // PASO 3: Validar cursor ANTES de usar
        let cursor = parsedData.snapshot_cursor
        console.log('[REALTIME CP5] snapshot_cursor from API:', cursor, 'valid:', isValidRedisCursor(cursor))

        if (!isValidRedisCursor(cursor)) {
          console.warn('[REALTIME CP5A] Invalid snapshot_cursor, applying workaround')
          // Workaround: si cursor es 0 o inválido, usar latest desde now
          // Backend debería garantizar cursor válido, pero defenderse aquí
          cursor = await _fetchLatestCursorFromPoll()
          console.log('[REALTIME CP5B] Fallback cursor from polling:', cursor)
        }

        if (!isValidRedisCursor(cursor)) {
          throw new Error(`Cannot obtain valid cursor: ${cursor}`)
        }

        // Cargar conversaciones ANTES de conectar SSE
        if (parsedData.conversations) {
          console.log('[REALTIME CP6] Upsert ' + parsedData.conversations.length + ' conversations')
          parsedData.conversations.forEach(conv => {
            conversationsStore.upsertConversation({
              id: conv.id,
              cliente_id: conv.cliente_id,
              channel_id: conv.channel_id,
              preview: conv.preview,
              ultima_actividad: conv.ultima_actividad,
              unread_count: conv.unread_count || 0,
              estado_atencion: conv.estado,
            })
          })
        }

        // PASO 2A: Set cursor en store
        console.log('[REALTIME CP7] setSnapshotCursor(' + cursor + ')')
        eventStore.setSnapshotCursor(cursor)
        console.log('[REALTIME CP7A] lastCursor now:', eventStore.lastCursor)

        // PASO 2B: Registrar listeners ANTES de conectar SSE
        console.log('[REALTIME CP8] Register event listeners')
        console.log('[DEBUG] subscribeToEvents function:', typeof subscribeToEvents)
        try {
          subscribeToEvents()
          console.log('[DEBUG] subscribeToEvents executed successfully')
        } catch (e) {
          console.error('[DEBUG] subscribeToEvents failed:', e.message)
          throw e
        }

        // PASO 2C: Connect SSE SOLO si cursor válido
        console.log('[REALTIME CP9] connect() with cursor:', eventStore.lastCursor)
        eventStore.connect()

        isInitialized.value = true
        console.log('[REALTIME CP10] initialize COMPLETED')

      } catch (error) {
        console.error('[REALTIME ERROR]', error.message)
        console.error('[REALTIME STACK]', error.stack)
        isInitialized.value = false
        throw error
      } finally {
        syncInProgress.value = false
        initializationPromise = null
      }
    })()

    return await initializationPromise
  }

  /**
   * Fallback: si API retorna cursor=0, usar REST polling para obtener latest
   */
  const _fetchLatestCursorFromPoll = async () => {
    try {
      const response = await fetch('/dashboard/whatsapp/api/events/poll/?cursor=0&limit=1')
      if (!response.ok) throw new Error('Poll failed')
      const data = await response.json()
      return data.latest_cursor || '0'
    } catch (err) {
      console.warn('Fallback poll failed:', err.message)
      return '0'
    }
  }

  /**
   * Load initial bandeja and timeline from REST.
   * CRITICALLY: obtener snapshot_cursor para SSE coherencia.
   */
  const loadInitialState = async (conversationsStore, messagesStore) => {
    try {
      // PRIORIDAD 7: Bandeja update from REST
      const response = await fetch('/dashboard/whatsapp/conversaciones/api/active/')
      const data = await response.json()

      // FASE 5B: Snapshot cursor para SSE (evita repetir historial)
      if (data.snapshot_cursor) {
        eventStore.setSnapshotCursor(data.snapshot_cursor)
        console.log('[realtime] Snapshot cursor established:', data.snapshot_cursor)
      } else {
        console.warn('[realtime] No snapshot_cursor in response - SSE may repeat histor')
      }

      if (data.conversations) {
        data.conversations.forEach(conv => {
          conversationsStore.upsertConversation({
            id: conv.id,
            cliente_id: conv.cliente_id,
            channel_id: conv.channel_id,
            preview: conv.preview,
            ultima_actividad: conv.ultima_actividad,
            unread_count: conv.unread_count || 0,
            estado_atencion: conv.estado,
          })
        })
      }
    } catch (error) {
      console.error('Failed to load initial state:', error)
      throw error
    }
  }

  /**
   * Subscribe to event store and update local state.
   * IDEMPOTENT: Only register once, cleanup old before re-registering
   */
  const subscribeToEvents = () => {
    console.log('[REALTIME subscribeToEvents] ENTERED, isSubscribed=' + isSubscribed)

    // IDEMPOTENT: If already subscribed, return
    if (isSubscribed && unsubscribeEvents) {
      console.log('[REALTIME subscribeToEvents] Already subscribed, skipping')
      return
    }

    // Cleanup old subscription if exists (should be rare)
    if (unsubscribeEvents) {
      console.log('[REALTIME subscribeToEvents] Cleaning up old subscription')
      unsubscribeEvents()
      unsubscribeEvents = null
      isSubscribed = false
    }

    // Handler for each event
    const processEvent = (event) => {
      console.log('[REALTIME processEvent] type=' + event.type + ', conv_id=' + (event.conversation_id || event.data?.conversation_id) + ', correlation_id=' + (event.correlation_id || event.data?.correlation_id))

      // Normalize event structure
      const eventData = event.data || event

      // PRIORIDAD 7: Update bandeja/timeline based on event type
      switch (event.type) {
        case 'message.created':
          handleMessageCreated({ ...event, data: eventData }, messagesStore, conversationsStore)
          break

        case 'conversation.created':
        case 'conversation.updated':
          handleConversationUpdated({ ...event, data: eventData }, conversationsStore)
          break

        case 'resync.required':
          handleResyncRequired(conversationsStore, messagesStore)
          break

        default:
          console.warn('[REALTIME] Unknown event type:', event.type)
      }
    }

    // Subscribe to eventStore
    console.log('[REALTIME subscribeToEvents] Registering subscription handler')
    unsubscribeEvents = eventStore.subscribe(processEvent)
    isSubscribed = true
    console.log('[REALTIME subscribeToEvents] Subscription registered')
  }

  /**
   * Handle message.created event.
   * PRIORIDADES 5, 7: Update conversation + timeline
   */
  const handleMessageCreated = (event, messagesStore, conversationsStore) => {
    const { message_id, conversation_id, sender_type, preview, timestamp, conversation } = event.data

    // Update or create message in timeline
    if (messagesStore && messagesStore.upsertMessage) {
      messagesStore.upsertMessage({
        id: message_id,
        conversation_id,
        sender_type,
        timestamp,
      })
    }

    // Update conversation in bandeja
    if (conversation && conversationsStore && conversationsStore.upsertConversation) {
      // IMPORTANT: conversation.unread_delta is INCREMENTAL, not absolute
      // Sum it to the existing counter, not replace it
      const existingConv = conversationsStore.getConversation(conversation_id)
      const currentUnread = existingConv?.unread_count || 0
      const newUnread = Math.max(0, currentUnread + (conversation.unread_delta || 0))

      conversationsStore.upsertConversation({
        id: conversation_id,
        preview,
        ultima_actividad: conversation.last_activity,
        unread_count: newUnread,
        estado_atencion: conversation.attention_state,
        bot_pausado: conversation.bot_paused,
      })
    }

    // PRIORIDAD 7: Reorder bandeja by -ultima_actividad
    if (conversationsStore && conversationsStore.reorderConversations) {
      conversationsStore.reorderConversations()
    }
  }

  /**
   * Handle conversation state change.
   */
  const handleConversationUpdated = (event, conversationsStore) => {
    const { conversation_id } = event.data

    if (conversationsStore && conversationsStore.updateConversationState) {
      conversationsStore.updateConversationState(conversation_id, event.data)
    }
  }

  /**
   * Handle resync request (cursor too old).
   * PRIORIDADES 8, 12: Full reconciliation via REST
   */
  const handleResyncRequired = async (conversationsStore, messagesStore) => {
    console.warn('Resync required - cursor too old')
    await eventStore.reconcileFromREST()
    await loadInitialState(conversationsStore, messagesStore)
  }

  /**
   * Cleanup on unmount or logout.
   * CRITICAL: Clear ALL resources to prevent leaks across navigation
   */
  const cleanup = () => {
    console.log('[REALTIME cleanup] START')

    // Cleanup subscription
    if (unsubscribeEvents) {
      console.log('[REALTIME cleanup] Unsubscribing from events')
      try {
        unsubscribeEvents()
      } catch (error) {
        console.error('[REALTIME cleanup] Unsubscribe error:', error)
      }
      unsubscribeEvents = null
      isSubscribed = false
    }

    // Disconnect eventStore (closes SSE, stops polling, resets state)
    try {
      eventStore.disconnect()
    } catch (error) {
      console.error('[REALTIME cleanup] Disconnect error:', error)
    }

    // Reset all state
    isInitialized.value = false
    syncInProgress.value = false
    initializationPromise = null

    console.log('[REALTIME cleanup] COMPLETE')
  }

  onMounted(() => {
    // Initialize will be called from parent layout, not here
    // This is just the hook structure for potential auto-init
  })

  onUnmounted(() => {
    cleanup()
  })

  return {
    initialize,
    cleanup,
    isInitialized,
    syncInProgress,
    connectionStatus: computed(() => eventStore.connectionStatus),
    eventCount: computed(() => eventStore.eventCount),
  }
}
