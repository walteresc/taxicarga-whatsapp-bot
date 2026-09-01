<template>
  <div
    ref="composerRoot"
    class="chat-composer"
  >
    <!-- Estado bot pausado (no mostrar "atendiendo" si pausado) -->
    <div
      v-if="attentionMode === 'bot' && effectiveBotPaused"
      class="bot-paused-state"
    >
      <div class="bot-message paused">
        <i class="ri-robot-line" />
        <span>El bot está pausado</span>
      </div>
    </div>

    <!-- Estado bot atendiendo -->
    <div
      v-else-if="attentionMode === 'bot'"
      class="bot-attending"
    >
      <div class="bot-message">
        <i class="ri-robot-line" />
        <span>El bot está atendiendo esta conversación</span>
      </div>
      <button
        class="take-control-btn"
        @click="$emit('take-control')"
      >
        Tomar conversación
      </button>
    </div>

    <!-- Estado sin asignar -->
    <div
      v-else-if="attentionMode === 'unassigned'"
      class="unassigned-state"
    >
      <div class="unassigned-message">
        <i class="ri-user-line" />
        <span>Esta conversación todavía no tiene asesor</span>
      </div>
      <button
        class="assign-btn"
        @click="$emit('assign-me')"
      >
        Asignarme
      </button>
    </div>

    <!-- Estado conversación cerrada -->
    <div
      v-else-if="attentionMode === 'closed'"
      class="closed-state"
    >
      <div class="closed-message">
        <i class="ri-lock-line" />
        <span>Conversación cerrada</span>
      </div>
      <button
        class="reopen-btn"
        @click="$emit('reopen')"
      >
        Reabrir
      </button>
    </div>

    <!-- Composer activo (asesor atendiendo) -->
    <div
      v-else-if="attentionMode === 'advisor'"
      class="composer-content"
    >
      <!-- Línea informativa -->
      <div class="composer-header">
        <div class="channel-info">
          <i class="ri-whatsapp-line" />
          <span>WhatsApp</span>
        </div>
        <div class="advisor-info">
          <span>Respondiendo como {{ advisorName }}</span>
        </div>
        <div class="status-badge">
          <span class="status-dot" />
          Disponible
        </div>
      </div>

      <!-- Respuesta citada -->
      <div
        v-if="replyingTo"
        class="reply-preview"
      >
        <div class="reply-close">
          <button @click="$emit('clear-reply')">
            <i class="ri-close-line" />
          </button>
        </div>
        <div class="reply-content">
          <span class="reply-label">Respondiendo a {{ replyingTo.senderName }}</span>
          <p class="reply-text">
            {{ replyingTo.text }}
          </p>
        </div>
      </div>

      <!-- Error de envío -->
      <div
        v-if="sendError"
        class="send-error-banner"
      >
        <i class="ri-error-warning-line" />
        <span>{{ sendError }}</span>
      </div>

      <!-- Compositor input -->
      <div class="composer-input-wrapper">
        <div class="composer-pill">
          <div
            ref="emojiAnchor"
            class="action-anchor"
          >
            <button
              class="action-btn"
              title="Emoji"
              :disabled="sending"
              @click="showEmojiPicker = !showEmojiPicker; showQuickReplies = false"
            >
              <i class="ri-emotion-line" />
            </button>

            <!-- Emoji picker: floating popover anchored to this button -->
            <div
              v-if="showEmojiPicker"
              class="popover emoji-picker"
            >
              <div
                v-for="emoji in emojis"
                :key="emoji"
                class="emoji-item"
                @click="insertEmoji(emoji)"
              >
                {{ emoji }}
              </div>
            </div>
          </div>

          <div
            ref="attachAnchor"
            class="action-anchor"
          >
            <button
              class="action-btn"
              title="Adjuntar"
              :disabled="sending"
              @click="showAttachMenu = !showAttachMenu; showEmojiPicker = false; showQuickReplies = false"
            >
              <i class="ri-attachment-line" />
            </button>

            <!-- Attach menu: floating popover anchored to this button -->
            <div
              v-if="showAttachMenu"
              class="popover attach-menu"
            >
              <button
                class="attach-option"
                @click="$refs.documentInput?.click(); showAttachMenu = false"
              >
                <span class="attach-icon attach-icon--document"><i class="ri-file-text-line" /></span>
                <span>Documento</span>
              </button>
              <button
                class="attach-option"
                @click="$refs.mediaInput?.click(); showAttachMenu = false"
              >
                <span class="attach-icon attach-icon--media"><i class="ri-image-2-line" /></span>
                <span>Fotos y videos</span>
              </button>
              <button
                class="attach-option"
                @click="$refs.audioFileInput?.click(); showAttachMenu = false"
              >
                <span class="attach-icon attach-icon--audio"><i class="ri-mic-2-line" /></span>
                <span>Audio</span>
              </button>
            </div>

            <input
              ref="documentInput"
              type="file"
              hidden
              @change="handleFileSelect"
            >
            <input
              ref="mediaInput"
              type="file"
              accept="image/*,video/*"
              hidden
              @change="handleImageSelect"
            >
            <input
              ref="audioFileInput"
              type="file"
              accept="audio/*"
              hidden
              @change="handleAudioFileSelect"
            >
          </div>

          <div
            ref="quickRepliesAnchor"
            class="action-anchor"
          >
            <button
              class="action-btn"
              title="Respuestas rápidas"
              :disabled="sending"
              @click="showQuickReplies = !showQuickReplies; showEmojiPicker = false"
            >
              <i class="ri-flashlight-line" />
            </button>

            <!-- Quick replies: floating popover anchored to this button -->
            <div
              v-if="showQuickReplies"
              class="popover quick-replies"
            >
              <button
                v-for="(reply, idx) in quickReplies"
                :key="idx"
                class="quick-reply-btn"
                @click="selectQuickReply(reply)"
              >
                {{ reply }}
              </button>
            </div>
          </div>

          <!-- Textarea con preview Markdown -->
          <div class="textarea-container">
            <textarea
              ref="textareaEl"
              v-model="messageText"
              placeholder="Escribe un mensaje..."
              class="message-textarea"
              rows="1"
              @keydown.enter.exact="sendMessage"
              @keydown.enter.shift="handleShiftEnter"
              @keydown.enter.ctrl="handleShiftEnter"
              @keydown.ctrl.b.exact="handleBold"
              @keydown.ctrl.i.exact="handleItalic"
              @keydown.ctrl.shift.x="handleStrikethrough"
            />
            <!-- Preview Markdown en tiempo real -->
            <div
              v-if="messageText.trim()"
              class="markdown-preview"
              v-html="renderMarkdownPreview(messageText)"
            />
          </div>

          <button
            class="action-btn"
            title="Grabar audio"
            :class="{ recording: recordingAudio }"
            :disabled="sending"
            @click="toggleAudioRecording"
          >
            <i :class="recordingAudio ? 'ri-stop-circle-fill' : 'ri-mic-line'" />
          </button>
        </div>

        <!-- Botón enviar -->
        <button
          class="send-btn"
          :disabled="!messageText.trim()"
          :class="{ active: messageText.trim() }"
          title="Enviar (Enter)"
          @click="sendMessage"
        >
          <i class="ri-send-plane-2-fill" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  replyingTo: Object,
  attentionMode: {
    type: String,
    default: 'unassigned',
    validator: v => ['bot', 'advisor', 'unassigned', 'closed'].includes(v),
  },
  advisorName: {
    type: String,
    default: 'Walter Escobar',
  },
  effectiveBotPaused: {
    type: Boolean,
    default: false,
  },
  // Parent-controlled: true while a send request is in flight (disables input)
  sending: {
    type: Boolean,
    default: false,
  },
  // Parent-controlled: visible error message from the last failed send attempt
  sendError: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['send-message', 'clear-reply', 'take-control', 'assign-me', 'reopen'])

const messageText = ref('')
const textareaEl = ref(null)
const showQuickReplies = ref(false)
const showEmojiPicker = ref(false)
const showAttachMenu = ref(false)
const recordingAudio = ref(false)
const emojiAnchor = ref(null)
const quickRepliesAnchor = ref(null)
const attachAnchor = ref(null)

// The textarea is :disabled="sending" while the request is in flight — a disabled
// field is force-blurred by the browser, so once it re-enables the advisor has to
// click back in manually to keep typing. Restore focus automatically instead.
watch(() => props.sending, (isSending, wasSending) => {
  if (wasSending && !isSending) {
    nextTick(() => textareaEl.value?.focus())
  }
})

// mousedown + capture: fires before any click handler (including the toggle
// buttons' own), so it reliably catches clicks anywhere outside each popover —
// including clicks elsewhere in the composer bar (e.g. the textarea), not just
// clicks outside the whole component.
const closePopoversIfOutside = event => {
  if (showEmojiPicker.value && emojiAnchor.value && !emojiAnchor.value.contains(event.target)) {
    showEmojiPicker.value = false
  }
  if (showQuickReplies.value && quickRepliesAnchor.value && !quickRepliesAnchor.value.contains(event.target)) {
    showQuickReplies.value = false
  }
  if (showAttachMenu.value && attachAnchor.value && !attachAnchor.value.contains(event.target)) {
    showAttachMenu.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', closePopoversIfOutside, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', closePopoversIfOutside, true)
})

const quickReplies = [
  'Entendido, en breve me comunico',
  'Gracias por tu consulta',
  'Te envío la cotización al WhatsApp',
  'Necesito confirmar algunos datos',
  'La cotización está lista',
  '¿En qué te puedo ayudar?',
]

const emojis = ['👍', '😊', '❤️', '🎉', '✨', '👏', '🙏', '🚀', '😂', '🙌', '💪', '⭐']

const autoResize = () => {
  const textarea = textareaEl.value
  if (!textarea) return

  textarea.style.height = 'auto'

  const newHeight = Math.min(textarea.scrollHeight, 200)

  textarea.style.height = `${newHeight}px`
}

// Single source of truth for resize: fires on every messageText change regardless
// of cause (typing, Ctrl/Shift+Enter newline, bold/italic insert, quick-reply,
// emoji, clear) — avoids each handler having to remember to call autoResize itself.
watch(messageText, () => {
  nextTick(autoResize)
})

const sendMessage = event => {
  // Enter's native behavior in a <textarea> is to insert a newline — without this,
  // the browser does that AND sends, leaving a stray \n (and whatever gets typed
  // right after it) sitting in the box on top of the next message.
  event?.preventDefault()

  // NOTE: deliberately NOT gated on props.sending — each send is independent (its
  // own optimistic bubble, own tempId), so blocking on "is a previous one still in
  // flight" only forced Enter to silently no-op while the advisor kept typing,
  // corrupting the next message. Only guard against sending nothing.
  if (!messageText.value.trim()) return

  emit('send-message', {
    text: messageText.value,
    type: 'text',
    clientMsgId: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  })

  // Cleared immediately (WhatsApp Web behavior) instead of waiting for the backend
  // to confirm — otherwise typing the NEXT message while this one is still in
  // flight edits the just-sent text instead of starting fresh. A failed send is
  // recovered from its own bubble (retry button), not from the composer.
  messageText.value = ''

  showQuickReplies.value = false
  showEmojiPicker.value = false
}

/** Called by the parent once a send is confirmed successful. */
const clear = () => {
  messageText.value = ''
  // Height reset handled by the messageText watcher (autoResize).
}

/** Called by the parent when a conversation is opened/selected. No-op if the
 * textarea isn't mounted (e.g. bot is attending, no composer input shown). */
const focus = () => {
  textareaEl.value?.focus()
}

defineExpose({ clear, focus })

/**
 * Wrap the selected text (or insert empty markers at the cursor) with WhatsApp's
 * own plain-text formatting syntax — *bold*, _italic_, ~strikethrough~. WhatsApp
 * renders these client-side; there's nothing to send differently, no backend
 * involved. If there's a selection, wrap it and keep it selected; otherwise
 * insert the marker pair with the cursor placed between them.
 */
const applyMarkup = (event, marker) => {
  event.preventDefault()

  const textarea = event.target
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selected = messageText.value.slice(start, end)

  messageText.value = messageText.value.slice(0, start) + marker + selected + marker + messageText.value.slice(end)

  nextTick(() => {
    if (selected) {
      textarea.selectionStart = start + marker.length
      textarea.selectionEnd = end + marker.length
    } else {
      textarea.selectionStart = textarea.selectionEnd = start + marker.length
    }
    textarea.focus()
  })
}

const handleBold = event => applyMarkup(event, '*')
const handleItalic = event => applyMarkup(event, '_')
const handleStrikethrough = event => applyMarkup(event, '~')

/** Insert a newline at the cursor (Shift+Enter or Ctrl+Enter), not just at the end. */
const handleShiftEnter = event => {
  event.preventDefault()

  const textarea = event.target
  const start = textarea.selectionStart
  const end = textarea.selectionEnd

  messageText.value = messageText.value.slice(0, start) + '\n' + messageText.value.slice(end)

  nextTick(() => {
    textarea.selectionStart = textarea.selectionEnd = start + 1
  })
}

const renderMarkdownPreview = (text) => {
  if (!text) return ''

  // Escapar HTML pero preservar estructura
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

  // Resaltar líneas que empiezan con "- " (viñeta). El textarea real es invisible
  // y este preview se le superpone encima — el cursor real sigue el ANCHO real del
  // texto, así que NUNCA hay que quitar ni reemplazar caracteres (ni "-" por "•", ni
  // los "*" del negrita): eso cambia el ancho visible vs. el real y el cursor queda
  // desfasado. Solo se aplica color/negrita al texto tal cual está escrito.
  const lines = escaped.split('\n')
  const processed = lines.map(line => {
    if (line.trim().startsWith('- ')) {
      return `<span class="preview-bullet">${line}</span>`
    }
    return line
  }).join('\n')

  // Negrita: se resalta el fragmento completo, asteriscos incluidos — no se ocultan.
  const withBold = processed.replace(/\*([^*]+)\*/g, '<strong>*$1*</strong>')

  // Preservar saltos de línea
  const final = withBold.replace(/\n/g, '<br>')

  return final
}

// tipo values match MensajeWhatsApp.tipo directly (Spanish) — the backend media
// send endpoint expects these exact strings, no translation layer needed.
const emitFile = (file, tipo) => {
  if (!file) return
  emit('send-message', {
    type: tipo,
    file,
    clientMsgId: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  })
}

const handleFileSelect = event => {
  emitFile(event.target.files?.[0], 'documento')
  event.target.value = ''
}

const handleImageSelect = event => {
  const file = event.target.files?.[0]

  emitFile(file, file?.type?.startsWith('video/') ? 'video' : 'imagen')
  event.target.value = ''
}

const handleAudioFileSelect = event => {
  emitFile(event.target.files?.[0], 'audio')
  event.target.value = ''
}

const toggleAudioRecording = () => {
  recordingAudio.value = !recordingAudio.value
  if (!recordingAudio.value) {
    emit('send-message', {
      type: 'audio',
      duration: '0:32',
    })
  }
}

const selectQuickReply = reply => {
  messageText.value = reply
  showQuickReplies.value = false
}

const insertEmoji = emoji => {
  messageText.value += emoji
  showEmojiPicker.value = false
}
</script>

<style scoped>
.chat-composer {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-top: 1px solid #e0e0e0;
  flex-shrink: 0;
  min-height: 52px;
  position: relative;
  z-index: 5;
}

.send-error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 16px 8px;
  padding: 8px 12px;
  background: #fdecea;
  color: #c0392b;
  border: 1px solid #f5c6cb;
  border-radius: 6px;
  font-size: 13px;
}

.send-error-banner i {
  font-size: 16px;
  flex-shrink: 0;
}

.spin {
  animation: composer-spin 0.8s linear infinite;
}

@keyframes composer-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.bot-attending,
.bot-paused-state,
.window-closed,
.unassigned-state,
.closed-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  gap: 12px;
}

.bot-attending {
  background: #fff3cd;
  border-top: 1px solid #e0e0e0;
}

.bot-paused-state {
  background: #f5f5f5;
  border-top: 1px solid #e0e0e0;
}

.unassigned-state {
  background: #e3f2fd;
  border-top: 1px solid #e0e0e0;
}

.closed-state {
  background: #f5f5f5;
  border-top: 1px solid #e0e0e0;
}

.bot-message,
.window-message,
.unassigned-message,
.closed-message {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex: 1;
}

.bot-message,
.window-message {
  color: #664d03;
}

.bot-message.paused {
  color: #666;
}

.unassigned-message {
  color: #1565c0;
}

.closed-message {
  color: #666;
}

.bot-message i,
.window-message i,
.unassigned-message i,
.closed-message i {
  font-size: 16px;
}

.take-control-btn,
.template-btn,
.assign-btn,
.reopen-btn {
  padding: 6px 14px;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}

.take-control-btn,
.template-btn {
  background: #664d03;
}

.take-control-btn:hover,
.template-btn:hover {
  background: #5a4402;
}

.assign-btn {
  background: #1565c0;
}

.assign-btn:hover {
  background: #0d47a1;
}

.reopen-btn {
  background: #666;
}

.reopen-btn:hover {
  background: #555;
}

.composer-content {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  gap: 8px;
}

.composer-header {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 6px;
  border-bottom: 1px solid #eee;
}

.channel-info {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #10b981;
  font-weight: 600;
}

.channel-info i {
  font-size: 14px;
}

.advisor-info {
  flex: 1;
  color: #666;
  font-size: 11px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #10b981;
  font-weight: 600;
  font-size: 11px;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
}

.reply-preview {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  background: #f0f4ff;
  border-left: 3px solid var(--v-primary-base, #ff6b3d);
  border-radius: 4px;
  font-size: 12px;
}

.reply-close {
  flex-shrink: 0;
}

.reply-close button {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 14px;
  padding: 0;
}

.reply-close button:hover {
  color: #333;
}

.reply-content {
  flex: 1;
  min-width: 0;
}

.reply-label {
  display: block;
  font-weight: 600;
  color: #333;
  margin-bottom: 2px;
}

.reply-text {
  margin: 0;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 4px 0;
}

.composer-pill {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: flex-end;
  gap: 2px;
  background: #fff;
  border: 1px solid #e9edef;
  border-radius: 24px;
  padding: 4px 6px;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
}

.action-btn {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 50%;
  color: #54656f;
  cursor: pointer;
  font-size: 20px;
  transition: background 0.15s, color 0.15s;
}

.action-btn:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1d;
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.action-btn.recording {
  background: #fde8e8;
  color: #e02b2b;
}

.message-textarea {
  display: block;
  width: 100%;
  box-sizing: border-box;
  padding: 9px 4px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.35;
  resize: none;
  min-height: 20px;
  max-height: 200px;
  outline: none;
  /* Real text stays invisible — the styled overlay below renders it (bold/bullets).
     Caret stays visible so the advisor can still see where they're typing. */
  color: transparent;
  caret-color: #111b21;
}

.message-textarea::placeholder {
  color: #667781;
}

/* Plain block wrapper (not flex) — its height is driven purely by the in-flow
   textarea, so the overlay (absolute, inset:0) always matches it exactly. */
.textarea-container {
  flex: 1;
  min-width: 0;
  position: relative;
}

.markdown-preview {
  position: absolute;
  inset: 0;
  box-sizing: border-box;
  padding: 9px 4px;
  font-size: 14px;
  line-height: 1.35;
  color: #111b21;
  pointer-events: none;
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow: hidden;
  font-family: inherit;
}

/* v-html content isn't compiled by Vue's template scoping — :deep() is required
   for these rules to actually reach it (a plain scoped selector silently never
   matches, since the injected markup never receives the data-v-xxxx attribute). */
:deep(.markdown-preview strong) {
  font-weight: 700;
}

:deep(.preview-bullet) {
  color: #008069;
}

.send-btn {
  flex-shrink: 0;
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #d9dbdf;
  color: #8696a0;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  font-size: 18px;
  transition: background 0.15s, color 0.15s, transform 0.1s;
}

.send-btn.active {
  background: #00a884;
  color: #fff;
}

.send-btn.active:hover:not(:disabled) {
  background: #06976f;
}

.send-btn:active:not(:disabled) {
  transform: scale(0.94);
}

.send-btn:disabled {
  cursor: not-allowed;
}

.action-anchor {
  position: relative;
  flex-shrink: 0;
  display: flex;
}

/* Floating panel that appears to originate from its trigger button, WhatsApp-style */
.popover {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.18);
  z-index: 30;
  animation: popover-in 0.12s ease-out;
}

.popover::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 14px;
  width: 12px;
  height: 12px;
  background: #fff;
  transform: translateY(-6px) rotate(45deg);
  border-radius: 2px;
  box-shadow: 2px 2px 2px rgba(0, 0, 0, 0.03);
  clip-path: polygon(100% 0, 0 0, 100% 100%);
}

@keyframes popover-in {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.quick-replies {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  width: 240px;
  max-height: 260px;
  overflow-y: auto;
}

.quick-reply-btn {
  padding: 8px 10px;
  background: transparent;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  text-align: left;
  color: #333;
  cursor: pointer;
  white-space: normal;
  transition: background 0.15s;
}

.quick-reply-btn:hover {
  background: #f0f2f5;
}

.emoji-picker {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 2px;
  padding: 8px;
  width: 240px;
}

.emoji-item {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  font-size: 20px;
  transition: background 0.15s;
  border: none;
}

.emoji-item:hover {
  background: #f0f2f5;
}

.attach-menu {
  display: flex;
  flex-direction: column;
  padding: 6px;
  width: 220px;
}

.attach-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  background: transparent;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  color: #333;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;
}

.attach-option:hover {
  background: #f0f2f5;
}

.attach-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 19px;
}

.attach-icon--document {
  background: #7f66ff;
}

.attach-icon--media {
  background: #bf59cf;
}

.attach-icon--audio {
  background: #ff9800;
}
</style>
