<template>
  <div
    class="conversation-panel"
    data-testid="conversation-panel"
  >
    <!-- Empty state -->
    <EmptyConversationState v-if="!conversationId" />

    <!-- Chat -->
    <div
      v-else
      class="chat-content"
      data-testid="chat-content"
    >
      <!-- Header -->
      <ConversationHeader
        :conversation="conversation"
        :bot-global-paused="botGlobalPaused"
        :effective-bot-paused="effectiveBotPaused"
        class="conversation-header"
        data-testid="conversation-header"
      />

      <!-- Messages -->
      <MessageTimeline
        :messages="messages"
        :loading="loadingMessages"
        class="message-timeline"
        data-testid="message-timeline-wrapper"
        @retry="handleRetryMessage"
      />

      <!-- Composer -->
      <ChatComposer
        ref="composerRef"
        class="chat-composer"
        :attention-mode="conversation?.attentionMode || 'unassigned'"
        :advisor-name="conversation?.responsable?.nombre || 'Walter Escobar'"
        :effective-bot-paused="effectiveBotPaused"
        :sending="sendingMessage"
        :send-error="sendError"
        @send-message="handleSendMessage"
        @take-control="handleTakeControl"
        @assign-me="handleAssignMe"
        @reopen="handleReopen"
        @clear-reply="clearReply"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import EmptyConversationState from './EmptyConversationState.vue'
import ConversationHeader from './ConversationHeader.vue'
import MessageTimeline from './MessageTimeline.vue'
import ChatComposer from './ChatComposer.vue'
import { conversationService } from '@/services/conversationService'
import { useMessagesStore } from '@/stores/messagesStore'
import { normalizeMessage } from '@/utils/messageNormalizer'

const props = defineProps({
  conversationId: {
    type: Number,
    default: null,
  },
  conversation: {
    type: Object,
    default: null,
  },
  botGlobalPaused: {
    type: Boolean,
    default: false,
  },
  effectiveBotPaused: {
    type: Boolean,
    default: false,
  },
})

// Use Pinia store for real-time updates from SSE
const messagesStore = useMessagesStore()
const loadingMessages = ref(false)

// Computed: get messages from store, or empty if no conversation selected
// CRITICAL: Access messagesStore.messages directly to ensure Vue reactivity
// Do NOT use getMessages() method as it may not trigger computed updates
const messages = computed(() => {
  const convId = props.conversationId

  console.log('[ConversationPanel computed] ENTRY: convId=' + convId)

  if (!convId) {
    console.log('[ConversationPanel computed] No conversationId, return []')
    
    return []
  }

  // Direct access to reactive property (Pinia auto-unwraps refs in components)
  const result = messagesStore.messages[convId] || []

  console.log('[ConversationPanel computed] RESULT: count=' + result.length)
  if (result.length > 0) {
    console.log('[ConversationPanel computed] First message:', result[0])
    console.log('[ConversationPanel computed] Last message:', result[result.length - 1])
  }

  return result
})

const loadMessages = async () => {
  if (!props.conversationId) {
    return
  }

  console.log('[ConversationPanel] loadMessages: conversationId=' + props.conversationId)

  loadingMessages.value = true
  try {
    // Load messages into Pinia store (will be reflected in computed messages)
    await messagesStore.loadConversationMessages(props.conversationId)
    console.log('[ConversationPanel] Messages loaded, count=' + messages.value.length)

    // Mark conversation as read when opened
    try {
      await fetch(`/dashboard/whatsapp/conversaciones/${props.conversationId}/mark-read/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      console.log('[ConversationPanel] Marked as read: ' + props.conversationId)
    } catch (error) {
      console.warn('[ConversationPanel] Error marking read:', error)
    }
  } catch (error) {
    console.error('Error loading messages:', error)
  } finally {
    loadingMessages.value = false
  }
}

const composerRef = ref(null)
const sendingMessage = ref(false)
const sendError = ref('')

/**
 * Send a text message to the backend and reconcile the optimistic bubble.
 * Shared by the composer's normal send and the "Reintentar" button on a failed
 * bubble (MessageBubble -> MessageTimeline -> here).
 */
const sendTextMessage = async (text, tempId) => {
  const convId = props.conversationId

  messagesStore.upsertMessage({
    id: tempId,
    conversation_id: convId,
    content: text,
    direction: 'saliente',
    sender_type: 'advisor',
    content_type: 'texto',
    timestamp: new Date().toISOString(),
    status: 'sending',
  })

  sendingMessage.value = true
  sendError.value = ''

  try {
    const response = await fetch(`/dashboard/whatsapp/conversaciones/${convId}/enviar/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': conversationService.getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ message: text, client_msg_id: tempId }),
    })

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    messagesStore.removeMessage(convId, tempId)

    if (data?.success && data.message) {
      messagesStore.upsertMessage(normalizeMessage(data.message))
      composerRef.value?.clear()
    } else {
      // Persist the failed attempt as its own bubble (backend already saved it with
      // estado='error' when data.message is present) so the advisor can retry it.
      const detail = data?.error_detail || 'No se pudo enviar el mensaje.'
      if (data?.message) {
        messagesStore.upsertMessage(normalizeMessage(data.message))
      } else {
        messagesStore.upsertMessage({
          id: tempId,
          conversation_id: convId,
          content: text,
          direction: 'saliente',
          sender_type: 'advisor',
          content_type: 'texto',
          timestamp: new Date().toISOString(),
          status: 'failed',
          errorDetail: detail,
        })
      }
      sendError.value = detail
    }
  } catch (error) {
    console.error('[ConversationPanel] Send message failed:', error)
    messagesStore.removeMessage(convId, tempId)
    messagesStore.upsertMessage({
      id: tempId,
      conversation_id: convId,
      content: text,
      direction: 'saliente',
      sender_type: 'advisor',
      content_type: 'texto',
      timestamp: new Date().toISOString(),
      status: 'failed',
      errorDetail: 'No se pudo conectar con el servidor.',
    })
    sendError.value = 'No se pudo conectar con el servidor. Verifica tu conexión e intenta de nuevo.'
  } finally {
    sendingMessage.value = false
  }
}

const handleSendMessage = messageData => {
  if (messageData.type !== 'text') {
    sendError.value = 'Enviar imágenes, audio o documentos desde el CRM todavía no está disponible.'

    return
  }

  const tempId = messageData.clientMsgId || `local-${Date.now()}`

  sendTextMessage(messageData.text, tempId)
}

/** Retry a previously failed outbound message (from MessageBubble's retry button). */
const handleRetryMessage = failedMessage => {
  if (!failedMessage?.text) return
  messagesStore.removeMessage(props.conversationId, failedMessage.id)
  sendTextMessage(failedMessage.text, `local-retry-${Date.now()}`)
}

const handleTakeControl = () => {
  console.log('Take control of conversation')

  // TODO: Implement take control
}

const handleAssignMe = () => {
  console.log('Assign conversation to me')

  // TODO: Implement assign to me
}

const handleReopen = () => {
  console.log('Reopen conversation')

  // TODO: Implement reopen conversation
}

const clearReply = () => {
  console.log('Clear reply')

  // TODO: Clear reply state
}

// Watch para cuando cambia el conversationId
watch(() => props.conversationId, (newId, oldId) => {
  console.log('[ConversationPanel watch] conversationId changed from ' + oldId + ' to ' + newId)
  loadMessages()
}, { immediate: false })

// Cargar mensajes al montar si hay conversationId
onMounted(() => {
  if (props.conversationId) {
    loadMessages()
  }
})
</script>

<style scoped>
.conversation-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}

.chat-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conversation-header {
  flex: 0 0 auto;
  min-height: 0;
}

.message-timeline {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
}

.chat-composer {
  flex: 0 0 auto;
  min-height: 52px;
}
</style>
