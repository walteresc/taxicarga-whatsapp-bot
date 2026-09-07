<script setup>
import { computed, onMounted, ref } from 'vue'

import { apiClient } from '@/services/apiClient'
import { useEscapeToClose } from '@/composables/useEscapeToClose'

const props = defineProps({
  leadId: { type: Number, required: true },
})
const emit = defineEmits(['close', 'sent'])

useEscapeToClose(() => emit('close'), { priority: 30 })

const search = ref('')
const drivers = ref([])
const conversations = ref([])
const loading = ref(true)
const sending = ref(false)
const errorMsg = ref('')
// clave = `d:<id>` para conductor, `c:<id>` para conversación
const selected = ref(new Set())
const doneKeys = ref(new Set())
const failedKeys = ref(new Set())

const norm = s => (s || '').toLowerCase()
const filteredDrivers = computed(() => {
  const q = norm(search.value)
  return drivers.value.filter(d => !q || norm(d.name).includes(q) || norm(d.phone).includes(q))
})
const filteredConvs = computed(() => {
  const q = norm(search.value)
  return conversations.value.filter(c => !q || norm(c.name).includes(q) || norm(c.phone).includes(q))
})

const sendLabel = computed(() => {
  if (sending.value) return 'Enviando…'
  const n = selected.value.size
  return n > 0 ? `Enviar a ${n}` : 'Elegí uno o más contactos'
})

const initials = name => (name || '?').trim().slice(0, 1).toUpperCase()

const toggle = key => {
  if (sending.value) return
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

onMounted(async () => {
  try {
    const [dRes, cRes] = await Promise.all([
      apiClient.get('drivers/', { status: 'active', pageSize: 200 }).catch(() => null),
      fetch('/dashboard/whatsapp/conversaciones/api/active/?limit=100&transportistas=all', { credentials: 'include' })
        .then(r => r.json()).catch(() => null),
    ])
    const dList = dRes?.data || dRes?.results || (Array.isArray(dRes) ? dRes : [])
    drivers.value = dList.filter(d => d.phone)
    conversations.value = (cRes?.conversations || []).map(c => ({
      id: c.id,
      name: c.name || c.profile_name || c.phone,
      phone: c.phone,
    }))
  } catch (e) {
    errorMsg.value = 'No se pudieron cargar los contactos.'
  } finally {
    loading.value = false
  }
})

const sendOne = async key => {
  const [kind, id] = key.split(':')
  const body = kind === 'd'
    ? (() => {
      const d = drivers.value.find(x => String(x.id) === id)
      return { phone: d.phone, name: d.name }
    })()
    : { conversationId: Number(id) }
  const res = await apiClient.post(`pipeline/leads/${props.leadId}/send-summary`, body)
  return res?.sent !== false
}

const send = async () => {
  if (selected.value.size === 0 || sending.value) return
  sending.value = true
  errorMsg.value = ''
  doneKeys.value = new Set()
  failedKeys.value = new Set()
  let anyFail = false
  for (const key of [...selected.value]) {
    try {
      const ok = await sendOne(key)
      if (ok) doneKeys.value = new Set(doneKeys.value).add(key)
      else { anyFail = true; failedKeys.value = new Set(failedKeys.value).add(key) }
    } catch {
      anyFail = true
      failedKeys.value = new Set(failedKeys.value).add(key)
    }
  }
  sending.value = false
  if (anyFail) {
    errorMsg.value = 'Algunos envíos fallaron (fuera de la ventana de 24h de WhatsApp). Mandalos a mano por WhatsApp Web.'
    return
  }
  emit('sent')
}
</script>

<template>
  <div
    class="sd-overlay"
    @click.self="$emit('close')"
  >
    <div class="sd-modal">
      <div class="sd-header">
        <h3>Compartir servicio con…</h3>
        <button
          class="sd-close"
          @click="$emit('close')"
        >
          <i class="ri-close-line" />
        </button>
      </div>

      <input
        v-model="search"
        class="sd-search"
        type="text"
        placeholder="Buscar por nombre o teléfono…"
      >

      <div class="sd-list">
        <div
          v-if="loading"
          class="sd-status"
        >
          Cargando…
        </div>
        <template v-else>
          <div
            v-if="filteredDrivers.length"
            class="sd-section"
          >
            🚚 Conductores
          </div>
          <button
            v-for="d in filteredDrivers"
            :key="`d:${d.id}`"
            class="sd-item"
            :class="{ 'sd-item--sel': selected.has(`d:${d.id}`) }"
            :disabled="sending"
            @click="toggle(`d:${d.id}`)"
          >
            <i :class="selected.has(`d:${d.id}`) ? 'ri-checkbox-fill' : 'ri-checkbox-blank-line'" />
            <span class="sd-avatar sd-avatar--driver">{{ initials(d.name) }}</span>
            <span class="sd-text">
              <span class="sd-name">{{ d.name }}</span>
              <span class="sd-phone">{{ d.phone }}</span>
            </span>
            <i
              v-if="doneKeys.has(`d:${d.id}`)"
              class="ri-check-double-line sd-ok"
            />
            <i
              v-else-if="failedKeys.has(`d:${d.id}`)"
              class="ri-error-warning-line sd-err"
            />
          </button>

          <div
            v-if="filteredConvs.length"
            class="sd-section"
          >
            Conversaciones
          </div>
          <button
            v-for="c in filteredConvs"
            :key="`c:${c.id}`"
            class="sd-item"
            :class="{ 'sd-item--sel': selected.has(`c:${c.id}`) }"
            :disabled="sending"
            @click="toggle(`c:${c.id}`)"
          >
            <i :class="selected.has(`c:${c.id}`) ? 'ri-checkbox-fill' : 'ri-checkbox-blank-line'" />
            <span class="sd-avatar">{{ initials(c.name) }}</span>
            <span class="sd-text">
              <span class="sd-name">{{ c.name }}</span>
              <span
                v-if="c.phone && c.phone !== c.name"
                class="sd-phone"
              >{{ c.phone }}</span>
            </span>
            <i
              v-if="doneKeys.has(`c:${c.id}`)"
              class="ri-check-double-line sd-ok"
            />
            <i
              v-else-if="failedKeys.has(`c:${c.id}`)"
              class="ri-error-warning-line sd-err"
            />
          </button>
        </template>
      </div>

      <div
        v-if="errorMsg"
        class="sd-error"
      >
        {{ errorMsg }}
      </div>

      <div class="sd-footer">
        <button
          class="sd-send"
          :disabled="selected.size === 0 || sending"
          @click="send"
        >
          <i
            v-if="sending"
            class="ri-loader-4-line spin"
          />
          {{ sendLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sd-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100040;
  pointer-events: auto;
}

.sd-modal {
  width: 400px;
  max-width: 92vw;
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
}

.sd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 16px;
  border-bottom: 1px solid #eee;
}

.sd-header h3 {
  margin: 0;
  font-size: 15px;
}

.sd-close {
  border: none;
  background: none;
  font-size: 18px;
  color: #666;
  cursor: pointer;
}

.sd-search {
  margin: 12px 16px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 20px;
  font-size: 13px;
  outline: none;
}

.sd-search:focus {
  border-color: #8b5cf6;
}

.sd-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.sd-status {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.sd-section {
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

.sd-item {
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
  font-size: 13px;
  color: #667085;
}

.sd-item:hover:not(:disabled) {
  background: #f5f5f5;
}

.sd-item:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.sd-item--sel {
  background: #f0ecfe;
  color: #4c1d95;
}

.sd-item > i:first-child {
  flex-shrink: 0;
  font-size: 18px;
  color: #8b5cf6;
}

.sd-avatar {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #94a3b8;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

.sd-avatar--driver {
  background: #0ea5e9;
}

.sd-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.sd-name {
  font-weight: 500;
  color: #222;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sd-phone {
  font-size: 12px;
  color: #888;
}

.sd-ok {
  color: #16a34a;
}

.sd-err {
  color: #dc2626;
}

.sd-error {
  margin: 0 16px 10px;
  padding: 8px 10px;
  background: #fef2f2;
  color: #b91c1c;
  border-radius: 6px;
  font-size: 12px;
}

.sd-footer {
  padding: 12px 16px;
  border-top: 1px solid #eee;
}

.sd-send {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: none;
  border-radius: 6px;
  background: #8b5cf6;
  color: #fff;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
}

.sd-send:disabled {
  background: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}

.spin {
  animation: sd-spin 0.8s linear infinite;
}

@keyframes sd-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
