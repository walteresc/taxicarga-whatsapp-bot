<script setup>
import { onMounted, reactive, ref } from 'vue'

import { useRouter } from 'vue-router'

import {
  leadServiceData, quoteAccept, quoteDetail, quoteList, quoteRevise, quoteSetState,
} from '@/services/commercialService'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'
import QuickQuoteDialog from '@/pages/atencion/bandeja-entrada/components/QuickQuoteDialog.vue'
import QuickBookingDialog from '@/pages/atencion/bandeja-entrada/components/QuickBookingDialog.vue'

const router = useRouter()
const pipeline = usePipelineStore()

const STATE = {
  sent: { label: 'Enviada', color: 'info' },
  delivered: { label: 'Entregada', color: 'info' },
  negotiating: { label: 'En negociación', color: 'warning' },
  accepted: { label: 'Aceptada', color: 'success' },
  rejected: { label: 'Rechazada', color: 'error' },
  expired: { label: 'Vencida', color: 'default' },
}
const TRANSITIONS = {
  sent: ['delivered', 'negotiating', 'rejected', 'expired'],
  delivered: ['negotiating', 'rejected', 'expired'],
  negotiating: ['rejected', 'expired'],
}

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const stateFilter = ref('')
let searchTimer

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })
const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    rows.value = (await quoteList({ search: search.value, state: stateFilter.value })).results
  } catch (e) {
    error.value = e.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }
onMounted(load)

// detalle
const detail = ref(null)
const detailOpen = ref(false)
const openDetail = async row => {
  detail.value = null
  detailOpen.value = true
  try { detail.value = await quoteDetail(row.id) } catch (e) { notify(e.message, 'error') }
}

// --- Ver servicio (modal compartido con la bandeja) ---
const viewOpen = ref(false)
const viewLeadId = ref(null)
const viewServiceData = ref({})
const viewInterprovincial = ref(false)
const quoteOpen = ref(false)
const bookingOpen = ref(false)

const openServiceView = async row => {
  if (!row.leadId) { notify('Esta cotización no tiene lead asociado.', 'warning'); return }
  viewLeadId.value = row.leadId
  viewInterprovincial.value = !!row.isInterprovincial
  viewServiceData.value = {}
  viewOpen.value = true
  try { viewServiceData.value = (await leadServiceData(row.leadId)).serviceData || {} } catch { /* precios vienen de /stage */ }
}

const afterServiceAction = async () => {
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

const busy = ref(false)
const changeState = async target => {
  busy.value = true
  try {
    await quoteSetState(detail.value.id, target)
    notify('Estado actualizado.')
    await openDetail(detail.value)
    await load()
  } catch (e) { notify(e.message || 'No se pudo cambiar el estado.', 'error') } finally { busy.value = false }
}

// nueva revisión
const reviseForm = reactive({ open: false, price: '', conditions: '', validityDays: 7, whatsappMessage: '' })
const submitRevise = async () => {
  busy.value = true
  try {
    detail.value = await quoteRevise(detail.value.id, { ...reviseForm })
    notify('Nueva revisión enviada al cliente.')
    reviseForm.open = false
    await load()
  } catch (e) { notify(e.message || 'No se pudo revisar.', 'error') } finally { busy.value = false }
}

// aceptar → crea reserva
const acceptOpen = ref(false)
const doAccept = async () => {
  busy.value = true
  try {
    const res = await quoteAccept(detail.value.id)
    notify(`Cotización aceptada. Reserva ${res.bookingCode} creada.`)
    acceptOpen.value = false
    detailOpen.value = false
    pipeline.bump()
    await load()
  } catch (e) { notify(e.message || 'No se pudo aceptar.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Cotizados
    </h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Precios enviados al cliente. Cuando acepte (por WhatsApp), márcala aceptada aquí para crear la reserva.
    </p>

    <VCard>
      <VCardText class="d-flex flex-wrap ga-3">
        <VTextField v-model="search" prepend-inner-icon="ri-search-line" label="Buscar código, cliente o ruta" density="compact" hide-details clearable style="max-width: 340px;" @update:model-value="onSearch" />
        <VSelect
          v-model="stateFilter" label="Estado" density="compact" hide-details clearable style="max-width: 200px;"
          :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))"
          @update:model-value="load"
        />
      </VCardText>

      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">{{ error }}</VAlert>

      <VDivider />

      <VTable>
        <thead>
          <tr><th>Código</th><th>Cliente</th><th>Ruta</th><th>Estado</th><th class="text-right">Precio</th><th>Origen</th><th class="text-right">Acciones</th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="text-center py-8"><VProgressCircular indeterminate /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="7" class="text-center text-medium-emphasis py-10">Sin cotizaciones.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium text-primary" style="cursor: pointer;" title="Ver detalle" @click="openServiceView(row)">
              <VBadge v-if="!row.seen" dot inline color="primary" class="me-1" title="Sin abrir" />{{ row.code }}
            </td>
            <td>{{ row.customerName }}</td>
            <td>{{ row.route }}</td>
            <td><VChip size="small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label || row.state }}</VChip></td>
            <td class="text-right">{{ soles(row.currentPrice) }}</td>
            <td class="text-capitalize">{{ row.origin }}</td>
            <td class="text-right text-no-wrap">
              <VBtn size="small" variant="text" icon="ri-eye-line" title="Ver detalle del servicio" :disabled="!row.leadId" @click="openServiceView(row)" />
              <VBtn size="small" variant="text" icon="ri-chat-3-line" title="Abrir conversación" :disabled="!row.conversationId" @click="openConversation(row)" />
              <VBtn size="small" variant="tonal" class="ms-1" @click="openDetail(row)">Revisiones</VBtn>
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Detalle -->
    <VDialog v-model="detailOpen" max-width="680">
      <VCard>
        <VCardTitle class="d-flex align-center ga-2">
          {{ detail?.code || 'Cotización' }}
          <VChip v-if="detail" size="small" :color="STATE[detail.state]?.color">{{ STATE[detail.state]?.label || detail.state }}</VChip>
        </VCardTitle>
        <VCardText v-if="!detail" class="text-center py-8"><VProgressCircular indeterminate /></VCardText>
        <VCardText v-else>
          <VTable density="compact" class="text-body-2 mb-4">
            <tbody>
              <tr><td>Cliente</td><td>{{ detail.service.customer.name }}</td></tr>
              <tr><td>Ruta</td><td>{{ detail.service.origin }} → {{ detail.service.destination }}</td></tr>
              <tr><td>Precio actual</td><td class="font-weight-bold">{{ soles(detail.currentPrice) }}</td></tr>
            </tbody>
          </VTable>

          <div class="text-overline mb-1">Revisiones</div>
          <VTable density="compact">
            <thead><tr><th>#</th><th class="text-right">Precio</th><th>Enviada</th><th>Condiciones</th></tr></thead>
            <tbody>
              <tr v-for="r in detail.revisions" :key="r.number">
                <td>v{{ r.number }}</td>
                <td class="text-right">{{ soles(r.price) }}</td>
                <td>{{ r.sent ? (r.sentAt || 'sí').slice(0, 10) : '—' }}</td>
                <td class="text-caption">{{ r.conditions || '—' }}</td>
              </tr>
            </tbody>
          </VTable>
        </VCardText>

        <VCardActions v-if="detail" class="flex-wrap px-4 pb-4 ga-2">
          <VMenu v-if="TRANSITIONS[detail.state]?.length">
            <template #activator="{ props }">
              <VBtn v-bind="props" variant="text" :disabled="busy">Cambiar estado</VBtn>
            </template>
            <VList>
              <VListItem v-for="t in TRANSITIONS[detail.state]" :key="t" @click="changeState(t)">
                <VListItemTitle>{{ STATE[t]?.label }}</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
          <VBtn variant="text" :disabled="busy || detail.state === 'accepted'" @click="Object.assign(reviseForm, { open: true, price: String(detail.currentPrice || ''), conditions: '', validityDays: 7, whatsappMessage: '' })">
            Nueva revisión
          </VBtn>
          <VSpacer />
          <VBtn variant="text" @click="detailOpen = false">Cerrar</VBtn>
          <VBtn v-if="!detail.hasBooking" color="success" :disabled="busy" @click="acceptOpen = true">Marcar aceptada</VBtn>
          <VChip v-else color="success" size="small">Reserva creada</VChip>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Nueva revisión -->
    <VDialog v-model="reviseForm.open" max-width="480">
      <VCard>
        <VCardTitle>Nueva revisión</VCardTitle>
        <VCardText>
          <VTextField v-model="reviseForm.price" label="Nuevo precio (S/)" type="number" class="mb-2" />
          <VTextField v-model.number="reviseForm.validityDays" label="Vigencia (días)" type="number" class="mb-2" />
          <VTextarea v-model="reviseForm.conditions" label="Condiciones" rows="2" auto-grow class="mb-2" />
          <VTextarea v-model="reviseForm.whatsappMessage" label="Mensaje WhatsApp (autogenerado si vacío)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="reviseForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" :disabled="!reviseForm.price" @click="submitRevise">Enviar revisión</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Confirmar aceptación -->
    <VDialog v-model="acceptOpen" max-width="440">
      <VCard>
        <VCardTitle>Marcar como aceptada</VCardTitle>
        <VCardText>
          Confirmas que el cliente <strong>aceptó</strong> esta cotización ({{ soles(detail?.currentPrice) }}).
          Se creará la <strong>reserva</strong> y quedará registrado quién y cuándo. Esto genera una venta.
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="acceptOpen = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" @click="doAccept">Sí, crear reserva</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Ver servicio: modal compartido con la bandeja -->
    <ServiceViewDialog
      v-if="viewOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      context="quotes"
      @close="viewOpen = false"
      @quote="quoteOpen = true"
      @book="bookingOpen = true"
      @changed="afterServiceAction"
      @seen="markRowSeen"
    />
    <QuickQuoteDialog
      v-if="quoteOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      :interprovincial="viewInterprovincial"
      draggable
      @close="quoteOpen = false"
      @done="afterServiceAction"
    />
    <QuickBookingDialog
      v-if="bookingOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      draggable
      @close="bookingOpen = false"
      @done="afterServiceAction"
    />

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
