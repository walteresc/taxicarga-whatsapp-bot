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
      <!-- Menú chevron (WhatsApp Web style) — flota fuera del área de texto de la
           burbuja (esquina superior), visible solo al pasar el mouse por el mensaje.
           El panel se teletransporta a <body> (ver más abajo): el timeline de
           mensajes tiene overflow:hidden para el scroll, y eso recorta cualquier
           dropdown posicionado dentro de él sin importar el z-index. -->
      <div class="message-menu-trigger">
        <button
          ref="menuTriggerBtn"
          class="menu-chevron"
          title="Opciones"
          @click.stop="toggleMenu"
        >
          <i class="ri-arrow-down-s-line" />
        </button>
      </div>

      <Teleport to="body">
        <div
          v-if="showMenuOptions"
          ref="menuPanelRef"
          class="message-menu message-menu--floating"
          :style="menuStyle"
          @click.stop
        >
          <button
            v-if="message.metaMessageId"
            class="menu-item"
            @click="handleReply"
          >
            <i class="ri-reply-line" />
            Responder
          </button>
          <button
            v-if="message.metaMessageId"
            class="menu-item"
            @click="openReactionPicker"
          >
            <i class="ri-emotion-happy-line" />
            Reaccionar
          </button>
          <button
            class="menu-item"
            @click="handleForward"
          >
            <i class="ri-share-forward-line" />
            Reenviar
          </button>
          <button
            class="menu-item menu-item--danger"
            @click="handleHideForMe"
          >
            <i class="ri-eye-off-line" />
            Ocultar en el CRM
          </button>
        </div>
      </Teleport>

      <!-- Selector rápido de emoji (WhatsApp-style) -->
      <Teleport to="body">
        <div
          v-if="showReactionPicker"
          ref="reactionPanelRef"
          class="reaction-picker reaction-picker--floating"
          :style="reactionStyle"
          @click.stop
        >
          <button
            v-for="emoji in quickEmojis"
            :key="emoji"
            class="reaction-picker-item"
            @click="pickReaction(emoji)"
          >
            {{ emoji }}
          </button>
        </div>
      </Teleport>

      <!-- Badge de reacción (esquina inferior de la burbuja, WhatsApp-style). Solo
           informativo: no sabemos si la puso el cliente o el asesor, así que no se
           quita con un clic acá — se quita eligiendo el mismo emoji otra vez en el
           selector (abajo, "Reaccionar"). -->
      <div
        v-if="message.reactionEmoji"
        class="reaction-badge"
      >
        {{ message.reactionEmoji }}
      </div>

      <!-- Cita del mensaje al que se responde -->
      <div
        v-if="message.replyTo"
        class="quoted-reply"
      >
        <span class="quoted-reply-sender">{{ message.replyTo.senderName }}</span>
        <span class="quoted-reply-text">{{ message.replyTo.text }}</span>
      </div>

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
            @click="openImageViewer(attachment.url, attachment.filename)"
          >
        </template>
        <div
          v-else
          class="message-unavailable"
        >
          <i :class="isUploading ? 'ri-loader-4-line spin' : 'ri-image-line'" />
          <span>{{ isUploading ? 'Enviando imagen...' : 'Imagen no disponible' }}</span>
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
          <AudioPlayer
            v-for="(attachment, idx) in message.attachments"
            :key="idx"
            :src="attachment.url"
          />
        </template>
        <div
          v-else
          class="message-unavailable"
        >
          <i :class="isUploading ? 'ri-loader-4-line spin' : 'ri-mic-line'" />
          <span>{{ isUploading ? 'Enviando audio...' : 'Audio no disponible' }}</span>
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
          <i :class="isUploading ? 'ri-loader-4-line spin' : 'ri-video-line'" />
          <span>{{ isUploading ? 'Enviando video...' : 'Video no disponible' }}</span>
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
          <i :class="isUploading ? 'ri-loader-4-line spin' : 'ri-file-line'" />
          <span>{{ isUploading ? 'Enviando documento...' : 'Documento no disponible' }}</span>
        </div>
      </div>

      <!-- Contenido de texto -->
      <p
        v-else
        class="message-text"
        v-html="renderWhatsAppText(message.text)"
      />

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
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { formatMessageTime } from '@/utils/dateUtils'
import { renderWhatsAppText } from '@/utils/whatsappMarkdown'
import AudioPlayer from './AudioPlayer.vue'
import { useImageViewer } from '@/composables/useImageViewer'

const { open: openImageViewer } = useImageViewer()

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['retry', 'reply', 'forward', 'hide-for-me', 'react'])

const showMenuOptions = ref(false)
const showReactionPicker = ref(false)
const quickEmojis = ['👍', '❤️', '😂', '😮', '😢', '🙏']

// Floating panels are teleported to <body> (see template) — the message timeline's
// scroll container has overflow:hidden, which clips any dropdown positioned inside
// it no matter the z-index. Position is computed from the trigger button's actual
// screen location instead of relying on CSS absolute positioning within the bubble.
const menuTriggerBtn = ref(null)
const menuPanelRef = ref(null)
const reactionPanelRef = ref(null)
const menuStyle = ref({})
const reactionStyle = ref({})

const computeFloatingStyle = () => {
  if (!menuTriggerBtn.value) return {}
  const rect = menuTriggerBtn.value.getBoundingClientRect()

  return {
    position: 'fixed',
    top: `${rect.bottom + 4}px`,
    right: `${window.innerWidth - rect.right}px`,
  }
}

const toggleMenu = () => {
  showReactionPicker.value = false
  if (showMenuOptions.value) {
    showMenuOptions.value = false

    return
  }
  menuStyle.value = computeFloatingStyle()
  showMenuOptions.value = true
}

// mousedown + capture (same pattern as ChatComposer's popovers): fires before the
// panel's own @click.stop, so it reliably detects clicks anywhere else — including
// the teleported panel itself, which is checked separately since it no longer lives
// inside the trigger's DOM subtree once teleported to <body>.
const closeFloatingIfOutside = event => {
  if (
    showMenuOptions.value
    && !menuTriggerBtn.value?.contains(event.target)
    && !menuPanelRef.value?.contains(event.target)
  ) {
    showMenuOptions.value = false
  }
  if (
    showReactionPicker.value
    && !menuTriggerBtn.value?.contains(event.target)
    && !reactionPanelRef.value?.contains(event.target)
  ) {
    showReactionPicker.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', closeFloatingIfOutside, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', closeFloatingIfOutside, true)
})

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

const isUploading = computed(() => props.message.status === 'sending')

const formatTime = timestamp => {
  return formatMessageTime(timestamp) || ''
}

const handleReply = () => {
  if (!props.message.metaMessageId) return
  emit('reply', props.message)
  showMenuOptions.value = false
}

const handleForward = () => {
  emit('forward', props.message)
  showMenuOptions.value = false
}

const handleHideForMe = () => {
  showMenuOptions.value = false
  const confirmed = window.confirm(
    'Se ocultará en el CRM. El cliente seguirá viéndolo en su WhatsApp.'
  )
  if (!confirmed) return
  emit('hide-for-me', props.message)
}

const openReactionPicker = () => {
  if (!props.message.metaMessageId) return
  showMenuOptions.value = false
  reactionStyle.value = computeFloatingStyle()
  showReactionPicker.value = true
}

/** Clicking the currently-active emoji again removes the reaction (sends ''). */
const pickReaction = emoji => {
  const next = props.message.reactionEmoji === emoji ? '' : emoji
  emit('react', { message: props.message, emoji: next })
  showReactionPicker.value = false
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
  position: relative;
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 8px;
  word-wrap: break-word;
  overflow-wrap: break-word;
  background: #e0e0e0;
  color: #333;
}

/* Menú chevron (WhatsApp Web style) — flota FUERA de la burbuja (esquina superior),
   nunca sobre el texto/cita. Blanco con borde para contraste sobre cualquier color
   de burbuja (naranja del asesor incluido). Solo visible al pasar el mouse. */
.message-menu-trigger {
  position: absolute;
  top: -10px;
  right: -8px;
  /* Must beat the bandeja sidebar's own filter-menu popover (z-index: 10000) — they
     can visually overlap since the sidebar and the chat panel are siblings. */
  z-index: 20000;
  opacity: 0;
  transition: opacity 0.15s;
}

.message-bubble:hover .message-menu-trigger {
  opacity: 1;
}

.menu-chevron {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 50%;
  cursor: pointer;
  color: #555;
  font-size: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: background 0.15s;
}

.menu-chevron:hover {
  background: #f0f0f0;
}

.message-menu {
  position: absolute;
  top: 30px;
  right: 0;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  min-width: 140px;
  z-index: 20;
  overflow: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: #333;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}

.menu-item:hover {
  background: #f5f5f5;
}

.menu-item--danger {
  color: #d32f2f;
}

.menu-item--danger:hover {
  background: #ffebee;
}

/* Selector rápido de emoji */
.reaction-picker {
  position: absolute;
  top: 30px;
  right: 0;
  display: flex;
  gap: 2px;
  padding: 6px 8px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  z-index: 20;
}

.message-container--customer .reaction-picker {
  right: auto;
  left: 0;
}

.reaction-picker-item {
  border: none;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  padding: 4px;
  border-radius: 50%;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}

.reaction-picker-item:hover {
  background: #f0f0f0;
  transform: scale(1.15);
}

/* Badge de reacción sobre la burbuja */
.reaction-badge {
  position: absolute;
  bottom: -10px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 13px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 50%;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
  z-index: 5;
}

.message-container--customer .reaction-badge {
  right: auto;
  left: 8px;
}

.menu-item i {
  font-size: 14px;
}

/* Cita del mensaje respondido */
.quoted-reply {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 8px;
  margin-bottom: 6px;
  border-left: 3px solid #ff9800;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 4px;
  font-size: 12px;
}

.message-bubble--advisor .quoted-reply {
  background: rgba(255, 255, 255, 0.18);
  border-left-color: #fff;
}

.quoted-reply-sender {
  font-weight: 600;
  color: #ff9800;
}

.message-bubble--advisor .quoted-reply-sender {
  color: #fff;
}

.quoted-reply-text {
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Botón de responder - visible al pasar el mouse por el mensaje */
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

/* v-html content isn't compiled by Vue's scoping — :deep() needed to reach it */
:deep(.message-text strong) {
  font-weight: 700;
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

/* WhatsApp's own blue for the read (double-check) tick — every other status stays
   the bubble's default text color, same as WhatsApp Web. */
.message-status.read {
  color: #53bdeb;
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
  cursor: pointer;
  transition: opacity 0.15s;
}

.message-image:hover {
  opacity: 0.92;
}

.message-video {
  max-width: 100%;
  max-height: 300px;
  border-radius: 6px;
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

.spin {
  animation: message-bubble-spin 0.8s linear infinite;
}

@keyframes message-bubble-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
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
