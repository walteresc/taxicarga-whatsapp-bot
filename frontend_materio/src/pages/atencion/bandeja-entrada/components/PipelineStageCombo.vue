<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { apiClient } from '@/services/apiClient'
import { usePipelineStore } from '@/stores/pipelineStore'

const props = defineProps({
  leadId: { type: Number, default: null },
})
const emit = defineEmits(['changed'])

const pipelineStore = usePipelineStore()

const STAGES = {
  potentials: { label: 'Oportunidad', color: '#607d8b' },
  review: { label: 'Estancados', color: '#f59e0b' },
  quoting: { label: 'Por cotizar', color: '#8b5cf6' },
  quotes: { label: 'Cotizados', color: '#14b8a6' },
  bookings: { label: 'Reserva', color: '#22c55e' },
  lost: { label: 'Perdido', color: '#ef4444' },
}
const MOVABLE = ['potentials', 'review', 'quoting']

const stage = ref(null)
const open = ref(false)
const busy = ref(false)
const errMsg = ref('')
const rootRef = ref(null)

const current = computed(() => STAGES[stage.value] || { label: 'Sin etapa', color: '#bbb' })
const canMove = computed(() => MOVABLE.includes(stage.value) || stage.value === null)

const load = async () => {
  errMsg.value = ''
  if (!props.leadId) { stage.value = null; return }
  try {
    const d = await apiClient.get(`pipeline/leads/${props.leadId}/stage`)
    stage.value = d.stage
  } catch {
    stage.value = null
  }
}
watch(() => props.leadId, load, { immediate: true })

const move = async target => {
  if (target === stage.value || busy.value || !props.leadId) return
  busy.value = true
  errMsg.value = ''
  try {
    const d = await apiClient.post(`pipeline/leads/${props.leadId}/stage`, { stage: target })
    stage.value = d.stage
    open.value = false
    pipelineStore.bump()
    emit('changed', d.stage)
  } catch (e) {
    errMsg.value = e.message || 'No se pudo mover.'
  } finally {
    busy.value = false
  }
}

const toggle = () => {
  if (!canMove.value) return
  open.value = !open.value
}

const closeIfOutside = e => {
  if (open.value && !rootRef.value?.contains(e.target)) open.value = false
}
watch(open, v => {
  if (v) document.addEventListener('mousedown', closeIfOutside, true)
  else document.removeEventListener('mousedown', closeIfOutside, true)
})

// Cotizar / Reservar desde el composer cambian la etapa por fuera de este
// componente — refrescar cuando lo avisan.
onMounted(() => window.addEventListener('pipeline:stage-refresh', load))
onUnmounted(() => window.removeEventListener('pipeline:stage-refresh', load))
</script>

<template>
  <div
    ref="rootRef"
    class="stage-combo"
  >
    <button
      class="stage-pill"
      :class="{ 'stage-pill--locked': !canMove }"
      :style="{ background: current.color }"
      :title="canMove ? 'Cambiar etapa del pipeline' : 'Esta etapa se generó con Cotizar / Reservar'"
      :disabled="busy"
      @click="toggle"
    >
      <i
        v-if="busy"
        class="ri-loader-4-line spin"
      />
      <template v-else>
        {{ current.label }}
        <i
          v-if="canMove"
          class="ri-arrow-down-s-line"
        />
        <i
          v-else
          class="ri-lock-line"
        />
      </template>
    </button>

    <div
      v-if="open"
      class="stage-menu"
    >
      <button
        v-for="key in MOVABLE"
        :key="key"
        class="stage-option"
        :class="{ 'stage-option--current': key === stage }"
        @click="move(key)"
      >
        <span
          class="stage-dot"
          :style="{ background: STAGES[key].color }"
        />
        {{ STAGES[key].label }}
        <i
          v-if="key === stage"
          class="ri-check-line"
        />
      </button>
      <div class="stage-hint">
        Cotizaciones y Reservas se generan con los botones <b>Cotizar</b> / <b>Reservar</b> del chat.
      </div>
    </div>

    <div
      v-if="errMsg"
      class="stage-err"
    >
      {{ errMsg }}
    </div>
  </div>
</template>

<style scoped>
.stage-combo {
  position: relative;
}

.stage-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border: none;
  border-radius: 14px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.stage-pill--locked {
  cursor: default;
  opacity: 0.9;
}

.stage-pill:disabled {
  opacity: 0.6;
  cursor: wait;
}

.stage-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 1200;
  min-width: 190px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
  padding: 4px;
}

.stage-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: none;
  font-size: 12px;
  color: #333;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
}

.stage-option:hover {
  background: #f5f5f5;
}

.stage-option--current {
  font-weight: 700;
}

.stage-option i {
  margin-left: auto;
  color: #22c55e;
}

.stage-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.stage-hint {
  padding: 6px 10px 4px;
  font-size: 10px;
  color: #999;
  line-height: 1.35;
  border-top: 1px solid #eee;
  margin-top: 4px;
}

.stage-err {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 1200;
  background: #ffebee;
  color: #d32f2f;
  font-size: 11px;
  padding: 6px 8px;
  border-radius: 6px;
  max-width: 240px;
}

.spin {
  animation: stage-spin 0.8s linear infinite;
}

@keyframes stage-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
