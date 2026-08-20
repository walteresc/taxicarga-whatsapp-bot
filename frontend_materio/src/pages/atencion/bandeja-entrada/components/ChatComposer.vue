<template>
  <div class="chat-composer">
    <!-- Estado bot atendiendo -->
    <div v-if="attentionMode === 'bot'" class="bot-attending">
      <div class="bot-message">
        <i class="ri-robot-line"></i>
        <span>El bot está atendiendo esta conversación</span>
      </div>
      <button class="take-control-btn" @click="$emit('take-control')">
        Tomar conversación
      </button>
    </div>

    <!-- Estado sin asignar -->
    <div v-else-if="attentionMode === 'unassigned'" class="unassigned-state">
      <div class="unassigned-message">
        <i class="ri-user-line"></i>
        <span>Esta conversación todavía no tiene asesor</span>
      </div>
      <button class="assign-btn" @click="$emit('assign-me')">
        Asignarme
      </button>
    </div>

    <!-- Estado conversación cerrada -->
    <div v-else-if="attentionMode === 'closed'" class="closed-state">
      <div class="closed-message">
        <i class="ri-lock-line"></i>
        <span>Conversación cerrada</span>
      </div>
      <button class="reopen-btn" @click="$emit('reopen')">
        Reabrir
      </button>
    </div>

    <!-- Composer activo (asesor atendiendo) -->
    <div v-else-if="attentionMode === 'advisor'" class="composer-content">
      <!-- Línea informativa -->
      <div class="composer-header">
        <div class="channel-info">
          <i class="ri-whatsapp-line"></i>
          <span>WhatsApp</span>
        </div>
        <div class="advisor-info">
          <span>Respondiendo como {{ advisorName }}</span>
        </div>
        <div class="status-badge">
          <span class="status-dot"></span>
          Disponible
        </div>
      </div>

      <!-- Respuesta citada -->
      <div v-if="replyingTo" class="reply-preview">
        <div class="reply-close">
          <button @click="$emit('clear-reply')">
            <i class="ri-close-line"></i>
          </button>
        </div>
        <div class="reply-content">
          <span class="reply-label">Respondiendo a {{ replyingTo.senderName }}</span>
          <p class="reply-text">{{ replyingTo.text }}</p>
        </div>
      </div>

      <!-- Compositor input -->
      <div class="composer-input-wrapper">
        <!-- Botones de acción -->
        <div class="composer-actions">
          <button
            class="action-btn"
            title="Adjuntar archivo"
            @click="$refs.fileInput?.click()"
          >
            <i class="ri-attachment-line"></i>
            <input
              ref="fileInput"
              type="file"
              hidden
              @change="handleFileSelect"
            />
          </button>

          <button
            class="action-btn"
            title="Adjuntar imagen"
            @click="$refs.imageInput?.click()"
          >
            <i class="ri-image-add-line"></i>
            <input
              ref="imageInput"
              type="file"
              accept="image/*"
              hidden
              @change="handleImageSelect"
            />
          </button>

          <button
            class="action-btn"
            title="Grabar audio"
            :class="{ recording: recordingAudio }"
            @click="toggleAudioRecording"
          >
            <i :class="recordingAudio ? 'ri-stop-circle-fill' : 'ri-mic-line'"></i>
          </button>

          <button
            class="action-btn"
            title="Respuestas rápidas"
            @click="showQuickReplies = !showQuickReplies"
          >
            <i class="ri-lightning-line"></i>
          </button>

          <button
            class="action-btn"
            title="Emoji"
            @click="showEmojiPicker = !showEmojiPicker"
          >
            <i class="ri-emotion-smile-line"></i>
          </button>
        </div>

        <!-- Textarea -->
        <textarea
          v-model="messageText"
          placeholder="Escribe un mensaje..."
          class="message-textarea"
          rows="1"
          @keydown.enter.exact="sendMessage"
          @keydown.enter.shift="handleShiftEnter"
          @input="autoResize"
        ></textarea>

        <!-- Botón enviar -->
        <button
          class="send-btn"
          :disabled="!messageText.trim()"
          @click="sendMessage"
          title="Enviar (Enter)"
        >
          <i class="ri-send-plane-2-fill"></i>
        </button>
      </div>

      <!-- Respuestas rápidas -->
      <div v-if="showQuickReplies" class="quick-replies">
        <button
          v-for="(reply, idx) in quickReplies"
          :key="idx"
          class="quick-reply-btn"
          @click="selectQuickReply(reply)"
        >
          {{ reply }}
        </button>
      </div>

      <!-- Emoji picker -->
      <div v-if="showEmojiPicker" class="emoji-picker">
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
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

defineProps({
  replyingTo: Object,
  attentionMode: {
    type: String,
    default: 'unassigned',
    validator: (v) => ['bot', 'advisor', 'unassigned', 'closed'].includes(v),
  },
  advisorName: {
    type: String,
    default: 'Walter Escobar',
  },
})

const emit = defineEmits(['send-message', 'clear-reply', 'take-control', 'assign-me', 'reopen'])

const messageText = ref('')
const showQuickReplies = ref(false)
const showEmojiPicker = ref(false)
const recordingAudio = ref(false)

const quickReplies = [
  'Entendido, en breve me comunico',
  'Gracias por tu consulta',
  'Te envío la cotización al WhatsApp',
  'Necesito confirmar algunos datos',
  'La cotización está lista',
  '¿En qué te puedo ayudar?',
]

const emojis = ['👍', '😊', '❤️', '🎉', '✨', '👏', '🙏', '🚀', '😂', '🙌', '💪', '⭐']

const autoResize = (event) => {
  const textarea = event.target
  textarea.style.height = 'auto'
  const newHeight = Math.min(textarea.scrollHeight, 120)
  textarea.style.height = `${newHeight}px`
}

const sendMessage = async () => {
  if (!messageText.value.trim()) return

  emit('send-message', {
    text: messageText.value,
    type: 'text',
  })

  messageText.value = ''
  showQuickReplies.value = false
  showEmojiPicker.value = false

  await nextTick()
  const textarea = document.querySelector('.message-textarea')
  if (textarea) {
    textarea.style.height = 'auto'
  }
}

const handleShiftEnter = (event) => {
  event.preventDefault()
  messageText.value += '\n'
  nextTick(() => {
    const textarea = event.target
    autoResize({ target: textarea })
  })
}

const handleFileSelect = (event) => {
  const file = event.target.files?.[0]
  if (file) {
    emit('send-message', {
      type: 'document',
      fileName: file.name,
      fileSize: `${(file.size / 1024).toFixed(2)} KB`,
    })
  }
  event.target.value = ''
}

const handleImageSelect = (event) => {
  const file = event.target.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      emit('send-message', {
        type: 'image',
        content: e.target.result,
      })
    }
    reader.readAsDataURL(file)
  }
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

const selectQuickReply = (reply) => {
  messageText.value = reply
  showQuickReplies.value = false
}

const insertEmoji = (emoji) => {
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
}

.bot-attending,
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
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
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
}

.composer-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f7;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  color: #666;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #e8e8eb;
  border-color: #999;
  color: #333;
}

.action-btn.recording {
  background: #ffebee;
  border-color: #f44336;
  color: #f44336;
}

.message-textarea {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: #f5f5f7;
  font-size: 13px;
  font-family: inherit;
  resize: none;
  min-height: 36px;
  max-height: 120px;
  outline: none;
  transition: all 0.2s;
}

.message-textarea:focus {
  border-color: var(--v-primary-base, #ff6b3d);
  background: #fff;
}

.message-textarea::placeholder {
  color: #999;
}

.send-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: #ff5722;
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(255, 107, 61, 0.3);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.quick-replies {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}

.quick-reply-btn {
  padding: 6px 12px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 16px;
  font-size: 11px;
  color: #666;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.quick-reply-btn:hover {
  background: #f9f9f9;
  border-color: #999;
  color: #333;
}

.emoji-picker {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}

.emoji-item {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f7;
  border-radius: 6px;
  cursor: pointer;
  font-size: 18px;
  transition: all 0.2s;
  border: none;
}

.emoji-item:hover {
  background: #e8e8eb;
  transform: scale(1.1);
}
</style>
