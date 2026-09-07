<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { leadServiceData, quoteRequestList } from '@/services/commercialService'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'
import QuickQuoteDialog from '@/pages/atencion/bandeja-entrada/components/QuickQuoteDialog.vue'
import QuickBookingDialog from '@/pages/atencion/bandeja-entrada/components/QuickBookingDialog.vue'

const router = useRouter()
const pipeline = usePipelineStore()

const DATA_SOURCE = {
  bot: { label: 'Bot', color: 'info' },
  asesor: { label: 'Asesor', color: 'secondary' },
  ambos: { label: 'Bot + asesor', color: 'primary' },
}

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
let searchTimer

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (text, color = 'success') => Object.assign(snackbar, { show: true, text, color })

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    rows.value = (await quoteRequestList({ search: search.value })).results
  } catch (e) {
    error.value = e.message || 'No se pudo cargar la cola.'
  } finally {
    loading.value = false
  }
}

const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }

onMounted(load)

// --- Ver detalle / Cotizar (reutiliza el modal de la bandeja) ---
const viewOpen = ref(false)
const viewLeadId = ref(null)
const viewServiceData = ref({})
const viewInterprovincial = ref(false)
const quoteOpen = ref(false)
const bookingOpen = ref(false)

const loadServiceData = async row => {
  viewLeadId.value = row.leadId
  viewInterprovincial.value = !!row.isInterprovincial
  viewServiceData.value = {}
  try {
    viewServiceData.value = (await leadServiceData(row.leadId)).serviceData || {}
  } catch { /* el modal igual carga los precios desde /stage */ }
}

const openDetail = async row => {
  if (!row.leadId) { notify('Esta oportunidad todavía no tiene lead.', 'warning'); return }
  viewOpen.value = true
  await loadServiceData(row)
}

const openQuote = async row => {
  if (!row.leadId) { notify('Esta oportunidad todavía no tiene lead.', 'warning'); return }
  viewOpen.value = true
  quoteOpen.value = true
  await loadServiceData(row)
}

const afterPipelineAction = async () => {
  quoteOpen.value = false
  bookingOpen.value = false
  viewOpen.value = false
  pipeline.bump()
  await load()
}

const markRowSeen = () => {
  const r = rows.value.find(x => x.leadId === viewLeadId.value)
  if (r) r.seen = true
}

const openConversation = row => {
  if (row.conversationId) router.push(`/atencion/bandeja-entrada?conversation=${row.conversationId}`)
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Por cotizar
    </h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Oportunidades listas para ponerles precio. Abre el detalle y cotiza sin salir de aquí.
    </p>

    <VCard>
      <VCardText>
        <VTextField
          v-model="search"
          prepend-inner-icon="ri-search-line"
          label="Buscar por cliente o ruta"
          density="compact" hide-details clearable style="max-width: 380px;"
          @update:model-value="onSearch"
        />
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">
        {{ error }}
        <template #append><VBtn size="small" variant="text" @click="load">Reintentar</VBtn></template>
      </VAlert>

      <VTable>
        <thead>
          <tr>
            <th>Cliente</th><th>Ruta</th><th>Fecha</th><th>Datos recabados por</th><th>Prioridad</th><th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="6" class="text-center py-8"><VProgressCircular indeterminate color="primary" /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="6" class="text-center text-medium-emphasis py-10">Nada por cotizar.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium text-primary" style="cursor: pointer;" title="Ver detalle" @click="openDetail(row)">
              <VBadge v-if="!row.seen" dot inline color="primary" class="me-1" title="Sin abrir" />{{ row.customerName }}
            </td>
            <td>
              {{ row.route }}
              <VChip v-if="row.isInterprovincial" size="x-small" color="warning" class="ms-1">Fuera de Lima</VChip>
            </td>
            <td>{{ row.serviceDate || 'Por confirmar' }}</td>
            <td>
              <VChip size="small" :color="DATA_SOURCE[row.dataSource]?.color || 'default'">
                {{ DATA_SOURCE[row.dataSource]?.label || '—' }}
              </VChip>
            </td>
            <td><VChip size="small" :color="row.priority === 'urgente' ? 'error' : row.priority === 'alta' ? 'warning' : 'default'">{{ row.priority }}</VChip></td>
            <td class="text-right text-no-wrap">
              <VBtn size="small" variant="text" icon="ri-eye-line" title="Ver detalle" @click="openDetail(row)" />
              <VBtn size="small" variant="text" icon="ri-chat-3-line" title="Abrir conversación" :disabled="!row.conversationId" @click="openConversation(row)" />
              <VBtn size="small" variant="tonal" color="primary" class="ms-1" @click="openQuote(row)">Cotizar</VBtn>
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Ver detalle / Cotizar: mismo modal que la bandeja -->
    <ServiceViewDialog
      v-if="viewOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      context="quoting"
      @close="viewOpen = false"
      @quote="quoteOpen = true"
      @book="bookingOpen = true"
      @changed="afterPipelineAction"
      @seen="markRowSeen"
    />
    <QuickQuoteDialog
      v-if="quoteOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      :interprovincial="viewInterprovincial"
      draggable
      @close="quoteOpen = false"
      @done="afterPipelineAction"
    />
    <QuickBookingDialog
      v-if="bookingOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      draggable
      @close="bookingOpen = false"
      @done="afterPipelineAction"
    />

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
