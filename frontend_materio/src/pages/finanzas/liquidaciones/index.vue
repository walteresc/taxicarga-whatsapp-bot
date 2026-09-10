<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  batchCreate, batchPay, batchVoid, settlementList, settlementSettle,
  settlementSummary, settlementUpdate, settlementVoid,
} from '@/services/settlementsService'

const STATE = {
  pendiente: { label: 'Pendiente', color: 'warning' },
  conciliada: { label: 'Conciliada', color: 'info' },
  pagada: { label: 'Liquidada', color: 'success' },
  anulada: { label: 'Anulada', color: 'default' },
}
const METHOD = {
  por_definir: 'Por definir',
  pasarela: 'Pasarela',
  transferencia: 'Transferencia',
  efectivo_transportista: 'Efectivo (transportista)',
}
const METHOD_ITEMS = Object.entries(METHOD).filter(([v]) => v !== 'por_definir').map(([value, title]) => ({ title, value }))

const soles = n => (n == null ? '—' : `S/ ${Math.round(n).toLocaleString('es-PE')}`)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const notify = (t, c = 'success') => Object.assign(snackbar, { show: true, text: t, color: c })

const rows = ref([])
const summary = ref(null)
const loading = ref(true)
const busy = ref(false)
const filters = reactive({ state: '', search: '' })
let searchTimer

const load = async () => {
  loading.value = true
  try {
    const [l, s] = await Promise.all([
      settlementList({ state: filters.state || undefined, search: filters.search || undefined }),
      settlementSummary(),
    ])
    rows.value = l.results
    summary.value = s
  } catch (e) { notify(e.message || 'No se pudo cargar.', 'error') } finally { loading.value = false }
}
const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 350) }
onMounted(load)

const setMethod = async (row, method) => {
  busy.value = true
  try { await settlementUpdate(row.id, { collectionMethod: method }); await load() }
  catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}
const toggleNoCommission = async row => {
  busy.value = true
  try { await settlementUpdate(row.id, { noCommission: !row.noCommission }); await load() }
  catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}

const settleForm = reactive({ open: false, row: null, reference: '', date: '', note: '' })
const openSettle = row => Object.assign(settleForm, {
  open: true, row, reference: '', date: new Date().toISOString().slice(0, 10), note: '',
})
const doSettle = async () => {
  busy.value = true
  try {
    await settlementSettle(settleForm.row.id, {
      reference: settleForm.reference || undefined,
      date: settleForm.date || undefined,
      note: settleForm.note || undefined,
    })
    settleForm.open = false
    notify('Liquidación registrada.')
    await load()
  } catch (e) { notify(e.message || 'No se pudo liquidar.', 'error') } finally { busy.value = false }
}
const voidRow = async row => {
  const reason = prompt('Motivo de anulación:')
  if (reason == null) return
  busy.value = true
  try { await settlementVoid(row.id, { reason }); notify('Anulada.'); await load() }
  catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}

const exportCsv = () => {
  const head = ['Servicio', 'Transportista', 'Ruta', 'Fecha', 'Precio', 'Costo', 'Comisión', 'Neto', 'Medio', 'Estado', 'Referencia']
  const lines = rows.value.map(r => [
    r.serviceCode, r.carrierName, r.route, r.date || '', r.servicePrice, r.carrierCost,
    r.commission, r.net, METHOD[r.collectionMethod], STATE[r.state]?.label, r.paymentRef || '',
  ].join(';'))
  const blob = new Blob(['﻿' + [head.join(';'), ...lines].join('\n')], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `liquidaciones-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
}

const netLabel = r => (r.net > 0 ? `Pagar ${soles(r.net)}` : r.net < 0 ? `Cobrar ${soles(-r.net)}` : '—')

// --- lote de pago ---
const selected = ref([])
const selectable = r => r.net > 0 && ['pendiente', 'conciliada'].includes(r.state)
const toggleAll = v => { selected.value = v ? rows.value.filter(selectable).map(r => r.id) : [] }
const selTotal = computed(() => rows.value.filter(r => selected.value.includes(r.id)).reduce((a, r) => a + r.net, 0))

const batch = reactive({ open: false, data: null, reference: '', date: '' })
const makeBatch = async () => {
  busy.value = true
  try {
    const d = await batchCreate({ ids: selected.value })
    Object.assign(batch, { open: true, data: d, reference: '', date: new Date().toISOString().slice(0, 10) })
    selected.value = []
    await load()
  } catch (e) { notify(e.message || 'No se pudo crear el lote.', 'error') } finally { busy.value = false }
}
const exportBatch = () => {
  const head = ['Transportista', 'Documento', 'Banco', 'Tipo', 'Cuenta', 'CCI', 'Yape', 'Titular', 'Monto', 'Servicio']
  const lines = batch.data.rows.map(r => [
    r.carrier, r.document, r.bank, r.accountType, r.account, r.cci, r.yape, r.holder, r.amount, r.service,
  ].join(';'))
  const blob = new Blob(['﻿' + [head.join(';'), ...lines].join('\n')], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `lote-pago-${batch.data.id}.csv`
  a.click()
}
const payBatch = async () => {
  busy.value = true
  try {
    batch.data = await batchPay(batch.data.id, { reference: batch.reference || undefined, date: batch.date || undefined })
    notify('Lote marcado como pagado. Las liquidaciones quedaron liquidadas.')
    await load()
  } catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}
const dropBatch = async () => {
  busy.value = true
  try { await batchVoid(batch.data.id); batch.open = false; notify('Lote anulado.'); await load() }
  catch (e) { notify(e.message || 'No se pudo.', 'error') } finally { busy.value = false }
}
</script>

<template>
  <section>
    <h1 class="text-h4 font-weight-bold mb-1">Liquidaciones de tercerización</h1>
    <p class="text-body-2 text-medium-emphasis mb-4" style="max-width: 72ch;">
      Por cada servicio adjudicado a un transportista: qué cobra la plataforma al cliente, qué se le paga al
      transportista y la comisión. <strong>Neto positivo</strong> = le pagás al transportista;
      <strong>negativo</strong> = te debe la comisión (cobró el servicio en efectivo).
    </p>

    <VRow v-if="summary" class="mb-2">
      <VCol cols="6" md="3"><VCard variant="tonal"><VCardText class="py-3">
        <div class="text-caption text-medium-emphasis">A pagar a transportistas</div>
        <div class="text-h6">{{ soles(summary.toPayCarriers) }}</div>
      </VCardText></VCard></VCol>
      <VCol cols="6" md="3"><VCard variant="tonal"><VCardText class="py-3">
        <div class="text-caption text-medium-emphasis">A cobrar (efectivo)</div>
        <div class="text-h6">{{ soles(summary.toCollectFromCarriers) }}</div>
      </VCardText></VCard></VCol>
      <VCol cols="6" md="3"><VCard variant="tonal"><VCardText class="py-3">
        <div class="text-caption text-medium-emphasis">Comisión pendiente</div>
        <div class="text-h6">{{ soles(summary.pendingCommission) }}</div>
      </VCardText></VCard></VCol>
      <VCol cols="6" md="3"><VCard variant="tonal"><VCardText class="py-3">
        <div class="text-caption text-medium-emphasis">Sin liquidar</div>
        <div class="text-h6">{{ summary.pendingCount }}</div>
      </VCardText></VCard></VCol>
    </VRow>

    <VCard>
      <VCardText class="d-flex flex-wrap align-center ga-2">
        <VTextField
          v-model="filters.search" placeholder="Buscar servicio, transportista, referencia"
          density="compact" hide-details clearable style="max-width: 320px;" prepend-inner-icon="ri-search-line"
          @update:model-value="onSearch"
        />
        <VSelect
          v-model="filters.state" label="Estado" density="compact" hide-details clearable style="max-width: 200px;"
          :items="Object.entries(STATE).map(([value, s]) => ({ title: s.label, value }))" @update:model-value="load"
        />
        <VSpacer />
        <VBtn size="small" variant="text" prepend-icon="ri-download-line" @click="exportCsv">Exportar CSV</VBtn>
      </VCardText>

      <VExpandTransition>
        <div v-if="selected.length" class="d-flex align-center flex-wrap ga-3 px-4 py-2 bg-primary" style="color: white;">
          <span class="text-body-2">{{ selected.length }} seleccionadas · a pagar {{ soles(selTotal) }}</span>
          <VSpacer />
          <VBtn size="small" variant="flat" color="white" :loading="busy" @click="makeBatch">Crear lote de pago</VBtn>
          <VBtn size="small" variant="text" color="white" @click="selected = []">Limpiar</VBtn>
        </div>
      </VExpandTransition>

      <VDivider />
      <VProgressLinear v-if="loading" indeterminate />
      <div v-else-if="!rows.length" class="text-center text-medium-emphasis py-10 text-body-2">Sin liquidaciones.</div>
      <div v-else style="overflow-x: auto;">
        <VTable density="compact" class="text-body-2">
          <thead>
            <tr>
              <th style="width: 36px;">
                <VCheckboxBtn density="compact"
                  :model-value="selected.length > 0 && selected.length === rows.filter(selectable).length"
                  :indeterminate="selected.length > 0 && selected.length < rows.filter(selectable).length"
                  @update:model-value="toggleAll" />
              </th>
              <th>Servicio</th><th>Transportista</th><th class="text-right">Precio</th>
              <th class="text-right">Costo</th><th class="text-right">Comisión</th><th class="text-right">Neto</th>
              <th>Cómo cobró el cliente</th><th>Estado</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" :class="{ 'text-disabled': r.state === 'anulada' }">
              <td>
                <VCheckboxBtn v-if="selectable(r)" v-model="selected" :value="r.id" density="compact" />
              </td>
              <td>
                <div class="font-weight-medium">{{ r.serviceCode }}</div>
                <div class="text-caption text-medium-emphasis">{{ r.route }}</div>
              </td>
              <td>{{ r.carrierName }}</td>
              <td class="text-right">{{ soles(r.servicePrice) }}</td>
              <td class="text-right">{{ soles(r.carrierCost) }}</td>
              <td class="text-right">
                <span v-if="r.noCommission" class="text-medium-emphasis">exento</span>
                <span v-else>{{ soles(r.commission) }} <span class="text-caption text-medium-emphasis">({{ r.commissionPct }}%)</span></span>
              </td>
              <td class="text-right font-weight-medium" :class="r.net < 0 ? 'text-error' : 'text-success'">{{ netLabel(r) }}</td>
              <td style="min-width: 190px;">
                <VSelect
                  :model-value="r.collectionMethod === 'por_definir' ? null : r.collectionMethod"
                  :items="METHOD_ITEMS" density="compact" hide-details placeholder="Elegir…"
                  :disabled="r.state === 'pagada' || r.state === 'anulada' || busy"
                  @update:model-value="v => setMethod(r, v)"
                />
              </td>
              <td><VChip size="x-small" :color="STATE[r.state]?.color">{{ STATE[r.state]?.label }}</VChip></td>
              <td class="text-right" style="white-space: nowrap;">
                <VBtn
                  v-if="['pendiente', 'conciliada'].includes(r.state)" size="x-small" color="success" variant="tonal"
                  :disabled="r.collectionMethod === 'por_definir'" @click="openSettle(r)"
                >Liquidar</VBtn>
                <VMenu v-if="r.state !== 'anulada' && r.state !== 'pagada'">
                  <template #activator="{ props }"><VBtn v-bind="props" icon="ri-more-2-fill" size="x-small" variant="text" /></template>
                  <VList density="compact">
                    <VListItem @click="toggleNoCommission(r)">
                      <VListItemTitle>{{ r.noCommission ? 'Volver a comisionar' : 'Marcar sin comisión' }}</VListItemTitle>
                    </VListItem>
                    <VListItem @click="voidRow(r)"><VListItemTitle class="text-error">Anular</VListItemTitle></VListItem>
                  </VList>
                </VMenu>
              </td>
            </tr>
          </tbody>
        </VTable>
      </div>
    </VCard>

    <VDialog v-model="settleForm.open" max-width="420">
      <VCard>
        <VCardTitle>Registrar liquidación</VCardTitle>
        <VCardText>
          <p class="text-body-2 mb-3">
            <strong>{{ settleForm.row?.net > 0 ? 'Pagar' : 'Cobrar' }}
            {{ soles(Math.abs(settleForm.row?.net || 0)) }}</strong>
            {{ settleForm.row?.net > 0 ? 'a' : 'de' }}
            <strong>{{ settleForm.row?.carrierName }}</strong> por {{ settleForm.row?.serviceCode }}.
          </p>
          <VTextField v-model="settleForm.reference" label="Referencia (N° operación, Yape, etc.)" density="compact" class="mb-2" />
          <VTextField v-model="settleForm.date" label="Fecha" type="date" density="compact" class="mb-2" />
          <VTextarea v-model="settleForm.note" label="Nota (opcional)" rows="2" auto-grow />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="settleForm.open = false">Cancelar</VBtn>
          <VBtn color="success" :loading="busy" @click="doSettle">Confirmar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Lote de pago -->
    <VDialog v-model="batch.open" max-width="720">
      <VCard v-if="batch.data">
        <VCardTitle class="d-flex align-center">
          Lote de pago #{{ batch.data.id }}
          <VChip class="ms-2" size="small" :color="batch.data.state === 'pagado' ? 'success' : 'info'">
            {{ batch.data.state === 'pagado' ? 'Pagado' : 'Borrador' }}
          </VChip>
          <VSpacer />
          <span class="text-body-1">{{ batch.data.count }} pagos · {{ soles(batch.data.total) }}</span>
        </VCardTitle>
        <VCardText>
          <VAlert v-if="batch.data.missingPayoutData" type="warning" variant="tonal" density="compact" class="mb-3">
            {{ batch.data.missingPayoutData }} transportista(s) sin datos de cobro cargados. Completalos en su ficha
            o pedíselos por el portal antes de transferir.
          </VAlert>
          <div style="overflow-x: auto;">
            <VTable density="compact" class="text-body-2">
              <thead><tr><th>Transportista</th><th>Banco</th><th>CCI / Cuenta</th><th>Yape</th><th class="text-right">Monto</th></tr></thead>
              <tbody>
                <tr v-for="(r, i) in batch.data.rows" :key="i" :class="{ 'text-error': !r.hasPayoutData }">
                  <td>{{ r.holder }}<div class="text-caption text-medium-emphasis">{{ r.service }}</div></td>
                  <td>{{ r.bank || '—' }}<span v-if="r.accountType" class="text-caption"> · {{ r.accountType }}</span></td>
                  <td>{{ r.cci || r.account || '—' }}</td>
                  <td>{{ r.yape || '—' }}</td>
                  <td class="text-right font-weight-medium">{{ soles(r.amount) }}</td>
                </tr>
              </tbody>
            </VTable>
          </div>

          <div v-if="batch.data.state !== 'pagado'" class="d-flex flex-wrap align-center ga-2 mt-4">
            <VTextField v-model="batch.reference" label="Referencia del pago" density="compact" hide-details style="max-width: 240px;" />
            <VTextField v-model="batch.date" label="Fecha" type="date" density="compact" hide-details style="max-width: 170px;" />
          </div>
        </VCardText>
        <VCardActions class="flex-wrap ga-2 px-4 pb-4">
          <VBtn variant="text" prepend-icon="ri-download-line" @click="exportBatch">Exportar CSV</VBtn>
          <VSpacer />
          <template v-if="batch.data.state !== 'pagado'">
            <VBtn variant="text" color="error" :loading="busy" @click="dropBatch">Anular lote</VBtn>
            <VBtn color="success" :loading="busy" @click="payBatch">Marcar todo pagado</VBtn>
          </template>
          <VBtn v-else variant="text" @click="batch.open = false">Cerrar</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">{{ snackbar.text }}</VSnackbar>
  </section>
</template>
