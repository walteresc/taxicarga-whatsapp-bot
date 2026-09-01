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
        @show-info="$emit('show-info')"
      />

      <!-- Messages -->
      <MessageTimeline
        :messages="messages"
        :loading="loadingMessages"
        class="message-timeline"
        data-testid="message-timeline-wrapper"
        @retry="handleRetryMessage"
        @reply="handleReplyToMessage"
        @forward="handleForwardMessage"
        @hide-for-me="handleHideForMe"
        @react="handleReactToMessage"
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
        :replying-to="replyingTo"
        @send-message="handleSendMessage"
        @take-control="handleTakeControl"
        @assign-me="handleAssignMe"
        @reopen="handleReopen"
        @clear-reply="clearReply"
      />
    </div>

    <!-- Mounted once — MessageBubble opens it via useImageViewer() -->
    <ImageViewer />

    <ForwardMessageModal
      v-if="forwardingMessage"
      :message="forwardingMessage"
      :conversation-id="conversationId"
      @close="forwardingMessage = null"
    />
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick, computed } from 'vue'
import EmptyConversationState from './EmptyConversationState.vue'
import ImageViewer from './ImageViewer.vue'
import ConversationHeader from './ConversationHeader.vue'
import MessageTimeline from './MessageTimeline.vue'
import ChatComposer from './ChatComposer.vue'
import ForwardMessageModal from './ForwardMessageModal.vue'
import { conversationService } from '@/services/conversationService'
import { useMessagesStore } from '@/stores/messagesStore'
import { useConversationsStore } from '@/stores/conversationsStore'

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

defineEmits(['show-info'])

// Use Pinia store for real-time updates from SSE
const messagesStore = useMessagesStore()
const conversationsStore = useConversationsStore()
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
      const response = await fetch(`/dashboard/whatsapp/conversaciones/${props.conversationId}/mark-read/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': conversationService.getCsrfToken(),
        },
        credentials: 'include',
      })

      if (response.ok) {
        // Clear the badge immediately — don't wait for the next /api/active/ reload
        conversationsStore.updateConversationState(props.conversationId, { unread: 0 })
        console.log('[ConversationPanel] Marked as read: ' + props.conversationId)
      } else {
        console.warn('[ConversationPanel] mark-read HTTP ' + response.status)
      }
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
const replyingTo = ref(null)
const forwardingMessage = ref(null)

/**
 * Send a text message to the backend and reconcile the optimistic bubble.
 * Shared by the composer's normal send and the "Reintentar" button on a failed
 * bubble (MessageBubble -> MessageTimeline -> here).
 */
const sendTextMessage = async (text, tempId, replyToId = null, replyToPreview = null) => {
  const convId = props.conversationId

  messagesStore.upsertMessage({
    id: tempId,
    clientMsgId: tempId,
    conversation_id: convId,
    content: text,
    direction: 'saliente',
    sender_type: 'advisor',
    content_type: 'texto',
    timestamp: new Date().toISOString(),
    status: 'sending',
    reply_to: replyToPreview,
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
      body: JSON.stringify({ message: text, client_msg_id: tempId, reply_to_id: replyToId || undefined }),
    })

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    // No removeMessage() here anymore — upsertMessage() reconciles the optimistic
    // bubble IN PLACE (matched by clientMsgId) instead of deleting it and pushing a
    // new one under the real id. That remove-then-push sequence was what caused the
    // bubble to visibly flicker: changing the v-for key tears down and recreates
    // the DOM node, replaying its entrance animation.
    if (data?.success && data.message) {
      // No composerRef.clear() here anymore — ChatComposer now clears its own text
      // synchronously the instant Enter is pressed, not on this later confirmation.
      // Calling it here too would wipe out whatever the advisor has already started
      // typing for their NEXT message by the time this response comes back.
      messagesStore.upsertMessage({ ...data.message, clientMsgId: tempId })
    } else {
      // Persist the failed attempt as its own bubble (backend already saved it with
      // estado='error' when data.message is present) so the advisor can retry it.
      const detail = data?.error_detail || 'No se pudo enviar el mensaje.'
      if (data?.message) {
        messagesStore.upsertMessage({ ...data.message, clientMsgId: tempId })
      } else {
        messagesStore.upsertMessage({
          id: tempId,
          clientMsgId: tempId,
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

/**
 * Upload and send an outbound media message (image/video/audio/document).
 * Mirrors sendTextMessage's optimistic-bubble + reconcile flow, but posts
 * multipart/form-data with the raw File instead of a JSON body.
 */
const sendMediaMessage = async (file, tipo, tempId) => {
  const convId = props.conversationId

  messagesStore.upsertMessage({
    id: tempId,
    clientMsgId: tempId,
    conversation_id: convId,
    content: '',
    direction: 'saliente',
    sender_type: 'advisor',
    content_type: tipo,
    timestamp: new Date().toISOString(),
    status: 'sending',
  })

  sendingMessage.value = true
  sendError.value = ''

  const formData = new FormData()

  formData.append('file', file)
  formData.append('type', tipo)
  formData.append('client_msg_id', tempId)

  try {
    const response = await fetch(`/dashboard/whatsapp/conversaciones/${convId}/enviar-media/`, {
      method: 'POST',
      headers: {
        'X-CSRFToken': conversationService.getCsrfToken(),
      },
      credentials: 'include',
      body: formData,
    })

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    // No removeMessage() — see sendTextMessage's comment: upsertMessage() now
    // reconciles the optimistic bubble in place, matched by clientMsgId.
    if (data?.success && data.message) {
      messagesStore.upsertMessage({ ...data.message, clientMsgId: tempId })
      composerRef.value?.clear()
    } else {
      const detail = data?.error_detail || 'No se pudo enviar el archivo.'

      if (data?.message) {
        messagesStore.upsertMessage({ ...data.message, clientMsgId: tempId })
      } else {
        messagesStore.upsertMessage({
          id: tempId,
          clientMsgId: tempId,
          conversation_id: convId,
          content: '',
          direction: 'saliente',
          sender_type: 'advisor',
          content_type: tipo,
          timestamp: new Date().toISOString(),
          status: 'failed',
          errorDetail: detail,
        })
      }
      sendError.value = detail
    }
  } catch (error) {
    console.error('[ConversationPanel] Send media failed:', error)
    messagesStore.removeMessage(convId, tempId)
    messagesStore.upsertMessage({
      id: tempId,
      conversation_id: convId,
      content: '',
      direction: 'saliente',
      sender_type: 'advisor',
      content_type: tipo,
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
  if (messageData.type === 'text') {
    const tempId = messageData.clientMsgId || `local-${Date.now()}`
    const replyToId = replyingTo.value?.id || null
    const replyToPreview = replyingTo.value ? { ...replyingTo.value } : null

    clearReply()
    sendTextMessage(messageData.text, tempId, replyToId, replyToPreview)

    return
  }

  if (messageData.file) {
    const tempId = messageData.clientMsgId || `local-${Date.now()}`

    sendMediaMessage(messageData.file, messageData.type, tempId)

    return
  }

  // Live mic recording still emits a placeholder with no real File — not wired yet.
  sendError.value = 'Grabar y enviar audio en vivo todavía no está disponible.'
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
  replyingTo.value = null
}

/** Set the reply target from a MessageBubble's reply trigger (disabled client-side
 * when the message lacks a wamid, but re-check here too — never trust the click alone). */
const handleReplyToMessage = message => {
  if (!message?.metaMessageId) return
  replyingTo.value = {
    id: message.id,
    senderName: message.senderName || 'Mensaje',
    text: message.text || message.caption || `[${message.contentType}]`,
    type: message.contentType,
  }
}

const handleForwardMessage = message => {
  forwardingMessage.value = message
}

/** "Ocultar en el CRM" — user already confirmed in MessageBubble. Removes it from
 * this session's timeline immediately; the SSE 'hidden' flag (handled in
 * useWhatsAppRealtime.js) does the same for any other session with this
 * conversation open. Never deletes anything server-side, only marks it. */
const handleHideForMe = async message => {
  const convId = props.conversationId

  try {
    const response = await fetch(
      `/dashboard/whatsapp/conversaciones/${convId}/mensajes/${message.id}/ocultar/`,
      {
        method: 'POST',
        headers: { 'X-CSRFToken': conversationService.getCsrfToken() },
        credentials: 'include',
      }
    )

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    if (data?.success) {
      messagesStore.removeMessage(convId, message.id)
    } else {
      sendError.value = 'No se pudo ocultar el mensaje.'
    }
  } catch (error) {
    console.error('[ConversationPanel] Hide message failed:', error)
    sendError.value = 'No se pudo conectar con el servidor.'
  }
}

/** React to a message (WhatsApp-style emoji). Optimistic update, rolled back on
 * failure — the real state also arrives shortly after via the message.updated SSE
 * event the backend publishes on success, so this is just for instant feedback. */
const handleReactToMessage = async ({ message, emoji }) => {
  if (!message?.metaMessageId) return

  const convId = props.conversationId
  const previousEmoji = message.reactionEmoji || ''

  messagesStore.upsertMessage({ ...message, reactionEmoji: emoji })

  try {
    const response = await fetch(
      `/dashboard/whatsapp/conversaciones/${convId}/mensajes/${message.id}/reaccionar/`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': conversationService.getCsrfToken(),
        },
        credentials: 'include',
        body: JSON.stringify({ emoji }),
      }
    )

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    if (!data?.success) {
      messagesStore.upsertMessage({ ...message, reactionEmoji: previousEmoji })
      sendError.value = data?.error_detail || 'No se pudo enviar la reacción.'
    }
  } catch (error) {
    console.error('[ConversationPanel] React failed:', error)
    messagesStore.upsertMessage({ ...message, reactionEmoji: previousEmoji })
    sendError.value = 'No se pudo conectar con el servidor.'
  }
}

// Watch para cuando cambia el conversationId
watch(() => props.conversationId, (newId, oldId) => {
  console.log('[ConversationPanel watch] conversationId changed from ' + oldId + ' to ' + newId)
  loadMessages()
  nextTick(() => composerRef.value?.focus())
}, { immediate: false })

// Cargar mensajes al montar si hay conversationId
onMounted(() => {
  if (props.conversationId) {
    loadMessages()
    nextTick(() => composerRef.value?.focus())
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
