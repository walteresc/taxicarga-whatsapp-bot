<template>
  <div class="conversation-header">
    <div class="header-left">
      <div class="contact-avatar">
        <img v-if="conversation.avatar" :src="conversation.avatar" :alt="conversation.name" />
        <div v-else class="avatar-placeholder">{{ getInitials(conversation.name) }}</div>
      </div>

      <div class="contact-info">
        <h3>{{ conversation.name }}</h3>
        <div class="contact-meta">
          <i :class="`ri-${getChannelIcon(conversation.channel)}`" class="channel-icon"></i>
          <span>{{ conversation.channel }}</span>
          <span class="separator">·</span>
          <span class="status">{{ getStatus(conversation) }}</span>
        </div>
      </div>
    </div>

    <div class="header-actions">
      <!-- Action button (dynamic based on attention mode) -->
      <button v-if="conversation.attentionMode === 'bot'" class="action-btn primary" @click="$emit('take-conversation')">
        <i class="ri-user-add-line"></i>
        Tomar conversación
      </button>
      <button v-else-if="conversation.attentionMode === 'advisor'" class="action-btn secondary" @click="$emit('return-bot')">
        <i class="ri-robot-line"></i>
        Devolver al bot
      </button>
      <button v-else-if="conversation.attentionMode === 'unassigned'" class="action-btn primary" @click="$emit('assign-me')">
        <i class="ri-user-add-line"></i>
        Asignarme
      </button>
      <button v-else-if="conversation.attentionMode === 'closed'" class="action-btn secondary" @click="$emit('reopen')">
        <i class="ri-refresh-line"></i>
        Reabrir
      </button>

      <!-- Menu button -->
      <button class="menu-btn" @click="showMenu = !showMenu">
        <i class="ri-more-2-fill"></i>
      </button>

      <!-- Dropdown menu -->
      <div v-if="showMenu" class="dropdown-menu">
        <button class="menu-item">
          <i class="ri-mail-open-line"></i>
          Marcar como no leída
        </button>
        <button class="menu-item">
          <i class="ri-shuffle-line"></i>
          Transferir
        </button>
        <button class="menu-item">
          <i class="ri-close-circle-line"></i>
          Cerrar conversación
        </button>
        <hr />
        <button class="menu-item danger">
          <i class="ri-forbid-line"></i>
          Bloquear contacto
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  conversation: {
    type: Object,
    required: true,
  },
})

defineEmits(['take-conversation', 'return-bot', 'assign-me', 'reopen'])

const showMenu = ref(false)

const getInitials = name => {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

const getChannelIcon = channel => {
  const icons = {
    WhatsApp: 'whatsapp-line',
    Correo: 'mail-line',
    Instagram: 'instagram-line',
    Facebook: 'facebook-circle-line',
    'Chat web': 'chat-3-line',
  }
  return icons[channel] || 'global-line'
}

const getStatus = conversation => {
  if (conversation.attentionMode === 'bot') return 'Bot atendiendo'
  if (conversation.attentionMode === 'advisor') return `Atendido por ${conversation.responsable?.nombre || 'Asesor'}`
  if (conversation.attentionMode === 'unassigned') return 'Esperando asignación'
  if (conversation.attentionMode === 'closed') return 'Conversación cerrada'
  return 'Esperando'
}
</script>

<style scoped>
.conversation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.contact-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}

.contact-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  color: #666;
}

.contact-info {
  min-width: 0;
  flex: 1;
}

.contact-info h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.contact-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #999;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.channel-icon {
  font-size: 12px;
}

.separator {
  opacity: 0.5;
}

.status {
  color: #10b981;
  font-weight: 500;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.action-btn.primary {
  background: var(--v-primary-base, #ff6b3d);
  color: white;
}

.action-btn.primary:hover {
  background: #ff5722;
}

.action-btn.secondary {
  background: #f0f0f0;
  color: #333;
}

.action-btn.secondary:hover {
  background: #e0e0e0;
}

.menu-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.menu-btn:hover {
  background: #f0f0f0;
  color: #333;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  min-width: 180px;
  overflow: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: none;
  font-size: 12px;
  color: #333;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}

.menu-item:hover {
  background: #f5f5f5;
}

.menu-item.danger {
  color: #f87171;
}

.dropdown-menu hr {
  margin: 4px 0;
  border: none;
  border-top: 1px solid #e0e0e0;
}
</style>
