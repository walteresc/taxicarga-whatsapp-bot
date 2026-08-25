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

export function useWhatsAppRealtime(conversationsStore, messagesStore) {
  const eventStore = useEventStore()
  const isInitialized = ref(false)
  const syncInProgress = ref(false)

  /**
   * Initialize real-time connection and load initial state.
   * Called once per session in authenticated layout.
   * FASE 5B: 11 checkpoints for diagnostic tracing.
   */
  const initialize = async () => {
    console.log('[REALTIME CP1] initialize entered')

    const isInitializedBefore = isInitialized.value
    console.log('[REALTIME CP2] isInitialized value before:', isInitializedBefore)

    if (isInitialized.value) {
      console.log('[REALTIME CP2B] Already initialized, returning early')
      return
    }

    syncInProgress.value = true

    try {
      console.log('[REALTIME CP3] loadInitialState start')
      const fetchUrl = '/dashboard/whatsapp/conversaciones/api/active/'
      console.log('[REALTIME CP3A] fetch URL:', fetchUrl)

      const fetchResponse = await fetch(fetchUrl)
      console.log('[REALTIME CP4] loadInitialState response status:', fetchResponse.status)
      console.log('[REALTIME CP4A] response headers content-type:', fetchResponse.headers.get('content-type'))

      if (!fetchResponse.ok) {
        const errorBody = await fetchResponse.text()
        console.error('[REALTIME CP4B] fetch failed:', {
          status: fetchResponse.status,
          statusText: fetchResponse.statusText,
          body: errorBody.substring(0, 200)
        })
        throw new Error(`HTTP ${fetchResponse.status}: ${fetchResponse.statusText}`)
      }

      const parsedData = await fetchResponse.json()
      console.log('[REALTIME CP5] loadInitialState parsed payload:', {
        conversations_count: parsedData.conversations?.length || 0,
        has_snapshot_cursor: 'snapshot_cursor' in parsedData,
        snapshot_cursor_value: parsedData.snapshot_cursor || 'MISSING',
        has_pagination: 'pagination' in parsedData
      })

      if (!parsedData.snapshot_cursor) {
        console.error('[REALTIME CP5A] CRITICAL: snapshot_cursor missing or falsy')
        console.error('[REALTIME CP5A] full response keys:', Object.keys(parsedData))
      }

      // Now update stores from REST data
      if (parsedData.conversations) {
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

      console.log('[REALTIME CP6] snapshot cursor assigned')
      const cursorBeforeSet = eventStore.lastCursor || '0'
      eventStore.setSnapshotCursor(parsedData.snapshot_cursor)
      console.log('[REALTIME CP6A] cursor before:', cursorBeforeSet)
      console.log('[REALTIME CP6B] cursor after:', eventStore.lastCursor || 'NOT SET')

      console.log('[REALTIME CP7] subscriptions registered')
      // Subscribe to events
      subscribeToEvents()

      console.log('[REALTIME CP8] eventStore.connect called')
      // PRIORIDAD 8: Start SSE + fallback polling
      eventStore.connect()
      console.log('[REALTIME CP8A] eventStore.connect returned')

      isInitialized.value = true
      console.log('[REALTIME CP11] initialize completed successfully')
    } catch (error) {
      console.error('[REALTIME ERROR] initialize failed:', {
        name: error?.name || 'unknown',
        message: error?.message || 'no message',
        stack: error?.stack?.split('\n').slice(0, 3).join('\n') || 'no stack',
        isInitializedBefore,
        isInitializedAfter: isInitialized.value
      })
    } finally {
      syncInProgress.value = false
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
   * Deduplication by event.id handles REST + SSE overlap.
   */
  const subscribeToEvents = () => {
    // Watch for new events
    const processEvent = (event) => {
      console.log('[REALTIME processEvent] type=' + event.type + ', conv_id=' + event.conversation_id)
      // PRIORIDAD 7: Update bandeja/timeline based on event type
      switch (event.type) {
        case 'message.created':
          handleMessageCreated(event, messagesStore, conversationsStore)
          break

        case 'conversation.created':
        case 'conversation.updated':
          handleConversationUpdated(event, conversationsStore)
          break

        case 'resync.required':
          handleResyncRequired(conversationsStore, messagesStore)
          break
      }
    }

    // Process existing pending events
    eventStore.events.forEach(processEvent)

    // CRITICAL FIX: Watch for new events from SSE/polling
    watch(
      () => eventStore.events,
      (newEvents, oldEvents) => {
        // Only process NEW events (those added since last watch)
        const oldIds = new Set(oldEvents?.map(e => e.id) || [])
        const newOnlyEvents = newEvents.filter(e => !oldIds.has(e.id))

        console.log('[REALTIME watch] ' + newOnlyEvents.length + ' new events')
        newOnlyEvents.forEach(processEvent)
      },
      { deep: true }
    )
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
   * PRIORIDAD 6: Lifecycle management
   */
  const cleanup = () => {
    eventStore.disconnect()
    isInitialized.value = false
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
