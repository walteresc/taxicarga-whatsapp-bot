<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { useRouter } from 'vue-router'

import {
  bookingAddPayment, bookingCancel, bookingDetail, bookingFinalize, bookingList,
  bookingSetMode, leadServiceData,
} from '@/services/commercialService'
import { driversService } from '@/services/personnelService'
import { fetchPizarra, pizarraAssign, pizarraUnassign } from '@/services/pizarraService'
import { usePipelineStore } from '@/stores/pipelineStore'
import ServiceViewDialog from '@/pages/atencion/bandeja-entrada/components/ServiceViewDialog.vue'
import QuickQuoteDialog from '@/pages/atencion/bandeja-entrada/components/QuickQuoteDialog.vue'

const router = useRouter()
const pipeline = usePipelineStore()

const STATE = {
  pending: { label: 'Pendiente', color: 'default' },
  scheduled: { label: 'Programada', color: 'info' },
  assigned: { label: 'Asignada', color: 'info' },
  on_route: { label: 'En ruta', color: 'warning' },
  completed: { label: 'Finalizada', color: 'success' },
  cancelled: { label: 'Cancelada', color: 'error' },
}
const PAY = {
  paid: { label: 'Pagada', color: 'success' },
  partial: { label: 'Amortizada', color: 'warning' },
  pending: { label: 'Pendiente', color: 'error' },
  no_price: { label: 'Sin precio', color: 'default' },
}
const METHODS = [
  { title: 'Yape', value: 'yape' }, { title: 'Plin', value: 'plin' },
  { title: 'BCP Persona Natural', value: 'bcp_personal' }, { title: 'BCP SOS Empresa', value: 'bcp_sos' },
  { title: 'Otro', value: 'otro' },
]
const CONCEPTS = [
  { title: 'Adelanto', value: 'adelanto' }, { title: 'Pago parcial', value: 'parcial' }, { title: 'Pago final', value: 'final' },
]

const EXEC = {
  propio: { label: 'Nuestro equipo', color: 'primary', icon: 'ri-team-line' },
  tercerizado: { label: 'Transportistas', color: 'secondary', icon: 'ri-truck-line' },
}
// Filtro combinado modalidad + estado de asignación.
const SEGMENTS = [
  { value: '', label: 'Todas' },
  { value: 'mode:propio', label: 'Nuestro equipo' },
  { value: 'mode:tercerizado', label: 'Transportistas' },
  { value: 'assign:unassigned', label: 'Sin asignar' },
  { value: 'assign:published', label: 'Publicadas' },
]

const rows = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const stateFilter = ref('')
const segment = ref('')
let searchTimer

const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })
const soles = n => `S/ ${Math.round(n || 0).toLocaleString('es-PE')}`

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const [k, v] = segment.value.split(':')
    rows.value = (await bookingList({
      search: search.value,
      state: stateFilter.value,
      mode: k === 'mode' ? v : undefined,
      assignment: k === 'assign' ? v : undefined,
    })).results
  } catch (e) { error.value = e.message || 'No se pudo cargar.' } finally { loading.value = false }
}

const setMode = async (row, mode) => {
  try {
    await bookingSetMode(row.id, mode)
    notify(mode === 'propio' ? 'Marcada para nuestro equipo.' : 'Marcada para transportistas.')
    await load()
    if (detail.value?.id === row.id) detail.value = await bookingDetail(row.id)
  } catch (e) {
    notify(e.message || 'No se pudo cambiar la modalidad.', 'error')
  }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }
onMounted(load)

const detail = ref(null)
const detailOpen = ref(false)

// --- Asignación (inline en el diálogo de gestión) ---
const assign = reactive({ loading: false, resources: [], drivers: [], editing: false })
const assignForm = reactive({ resourceId: null, driverId: null, start: '', end: '' })
const assignBusy = ref(false)

const resourceItems = computed(() => assign.resources.map(r => ({
  title: r.sublabel ? `${r.label} — ${r.sublabel}` : r.label,
  value: r.id, driverId: r.driverId,
})))
const driverItems = computed(() => assign.drivers.map(d => ({ title: d.name, value: d.id })))

const loadAssignOptions = async () => {
  if (!detail.value?.serviceDate) { assign.resources = []; return }
  assign.loading = true
  try {
    const [board, drv] = await Promise.all([
      fetchPizarra(detail.value.serviceDate),
      driversService.list({ status: 'active', pageSize: 200 }).catch(() => ({ results: [] })),
    ])
    assign.resources = (board.resources || []).filter(r => r.kind === 'propio')
    assign.drivers = drv.results || []
  } catch { assign.resources = [] } finally { assign.loading = false }
}

const resetAssignForm = () => {
  const d = detail.value || {}
  Object.assign(assignForm, {
    resourceId: d.assignedVehicleId ? `v${d.assignedVehicleId}` : null,
    driverId: null,
    start: d.assignedStart || d.serviceTime || '08:00',
    end: d.assignedEnd || '',
  })
}

const onAssignResource = id => {
  const r = resourceItems.value.find(x => x.value === id)
  if (r?.driverId && !assignForm.driverId) assignForm.driverId = r.driverId
}

const openDetail = async row => {
  detail.value = null
  detailOpen.value = true
  assign.editing = false
  try {
    detail.value = await bookingDetail(row.id)
    resetAssignForm()
    loadAssignOptions()
  } catch (e) { notify(e.message, 'error') }
}
const refreshDetail = async () => {
  detail.value = await bookingDetail(detail.value.id)
  resetAssignForm()
  await load()
  pipeline.bump()
}

const submitAssign = async () => {
  if (!assignForm.resourceId) { notify('Elegí un vehículo.', 'warning'); return }
  assignBusy.value = true
  try {
    await pizarraAssign({
      serviceId: detail.value.id,
      resourceId: assignForm.resourceId,
      start: assignForm.start || undefined,
      end: assignForm.end || undefined,
      driverId: assignForm.driverId || undefined,
    })
    notify('Reserva asignada.')
    assign.editing = false
    await refreshDetail()
  } catch (e) { notify(e.message || 'No se pudo asignar.', 'error') } finally { assignBusy.value = false }
}

const unassignBooking = async () => {
  if (!detail.value?.assignmentId) return
  if (!confirm('¿Quitar la asignación de esta reserva?')) return
  assignBusy.value = true
  try {
    await pizarraUnassign(detail.value.assignmentId)
    notify('Asignación quitada.')
    await refreshDetail()
  } catch (e) { notify(e.message || 'No se pudo quitar.', 'error') } finally { assignBusy.value = false }
}

const toggleMode = () => {
  if (!detail.value) return
  setMode(detail.value, detail.value.executionMode === 'propio' ? 'tercerizado' : 'propio')
}

// --- Ver servicio (modal compartido con la bandeja) ---
const viewOpen = ref(false)
const viewLeadId = ref(null)
const viewServiceData = ref({})
const viewInterprovincial = ref(false)
const quoteOpen = ref(false)

const openServiceView = async row => {
  if (!row.leadId) { notify('Esta reserva no tiene lead asociado.', 'warning'); return }
  viewLeadId.value = row.leadId
  viewInterprovincial.value = !!row.isInterprovincial
  viewServiceData.value = {}
  viewOpen.value = true
  try { viewServiceData.value = (await leadServiceData(row.leadId)).serviceData || {} } catch { /* precios vienen de /stage */ }
}

const afterServiceAction = async () => {
  quoteOpen.value = false
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

const payForm = reactive({ open: false, bookingId: null, code: '', concept: 'parcial', method: 'yape', amount: '', note: '' })
const openPay = row => {
  Object.assign(payForm, { open: true, bookingId: row.id, code: row.code, concept: 'parcial', method: 'yape', amount: '', note: '' })
}
const submitPay = async () => {
  busy.value = true
  try {
    await bookingAddPayment(payForm.bookingId, {
      concept: payForm.concept, method: payForm.method, amount: payForm.amount, note: payForm.note,
    })
    notify('Pago registrado.')
    payForm.open = false
    payForm.amount = ''
    await load()
    pipeline.bump()
    if (detail.value?.id === payForm.bookingId) detail.value = await bookingDetail(payForm.bookingId)
  } catch (e) { notify(e.message || 'No se pudo registrar el pago.', 'error') } finally { busy.value = false }
}

const finForm = reactive({ open: false, finalAmount: '', method: 'yape', note: '' })
const submitFinalize = async () => {
  busy.value = true
  try {
    await bookingFinalize(detail.value.id, { ...finForm })
    notify('Reserva finalizada.')
    finForm.open = false
    await refreshDetail()
  } catch (e) { notify(e.message || 'No se pudo finalizar.', 'error') } finally { busy.value = false }
}

const cancelForm = reactive({ open: false, reason: '' })
const submitCancel = async () => {
  busy.value = true
  try {
    await bookingCancel(detail.value.id, cancelForm.reason)
    notify('Reserva cancelada.')
    cancelForm.open = false
    await refreshDetail()
  } catch (e) { notify(e.message || 'No se pudo cancelar.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">
      Reservas
    </h1>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Ventas cerradas. Asigná a un equipo, registrá pagos, finalizá o cancelá. El detalle completo está en cada reserva.
    </p>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-4">
        <VTextField v-model="search" prepend-inner-icon="ri-search-line" label="Buscar código, cliente o ruta" density="compact" hide-details clearable style="max-width: 300px;" @update:model-value="onSearch" />
        <div class="d-flex flex-wrap ga-2">
          <VChip
            v-for="s in SEGMENTS" :key="s.value"
            :color="segment === s.value ? 'primary' : undefined"
            :variant="segment === s.value ? 'flat' : 'tonal'"
            @click="segment = s.value; load()"
          >
            {{ s.label }}
          </VChip>
        </div>
        <VSelect
          v-model="stateFilter" label="Estado" density="compact" hide-details clearable style="max-width: 160px;"
          :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))"
          @update:model-value="load"
        />
      </VCardText>
      <VAlert v-if="error" type="error" variant="tonal" class="ma-4">{{ error }}</VAlert>

      <VDivider />

      <VTable>
        <thead>
          <tr>
            <th>Código</th><th>Cliente</th><th>Ruta</th><th>Fecha</th><th>Hora</th>
            <th>Estado</th><th class="text-right">Precio</th><th>Asignación</th><th>Pago</th>
            <th class="text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="10" class="text-center py-8"><VProgressCircular indeterminate /></td></tr>
          <tr v-else-if="!rows.length"><td colspan="10" class="text-center text-medium-emphasis py-10">Sin reservas.</td></tr>
          <tr v-for="row in rows" v-else :key="row.id">
            <td class="font-weight-medium">
              <button type="button" class="rsv-link" title="Ver detalle" @click="openServiceView(row)">
                <VBadge v-if="!row.seen" dot inline color="primary" class="me-1" title="Sin abrir" />{{ row.code }}
              </button>
            </td>
            <td>{{ row.customerName }}</td>
            <td>{{ row.route }}<VChip v-if="row.isInterprovincial" size="x-small" color="warning" class="ms-1">Fuera de Lima</VChip></td>
            <td class="text-no-wrap">{{ row.serviceDate || 'Por confirmar' }}</td>
            <td class="text-no-wrap">
              {{ row.serviceTime || '—' }}
              <VChip v-if="row.isNight" size="x-small" color="deep-purple" variant="tonal" class="ms-1" title="Ventana nocturna">
                <VIcon start icon="ri-moon-line" size="12" /> noche
              </VChip>
            </td>
            <td><VChip size="small" :color="STATE[row.state]?.color">{{ STATE[row.state]?.label || row.state }}</VChip></td>
            <td class="text-right">{{ soles(row.price) }}</td>
            <td class="text-no-wrap">
              <VChip size="small" :color="EXEC[row.executionMode]?.color" variant="tonal">
                <VIcon start :icon="EXEC[row.executionMode]?.icon" size="14" />
                {{ EXEC[row.executionMode]?.label }}
              </VChip>
              <div class="text-caption text-medium-emphasis mt-1">
                <template v-if="row.assignmentState === 'asignado'">→ {{ row.executor }}</template>
                <template v-else-if="row.assignmentState === 'publicado'">⏳ publicada</template>
                <template v-else>sin asignar</template>
              </div>
            </td>
            <td><VChip size="x-small" :color="PAY[row.paymentState]?.color">{{ PAY[row.paymentState]?.label }}</VChip></td>
            <td class="text-right text-no-wrap">
              <VBtn size="small" variant="text" icon="ri-eye-line" title="Ver detalle del servicio" :disabled="!row.leadId" @click="openServiceView(row)" />
              <VBtn size="small" variant="text" icon="ri-chat-3-line" title="Abrir conversación" :disabled="!row.conversationId" @click="openConversation(row)" />
              <VBtn
                v-if="row.state !== 'completed' && row.state !== 'cancelled'"
                size="small" variant="text" icon="ri-money-dollar-circle-line" title="Registrar pago" @click="openPay(row)"
              />
              <VBtn
                size="small" variant="text" icon="ri-team-line"
                title="Gestionar asignación / equipo" @click="openDetail(row)"
              />
            </td>
          </tr>
        </tbody>
      </VTable>
    </VCard>

    <!-- Detalle -->
    <VDialog v-model="detailOpen" max-width="680">
      <VCard>
        <VCardTitle class="d-flex align-center ga-2">
          {{ detail?.code || 'Reserva' }}
          <VChip v-if="detail" size="small" :color="STATE[detail.state]?.color">{{ STATE[detail.state]?.label }}</VChip>
        </VCardTitle>
        <VCardText v-if="!detail" class="text-center py-8"><VProgressCircular indeterminate /></VCardText>
        <VCardText v-else>
          <VTable density="compact" class="text-body-2 mb-3">
            <tbody>
              <tr><td>Cliente</td><td>{{ detail.customerName }}</td></tr>
              <tr><td>Ruta</td><td>{{ detail.route }}</td></tr>
              <tr><td>Fecha / horario</td><td>{{ detail.serviceDate || 'Por confirmar' }} · {{ detail.schedule || '' }}</td></tr>
              <tr><td>Precio</td><td>{{ soles(detail.price) }}</td></tr>
              <tr><td>Cobrado / saldo</td><td>{{ soles(detail.paid) }} / <strong>{{ soles(detail.balance) }}</strong></td></tr>
              <tr><td>Inventario</td><td style="white-space: pre-line">{{ detail.items || '—' }}</td></tr>
            </tbody>
          </VTable>

          <div class="text-overline mb-1">Asignación</div>
          <div class="d-flex flex-wrap align-center ga-2 mb-3">
            <VChip :color="EXEC[detail.executionMode]?.color" variant="tonal">
              <VIcon start :icon="EXEC[detail.executionMode]?.icon" size="16" /> {{ EXEC[detail.executionMode]?.label }}
            </VChip>
            <VBtn
              v-if="detail.assignmentState !== 'asignado' && detail.state !== 'completed' && detail.state !== 'cancelled'"
              size="small" variant="tonal" icon="ri-arrow-left-right-line"
              :title="detail.executionMode === 'propio' ? 'Pasar a transportistas' : 'Pasar a nuestro equipo'"
              @click="toggleMode"
            />
            <span v-if="detail.assignmentState === 'publicado'" class="text-body-2 text-medium-emphasis">⏳ publicada en el grupo</span>
          </div>

          <!-- Ya asignada -->
          <div v-if="detail.assignmentState === 'asignado'" class="d-flex flex-wrap align-center ga-3 mb-4">
            <span class="text-body-2"><VIcon icon="ri-user-line" size="16" class="me-1" />{{ detail.executor }}</span>
            <VBtn
              v-if="detail.state !== 'completed' && detail.state !== 'cancelled'"
              size="small" variant="text" color="error" :loading="assignBusy" @click="unassignBooking"
            >
              Quitar asignación
            </VBtn>
          </div>

          <!-- Asignar (inline) -->
          <template v-else-if="detail.state !== 'completed' && detail.state !== 'cancelled'">
            <VAlert v-if="!detail.serviceDate" type="warning" variant="tonal" density="compact" class="mb-4">
              Definí la fecha del servicio (en "Ver detalle") antes de asignar.
            </VAlert>
            <div v-else class="mb-4">
              <div v-if="assign.loading" class="text-center py-3"><VProgressCircular indeterminate size="24" color="primary" /></div>
              <template v-else>
                <VRow dense>
                  <VCol cols="12" sm="6">
                    <VSelect
                      v-model="assignForm.resourceId" :items="resourceItems" label="Vehículo"
                      density="comfortable" prepend-inner-icon="ri-car-line" hide-details
                      no-data-text="Sin vehículos disponibles ese día"
                      @update:model-value="onAssignResource"
                    />
                  </VCol>
                  <VCol cols="12" sm="6">
                    <VAutocomplete
                      v-model="assignForm.driverId" :items="driverItems" label="Conductor (opcional)"
                      density="comfortable" prepend-inner-icon="ri-user-line" clearable hide-details
                    />
                  </VCol>
                </VRow>
                <div class="d-flex flex-wrap ga-6 mt-3">
                  <AppTimeField v-model="assignForm.start" label="Inicio" density="comfortable" />
                  <AppTimeField v-model="assignForm.end" label="Fin (opcional)" density="comfortable" />
                </div>
                <VBtn
                  class="mt-3" color="primary" :loading="assignBusy"
                  :disabled="!assignForm.resourceId" prepend-icon="ri-team-line"
                  @click="submitAssign"
                >
                  Asignar a este vehículo
                </VBtn>
              </template>
            </div>
          </template>

          <div class="text-overline mb-1">Pagos</div>
          <VTable v-if="detail.payments.length" density="compact">
            <thead><tr><th>Fecha</th><th>Concepto</th><th>Método</th><th class="text-right">Monto</th></tr></thead>
            <tbody>
              <tr v-for="p in detail.payments" :key="p.id">
                <td>{{ (p.paidAt || '').slice(0, 10) }}</td><td class="text-capitalize">{{ p.concept }}</td>
                <td>{{ p.method }}</td><td class="text-right">{{ soles(p.amount) }}</td>
              </tr>
            </tbody>
          </VTable>
          <p v-else class="text-medium-emphasis text-caption">Sin pagos registrados.</p>
        </VCardText>

        <VCardActions v-if="detail && detail.state !== 'completed' && detail.state !== 'cancelled'" class="flex-wrap px-4 pb-4 ga-2">
          <VBtn variant="text" :disabled="busy" @click="openPay(detail)">Registrar pago</VBtn>
          <VBtn variant="text" color="error" :disabled="busy" @click="cancelForm.open = true">Cancelar</VBtn>
          <VSpacer />
          <VBtn variant="text" @click="detailOpen = false">Cerrar</VBtn>
          <VBtn color="success" :disabled="busy" @click="finForm.open = true">Finalizar</VBtn>
        </VCardActions>
        <VCardActions v-else-if="detail" class="px-4 pb-4">
          <VSpacer /><VBtn variant="text" @click="detailOpen = false">Cerrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Pago -->
    <VDialog v-model="payForm.open" max-width="440">
      <VCard>
        <VCardTitle>Registrar pago{{ payForm.code ? ` · ${payForm.code}` : '' }}</VCardTitle>
        <VCardText>
          <VSelect v-model="payForm.concept" :items="CONCEPTS" label="Concepto" class="mb-2" />
          <VSelect v-model="payForm.method" :items="METHODS" label="Método" class="mb-2" />
          <VTextField v-model="payForm.amount" label="Monto (S/)" type="number" class="mb-2" />
          <VTextField v-model="payForm.note" label="Observación" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="payForm.open = false">Cancelar</VBtn>
          <VBtn color="primary" :loading="busy" :disabled="!payForm.amount" @click="submitPay">Registrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Finalizar -->
    <VDialog v-model="finForm.open" max-width="460">
      <VCard>
        <VCardTitle>Finalizar reserva</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">Saldo pendiente: <strong>{{ soles(detail?.balance) }}</strong>. Si registras el pago final, indícalo:</p>
          <VTextField v-model="finForm.finalAmount" label="Pago final (opcional)" type="number" class="mb-2" />
          <VSelect v-model="finForm.method" :items="METHODS" label="Método" class="mb-2" />
          <VTextField v-model="finForm.note" label="Observación (obligatoria si el pago es menor al saldo)" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="finForm.open = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" @click="submitFinalize">Finalizar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Cancelar -->
    <VDialog v-model="cancelForm.open" max-width="440">
      <VCard>
        <VCardTitle>Cancelar reserva</VCardTitle>
        <VCardText>
          <VTextField v-model="cancelForm.reason" label="Motivo de la cancelación" autofocus />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="cancelForm.open = false">No</VBtn>
          <VBtn color="error" :loading="busy" :disabled="!cancelForm.reason.trim()" @click="submitCancel">Cancelar reserva</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Ver servicio: modal compartido con la bandeja -->
    <ServiceViewDialog
      v-if="viewOpen && viewLeadId"
      :lead-id="viewLeadId"
      :service-data="viewServiceData"
      context="bookings"
      @close="viewOpen = false"
      @quote="quoteOpen = true"
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

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>

<style scoped>
.rsv-link {
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}
.rsv-link:hover {
  text-decoration: underline;
}
</style>
