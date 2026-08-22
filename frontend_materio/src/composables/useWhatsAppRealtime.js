/**
 * FASE 5B Real-time composable
 *
 * Integrates event streaming (SSE + fallback polling) with local state management.
 * Handles: SSE connection, event deduplication, state updates, error recovery.
 *
 * PRIORIDADES 5-7: Real-time bandeja/timeline updates + visual sync
 * PRIORIDADES 8-9: SSE/fallback + multi-tab
 */

import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useEventStore } from '@/stores/eventStore'

export function useWhatsAppRealtime(conversationsStore, messagesStore) {
  const eventStore = useEventStore()
  const isInitialized = ref(false)
  const syncInProgress = ref(false)

  /**
   * Initialize real-time connection and load initial state.
   * Called once per session in authenticated layout.
   */
  const initialize = async () => {
    if (isInitialized.value) return

    syncInProgress.value = true

    try {
      // PRIORIDAD 6: Load initial REST state
      await loadInitialState(conversationsStore, messagesStore)

      // PRIORIDAD 8: Start SSE + fallback polling
      eventStore.connect()

      // Subscribe to events
      subscribeToEvents()

      isInitialized.value = true
    } catch (error) {
      console.error('Failed to initialize real-time:', error)
    } finally {
      syncInProgress.value = false
    }
  }

  /**
   * Load initial bandeja and timeline from REST.
   */
  const loadInitialState = async (conversationsStore, messagesStore) => {
    try {
      // PRIORIDAD 7: Bandeja update from REST
      const response = await fetch('/dashboard/whatsapp/conversaciones/api/active/')
      const data = await response.json()

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

    // Watch for new events (in real implementation, use watch API)
    // This is simplified - actual impl would use Pinia watch
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
      conversationsStore.upsertConversation({
        id: conversation_id,
        preview,
        ultima_actividad: conversation.last_activity,
        unread_count: conversation.unread_count,
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
