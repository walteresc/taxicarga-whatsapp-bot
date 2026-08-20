<template>
  <div class="bot-control">
    <div class="control-card">
      <h3>Control Bot Global</h3>
      <div class="status">
        <span :class="['status-badge', botStatus]">
          {{ botStatus === 'ACTIVO' ? '✓ Activo' : '⏸ Pausado' }}
        </span>
      </div>
      <div class="buttons">
        <button v-if="botStatus === 'PAUSADO'" @click="activateBot" class="btn-activate">
          Activar Bot
        </button>
        <button v-else @click="pauseBot" class="btn-pause">
          Pausar Bot
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { conversationService } from '@/services/conversationService'

const botStatus = ref('ACTIVO')
const loading = ref(false)

const checkBotStatus = async () => {
  try {
    const response = await conversationService.getBotStatus()
    botStatus.value = response.status === 'active' ? 'ACTIVO' : 'PAUSADO'
  } catch (error) {
    console.error('Error checking bot status:', error)
  }
}

const pauseBot = async () => {
  loading.value = true
  try {
    await conversationService.pauseBot()
    botStatus.value = 'PAUSADO'
  } catch (error) {
    console.error('Error pausing bot:', error)
  }
  loading.value = false
}

const activateBot = async () => {
  loading.value = true
  try {
    await conversationService.activateBot()
    botStatus.value = 'ACTIVO'
  } catch (error) {
    console.error('Error activating bot:', error)
  }
  loading.value = false
}

onMounted(() => {
  checkBotStatus()
})
</script>

<style scoped>
.bot-control {
  padding: 12px;
}

.control-card {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
}

.control-card h3 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
}

.status {
  margin-bottom: 12px;
}

.status-badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.ACTIVO {
  background: #d4edda;
  color: #155724;
}

.status-badge.PAUSADO {
  background: #fff3cd;
  color: #856404;
}

.buttons {
  display: flex;
  gap: 8px;
}

button {
  flex: 1;
  padding: 8px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-activate {
  background: #28a745;
  color: white;
}

.btn-activate:hover {
  background: #218838;
}

.btn-pause {
  background: #ffc107;
  color: black;
}

.btn-pause:hover {
  background: #e0a800;
}
</style>
