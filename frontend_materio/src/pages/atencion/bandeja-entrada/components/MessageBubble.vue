<template>
  <div
    class="message-container"
    :class="[`message-container--${message.senderType}`]"
    :data-testid="`message-row-${message.id}`"
    :data-sender="message.senderType"
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
      :class="[`message-bubble--${message.senderType}`]"
      :data-testid="`message-bubble-${message.id}`"
    >
      <!-- Contenido de imagen -->
      <div
        v-if="message.contentType === 'image'"
        class="message-multimedia"
      >
        <template v-if="hasAttachments">
          <img
            v-for="(attachment, idx) in message.attachments"
            :key="idx"
            :src="attachment.url"
            :alt="attachment.filename || 'Imagen'"
            class="message-image"
          >
        </template>
        <div
          v-else
          class="message-unavailable"
        >
          <i class="ri-image-line" />
          <span>Imagen no disponible</span>
        </div>
        <p
          v-if="message.caption"
          class="message-caption"
        >{{ message.caption }}</p>
      </div>

      <!-- Contenido de audio -->
      <div
        v-else-if="message.contentType === 'audio'"
        class="message-multimedia"
      >
        <template v-if="hasAttachments">
          <div
            v-for="(attachment, idx) in message.attachments"
            :key="idx"
            class="message-audio"
          >
            <audio
              controls
              class="audio-player"
            >
              <source
                :src="attachment.url"
                :type="attachment.mime_type || 'audio/ogg'"
              >
              Tu navegador no soporta audio.
            </audio>
          </div>
        </template>
        <div
          v-else
          class="message-unavailable"
        >
          <i class="ri-mic-line" />
          <span>Audio no disponible</span>
        </div>
      </div>

      <!-- Contenido de video -->
      <div
        v-else-if="message.contentType === 'video'"
        class="message-multimedia"
      >
        <template v-if="hasAttachments">
          <video
            v-for="(attachment, idx) in message.attachments"
            :key="idx"
            controls
            class="message-video"
          >
            <source
              :src="attachment.url"
              :type="attachment.mime_type || 'video/mp4'"
            >
            Tu navegador no soporta video.
          </video>
        </template>
        <div
          v-else
          class="message-unavailable"
        >
          <i class="ri-video-line" />
          <span>Video no disponible</span>
        </div>
        <p
          v-if="message.caption"
          class="message-caption"
        >{{ message.caption }}</p>
      </div>

      <!-- Contenido de documento -->
      <div
        v-else-if="message.contentType === 'document'"
        class="message-document"
      >
        <template v-if="hasAttachments">
          <div
            v-for="(attachment, idx) in message.attachments"
            :key="idx"
            class="document-link"
          >
            <a
              :href="attachment.url"
              :download="attachment.filename"
              target="_blank"
              rel="noopener noreferrer"
            >
              <i class="ri-file-download-line" />
              {{ attachment.filename || 'Descargar archivo' }}
            </a>
          </div>
        </template>
        <div
          v-else
          class="message-unavailable"
        >
          <i class="ri-file-line" />
          <span>Documento no disponible</span>
        </div>
      </div>

      <!-- Contenido de texto -->
      <p
        v-else
        class="message-text"
      >
        {{ message.text }}
      </p>

      <div class="message-footer">
        <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        <span
          v-if="showStatus"
          class="message-status"
          :class="[message.status]"
        >
          <i :class="getStatusIcon(message.status)" />
        </span>
      </div>
    </div>

    <!-- Botón de reintentar si falló -->
    <div
      v-if="message.status === 'failed'"
      class="message-retry"
    >
      <span
        v-if="message.errorDetail"
        class="retry-error-detail"
      >{{ message.errorDetail }}</span>
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

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['retry'])

// Message must come pre-normalized with canonical senderType
const showSenderName = computed(() => {
  return ['bot', 'advisor'].includes(props.message.senderType) && props.message.senderName
})

const showStatus = computed(() => {
  return props.message.senderType === 'advisor' && props.message.status
})

const hasAttachments = computed(() => {
  return Array.isArray(props.message.attachments) && props.message.attachments.length > 0
})

const formatTime = timestamp => {
  return formatMessageTime(timestamp) || ''
}

const getStatusIcon = status => {
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

.message-container--customer {
  align-items: flex-start;
}

.message-container--bot,
.message-container--advisor {
  align-items: flex-end;
}

.message-container--system {
  align-items: center;
}

.message-container--unknown {
  align-items: flex-start;
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

/* Burbuja del mensaje - Base */
.message-bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 8px;
  word-wrap: break-word;
  overflow-wrap: break-word;
  background: #e0e0e0;
  color: #333;
}

/* Customer (inbound) - left aligned, light background */
.message-bubble--customer {
  background: #f0f0f0;
  color: #333;
  border-bottom-left-radius: 2px;
}

/* Bot - right aligned, brand color */
.message-bubble--bot {
  background: #fff3e0;
  color: #333;
  border-bottom-right-radius: 2px;
  border: 1px solid #ffe0b2;
}

/* Advisor - right aligned, distinct from bot */
.message-bubble--advisor {
  background: #ff9800;
  color: #fff;
  border-bottom-right-radius: 2px;
}

/* System - centered, transparent */
.message-bubble--system {
  background: transparent;
  color: #999;
  font-size: 12px;
  text-align: center;
  width: 100%;
  max-width: 100%;
}

/* Unknown sender - neutral visible style (never transparent) */
.message-bubble--unknown {
  background: #e8e8e8;
  color: #666;
  border: 1px dashed #999;
  border-bottom-left-radius: 2px;
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
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  margin-top: 4px;
}

.retry-error-detail {
  font-size: 11px;
  color: #f44336;
  text-align: right;
  max-width: 240px;
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

/* Multimedia */
.message-multimedia {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-image {
  max-width: 100%;
  max-height: 300px;
  border-radius: 6px;
  object-fit: cover;
}

.message-video {
  max-width: 100%;
  max-height: 300px;
  border-radius: 6px;
}

.audio-player {
  width: 100%;
  max-width: 300px;
  height: 32px;
  border-radius: 4px;
}

.message-caption {
  margin: 4px 0 0 0;
  font-size: 13px;
  line-height: 1.4;
}

.message-unavailable {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 4px;
  font-size: 13px;
  font-style: italic;
  opacity: 0.75;
  min-width: 140px;
}

.message-unavailable i {
  font-size: 16px;
}

.message-document {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.document-link {
  display: flex;
  align-items: center;
}

.document-link a {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  text-decoration: none;
  transition: all 0.2s;
  word-break: break-all;
}

.message-bubble--customer .document-link a {
  color: #1976d2;
  background: rgba(25, 118, 210, 0.1);
}

.message-bubble--customer .document-link a:hover {
  background: rgba(25, 118, 210, 0.2);
}

.message-bubble--bot .document-link a {
  color: #1976d2;
  background: rgba(25, 118, 210, 0.1);
}

.message-bubble--bot .document-link a:hover {
  background: rgba(25, 118, 210, 0.2);
}

.message-bubble--advisor .document-link a {
  color: #fff;
  background: rgba(255, 255, 255, 0.2);
}

.message-bubble--advisor .document-link a:hover {
  background: rgba(255, 255, 255, 0.3);
}

.document-link i {
  font-size: 16px;
}
</style>
