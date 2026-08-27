<template>
  <div class="conversation-panel" data-testid="conversation-panel">
    <!-- Empty state -->
    <EmptyConversationState v-if="!conversationId" />

    <!-- Chat -->
    <div v-else class="chat-content" data-testid="chat-content">
      <!-- Header -->
      <ConversationHeader :conversation="conversation" :bot-global-paused="botGlobalPaused" :effective-bot-paused="effectiveBotPaused" class="conversation-header" data-testid="conversation-header" />

      <!-- Messages -->
      <MessageTimeline :messages="messages" :loading="loadingMessages" class="message-timeline" data-testid="message-timeline-wrapper" />

      <!-- Composer -->
      <ChatComposer
        class="chat-composer"
        :attention-mode="conversation?.attentionMode || 'unassigned'"
        :advisor-name="conversation?.responsable?.nombre || 'Walter Escobar'"
        :effective-bot-paused="effectiveBotPaused"
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
  } catch (error) {
    console.error('Error loading messages:', error)
  } finally {
    loadingMessages.value = false
  }
}

const handleSendMessage = (messageData) => {
  console.log('Send message:', messageData)
  // TODO: Implement send message via API
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
