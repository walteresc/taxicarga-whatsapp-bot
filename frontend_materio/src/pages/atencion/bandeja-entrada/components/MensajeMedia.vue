<template>
  <div
    class="message-container"
    :class="[senderType]"
  >
    <!-- Mostrar nombre del asesor/bot encima del mensaje -->
    <div
      v-if="showSenderName"
      class="sender-name"
    >
      {{ message.senderName }}
    </div>

    <!-- Burbuja del mensaje -->
    <div
      class="message-bubble"
      :class="[senderType, `media-${message.tipo}`]"
    >
      <!-- Contenido según tipo -->
      <component
        :is="mediaComponent"
        :message="message"
      />

      <div class="message-footer">
        <span class="message-time">{{ formatTime(message.fecha_mensaje) }}</span>
        <span
          v-if="showStatus"
          class="message-status"
          :class="[message.estado]"
        >
          <i :class="getStatusIcon(message.estado)" />
        </span>
      </div>
    </div>

    <!-- Indicador de retención -->
    <div
      v-if="showRetentionWarning"
      class="retention-warning"
    >
      <i class="ri-shield-exclamation-line" />
      <span>Se eliminará el {{ retentionDate }}</span>
    </div>

    <!-- Loading state (para media_status=PENDING) -->
    <div
      v-if="isMediaPending"
      class="media-loading"
    >
      <div class="spinner" />
      <span>Descargando multimedia...</span>
    </div>

    <!-- Error state (para media_status=FAILED/EXPIRED) -->
    <div
      v-if="isMediaFailed"
      class="media-error"
    >
      <i class="ri-alert-line" />
      <span>{{ mediaErrorMessage }}</span>
    </div>

    <!-- Botón de reintentar si falló -->
    <div
      v-if="message.estado === 'error'"
      class="message-retry"
    >
      <button
        class="retry-btn"
        @click="retryMessage"
      >
        <i class="ri-refresh-line" />
        Reintentar
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatMessageTime } from '@/utils/dateUtils'

// Media type components
import MediaText from './media/MediaText.vue'
import MediaImage from './media/MediaImage.vue'
import MediaVideo from './media/MediaVideo.vue'
import MediaAudio from './media/MediaAudio.vue'
import MediaDocument from './media/MediaDocument.vue'
import MediaLocation from './media/MediaLocation.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['retry'])

// Mapped types
const TIPO_TO_COMPONENT = {
  texto: MediaText,
  imagen: MediaImage,
  video: MediaVideo,
  audio: MediaAudio,
  documento: MediaDocument,
  ubicacion: MediaLocation,
}

const senderType = computed(() => {
  const senderMap = {
    customer: 'client',
    bot: 'bot',
    advisor: 'advisor',
    system: 'system',
  }

  
  return senderMap[props.message.sender_type] || 'client'
})

const showSenderName = computed(() => {
  return ['bot', 'advisor'].includes(senderType.value) && props.message.senderName
})

const showStatus = computed(() => {
  return senderType.value === 'advisor' && props.message.estado
})

const mediaComponent = computed(() => {
  return TIPO_TO_COMPONENT[props.message.tipo] || MediaText
})

// Media status
const isMediaPending = computed(() => {
  return props.message.media_status === 'pending' ||
         props.message.media_status === 'downloading'
})

const isMediaFailed = computed(() => {
  return props.message.media_status === 'failed' ||
         props.message.media_status === 'expired'
})

const mediaErrorMessage = computed(() => {
  if (props.message.media_status === 'expired') {
    return 'El archivo ha expirado'
  }
  if (props.message.media_status === 'failed') {
    return 'No se pudo descargar el archivo'
  }
  
  return 'Archivo no disponible'
})

// Retention warning
const showRetentionWarning = computed(() => {
  // Show warning if:
  // 1. File is ready (media_status === 'ready')
  // 2. NOT protected from cleanup
  // 3. Expiration date is within 3 days
  if (!props.message.adjuntos || props.message.adjuntos.length === 0) {
    return false
  }

  const adjunto = props.message.adjuntos[0]
  if (adjunto.protected_from_cleanup || !adjunto.retain_until) {
    return false
  }

  const retainDate = new Date(adjunto.retain_until)
  const now = new Date()
  const daysUntilDelete = (retainDate - now) / (1000 * 60 * 60 * 24)

  return daysUntilDelete <= 3 && daysUntilDelete > 0
})

const retentionDate = computed(() => {
  if (!props.message.adjuntos || props.message.adjuntos.length === 0) {
    return ''
  }

  const adjunto = props.message.adjuntos[0]
  if (!adjunto.retain_until) return ''

  const date = new Date(adjunto.retain_until)
  
  return date.toLocaleDateString('es-PE', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
})

const formatTime = timestamp => {
  return formatMessageTime(timestamp) || ''
}

const getStatusIcon = status => {
  const icons = {
    recibido: 'ri-time-line',
    enviado: 'ri-check-line',
    entregado: 'ri-check-double-line',
    leido: 'ri-check-double-fill',
    error: 'ri-close-circle-line',
    pendiente: 'ri-time-line',
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

/* Media-specific styles */
.message-bubble.media-imagen,
.message-bubble.media-video {
  padding: 4px;
  background: #f5f5f5;
}

.message-bubble.media-audio,
.message-bubble.media-documento {
  max-width: 300px;
  padding: 12px;
}

.message-footer {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 11px;
}

.message-time {
  color: #999;
}

.message-bubble.advisor .message-time {
  color: rgba(255, 255, 255, 0.7);
}

.message-status {
  display: inline-flex;
  align-items: center;
}

.message-status i {
  font-size: 12px;
}

.message-status.enviado,
.message-status.entregado {
  color: #4caf50;
}

.message-status.leido {
  color: #2196f3;
}

.message-status.error {
  color: #f44336;
}

/* Retention warning */
.retention-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #f44336;
  padding: 0 12px;
  margin-top: 4px;
}

.retention-warning i {
  font-size: 14px;
}

/* Media loading state */
.media-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  padding: 8px 12px;
  background: #f9f9f9;
  border-radius: 6px;
  margin-top: 4px;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #e0e0e0;
  border-top-color: #ff9800;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Media error state */
.media-error {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #f44336;
  padding: 8px 12px;
  background: #ffebee;
  border-radius: 6px;
  border-left: 3px solid #f44336;
  margin-top: 4px;
}

.media-error i {
  font-size: 14px;
}

/* Retry button */
.message-retry {
  margin-top: 6px;
  padding: 0 12px;
}

.retry-btn {
  padding: 6px 12px;
  font-size: 12px;
  background: #ff9800;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: #f57c00;
}

.retry-btn i {
  font-size: 14px;
}
</style>
