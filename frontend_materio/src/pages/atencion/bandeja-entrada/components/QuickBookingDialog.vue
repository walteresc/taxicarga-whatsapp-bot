<script setup>
import { computed, ref } from 'vue'

import { apiClient } from '@/services/apiClient'
import { useEscapeToClose } from '@/composables/useEscapeToClose'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceSummary from './ServiceSummary.vue'

const props = defineProps({
  leadId: { type: Number, required: true },
  serviceData: { type: Object, default: () => ({}) },
  // Panel flotante arrastrable (se abre al costado del modal Ver).
  draggable: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'done'])

const pipelineStore = usePipelineStore()
useEscapeToClose(() => emit('close'), { priority: 20 })
const ss = ref(null)
const busy = ref(false)
const errMsg = ref('')

// Campos mínimos para crear la reserva (coinciden con booking_missing_fields del backend).
const REQUIRED = [
  ['customerName', 'Cliente'],
  ['addressOrigin', 'Dirección de origen'],
  ['addressDestination', 'Dirección de destino'],
  ['serviceDate', 'Fecha del servicio'],
  ['schedule', 'Horario'],
]

// Traduce los nombres técnicos que puede devolver el backend a algo legible.
const friendlyError = msg => {
  if (!msg) return msg
  const map = {
    cliente_nombre: 'Cliente', direccion_origen: 'Dirección de origen',
    direccion_destino: 'Dirección de destino', fecha_servicio: 'Fecha del servicio',
    horario_servicio: 'Horario',
  }
  return msg
    .replace(/ubicacion_\d+_direccion/g, 'Dirección (con calle y número)')
    .replace(/ubicacion_\d+_piso/g, 'Piso')
    .replace(/ubicacion_\d+_ascensor/g, 'Acceso (ascensor/escaleras)')
    .replace(/\b(cliente_nombre|direccion_origen|direccion_destino|fecha_servicio|horario_servicio)\b/g,
      m => map[m])
}

const submit = async () => {
  errMsg.value = ''
  const p = ss.value?.buildPayload() || {}

  const missing = REQUIRED.filter(([k]) => !String(p[k] ?? '').trim()).map(([, label]) => label)
  if (missing.length) {
    errMsg.value = `Faltan datos para crear la reserva: ${missing.join(', ')}.`

    return
  }

  busy.value = true
  try {
    // 1) Guardar todos los campos del servicio (mismo endpoint que Editar).
    await apiClient.patch(`pipeline/leads/${props.leadId}/service`, p)
    // 2) Crear la reserva (Servicio) con los datos que necesita.
    await apiClient.post(`pipeline/leads/${props.leadId}/quick-booking`, {
      customerName: p.customerName,
      contactName: p.contactName,
      contactPhone: p.contactPhone,
      serviceDate: p.serviceDate,
      schedule: p.schedule,
      type: p.type,
      addressOrigin: p.addressOrigin,
      addressDestination: p.addressDestination,
      districtOrigin: p.origin,
      districtDestination: p.destination,
      price: p.quotedPrice || props.serviceData?.quoted_price || props.serviceData?.price || '',
    })
    pipelineStore.bump()
    window.dispatchEvent(new Event('pipeline:stage-refresh'))
    emit('done', { stage: 'bookings' })
    emit('close')
  } catch (e) {
    errMsg.value = friendlyError(e.message) || 'No se pudo crear la reserva.'
  } finally {
    busy.value = false
  }
}

// ── Arrastre ───────────────────────────────────────────────────────────────
const dragPos = ref({ x: 0, y: 0 })
let dragStart = null
const onDragStart = e => {
  if (!props.draggable || e.target.closest('button, input, textarea, a, .v-field')) return
  dragStart = { px: e.clientX, py: e.clientY, x: dragPos.value.x, y: dragPos.value.y }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
}
const onDragMove = e => {
  if (!dragStart) return
  dragPos.value = {
    x: dragStart.x + (e.clientX - dragStart.px),
    y: dragStart.y + (e.clientY - dragStart.py),
  }
}
const onDragEnd = () => {
  dragStart = null
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
}
const modalStyle = computed(() =>
  props.draggable ? { transform: `translate(${dragPos.value.x}px, ${dragPos.value.y}px)` } : {})
</script>

<template>
  <div
    class="qb-overlay"
    :class="{ 'qb-overlay--drag': draggable }"
    @click.self="draggable ? null : $emit('close')"
  >
    <VCard
      class="qb-card"
      :class="{ 'qb-card--drag': draggable }"
      :style="modalStyle"
      width="820"
      max-width="96vw"
    >
      <VCardItem
        class="py-2"
        :class="{ 'qb-head--drag': draggable }"
        @pointerdown="onDragStart"
      >
        <VCardTitle class="d-flex align-center ga-2 text-body-1">
          <VIcon
            v-if="draggable"
            icon="ri-drag-move-2-line"
            size="16"
            class="text-medium-emphasis"
          />
          <VIcon
            icon="ri-calendar-check-line"
            size="18"
            color="success"
          />
          Reservar
          <VSpacer />
          <VBtn
            icon="ri-close-line"
            variant="text"
            size="small"
            @click="$emit('close')"
          />
        </VCardTitle>
      </VCardItem>

      <VDivider />

      <VCardText class="qb-body">
        <ServiceSummary
          ref="ss"
          booking-mode
          :service-data="serviceData"
          :lead-id="leadId"
        />
        <VAlert
          v-if="errMsg"
          type="error"
          variant="tonal"
          density="compact"
          class="mt-2"
        >
          {{ errMsg }}
        </VAlert>
      </VCardText>

      <VDivider />

      <VCardActions class="justify-end pa-3">
        <VBtn
          variant="text"
          :disabled="busy"
          @click="$emit('close')"
        >
          Cancelar
        </VBtn>
        <VBtn
          color="success"
          :loading="busy"
          @click="submit"
        >
          Crear reserva
        </VBtn>
      </VCardActions>
    </VCard>
  </div>
</template>

<style scoped>
.qb-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100000;
  padding: 16px;
}

.qb-overlay--drag {
  background: rgba(0, 0, 0, 0.22);
  z-index: 100010;
}

.qb-card {
  display: flex;
  flex-direction: column;
  max-height: 92vh;
}

.qb-card--drag {
  pointer-events: auto;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
}

.qb-head--drag {
  cursor: move;
  user-select: none;
  background: rgb(var(--v-theme-success), 0.06);
}

.qb-body {
  overflow-y: auto;
  padding: 12px;
}
</style>
