<template>
  <div :class="['message-container', senderType]" :data-testid="`message-row-${message.id}`" :data-sender="senderType">
    <!-- Mostrar nombre del asesor/bot encima del mensaje -->
    <div v-if="showSenderName" class="sender-name">{{ message.senderName }}</div>

    <!-- Burbuja del mensaje -->
    <div :class="['message-bubble', senderType]" :data-testid="`message-bubble-${message.id}`">
      <p class="message-text">{{ message.text }}</p>

      <div class="message-footer">
        <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        <span v-if="showStatus" :class="['message-status', message.status]">
          <i :class="getStatusIcon(message.status)"></i>
        </span>
      </div>
    </div>

    <!-- Botón de reintentar si falló -->
    <div v-if="message.status === 'failed'" class="message-retry">
      <button @click="retryMessage" class="retry-btn">
        <i class="ri-refresh-line"></i>
        Reintentar
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatMessageTime } from '@/utils/dateUtils'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['retry'])

const senderType = computed(() => {
  return props.message.sender || 'client'
})

const showSenderName = computed(() => {
  return ['bot', 'advisor'].includes(senderType.value) && props.message.senderName
})

const showStatus = computed(() => {
  return senderType.value === 'advisor' && props.message.status
})

const formatTime = (timestamp) => {
  return formatMessageTime(timestamp) || ''
}

const getStatusIcon = (status) => {
  const icons = {
    sending: 'ri-time-line',
    sent: 'ri-check-line',
    delivered: 'ri-check-double-line',
    read: 'ri-check-double-fill',
    failed: 'ri-close-circle-line',
  }
  return icons[status] || 'ri-time-line'
}

const retryMessage = () => {
  emit('retry', props.message)
}
</script>

<style scoped>
.message-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  animation: slideIn 0.2s ease-out;
}

.message-container.client {
  align-items: flex-start;
}

.message-container.bot,
.message-container.advisor {
  align-items: flex-end;
}

.message-container.system {
  align-items: center;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Nombre del remitente */
.sender-name {
  font-size: 11px;
  font-weight: 600;
  color: #666;
  padding: 0 12px;
}

/* Burbuja del mensaje */
.message-bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 8px;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.message-bubble.client {
  background: #f0f0f0;
  color: #333;
  border-bottom-left-radius: 2px;
}

.message-bubble.bot {
  background: #fff3e0;
  color: #333;
  border-bottom-right-radius: 2px;
  border: 1px solid #ffe0b2;
}

.message-bubble.advisor {
  background: #ff9800;
  color: #fff;
  border-bottom-right-radius: 2px;
}

.message-bubble.system {
  background: transparent;
  color: #999;
  font-size: 12px;
  text-align: center;
  width: 100%;
  max-width: 100%;
}

.message-text {
  margin: 0;
  line-height: 1.4;
  white-space: pre-wrap;
}

/* Footer con hora y estado */
.message-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 11px;
}

.message-container.client .message-footer {
  justify-content: flex-start;
  color: #999;
}

.message-container.bot .message-footer,
.message-container.advisor .message-footer {
  justify-content: flex-end;
}

.message-container.bot .message-footer {
  color: #666;
}

.message-container.advisor .message-footer {
  color: #fff;
  opacity: 0.8;
}

.message-status {
  display: inline-flex;
  align-items: center;
}

.message-status i {
  font-size: 12px;
}

.message-status.failed {
  color: #f44336;
}

/* Botón de reintentar */
.message-retry {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}

.retry-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid #f44336;
  color: #f44336;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover {
  background: #ffebee;
}

.retry-btn i {
  font-size: 12px;
}
</style>
