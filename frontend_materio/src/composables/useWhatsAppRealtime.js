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

        // limit=100 (the backend's own cap) — without it the endpoint defaults to 25
        // and any conversation past that page silently never loads into the bandeja,
        // since there's no pagination/infinite-scroll UI to fetch further pages.
        const fetchUrl = '/dashboard/whatsapp/conversaciones/api/active/?limit=100'
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
              name: conv.name,
              phone: conv.phone,
              preview: conv.preview,
              ultima_actividad: conv.ultima_actividad || conv.last_activity,
              unread_count: conv.unread_count || 0,
              estado_atencion: conv.estado_atencion,
              avatar: conv.avatar,
              channel: conv.channel,
              estado_cotizacion: conv.estado_cotizacion,
              lead_id: conv.lead_id,
              responsable: conv.responsable,
              service_data: conv.service_data,
              archived: conv.archived || false,
              is_transportista: conv.is_transportista || false,
            })
          })
        }

        // Archivadas: separadas del snapshot principal (el endpoint las excluye por
        // defecto). Se cargan en el MISMO store — así la pestaña "Archivados" y el
        // tiempo real (archivar/desarchivar) comparten una sola fuente de verdad,
        // sin duplicar lógica de actualización en vivo.
        try {
          const archivedResponse = await fetch('/dashboard/whatsapp/conversaciones/api/active/?archived=true&limit=100')
          if (archivedResponse.ok) {
            const archivedData = await archivedResponse.json()
            const archivedList = archivedData.conversations || []

            archivedList.forEach(conv => {
              conversationsStore.upsertConversation({
                id: conv.id,
                cliente_id: conv.cliente_id,
                channel_id: conv.channel_id,
                name: conv.name,
                phone: conv.phone,
                preview: conv.preview,
                ultima_actividad: conv.ultima_actividad || conv.last_activity,
                unread_count: conv.unread_count || 0,
                estado_atencion: conv.estado_atencion,
                avatar: conv.avatar,
                channel: conv.channel,
                estado_cotizacion: conv.estado_cotizacion,
                lead_id: conv.lead_id,
                responsable: conv.responsable,
                service_data: conv.service_data,
                archived: true,
                is_transportista: conv.is_transportista || false,
              })
            })
            console.log('[REALTIME CP6B] Upsert ' + archivedList.length + ' archived conversations')
          }
        } catch (archivedError) {
          console.warn('[REALTIME CP6B] Failed to load archived conversations:', archivedError.message)
        }

        // Transportistas: separados del snapshot principal (el endpoint los excluye
        // por defecto, igual que archivadas). Se cargan en el MISMO store — la
        // pestaña "Transportistas" y el interruptor "Incluir transportistas" son
        // puramente client-side sobre un store que ya tiene todo.
        try {
          const transportistasResponse = await fetch('/dashboard/whatsapp/conversaciones/api/active/?transportistas=true&limit=100')
          if (transportistasResponse.ok) {
            const transportistasData = await transportistasResponse.json()
            const transportistasList = transportistasData.conversations || []

            transportistasList.forEach(conv => {
              conversationsStore.upsertConversation({
                id: conv.id,
                cliente_id: conv.cliente_id,
                channel_id: conv.channel_id,
                name: conv.name,
                phone: conv.phone,
                preview: conv.preview,
                ultima_actividad: conv.ultima_actividad || conv.last_activity,
                unread_count: conv.unread_count || 0,
                estado_atencion: conv.estado_atencion,
                avatar: conv.avatar,
                channel: conv.channel,
                estado_cotizacion: conv.estado_cotizacion,
                lead_id: conv.lead_id,
                responsable: conv.responsable,
                service_data: conv.service_data,
                archived: conv.archived || false,
                is_transportista: true,
              })
            })
            console.log('[REALTIME CP6C] Upsert ' + transportistasList.length + ' transportista conversations')
          }
        } catch (transportistasError) {
          console.warn('[REALTIME CP6C] Failed to load transportista conversations:', transportistasError.message)
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
      const response = await fetch('/dashboard/whatsapp/conversaciones/api/active/?limit=100')
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
          conversationsStore.upsertConversation(conv)
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
    const processEvent = event => {
      console.log('[REALTIME processEvent] type=' + event.type + ', conv_id=' + (event.conversation_id || event.data?.conversation_id) + ', correlation_id=' + (event.correlation_id || event.data?.correlation_id))

      // Normalize event structure
      const eventData = event.data || event

      // Record handled event in diagnostics
      if (typeof window !== 'undefined' && window.__WHATSAPP_REALTIME_DIAGNOSTICS__) {
        const diagnostics = Object.values(window.__WHATSAPP_REALTIME_DIAGNOSTICS__)[0]
        if (diagnostics) {
          if (!diagnostics.handledEvents) diagnostics.handledEvents = []
          diagnostics.handledEvents.push({
            id: event.event_id,
            type: event.type,
            message_id: event.message_id,
            conversation_id: event.conversation_id,
            timestamp: new Date().toISOString(),
          })
        }
      }

      // PRIORIDAD 7: Update bandeja/timeline based on event type
      switch (event.type) {
      case 'message.created':
      case 'message.updated':
        // message.updated: published once async media (download or CRM upload)
        // finishes AFTER the message row was already created — same payload
        // shape as message.created, handled identically (upsertMessage by id).
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
    const eventData = (event.data && Object.keys(event.data).length > 0) ? event.data : event
    const { message_id, conversation_id, content, direction, origen, content_type, timestamp, from, sender_type, event_id, replay_of, attachments, caption, meta_message_id, reply_to, reaction_emoji, hidden, conversation: convMeta } = eventData

    // 'Ocultar en el CRM' — drop it from this session's timeline too (shared inbox:
    // whoever hid it, everyone stops seeing it, live, no reload). Never touches
    // anything server-side beyond the flag already set before this event was sent.
    if (hidden) {
      if (messagesStore && messagesStore.removeMessage) {
        messagesStore.removeMessage(conversation_id, message_id)
      }

      return
    }

    console.log('[handleMessageCreated] EXEC: message_id=' + message_id + ', conversation_id=' + conversation_id + ', event_id=' + event_id + ', replay_of=' + (replay_of || 'N/A'))

    // TRABAJO A: Record handler execution
    if (typeof window !== 'undefined' && window.__WHATSAPP_REALTIME_DIAGNOSTICS__) {
      const diagnostics = Object.values(window.__WHATSAPP_REALTIME_DIAGNOSTICS__)[0]
      if (diagnostics && !diagnostics.handledEvents) {
        diagnostics.handledEvents = []
      }
      if (diagnostics) {
        diagnostics.handledEvents.push({
          id: event_id,
          type: 'message.created',
          message_id: message_id,
          conversation_id: conversation_id,
          replay_of: replay_of,
          timestamp: new Date().toISOString(),
        })
      }
    }

    // Update or create message in timeline
    if (messagesStore && messagesStore.upsertMessage) {
      console.log('[handleMessageCreated] Calling upsertMessage with:', { message_id, conversation_id, direction, origen, sender_type, content: content?.substring(0, 20) })
      messagesStore.upsertMessage({
        id: message_id,
        message_id,
        conversation_id,
        content,
        direction,
        origen,
        content_type,
        timestamp,
        sender: from,
        sender_type,
        attachments,
        caption,
        meta_message_id,
        reply_to,
        reaction_emoji,
      })
      console.log('[handleMessageCreated] upsertMessage called successfully')
    } else {
      console.warn('[handleMessageCreated] messagesStore or upsertMessage not available')
    }

    // Update conversation in bandeja (increment unread counter) — only for genuinely
    // NEW messages. message.updated re-delivers an existing message (media became
    // available after the fact) and must not count as a second unread arrival.
    if (event.type !== 'message.updated' && conversationsStore && conversationsStore.upsertConversation) {
      const existingConv = conversationsStore.getConversation(conversation_id)
      const currentUnread = existingConv?.unread || 0
      const newUnread = currentUnread + 1  // Increment by 1 for new message

      console.log('[handleMessageCreated] Updating conversation: unread ' + currentUnread + ' -> ' + newUnread)

      // name/phone only included when present (backend now sends them) — never pass
      // them as explicit `undefined`, which would clobber a name already loaded via
      // REST. This is what fixes a brand-new conversation (first SSE event ever seen
      // for it, not yet in the store) showing "Desconocido" until the next reload.
      const convPatch = {
        id: conversation_id,
        ultima_actividad: new Date().toISOString(),
        unread_count: newUnread,
      }
      if (convMeta?.name) convPatch.name = convMeta.name
      if (convMeta?.phone) convPatch.phone = convMeta.phone

      conversationsStore.upsertConversation(convPatch)
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
