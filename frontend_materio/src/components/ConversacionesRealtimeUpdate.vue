<!--
Real-time update handler for conversaciones list (FASE 5B)
Integrates with event store to refresh bandeja items in real time
-->

<script setup>
import { computed, watch } from 'vue'
import { useRealtime } from '@/composables/useRealtime'

const props = defineProps({
  conversaciones: {
    type: Array,
    default: () => [],
  },
  onConversationUpdate: {
    type: Function,
    default: null,
  },
})

const emit = defineEmits(['update-conversation'])

const { events, isConnected, getEventsByType } = useRealtime()

// Listen to conversation updates
const conversationUpdates = computed(() =>
  getEventsByType('conversation_update')
)

const messageCreatedEvents = computed(() =>
  getEventsByType('message_created')
)

// Handle conversation updates
watch(conversationUpdates, (updates) => {
  updates.forEach((update) => {
    const convId = update.data?.conversation_id
    if (convId) {
      emit('update-conversation', {
        id: convId,
        preview: update.data?.preview,
        lastActivity: update.data?.last_activity,
      })
      if (props.onConversationUpdate) {
        props.onConversationUpdate(convId)
      }
    }
  })
})

// Handle new messages (update conversation preview/activity)
watch(messageCreatedEvents, (events) => {
  events.forEach((event) => {
    const convId = event.data?.conversation_id
    if (convId) {
      emit('update-conversation', {
        id: convId,
        lastMessage: {
          id: event.data?.message_id,
          sender: event.data?.sender_type,
          timestamp: event.data?.timestamp,
        },
      })
    }
  })
})

// Expose status for parent components
const connectionStatus = computed(() => ({
  isConnected,
  eventCount: events.length,
}))

defineExpose({
  connectionStatus,
})
</script>

<template>
  <div class="conversaciones-realtime">
    <!-- Connection indicator -->
    <div v-if="!isConnected" class="connection-warning">
      <v-icon size="small">mdi-wifi-off</v-icon>
      <span>Reconectando...</span>
    </div>
  </div>
</template>

<style scoped>
.conversaciones-realtime {
  position: relative;
}

.connection-warning {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: #ff9800;
  color: white;
  padding: 12px 16px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  z-index: 1000;
}
</style>
