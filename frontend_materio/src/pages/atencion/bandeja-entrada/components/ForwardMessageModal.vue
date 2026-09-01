<template>
  <div
    class="forward-overlay"
    @click.self="$emit('close')"
  >
    <div class="forward-modal">
      <div class="forward-header">
        <h3>Reenviar mensaje</h3>
        <button
          class="forward-close"
          @click="$emit('close')"
        >
          <i class="ri-close-line" />
        </button>
      </div>

      <div class="forward-preview">
        <i :class="previewIcon" />
        <span>{{ previewText }}</span>
      </div>

      <input
        v-model="search"
        class="forward-search"
        type="text"
        placeholder="Buscar por nombre o teléfono..."
        autofocus
        @input="onSearchInput"
      >

      <div class="forward-list">
        <div
          v-if="loading"
          class="forward-status"
        >
          Buscando...
        </div>
        <div
          v-else-if="results.length === 0"
          class="forward-status"
        >
          Sin resultados
        </div>
        <button
          v-for="conv in results"
          :key="conv.id"
          class="forward-item"
          :disabled="sendingTo !== null"
          @click="selectTarget(conv)"
        >
          <div class="forward-avatar">
            {{ initials(conv.name) }}
          </div>
          <div class="forward-item-text">
            <div class="forward-item-name">
              {{ conv.name }}
            </div>
            <div class="forward-item-phone">
              {{ conv.phone }}
            </div>
          </div>
          <i
            v-if="sendingTo === conv.id"
            class="ri-loader-4-line spin"
          />
        </button>
      </div>

      <div
        v-if="errorMsg"
        class="forward-error"
      >
        {{ errorMsg }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { conversationService } from '@/services/conversationService'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
  conversationId: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits(['close', 'forwarded'])

const search = ref('')
const results = ref([])
const loading = ref(false)
const sendingTo = ref(null)
const errorMsg = ref('')
let debounceTimer = null

const previewIcon = computed(() => {
  const icons = {
    image: 'ri-image-line',
    video: 'ri-video-line',
    audio: 'ri-mic-line',
    document: 'ri-file-line',
  }

  return icons[props.message.contentType] || 'ri-chat-1-line'
})

const previewText = computed(() => {
  if (props.message.contentType === 'text') return props.message.text
  if (props.message.caption) return props.message.caption

  const labels = {
    image: 'Imagen',
    video: 'Video',
    audio: 'Audio',
    document: 'Documento',
  }

  return labels[props.message.contentType] || props.message.contentType
})

const initials = name => {
  if (!name) return '?'

  return name.trim().slice(0, 1).toUpperCase()
}

const fetchConversations = async q => {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '20' })
    if (q) params.set('q', q)

    const response = await fetch(`/dashboard/whatsapp/conversaciones/api/active/?${params}`, {
      credentials: 'include',
    })
    const data = await response.json()

    results.value = (data.conversations || []).filter(c => c.id !== props.conversationId)
  } catch (error) {
    console.error('[ForwardMessageModal] Search failed:', error)
    results.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchConversations(''))

const onSearchInput = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => fetchConversations(search.value), 300)
}

const selectTarget = async conv => {
  if (sendingTo.value !== null) return
  sendingTo.value = conv.id
  errorMsg.value = ''

  try {
    const response = await fetch(
      `/dashboard/whatsapp/conversaciones/${props.conversationId}/mensajes/${props.message.id}/reenviar/`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': conversationService.getCsrfToken(),
        },
        credentials: 'include',
        body: JSON.stringify({ target_conversation_id: conv.id }),
      }
    )

    let data = null
    try {
      data = await response.json()
    } catch {
      data = null
    }

    if (data?.success) {
      emit('forwarded', { targetConversationId: conv.id })
      emit('close')
    } else {
      errorMsg.value = data?.error_detail || 'No se pudo reenviar el mensaje.'
      sendingTo.value = null
    }
  } catch (error) {
    console.error('[ForwardMessageModal] Forward failed:', error)
    errorMsg.value = 'No se pudo conectar con el servidor.'
    sendingTo.value = null
  }
}
</script>

<style scoped>
.forward-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.forward-modal {
  width: 400px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.forward-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #eee;
}

.forward-header h3 {
  margin: 0;
  font-size: 16px;
}

.forward-close {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
  color: #666;
  display: flex;
}

.forward-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #f5f5f5;
  font-size: 13px;
  color: #444;
  border-bottom: 1px solid #eee;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.forward-search {
  margin: 12px 16px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 20px;
  font-size: 13px;
  outline: none;
}

.forward-search:focus {
  border-color: #ff9800;
}

.forward-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.forward-status {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.forward-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}

.forward-item:hover:not(:disabled) {
  background: #f5f5f5;
}

.forward-item:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.forward-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #ff9800;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

.forward-item-text {
  flex: 1;
  min-width: 0;
}

.forward-item-name {
  font-size: 13px;
  font-weight: 500;
  color: #222;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.forward-item-phone {
  font-size: 12px;
  color: #888;
}

.forward-item i.spin {
  animation: forward-spin 0.8s linear infinite;
  color: #ff9800;
}

@keyframes forward-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.forward-error {
  margin: 0 16px 12px;
  padding: 8px 10px;
  background: #ffebee;
  color: #d32f2f;
  border-radius: 6px;
  font-size: 12px;
}
</style>
