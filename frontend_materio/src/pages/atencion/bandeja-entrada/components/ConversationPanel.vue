<template>
  <div class="conversation-panel">
    <!-- Empty state -->
    <EmptyConversationState v-if="!conversationId" />

    <!-- Chat -->
    <div v-else class="chat-content">
      <!-- Header -->
      <ConversationHeader :conversation="conversation" class="conversation-header" />

      <!-- Messages -->
      <MessageTimeline :messages="messages" :loading="loadingMessages" class="message-timeline" />

      <!-- Composer -->
      <ChatComposer
        class="chat-composer"
        :bot-attending="conversation?.estadoAtencion === 'bot'"
        :advisor-name="conversation?.responsable?.name || 'Walter Escobar'"
        @send-message="handleSendMessage"
        @take-control="handleTakeControl"
        @clear-reply="clearReply"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import EmptyConversationState from './EmptyConversationState.vue'
import ConversationHeader from './ConversationHeader.vue'
import MessageTimeline from './MessageTimeline.vue'
import ChatComposer from './ChatComposer.vue'
import { conversationService } from '@/services/conversationService'

const props = defineProps({
  conversationId: {
    type: Number,
    default: null,
  },
  conversation: {
    type: Object,
    default: null,
  },
})

const messages = ref([])
const loadingMessages = ref(false)

const loadMessages = async () => {
  if (!props.conversationId) {
    messages.value = []
    return
  }

  loadingMessages.value = true
  try {
    const data = await conversationService.getConversationMessages(props.conversationId)
    messages.value = data.messages || []
  } catch (error) {
    console.error('Error loading messages:', error)
    messages.value = []
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

const clearReply = () => {
  console.log('Clear reply')
  // TODO: Clear reply state
}

// Watch para cuando cambia el conversationId
watch(() => props.conversationId, () => {
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
  overflow: visible;
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
