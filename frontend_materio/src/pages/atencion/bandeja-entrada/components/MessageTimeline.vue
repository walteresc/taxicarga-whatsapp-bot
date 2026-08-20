<template>
  <div class="message-timeline">
    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <div v-for="i in 5" :key="`skeleton-${i}`" class="skeleton-message">
        <div class="skeleton-avatar"></div>
        <div class="skeleton-bubble"></div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="messageGroups.length === 0" class="empty-state">
      <i class="ri-message-2-line"></i>
      <p>Sin mensajes</p>
    </div>

    <!-- Messages grouped by date -->
    <div v-else>
      <div v-for="group in messageGroups" :key="group.displayDate || 'invalid'" class="message-group">
        <!-- Date separator (only if date is valid) -->
        <div v-if="group.displayDate" class="date-separator">
          <span>{{ group.displayDate }}</span>
        </div>

        <!-- Messages in this group -->
        <div v-for="message in group.messages" :key="message.id">
          <MessageBubble v-if="message.type !== 'internal-note'" :message="message" />
          <InternalNote v-else :note="message" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MessageBubble from './MessageBubble.vue'
import InternalNote from './InternalNote.vue'
import { groupMessagesByDate } from '@/utils/dateUtils'

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  loading: Boolean,
})

const messageGroups = computed(() => {
  return groupMessagesByDate(props.messages)
})
</script>

<style scoped>
.message-timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  overscroll-behavior: contain;
}

.loading-state {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-message {
  display: flex;
  gap: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f0f0;
  flex-shrink: 0;
}

.skeleton-bubble {
  flex: 1;
  height: 40px;
  border-radius: 8px;
  background: #f0f0f0;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: #999;
}

.empty-state i {
  font-size: 48px;
  opacity: 0.3;
}

.empty-state p {
  margin: 0;
  font-size: 13px;
}

.message-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.date-separator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
}

.date-separator::before,
.date-separator::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e0e0e0;
}

.date-separator span {
  font-size: 11px;
  color: #999;
  font-weight: 500;
  white-space: nowrap;
}
</style>
