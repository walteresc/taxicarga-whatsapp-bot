<script setup>
import { computed, onMounted, ref } from 'vue'

import { apiClient } from '@/services/apiClient'
import { useEscapeToClose } from '@/composables/useEscapeToClose'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceSummary from './ServiceSummary.vue'
import SendToDriverModal from './SendToDriverModal.vue'

const props = defineProps({
  leadId: { type: Number, required: true },
  serviceData: { type: Object, default: () => ({}) },
  // Desde dónde se abrió: define los botones del pie.
  //  'review' | 'potentials' | 'quotes' | 'quoting' → compartir · cotizar · reservar · descartar
  //  'bookings'                                     → compartir · cotizar · cancelar reserva
  //  'chat' (bandeja, por defecto)                  → según la etapa del lead
  context: { type: String, default: 'chat' },
})
const emit = defineEmits(['close', 'quote', 'book', 'changed', 'seen'])

const pipelineStore = usePipelineStore()
const stageExtra = ref({})
const stage = ref('')
const stageLabel = ref('')
const stageColor = ref('default')
const sendOpen = ref(false)
const summary = ref(null)
const editing = ref(false)
const cancelling = ref(false)
const discarding = ref(false)

const isQuoted = computed(() =>
  ['quotes', 'bookings'].includes(stage.value) || !!props.serviceData?.quoted_price)
const isBooked = computed(() => stage.value === 'bookings')

// Botones del pie según el origen del modal.
const footer = computed(() => {
  if (props.context === 'lost') return ['share']
  if (props.context === 'bookings') return ['share', 'quote', 'cancel']
  if (['review', 'potentials', 'quotes', 'quoting'].includes(props.context))
    return ['share', 'quote', 'book', 'discard']

  return isBooked.value ? ['share', 'quote', 'cancel'] : ['share', 'quote', 'book']
})

useEscapeToClose(() => emit('close'), {
  priority: 10,
  disabled: () => editing.value || sendOpen.value,
})

const STAGE_COLOR = {
  potentials: 'info', review: 'warning', quoting: 'secondary',
  quotes: 'primary', bookings: 'success', lost: 'error',
}

const loadStage = async () => {
  try {
    const d = await apiClient.get(`pipeline/leads/${props.leadId}/stage`)
    stage.value = d.stage || ''
    stageLabel.value = d.label || ''
    stageColor.value = STAGE_COLOR[d.stage] || 'default'
    stageExtra.value = {
      suggestedPrice: d.suggestedPrice,
      quotedPrice: d.quotedPrice,
      chatPrice: d.chatPrice,
      chatPriceIncludes: d.chatPriceIncludes,
      chatPriceNote: d.chatPriceNote,
      chatPriceAccepted: d.chatPriceAccepted,
    }
  } catch { /* no bloquea */ }
}
onMounted(loadStage)

const markSeen = async () => {
  try {
    await apiClient.post(`pipeline/leads/${props.leadId}/mark-seen`, { stage: props.context })
    pipelineStore.bump()
    emit('seen')
  } catch { /* el badge de "no visto" no es crítico */ }
}
onMounted(markSeen)

const cancelBooking = async () => {
  if (!window.confirm('¿Cancelar la reserva de este servicio?')) return
  cancelling.value = true
  try {
    await apiClient.post(`pipeline/leads/${props.leadId}/cancel-booking`, {})
    pipelineStore.bump()
    window.dispatchEvent(new Event('pipeline:stage-refresh'))
    emit('changed')
    await loadStage()
  } catch (e) {
    window.alert(e.message || 'No se pudo cancelar la reserva.')
  } finally {
    cancelling.value = false
  }
}

const discardService = async () => {
  const reason = window.prompt('Motivo del descarte:')
  if (!reason || !reason.trim()) return
  discarding.value = true
  try {
    await apiClient.post(`pipeline/leads/${props.leadId}/discard`, { reason: reason.trim() })
    pipelineStore.bump()
    window.dispatchEvent(new Event('pipeline:stage-refresh'))
    emit('changed')
    emit('close')
  } catch (e) {
    window.alert(e.message || 'No se pudo descartar.')
  } finally {
    discarding.value = false
  }
}
</script>

<template>
  <div
    class="sv-overlay"
    @click.self="$emit('close')"
  >
    <VCard
      class="sv-card"
      width="820"
      max-width="96vw"
    >
      <VCardItem class="py-2">
        <VCardTitle class="d-flex align-center ga-2 text-body-1">
          {{ editing ? 'Editar servicio' : 'Resumen del servicio' }}
          <VChip
            v-if="stageLabel && !editing"
            :color="stageColor"
            size="small"
            label
          >
            {{ stageLabel }}
          </VChip>
          <VSpacer />
          <VBtn
            v-if="!editing"
            size="small"
            variant="tonal"
            color="primary"
            prepend-icon="ri-pencil-line"
            class="me-6"
            @click="summary?.startEdit()"
          >
            Editar
          </VBtn>
          <VBtn
            icon="ri-close-line"
            variant="text"
            size="small"
            @click="$emit('close')"
          />
        </VCardTitle>
      </VCardItem>

      <VDivider />

      <VCardText class="sv-body">
        <ServiceSummary
          ref="summary"
          :service-data="serviceData"
          :stage-extra="stageExtra"
          :lead-id="leadId"
          external-edit-control
          @edit-change="editing = $event"
        />
      </VCardText>

      <VDivider v-if="!editing" />

      <VCardActions
        v-if="!editing"
        class="ga-4 px-4 py-3 sv-actions"
      >
        <VBtn
          v-if="footer.includes('share')"
          variant="text"
          color="default"
          prepend-icon="ri-share-forward-line"
          @click="sendOpen = true"
        >
          Compartir
        </VBtn>
        <VSpacer />
        <VBtn
          v-if="footer.includes('discard')"
          variant="text"
          color="error"
          prepend-icon="ri-delete-bin-line"
          :loading="discarding"
          @click="discardService"
        >
          Descartar
        </VBtn>
        <VBtn
          v-if="footer.includes('cancel')"
          variant="text"
          color="error"
          prepend-icon="ri-close-circle-line"
          :loading="cancelling"
          @click="cancelBooking"
        >
          Cancelar reserva
        </VBtn>
        <VBtn
          v-if="footer.includes('quote')"
          variant="text"
          color="primary"
          prepend-icon="ri-price-tag-3-line"
          @click="$emit('quote')"
        >
          {{ isQuoted ? 'Recotizar' : 'Cotizar' }}
        </VBtn>
        <VBtn
          v-if="footer.includes('book')"
          variant="text"
          color="success"
          prepend-icon="ri-calendar-check-line"
          @click="$emit('book')"
        >
          Reservar
        </VBtn>
      </VCardActions>
    </VCard>

    <SendToDriverModal
      v-if="sendOpen"
      :lead-id="leadId"
      @close="sendOpen = false"
      @sent="sendOpen = false"
    />
  </div>
</template>

<style scoped>
.sv-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100000;
  padding: 16px;
}

.sv-card {
  display: flex;
  flex-direction: column;
  max-height: 92vh;
}

.sv-body {
  overflow-y: auto;
  padding: 12px 12px 24px;
}

.sv-actions {
  flex-wrap: wrap;
  row-gap: 8px;
}

.sv-actions :deep(.v-btn) {
  padding-inline: 14px;
}
</style>
