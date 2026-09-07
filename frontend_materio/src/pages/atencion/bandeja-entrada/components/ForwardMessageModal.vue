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
        <template
          v-for="(row, i) in displayRows"
          :key="row.kind === 'header' ? `h-${i}` : row.conv.id"
        >
          <div
            v-if="row.kind === 'header'"
            class="forward-section-header"
          >
            {{ row.label }}
          </div>
          <button
            v-else
            class="forward-item"
            :class="{ 'forward-item--selected': selectedIds.has(row.conv.id) }"
            :disabled="sending"
            @click="toggleTarget(row.conv)"
          >
            <div class="forward-checkbox">
              <i :class="selectedIds.has(row.conv.id) ? 'ri-checkbox-fill' : 'ri-checkbox-blank-line'" />
            </div>
            <div class="forward-avatar">
              {{ initials(row.conv.name || row.conv.phone) }}
            </div>
            <div class="forward-item-text">
              <div class="forward-item-name">
                {{ row.conv.name || row.conv.phone }}
              </div>
              <div
                v-if="row.conv.name && row.conv.phone"
                class="forward-item-phone"
              >
                {{ row.conv.phone }}
              </div>
            </div>
            <i
              v-if="sentIds.has(row.conv.id)"
              class="ri-check-double-line forward-sent-icon"
            />
            <i
              v-else-if="failedIds.has(row.conv.id)"
              class="ri-error-warning-line forward-error-icon"
            />
            <i
              v-else-if="sending && selectedIds.has(row.conv.id)"
              class="ri-loader-4-line spin"
            />
          </button>
        </template>
      </div>

      <div
        v-if="errorMsg"
        class="forward-error"
      >
        {{ errorMsg }}
      </div>

      <div class="forward-footer">
        <button
          class="forward-send-btn"
          :disabled="selectedIds.size === 0 || sending"
          @click="sendToSelected"
        >
          <i
            v-if="sending"
            class="ri-loader-4-line spin"
          />
          {{ sendButtonLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { conversationService } from '@/services/conversationService'
import { useEscapeToClose } from '@/composables/useEscapeToClose'

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

useEscapeToClose(() => emit('close'))

const search = ref('')
const results = ref([])
const memberCount = ref(0)
const sourceCategory = ref(null) // 'campo' | 'oficina' | 'transportista' | null
const loading = ref(false)
const sending = ref(false)
const selectedIds = ref(new Set())
const sentIds = ref(new Set())
const failedIds = ref(new Set())
const errorMsg = ref('')
let debounceTimer = null

const sendButtonLabel = computed(() => {
  if (sending.value) return 'Enviando...'
  const n = selectedIds.value.size

  return n > 0 ? `Enviar a ${n}` : 'Elige uno o más contactos'
})

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

const CATEGORY_FIELD = { campo: 'is_campo', oficina: 'is_oficina', transportista: 'is_transportista' }
const CATEGORY_LABEL = { campo: '🚛 Personal de campo', oficina: '🏢 Oficina', transportista: '🚚 Transportistas' }

// Filas a mostrar: si la conversación de origen es de Campo/Oficina/
// Transportistas, sus otros integrantes van primero (con encabezado) para
// reenviar rápido, y el resto abajo. Si no, lista normal.
const displayRows = computed(() => {
  if (!sourceCategory.value || memberCount.value === 0) {
    return results.value.map(conv => ({ kind: 'item', conv }))
  }
  const rows = [{ kind: 'header', label: CATEGORY_LABEL[sourceCategory.value] }]
  results.value.slice(0, memberCount.value).forEach(conv => rows.push({ kind: 'item', conv }))
  if (results.value.length > memberCount.value) {
    rows.push({ kind: 'header', label: 'Otras conversaciones' })
    results.value.slice(memberCount.value).forEach(conv => rows.push({ kind: 'item', conv }))
  }

  return rows
})

const fetchConversations = async q => {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '100', transportistas: 'all' })
    if (q) params.set('q', q)

    const response = await fetch(`/dashboard/whatsapp/conversaciones/api/active/?${params}`, {
      credentials: 'include',
    })
    const data = await response.json()
    const all = data.conversations || []

    // Categoría de la conversación de origen (una sola de las tres, o ninguna).
    const source = all.find(c => c.id === props.conversationId)
    sourceCategory.value = source?.is_campo ? 'campo'
      : source?.is_oficina ? 'oficina'
        : source?.is_transportista ? 'transportista'
          : null

    const others = all.filter(c => c.id !== props.conversationId)
    if (sourceCategory.value) {
      const field = CATEGORY_FIELD[sourceCategory.value]
      const members = others.filter(c => c[field])
      const rest = others.filter(c => !c[field])
      results.value = [...members, ...rest]
      memberCount.value = members.length
    } else {
      results.value = others
      memberCount.value = 0
    }
  } catch (error) {
    console.error('[ForwardMessageModal] Search failed:', error)
    results.value = []
    memberCount.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchConversations(''))

const onSearchInput = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => fetchConversations(search.value), 300)
}

const toggleTarget = conv => {
  if (sending.value) return
  const next = new Set(selectedIds.value)
  if (next.has(conv.id)) next.delete(conv.id)
  else next.add(conv.id)
  selectedIds.value = next
}

const forwardOne = async targetId => {
  const response = await fetch(
    `/dashboard/whatsapp/conversaciones/${props.conversationId}/mensajes/${props.message.id}/reenviar/`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': conversationService.getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ target_conversation_id: targetId }),
    }
  )

  let data = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  return Boolean(data?.success)
}

// Uno por uno (no Promise.all): WhatsApp no tiene "grupo real" gestionable por
// API (ver docs/decisión del equipo) — reenviar a varios es, por dentro, N
// mensajes 1 a 1 al número de cada quien. Secuencial evita saturar al mismo
// tiempo el límite de envíos y deja ver el progreso contacto por contacto.
const sendToSelected = async () => {
  if (selectedIds.value.size === 0 || sending.value) return
  sending.value = true
  errorMsg.value = ''
  sentIds.value = new Set()
  failedIds.value = new Set()

  const targets = [...selectedIds.value]
  let anyFailed = false

  for (const targetId of targets) {
    try {
      const ok = await forwardOne(targetId)
      if (ok) {
        sentIds.value = new Set(sentIds.value).add(targetId)
      } else {
        anyFailed = true
        failedIds.value = new Set(failedIds.value).add(targetId)
      }
    } catch (error) {
      console.error('[ForwardMessageModal] Forward failed:', error)
      anyFailed = true
      failedIds.value = new Set(failedIds.value).add(targetId)
    }
  }

  sending.value = false

  if (anyFailed) {
    errorMsg.value = 'Algunos envíos fallaron — revisa los marcados en rojo.'

    return
  }

  emit('forwarded', { targetConversationIds: targets })
  emit('close')
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
  z-index: 100000;
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

.forward-section-header {
  padding: 10px 8px 4px;
  font-size: 11px;
  font-weight: 700;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  position: sticky;
  top: 0;
  background: #fff;
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

.forward-item--selected {
  background: #fff3e0;
}

.forward-checkbox {
  flex-shrink: 0;
  font-size: 18px;
  color: #ff9800;
}

.forward-sent-icon {
  color: #2e7d32;
}

.forward-error-icon {
  color: #d32f2f;
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

.forward-item i.spin,
.forward-send-btn i.spin {
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

.forward-footer {
  padding: 12px 16px;
  border-top: 1px solid #eee;
}

.forward-send-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: none;
  border-radius: 6px;
  background: #ff9800;
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}

.forward-send-btn:disabled {
  background: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}
</style>
