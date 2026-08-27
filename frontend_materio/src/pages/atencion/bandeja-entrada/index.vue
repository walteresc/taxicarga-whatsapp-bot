<template>
  <div class="bandeja-page">
    <!-- Cabecera principal -->
    <div class="page-header">
      <div class="header-left">
        <h1>Bandeja de entrada <span class="count-badge">{{ conversationCount }}</span></h1>
      </div>
      <div class="header-right">
        <div class="status-indicator">
          <span :class="['dot', botGlobalPaused ? 'inactive' : 'active']"></span>
          <span class="status-text">{{ botGlobalPaused ? 'Bot global pausado' : 'Bot global activo' }}</span>
        </div>
        <button v-if="botGlobalPaused" @click="activateBot" class="activate-btn">
          <i class="ri-play-line"></i>
          Reanudar bot
        </button>
        <button v-else @click="pauseBot" class="pause-btn">
          <i class="ri-pause-line"></i>
          Pausar bot
        </button>
        <button class="settings-btn">
          <i class="ri-settings-3-line"></i>
        </button>
      </div>
    </div>

    <!-- Área de trabajo principal -->
    <div class="main-container">
      <!-- Panel izquierdo: Lista de conversaciones -->
      <div class="left-panel">
        <ConversationListComponent
          :selected-conversation-id="selectedConversationId"
          @conversation-selected="selectConversation"
          @update-count="conversationCount = $event"
        />
      </div>

      <!-- Panel central: Chat -->
      <div class="center-panel">
        <ConversationPanelComponent
          :conversation-id="selectedConversationId"
          :conversation="selectedConversation"
          :bot-global-paused="botGlobalPaused"
          :effective-bot-paused="effectiveBotPaused"
        />
      </div>

      <!-- Panel derecho: Información del contacto (desktop) -->
      <div v-if="selectedConversation && isDesktop" class="right-panel">
        <ContactDetailsComponent
          :contact="selectedConversation"
          :service="selectedConversation.serviceData"
          :advisor="selectedConversation.responsable"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useDisplay } from 'vuetify'
import ConversationListComponent from './ConversationList.vue'
import ConversationPanelComponent from './components/ConversationPanel.vue'
import ContactDetailsComponent from './components/ContactDetails.vue'
import { conversationService } from '@/services/conversationService'
import { useAuthGuard } from '@/composables/useAuthGuard'

const { checkAuth } = useAuthGuard()
const { mdAndUp } = useDisplay()

// Estado único para la conversación seleccionada
const selectedConversationId = ref(null)
const selectedConversation = ref(null)
const botGlobalPaused = ref(false)  // true = paused, false = active
const conversationCount = ref(0)

// Computed
const isDesktop = computed(() => mdAndUp.value)

// CORRECCIÓN 1: Estado efectivo del bot = global OR conversación individual
const effectiveBotPaused = computed(() => {
  const globalPaused = botGlobalPaused.value
  const conversationPaused = selectedConversation.value?.bot_paused ?? false
  return globalPaused || conversationPaused
})

// Métodos
const selectConversation = (conversation) => {
  selectedConversationId.value = conversation.id
  selectedConversation.value = conversation
}

const pauseBot = async () => {
  try {
    await conversationService.pauseBot()
    botGlobalPaused.value = true
    console.log('[BandejaPagina] Bot pausado globalmente')
  } catch (error) {
    console.error('Error pausing bot:', error)
  }
}

const activateBot = async () => {
  try {
    await conversationService.activateBot()
    botGlobalPaused.value = false
    console.log('[BandejaPagina] Bot reactivado globalmente')
  } catch (error) {
    console.error('Error activating bot:', error)
  }
}

const loadBotStatus = async () => {
  try {
    const status = await conversationService.getBotStatus()
    botGlobalPaused.value = status.is_paused
    console.log('[BandejaPagina] Estado del bot cargado:', { is_paused: status.is_paused })
  } catch (error) {
    console.error('Error getting bot status:', error)
  }
}

// Lifecycle
onMounted(async () => {
  // Verificar autenticación
  const isAuth = await checkAuth()
  if (!isAuth) return

  // Cargar estado del bot global
  await loadBotStatus()
})
</script>

<style scoped>
.bandeja-page {
  height: 100dvh;
  max-height: 100dvh;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  background: #f5f5f5;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 64px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
}

.header-left h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #333;
  display: flex;
  align-items: center;
  gap: 12px;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  background: #f0f0f0;
  border-radius: 14px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  min-width: 32px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot.active {
  background: #10b981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
}

.dot.inactive {
  background: #fbbf24;
  box-shadow: 0 0 8px rgba(251, 191, 36, 0.5);
}

.status-text {
  font-weight: 600;
}

.pause-btn,
.activate-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.pause-btn {
  background: #fbbf24;
  color: #333;
}

.activate-btn {
  background: #10b981;
  color: white;
}

.settings-btn {
  padding: 8px;
  background: transparent;
  border: none;
  color: #666;
  font-size: 18px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.main-container {
  display: grid;
  grid-template-columns: 350px minmax(500px, 1fr) 330px;
  gap: 0;
  overflow: hidden;
  min-height: 0;
  height: 100%;
  width: 100%;
  align-items: stretch;
}

@media (max-width: 1439px) {
  .main-container {
    grid-template-columns: 330px minmax(450px, 1fr);
  }

  .right-panel {
    display: none !important;
  }
}

@media (max-width: 1024px) {
  .main-container {
    grid-template-columns: 1fr;
  }

  .left-panel {
    display: none;
  }
}

.left-panel {
  width: 350px;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.center-panel {
  background: #fff;
  overflow: hidden;
  min-height: 0;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.right-panel {
  width: 330px;
  background: #fff;
  border-left: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

@media (max-width: 1024px) {
  .left-panel {
    width: 300px;
  }
  .right-panel {
    display: none;
  }
}

@media (max-width: 768px) {
  .left-panel {
    width: 100%;
  }
  .center-panel {
    display: none;
  }
  .right-panel {
    display: none;
  }
}
</style>
