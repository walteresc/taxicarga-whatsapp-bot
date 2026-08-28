<template>
  <div class="chat-window">
    <div
      v-if="!conversation"
      class="empty-state"
    >
      <i class="ri-mail-open-line" />
      <p class="title">
        Selecciona una conversación
      </p>
      <p class="text">
        Elige una conversación de la lista para revisar mensajes y responder
      </p>
    </div>
    <div
      v-else
      class="chat-content"
    >
      <!-- ENCABEZADO -->
      <div class="chat-header">
        <div class="header-left">
          <h3>{{ conversation.name }}</h3>
          <p>{{ conversation.phone }} · {{ conversation.channel }}</p>
        </div>
        <div class="header-actions">
          <button
            v-if="conversation.status === 'COTIZAR'"
            class="badge-btn orange"
          >
            Por cotizar
          </button>
          <button
            v-if="conversation.status === 'BOT'"
            class="badge-btn success"
          >
            Bot atendiendo
          </button>
          <button
            class="action-btn primary"
            @click="$emit('take-control')"
          >
            Tomar control
          </button>
          <button class="action-btn menu-btn">
            <i class="ri-more-2-fill" />
          </button>
        </div>
      </div>

      <!-- MENSAJES -->
      <div
        ref="messagesContainer"
        class="messages-container"
      >
        <div
          v-if="loadingMessages"
          class="loading"
        >
          Cargando mensajes...
        </div>
        <div v-else>
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message"
            :class="[{ 'from-client': msg.sender === 'client', 'from-bot': msg.sender === 'bot', 'from-advisor': msg.sender === 'advisor' }]"
          >
            <div class="msg-bubble">
              <p>{{ msg.content }}</p>
              <div class="msg-footer">
                <small>{{ formatTime(msg.timestamp) }}</small>
                <span
                  v-if="msg.sender === 'bot'"
                  class="ia-badge"
                >IA</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- INPUT -->
      <div class="input-area">
        <div class="input-wrapper">
          <button class="icon-btn">
            <i class="ri-attachment-line" />
          </button>
          <input
            v-model="newMessage"
            type="text"
            placeholder="Escribe un mensaje..."
            class="input-field"
            @keyup.enter="sendMessage"
          >
          <button class="icon-btn">
            <i class="ri-emotion-smile-line" />
          </button>
        </div>
        <button
          class="send-btn"
          @click="sendMessage"
        >
          <i class="ri-send-plane-2-fill" />
          Enviar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { conversationService } from '@/services/conversationService'

const props = defineProps({
  conversation: Object,
})

const emit = defineEmits(['take-control', 'return-bot', 'send-to-quote', 'close'])

const messages = ref([])
const newMessage = ref('')
const loadingMessages = ref(false)
const messagesContainer = ref(null)

const formatTime = time => {
  if (!time) return ''
  const date = new Date(time)
  
  return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}

const loadMessages = async () => {
  if (!props.conversation) return
  loadingMessages.value = true
  try {
    const data = await conversationService.getConversationMessages(props.conversation.id)

    messages.value = data.messages || []
    setTimeout(scrollToBottom, 100)
  } catch (error) {
    console.error('Error loading messages:', error)
  }
  loadingMessages.value = false
}

const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const sendMessage = async () => {
  if (!newMessage.value.trim() || !props.conversation) return

  const messageText = newMessage.value

  newMessage.value = ''

  try {
    await conversationService.sendMessage(props.conversation.id, messageText)
    messages.value.push({
      id: Date.now(),
      content: messageText,
      sender: 'advisor',
      timestamp: new Date().toISOString(),
    })
    scrollToBottom()
  } catch (error) {
    console.error('Error sending message:', error)
    newMessage.value = messageText
  }
}

watch(
  () => props.conversation?.id,
  () => {
    loadMessages()
  },
)
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 14px;
  flex-direction: column;
  gap: 16px;
}

.empty-state i {
  font-size: 64px;
  color: #ddd;
  opacity: 0.5;
}

.empty-state p {
  margin: 0;
  text-align: center;
}

.empty-state .title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.empty-state .text {
  font-size: 13px;
  color: #999;
  margin: 0;
}

.chat-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
}

.header-left h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.header-left p {
  margin: 0;
  font-size: 12px;
  color: #999;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.badge-btn {
  padding: 4px 10px;
  border: 1px solid;
  background: #fff;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.badge-btn.orange {
  border-color: #ff6b3d;
  color: #ff6b3d;
  background: #ffe8d6;
}

.badge-btn.success {
  border-color: #10b981;
  color: #10b981;
  background: #d1fae5;
}

.action-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn.primary {
  background: #ff6b3d;
  color: white;
}

.action-btn.primary:hover {
  background: #ff5722;
}

.menu-btn {
  background: transparent;
  color: #666;
  padding: 6px;
}

.menu-btn:hover {
  background: #f0f0f0;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fafafa;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 12px;
}

.message {
  display: flex;
  margin-bottom: 8px;
}

.message.from-client {
  justify-content: flex-start;
}

.message.from-advisor,
.message.from-bot {
  justify-content: flex-end;
}

.msg-bubble {
  max-width: 55%;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.4;
  word-wrap: break-word;
}

.message.from-client .msg-bubble {
  background: #e8eaf6;
  color: #333;
}

.message.from-advisor .msg-bubble {
  background: #ff6b3d;
  color: white;
}

.message.from-bot .msg-bubble {
  background: #10b981;
  color: white;
}

.msg-bubble p {
  margin: 0 0 4px 0;
}

.msg-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: flex-end;
}

.msg-footer small {
  font-size: 11px;
  opacity: 0.8;
}

.ia-badge {
  display: inline-block;
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 9px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.2);
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #e0e0e0;
}

.input-wrapper {
  display: flex;
  align-items: center;
  flex: 1;
  gap: 4px;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: #f9f9f9;
}

.icon-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 18px;
  padding: 0;
  transition: color 0.2s;
}

.icon-btn:hover {
  color: #666;
}

.input-field {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 13px;
  outline: none;
}

.send-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #ff6b3d;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover {
  background: #ff5722;
}
</style>
