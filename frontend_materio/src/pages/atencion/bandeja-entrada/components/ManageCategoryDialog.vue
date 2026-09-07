<script setup>
import { computed, onMounted, ref } from 'vue'

import { useEscapeToClose } from '@/composables/useEscapeToClose'
import { conversationService } from '@/services/conversationService'

const props = defineProps({
  category: {
    type: String,
    required: true,
    validator: v => ['oficina', 'transportista', 'campo'].includes(v),
  },
})
const emit = defineEmits(['close', 'changed'])

useEscapeToClose(() => emit('close'))

const CONFIG = {
  oficina: {
    title: '🏢 Contactos de Oficina',
    field: 'is_oficina',
    setter: (id, value) => conversationService.setOficina(id, value),
  },
  transportista: {
    title: '🚚 Contactos de Transportistas',
    field: 'is_transportista',
    setter: (id, value) => conversationService.setTransportista(id, value),
  },
  campo: {
    title: '🚛 Contactos de Campo',
    field: 'is_campo',
    setter: (id, value) => conversationService.setCampo(id, value),
  },
}

const config = computed(() => CONFIG[props.category])

const search = ref('')
const results = ref([])
const loading = ref(false)
const busyId = ref(null)
const errorMsg = ref('')
let debounceTimer = null

const fetchConversations = async q => {
  loading.value = true
  try {
    // transportistas=all: el diálogo tiene que poder ver y gestionar TODOS los
    // contactos, incluidos los que ya son transportistas (el endpoint los
    // excluye por defecto).
    const params = new URLSearchParams({ limit: '30', transportistas: 'all' })
    if (q) params.set('q', q)

    const response = await fetch(`/dashboard/whatsapp/conversaciones/api/active/?${params}`, {
      credentials: 'include',
    })
    const data = await response.json()

    results.value = data.conversations || []
  } catch (error) {
    console.error('[ManageCategoryDialog] Search failed:', error)
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

const toggle = async conv => {
  if (busyId.value !== null) return
  busyId.value = conv.id
  errorMsg.value = ''
  try {
    await config.value.setter(conv.id, !conv[config.value.field])
    conv[config.value.field] = !conv[config.value.field]
    emit('changed')
  } catch (error) {
    errorMsg.value = error.message || 'No se pudo actualizar.'
  } finally {
    busyId.value = null
  }
}

const initials = name => (name || '?').trim().slice(0, 1).toUpperCase()

// El número que se buscó no existe todavía como contacto — se puede crear de
// una vez y marcarlo directo, sin salir de este diálogo.
const looksLikeNewPhone = computed(() => {
  const digits = search.value.replace(/\D/g, '')

  return digits.length >= 8 && results.value.length === 0 && !loading.value
})

const showCreateForm = ref(false)
const newContactName = ref('')
const creating = ref(false)

const createAndAdd = async () => {
  const digits = search.value.replace(/\D/g, '')
  if (!digits) return
  creating.value = true
  errorMsg.value = ''
  try {
    const created = await conversationService.createManualConversation(digits, newContactName.value)
    await config.value.setter(created.conversation_id, true)
    showCreateForm.value = false
    newContactName.value = ''
    search.value = ''
    emit('changed')
    await fetchConversations('')
  } catch (error) {
    errorMsg.value = error.message || 'No se pudo crear el contacto.'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div
    class="forward-overlay"
    @click.self="$emit('close')"
  >
    <div class="forward-modal">
      <div class="forward-header">
        <h3>{{ config.title }}</h3>
        <button
          class="forward-close"
          @click="$emit('close')"
        >
          <i class="ri-close-line" />
        </button>
      </div>

      <p class="oficina-hint">
        Agrega o quita contactos de esta partición. Se quedan ahí hasta que los quites.
      </p>

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
        <template v-else-if="results.length === 0">
          <div
            v-if="!looksLikeNewPhone"
            class="forward-status"
          >
            Sin resultados
          </div>
          <div
            v-else
            class="new-contact-box"
          >
            <p class="forward-status">
              No hay ningún contacto con ese número todavía.
            </p>
            <button
              v-if="!showCreateForm"
              class="oficina-toggle-btn"
              @click="showCreateForm = true"
            >
              + Crear contacto y agregar
            </button>
            <template v-else>
              <input
                v-model="newContactName"
                class="forward-search"
                type="text"
                placeholder="Nombre del contacto (opcional)"
                style="margin: 8px 0;"
                @keydown.enter="createAndAdd"
              >
              <button
                class="oficina-toggle-btn"
                :disabled="creating"
                @click="createAndAdd"
              >
                <i
                  v-if="creating"
                  class="ri-loader-4-line spin"
                />
                <template v-else>
                  Crear y agregar
                </template>
              </button>
            </template>
          </div>
        </template>
        <div
          v-for="conv in results"
          :key="conv.id"
          class="forward-item"
        >
          <div class="forward-avatar">
            {{ initials(conv.name || conv.phone) }}
          </div>
          <div class="forward-item-text">
            <div class="forward-item-name">
              {{ conv.name || conv.phone }}
            </div>
            <div
              v-if="conv.name && conv.phone"
              class="forward-item-phone"
            >
              {{ conv.phone }}
            </div>
          </div>
          <button
            class="oficina-toggle-btn"
            :class="{ 'oficina-toggle-btn--remove': conv[config.field] }"
            :disabled="busyId === conv.id"
            @click="toggle(conv)"
          >
            <i
              v-if="busyId === conv.id"
              class="ri-loader-4-line spin"
            />
            <template v-else>
              {{ conv[config.field] ? 'Quitar' : 'Agregar' }}
            </template>
          </button>
        </div>
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
  width: 420px;
  max-width: 90vw;
  max-height: 80vh;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
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
  font-size: 15px;
}

.forward-close {
  border: none;
  background: transparent;
  font-size: 18px;
  color: #666;
  cursor: pointer;
}

.oficina-hint {
  margin: 10px 16px 0;
  font-size: 12px;
  color: #888;
}

.forward-search {
  width: calc(100% - 32px);
  margin: 10px 16px;
  padding: 8px 10px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 13px;
}

.forward-search:focus {
  outline: none;
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

.new-contact-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 16px 16px;
}

.forward-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px;
  border-radius: 6px;
}

.forward-item:hover {
  background: #f5f5f5;
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

.oficina-toggle-btn {
  flex-shrink: 0;
  padding: 6px 12px;
  border: 1px solid #ff9800;
  border-radius: 16px;
  background: #fff3e0;
  color: #ff9800;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.oficina-toggle-btn--remove {
  border-color: #d32f2f;
  background: #ffebee;
  color: #d32f2f;
}

.oficina-toggle-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.oficina-toggle-btn i.spin {
  animation: oficina-spin 0.8s linear infinite;
}

@keyframes oficina-spin {
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
